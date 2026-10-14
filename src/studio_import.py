"""Import generated selections through the shared Studio model, atomically per run."""
import copy
import json
from versions import LOCK, highlight_nodes, project, tree, uid


class ReconciliationRequired(FileExistsError):
    pass


def leaves(value, node):
    if isinstance(value, dict):
        for k, child in value.items(): yield from leaves(child, node['children'][k])
    elif isinstance(value, list):
        for child, n in zip(value, node['children']): yield from leaves(child, n)
    else: yield node['id'], value


def entry_matches(entry, original):
    fixed = {k: v for k, v in entry.items() if k not in ('summary', 'description', 'highlights')}
    return all((isinstance(original.get(k), list) and all(x in original[k] for x in v))
               if isinstance(v, list) else original.get(k) == v for k, v in fixed.items())


def build(loaded, documents, snapshot=None, references=None, entry_map=None, acknowledge=False):
    data, state = copy.deepcopy(loaded['data']), copy.deepcopy(loaded['state'])
    resume = documents['resume']; references = references or {}; entry_map = entry_map or {}
    conflicts = []; additions = []; used_references = set()
    if snapshot:
        current = dict(leaves(data, state['tree']))
        changed = [ident for ident, text in leaves(snapshot['data'], snapshot['state']['tree']) if current.get(ident) != text]
        changed.extend(ident for ident,level in snapshot['state'].get('masterIndent',{}).items() if state.get('masterIndent',{}).get(ident)!=level)
        if changed and not acknowledge: conflicts.append('Source content changed or disappeared: '+', '.join(changed))
    source_highlights = {i: (text, path) for i, text, path in highlight_nodes(
        snapshot['data'] if snapshot else data, snapshot['state']['tree'] if snapshot else state['tree'])}
    version = {'id': 'job-'+uid(), 'name': 'Generated '+uid()[:8], 'excluded': [], 'indent': {},
               'wording': {}, 'prose': {}, 'order': {}, 'reviewStatus': 'unreviewed'}
    def select(value, node, generated, path):
        if isinstance(value, dict):
            for key, child in value.items():
                if key not in generated:
                    version['excluded'].append(node['children'][key]['id'])
                elif key in ('summary', 'description') or (path == ('basics',) and key == 'label'):
                    if path==('basics',) and key=='summary':version['summaryOverride']=generated[key]
                    else:version['prose'][node['children'][key]['id']] = generated[key]
                else: select(child, node['children'][key], generated[key], path+(key,))
            for key in set(generated)-set(value):
                if key in ('summary', 'description') or (path == ('basics',) and key == 'label'):
                    value[key] = generated[key]; node['children'][key] = tree(generated[key])
                    for existing in state['versions']:existing['excluded'].append(node['children'][key]['id'])
                    if path==('basics',) and key=='summary':version['summaryOverride']=generated[key]
                    else:version['prose'][node['children'][key]['id']] = generated[key]
                else: conflicts.append('Unsupported field: '+ '/'.join(map(str,path+(key,))))
        elif isinstance(value, list):
            chosen=[]
            for index, item in enumerate(generated):
                point_path = '/'.join(map(str, path+(index,)))
                if path[-1] == 'highlights':
                    refs = references.get(point_path, [])
                    used_references.add(point_path)
                    if not isinstance(refs, list) or len(set(refs)) != len(refs) or any(r not in source_highlights for r in refs):
                        raise ValueError('Invalid source highlight references for '+point_path)
                    valid_ids = {n['id'] for n in node['children']}
                    missing=any(r not in state['highlights'] for r in refs)
                    if missing and not acknowledge:
                        conflicts.append('Source highlight moved or disappeared: '+point_path); continue
                    matches = [n['id'] for text,n in zip(value,node['children']) if text == item]
                    ident = refs[0] if len(refs) == 1 and refs[0] in valid_ids else (matches[0] if not refs and len(matches) == 1 else None)
                    if ident is None and len(refs)>1:
                        combined=[n['id'] for text,n in zip(value,node['children']) if text==item and any(w.get('provenance',{}).get('sourceHighlights')==refs for w in state['highlights'][n['id']]['wordings'])]
                        if len(combined)==1:ident=combined[0]
                    if ident is None:
                        ident=uid(); value.append(item); node['children'].append({'id':ident})
                        state['highlights'][ident]={'defaultWording':ident,'wordings':[{'id':ident,'text':item,'reviewStatus':'unreviewed','provenance':{'sourceHighlights':refs}}]}
                        state['masterIndent'][ident]=0
                        additions.append({'highlightId':ident,'text':item,'kind':'separate','sourceHighlights':refs,'path':point_path})
                    group=state['highlights'][ident]
                    wording=next((w for w in group['wordings'] if w['text']==item),None)
                    if not wording:
                        wording={'id':uid(),'text':item,'reviewStatus':'unreviewed','provenance':{'sourceHighlights':refs}}
                        group['wordings'].append(wording)
                        additions.append({'highlightId':ident,'text':item,'kind':'alternative','sourceHighlights':refs,'path':point_path})
                    if ident in version['wording']:
                        conflicts.append('More than one wording selected for the same highlight: '+point_path); continue
                    version['wording'][ident]=wording['id']; chosen.append(ident)
                else:
                    matches=[i for i, original in enumerate(value) if entry_matches(item,original)] if isinstance(item,dict) else [i for i, original in enumerate(value) if item==original]
                    mapped=entry_map.get(point_path)
                    if mapped: matches=[i for i,n in enumerate(node['children']) if n['id']==mapped]
                    if len(matches)!=1:
                        conflicts.append('Choose a master entry for '+point_path); continue
                    i=matches[0]; ident=node['children'][i]['id']
                    if ident in chosen: conflicts.append('Repeated entry: '+point_path); continue
                    chosen.append(ident);select(value[i],node['children'][i],item,path+(index,))
            version['order'][node['id']]=chosen
            version['excluded'].extend(n['id'] for n in node['children'] if n['id'] not in chosen)
        elif value != generated:
            conflicts.append('Source fact does not match: '+ '/'.join(map(str,path)))
    select(data,state['tree'],resume,())
    if set(references)-used_references: raise ValueError('Source references contain unknown generated points.')
    return data,state,version,{'conflicts':conflicts,'additions':additions,'resume':resume,
                              'entries':{section:[{'id':n['id'],'label':e.get('name') or e.get('institution') or e.get('organization') or str(i+1)} for i,(e,n) in enumerate(zip(values,state['tree']['children'][section]['children'])) if isinstance(e,dict)] for section,values in data.items() if isinstance(values,list)}}


def import_run(service, identifier, run_id, preview=False, expected=None, acknowledge=False, entry_map=None):
    import application_drafts
    folder=application_drafts.folder_for(service,identifier,run_id)
    with service.lock, LOCK:
        loaded=service.master.load()
        existing=next((v for v in loaded['state']['versions'] if v.get('provenance',{}).get('jobId')==identifier and v.get('provenance',{}).get('runId')==run_id),None)
        if existing: return {'versionId':existing['id'],'alreadyImported':True,'revision':loaded['revision'],'conflicts':[]}
        if expected is not None and expected!=loaded['revision']: raise ReconciliationRequired('Studio changed after the import preview. Preview again; your drafts are retained.')
        documents=json.loads((folder/('draft.json' if (folder/'draft.json').exists() else 'documents.json')).read_text())
        snapshot=json.loads((folder/'studio-snapshot.json').read_text()) if (folder/'studio-snapshot.json').exists() else None
        original=json.loads((folder/'documents.json').read_text())
        references=original.get('highlightSources',{}) if documents['resume']==original['resume'] else {}
        data,state,version,result=build(loaded,documents,snapshot,references,entry_map,acknowledge)
        result['revision']=loaded['revision']
        result['draftRevision']=application_drafts.read(service,identifier,run_id)['revision']
        if preview: return result
        if result['conflicts']: raise ReconciliationRequired('Import needs reconciliation. '+ '; '.join(result['conflicts']))
        job=service.jobs.read(identifier)
        version['id']='job-'+run_id
        version['name']=(job['company']+' — '+job['title'])[:65]+' '+run_id[:8]
        version['provenance']={'jobId':identifier,'runId':run_id,'sourceHighlights':list(references.values())}
        for addition in result['additions']:
            for w in state['highlights'][addition['highlightId']]['wordings']:
                if w['text']==addition['text']: w.setdefault('provenance',{}).update(jobId=identifier,runId=run_id)
        state['versions'].append(version)
        if project(data,state,version['id'])[0] != documents['resume']:
            raise ReconciliationRequired('Imported projection differs from the saved résumé. Reconcile source fields before importing.')
        saved=service.master.save(data,state,loaded['revision'],'master')
        return {'versionId':version['id'],'revision':saved['revision'],'alreadyImported':False,'conflicts':[]}
