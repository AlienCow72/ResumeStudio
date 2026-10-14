"""Master storage and version projections. IDs and formatting never enter resume JSON."""
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path

LOCK = threading.RLock()

def encoded(value): return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()
def uid(): return uuid.uuid4().hex

def tree(value):
    node={'id':uid()}
    if isinstance(value,dict): node['children']={k:tree(v) for k,v in value.items()}
    elif isinstance(value,list): node['children']=[tree(v) for v in value]
    return node

def check_tree(value,node,seen=None):
    seen=set() if seen is None else seen
    if not isinstance(node,dict) or not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',str(node.get('id',''))) or node['id'] in seen: raise ValueError('Invalid or duplicate item ID. Reload the editor.')
    seen.add(node['id'])
    children=node.get('children')
    if isinstance(value,dict):
        if not isinstance(children,dict) or set(value)!=set(children): raise ValueError('Field IDs do not match master data.')
        for k,v in value.items(): check_tree(v,children[k],seen)
    elif isinstance(value,list):
        if not isinstance(children,list) or len(value)!=len(children): raise ValueError('Entry IDs do not match master data.')
        for v,n in zip(value,children): check_tree(v,n,seen)
    return seen

def highlight_nodes(data, node, path=()):
    if isinstance(data, dict):
        for key, value in data.items():
            yield from highlight_nodes(value, node['children'][key], path+(key,))
    elif isinstance(data, list):
        for i, (value, child) in enumerate(zip(data, node['children'])):
            if path and path[-1] == 'highlights':
                yield child['id'], value, path+(i,)
            else:
                yield from highlight_nodes(value, child, path+(i,))


def migrate(data, state):
    """Upgrade metadata only, keeping every saved projection unchanged."""
    state = copy.deepcopy(state)
    if state.get('schemaVersion') == 2:
        return state
    before = {v['id']: project(data, state, v['id']) for v in state['versions']}
    seed = next((v.get('indent', {}) for v in state['versions'] if v['name'].casefold() == 'joblinks'), {})
    state.update(schemaVersion=2, highlights={}, masterIndent={})
    for ident, text, path in highlight_nodes(data, state['tree']):
        state['highlights'][ident] = {'defaultWording': ident, 'wordings': [{'id': ident, 'text': text, 'reviewStatus': 'reviewed'}]}
        state['masterIndent'][ident] = seed.get(ident, 0)
        for version in state['versions']:
            desired=version.setdefault('indent', {}).get(ident, 0)
            if desired!=state['masterIndent'][ident]:version['indent'][ident]=desired
            else:version['indent'].pop(ident,None)
    for version in state['versions']:
        version.setdefault('reviewStatus', 'unreviewed')
    if any(project(data, state, ident) != projected for ident, projected in before.items()):
        raise ValueError('Migration would change an existing version. Restore the backup.')
    return state


def selected_wording(state, version, ident):
    group = state.get('highlights', {}).get(ident)
    if not group:
        return None
    selected = version.get('wording', {}).get(ident, group['defaultWording'])
    return next((w for w in group['wordings'] if w['id'] == selected), None)


def prepare(data, state, old):
    """Keep master strings and initial wording synchronized; invalidate affected reviews."""
    state = copy.deepcopy(state)
    if state.get('schemaVersion') == 1:
        state = migrate(data, state)
    for v in state['versions']:v.setdefault('excluded',[]);v.setdefault('indent',{})
    previous = old['state']
    old_highlights = dict((ident, text) for ident, text, _ in highlight_nodes(old['data'], previous['tree']))
    current = dict((ident, text) for ident, text, _ in highlight_nodes(data, state['tree']))
    for ident, text in current.items():
        if ident not in state['highlights']:
            state['highlights'][ident] = {'defaultWording': ident, 'wordings': [{'id': ident, 'text': text, 'reviewStatus': 'unreviewed'}]}
        group = state['highlights'][ident]
        initial = next(w for w in group['wordings'] if w['id'] == group['defaultWording'])
        initial['text'] = text
        prior = previous.get('highlights', {}).get(ident, {})
        for wording in group['wordings']:
            original = next((w for w in prior.get('wordings', []) if w['id'] == wording['id']), None)
            if not original or original['text'] != wording['text']:
                wording['reviewStatus'] = 'unreviewed'
        if ident not in old_highlights:
            for version in state['versions']:
                if any(v['id'] == version['id'] for v in previous['versions']) and ident not in version.get('wording', {}):
                    if ident not in version['excluded']: version['excluded'].append(ident)
    for ident in set(state['highlights']) - set(current):
        del state['highlights'][ident]
        state['masterIndent'].pop(ident, None)
        for v in state['versions']:
            v.get('wording', {}).pop(ident, None)
            v.get('indent', {}).pop(ident, None)
    for v in state['versions']:
        v.setdefault('excluded',[]);v.setdefault('indent',{});v.setdefault('reviewStatus','unreviewed')
        prior = next((x for x in previous['versions'] if x['id'] == v['id']), None)
        if not prior or project(data, state, v['id']) != project(old['data'], previous, v['id']):
            v['reviewStatus'] = 'unreviewed'
        if v.pop('markReviewed', False):
            v['reviewStatus'] = 'reviewed'
            def approve(value, node):
                if node['id'] in v.get('excluded', []): return
                wording = selected_wording(state, v, node['id'])
                if wording: wording['reviewStatus'] = 'reviewed'
                children = node.get('children', {})
                if isinstance(value, dict):
                    for k, x in value.items(): approve(x, children[k])
                elif isinstance(value, list):
                    for x, child in zip(value, children): approve(x, child)
            approve(data, state['tree'])
    return state

def validate(data,state):
    if not isinstance(data,dict): raise ValueError('Master must be a JSON object.')
    if 'basics' in data and not isinstance(data['basics'],dict): raise ValueError('basics must be an object.')
    for k in ['work','skills','education','projects','volunteer','awards','certificates','publications','languages','interests','references']:
        if k in data and (not isinstance(data[k],list) or any(not isinstance(v,dict) for v in data[k])):raise ValueError(k+' must be an array of objects.')
    def strings(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if k in {'highlights','keywords','courses','roles'} and (not isinstance(x,list) or any(not isinstance(y,str) for y in x)):raise ValueError(k+' must contain strings.')
                strings(x)
        elif isinstance(v,list):
            for x in v:strings(x)
    strings(data)
    if not isinstance(state,dict) or state.get('schemaVersion') not in (1,2):raise ValueError('Refresh the editor to load the new versions workflow.')
    check_tree(data,state['tree'])
    names=set(); identifiers=set()
    for version in state['versions']:
        if not isinstance(version,dict):raise ValueError('Invalid version.')
        ident=version.get('id',''); name=version.get('name','')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',ident) or len(ident)>60 or ident=='master' or ident in identifiers:raise ValueError('Version IDs must be unique lowercase names with hyphens.')
        if not isinstance(name,str) or not name.strip() or len(name)>80 or name.casefold() in names:raise ValueError('Version names must be unique and 1–80 characters.')
        identifiers.add(ident); names.add(name.casefold())
        if not isinstance(version.get('excluded',[]),list) or any(not isinstance(x,str) for x in version.get('excluded',[])):raise ValueError('Invalid selections.')
        if not isinstance(version.get('indent',{}),dict) or any(type(x)!=int or not 0<=x<=3 for x in version.get('indent',{}).values()):raise ValueError('Indentation must be between 0 and 3.')
        if 'summaryOverride' in version and not isinstance(version['summaryOverride'],str):raise ValueError('Summary must be text.')
    ids = check_tree(data, state['tree'])
    if state.get('schemaVersion') == 2:
        highlights = state.get('highlights')
        if not isinstance(highlights, dict) or not isinstance(state.get('masterIndent'), dict): raise ValueError('Invalid highlight metadata.')
        highlight_ids = {i for i, _, _ in highlight_nodes(data, state['tree'])}
        for ident, group in highlights.items():
            if not isinstance(ident,str) or not isinstance(group, dict): raise ValueError('Unknown highlight.')
            wordings = group.get('wordings', [])
            if not wordings or len({w.get('id') for w in wordings}) != len(wordings): raise ValueError('Invalid wording IDs.')
            if group.get('defaultWording') not in {w['id'] for w in wordings}: raise ValueError('Missing initial wording.')
            for w in wordings:
                if not isinstance(w.get('id'), str) or not isinstance(w.get('text'), str) or w.get('reviewStatus') not in ('reviewed', 'unreviewed'): raise ValueError('Invalid wording.')
        if any(not isinstance(i,str) or type(x) != int or not 0 <= x <= 3 for i, x in state['masterIndent'].items()): raise ValueError('Invalid master indentation.')
        for v in state['versions']:
            if v.get('reviewStatus', 'unreviewed') not in ('reviewed', 'unreviewed'): raise ValueError('Invalid review status.')
            for ident, wording in v.get('wording', {}).items():
                if ident not in highlights or wording not in {w['id'] for w in highlights[ident]['wordings']}: raise ValueError('Unknown wording selection.')
            if not isinstance(v.get('prose', {}), dict) or any(not isinstance(x, str) for x in v.get('prose', {}).values()): raise ValueError('Invalid prose overrides.')
            for parent, order in v.get('order', {}).items():
                if parent not in ids or not isinstance(order, list) or len(set(order)) != len(order) or any(not isinstance(x,str) for x in order): raise ValueError('Invalid ordering.')
    return data,state

def project(data,state,active='master'):
    version=next((v for v in state['versions'] if v['id']==active),None)
    if active!='master' and version is None:raise ValueError('Unknown version.')
    version=version or {}; excluded=set(version.get('excluded',[])); levels={}
    def visit(value,node,path):
        if node['id'] in excluded:return None
        if node['id'] in version.get('prose',{}):value=version['prose'][node['id']]
        if path==('basics','summary') and 'summaryOverride' in version:value=version['summaryOverride']
        if isinstance(value,dict):
            result={}
            for k,v in value.items():
                synthetic=node['id']+'-'+k
                if synthetic in excluded:continue
                item=visit(version.get('prose',{}).get(synthetic,v),node['children'][k],path+(k,))
                if item is not None:result[k]=item
            for key in ('summary','description','label'):
                ident=node['id']+'-'+key
                if key not in value and ident in version.get('prose',{}) and ident not in excluded and (key!='label' or path==('basics',)):
                    if version['prose'][ident]:result[key]=version['prose'][ident]
            if len(path)==2 and path[0] in {'work','volunteer'} and value.get('endDate') and not result.get('endDate'):
                levels['/'.join(map(str,path))+'/hidePresent']=True
            return result or None
        if isinstance(value,list):
            result=[]; indents=[]
            pairs=list(zip(value,node['children']))
            order=version.get('order',{}).get(node['id'],[])
            rank={ident:i for i,ident in enumerate(order)}
            pairs.sort(key=lambda pair:rank.get(pair[1]['id'],len(rank)))
            for v,n in pairs:
                wording=selected_wording(state,version,n['id']) if active!='master' else None
                if wording:
                    group=state['highlights'][n['id']]
                    if wording['id']!=group['defaultWording']:v=wording['text']
                item=visit(v,n,path+(len(result),))
                if item is not None:
                    result.append(item)
                    desired=version.get('indent',{}).get(n['id'],state.get('masterIndent',{}).get(n['id'],0))
                    # Excluding a parent bullet must never create an orphaned nested list.
                    indents.append(min(desired,indents[-1]+1) if indents else 0)
            if path and path[-1]=='highlights':levels['/'.join(map(str,path))]=indents
            return result or None
        return value if value!='' else None
    result=visit(data,state['tree'],()) or {}
    # Permit an override when the master has no summary yet.
    if 'summaryOverride' in version and 'summary' not in data.get('basics',{}):
        basics=state['tree'].get('children',{}).get('basics',{})
        if basics.get('id') not in excluded and str(basics.get('id'))+'-summary' not in excluded and version['summaryOverride']:result.setdefault('basics',{})['summary']=version['summaryOverride']
    return result,levels

class Store:
    def __init__(self,root):
        self.root=Path(root)
        self.data=self.root/'data'
        self.output=self.root/'output'
        self.source=self.data/'resume.json'
        self.settings=self.data/'versions.json'
    def initialize(self):
        with LOCK:
            self.data.mkdir(parents=True,exist_ok=True)
            self.output.mkdir(parents=True,exist_ok=True)
            if not self.source.exists():
                if self.settings.exists():
                    raise ValueError('Master is missing. Restore data/resume.json and data/versions.json from the same backup.')
                shutil.copy2(self.data/'originals'/'resume.json',self.source)
            if not self.settings.exists():
                data=json.loads(self.source.read_text())
                self.write(self.settings,encoded({'schemaVersion':1,'tree':tree(data),'versions':[],'masterHash':hashlib.sha256(self.source.read_bytes()).hexdigest()}))
    def write(self,path,body):
        fd,name=tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
            os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)
    def revision(self):return hashlib.sha256(self.source.read_bytes()+b'\0'+self.settings.read_bytes()).hexdigest()
    def load(self):
        with LOCK:return self._load()
    def _load(self):
        self.initialize()
        data=json.loads(self.source.read_text());state=json.loads(self.settings.read_text())
        # Never guess new ID mappings after external structural changes.
        warning=''
        if state.get('masterHash')!=hashlib.sha256(self.source.read_bytes()).hexdigest():
            raise ValueError('Master changed outside the editor. Restore resume.json and versions.json from the same backup, or re-import your changes through the master editor to preserve version IDs.')
        validate(data,state)
        if state.get('schemaVersion')==1:
            return self.save(data,migrate(data,state),self.revision(),'master',migrating=True)
        return {'data':data,'state':state,'revision':self.revision(),'warning':warning}
    def save(self,data,state,expected,active,migrating=False):
        with LOCK:
            old=({'data':json.loads(self.source.read_text()),'state':json.loads(self.settings.read_text()),'revision':self.revision()} if migrating else self.load())
            if expected!=old['revision']:raise FileExistsError('Files changed on disk. Export your draft, then reload before saving.')
            validate(data,state)
            if active!='master' and not any(v['id']==active for v in state['versions']):raise ValueError('Unknown version.')
            if active!='master' and (data!=old['data'] or state['tree']!=old['state']['tree']):raise ValueError('Edit master content in Master, then save before switching versions.')
            if active!='master':
                if state.get('masterIndent',{})!=old['state'].get('masterIndent',{}):raise ValueError('Edit shared indentation in Master.')
                for ident,group in old['state'].get('highlights',{}).items():
                    current=state.get('highlights',{}).get(ident,{})
                    if current.get('defaultWording')!=group['defaultWording']:raise ValueError('Edit shared wording in Master.')
                    for wording in group['wordings']:
                        if next((w for w in current.get('wordings',[]) if w['id']==wording['id']),None)!=wording:raise ValueError('Edit shared wording in Master, or create an alternative for this version.')
            if not migrating:
                for prior in old['state']['versions']:
                    if prior.get('provenance',{}).get('jobId'):
                        linked=next((v for v in state['versions'] if v['id']==prior['id']),None)
                        if not linked or linked.get('provenance')!=prior['provenance']:raise ValueError('Retain versions linked to jobs; their IDs and provenance must remain stable.')
            state=prepare(data,state,old) if not migrating else copy.deepcopy(state)
            validate(data,state)
            payload=self.source.read_bytes() if data==old['data'] else encoded(data);state['masterHash']=hashlib.sha256(payload).hexdigest()
            writes={self.source:payload,self.settings:encoded(state)}
            for v in state['versions']:writes[self.output/f'resume-{v["id"]}.json']=encoded(project(data,state,v['id'])[0])
            removed={self.output/f'resume-{v["id"]}.json' for v in old['state']['versions']}-{p for p in writes}
            previous={p:p.read_bytes() if p.exists() else None for p in set(writes)|removed}
            backup=self.data/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f');backup.mkdir(parents=True)
            for p,body in previous.items():
                if body is not None:(backup/p.name).write_bytes(body)
            try:
                for p,body in writes.items():self.write(p,body)
                for p in removed:p.unlink(missing_ok=True)
            except Exception:
                for p,body in previous.items():
                    if body is None:p.unlink(missing_ok=True)
                    else:self.write(p,body)
                raise
            return self.load()
