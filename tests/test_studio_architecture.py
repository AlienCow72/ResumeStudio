import copy
import hashlib
import io
import json
import shutil
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import application_drafts as drafts
import server
from generation import GenerationService
from jobs import JobStore
from studio_import import import_run, ReconciliationRequired
from versions import Store, encoded, highlight_nodes, project, tree
from test_generation import MASTER, POSTING, LETTER


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        originals=self.root/'data'/'originals';originals.mkdir(parents=True)
        self.data=copy.deepcopy(MASTER);self.data['work'][0]['highlights']=['Parent','Child','Third']
        self.data['projects']=[{'name':'Tool','description':'Original description','highlights':['Project parent','Project child']}]
        (originals/'resume.json').write_text(json.dumps(self.data))
        self.store=Store(self.root);self.loaded=self.store.load()
        self.jobs=JobStore(self.root);self.job=self.jobs.save({'company':'Hiring','title':'Engineer','url':'https://example.com/job'})
        self.service=GenerationService(self.jobs,self.store,renderer=Mock(side_effect=lambda html:html.encode()))
        self.ids=[i for i,_,_ in highlight_nodes(self.loaded['data'],self.loaded['state']['tree'])]
        self.run='a'*32;self.folder=self.service.base(self.job['id'])/'runs'/self.run

    def tearDown(self):self.temp.cleanup()

    def version(self,loaded=None):
        loaded=loaded or self.loaded
        v={'id':'joblinks','name':'Joblinks','excluded':[],'indent':{},'reviewStatus':'unreviewed'}
        loaded['state']['versions'].append(v);return v

    def save(self,loaded,active='master'):
        return self.store.save(loaded['data'],loaded['state'],loaded['revision'],active)

    def documents(self,resume=None,refs=None,snapshot=True):
        self.jobs.write(self.folder/'documents.json',{'resume':resume or self.data,'coverLetter':LETTER,'reviewNotes':'','highlightSources':refs or {}})
        self.jobs.write(self.folder/'job-description.json',POSTING)
        if snapshot:self.jobs.write(self.folder/'studio-snapshot.json',self.store.load())
        self.service.persist(self.job['id'],{'status':'ready','runId':self.run,'sourceUrl':self.job['url'],'files':[]})

    def test_migration_preserves_real_versions_and_repeat_load(self):
        real=Path(__file__).resolve().parents[1]/'data'
        shutil.copy2(real/'resume.json',self.store.source);shutil.copy2(real/'versions.json',self.store.settings)
        data=json.loads(self.store.source.read_text());state=json.loads(self.store.settings.read_text())
        before={v['id']:project(data,state,v['id']) for v in state['versions']};raw=self.store.source.read_bytes()
        loaded=self.store.load()
        self.assertEqual(loaded['state']['schemaVersion'],2)
        for ident,projection in before.items():self.assertEqual(project(data,loaded['state'],ident),projection)
        joblinks=next(v for v in state['versions'] if v['name'].lower()=='joblinks')
        for ident,_,_ in highlight_nodes(data,state['tree']):self.assertEqual(loaded['state']['masterIndent'][ident],state['masterIndent'].get(ident,0) if state['schemaVersion']==2 else joblinks.get('indent',{}).get(ident,0))
        self.assertEqual(self.store.source.read_bytes(),raw)
        self.assertEqual(self.store.load(),loaded)
        if state['schemaVersion']==1:
            self.assertTrue(any(json.loads((backup/'versions.json').read_text())==state for backup in (self.root/'data'/'backups').iterdir()))

    def test_legacy_indentation_migration_preserves_existing_projections(self):
        legacy={'schemaVersion':1,'tree':self.loaded['state']['tree'],'masterHash':hashlib.sha256(self.store.source.read_bytes()).hexdigest(),
                'versions':[{'id':'joblinks','name':'Joblinks','excluded':[self.ids[2]],'indent':{self.ids[1]:1,self.ids[4]:1},'summaryOverride':'Legacy objective'},
                            {'id':'other','name':'Other','excluded':[self.ids[0]],'indent':{self.ids[1]:3}}]}
        before={v['id']:project(self.loaded['data'],legacy,v['id']) for v in legacy['versions']}
        self.store.write(self.store.settings,encoded(legacy));loaded=self.store.load()
        for ident,projection in before.items():self.assertEqual(project(loaded['data'],loaded['state'],ident),projection)
        self.assertEqual(loaded['state']['masterIndent'][self.ids[1]],1)
        self.assertEqual(loaded['state']['masterIndent'][self.ids[4]],1)
        self.assertEqual(self.store.load(),loaded)

    def test_alternatives_review_invalidation_and_master_isolation(self):
        v=self.version();self.loaded=self.save(self.loaded)
        state=self.loaded['state'];group=state['highlights'][self.ids[0]]
        group['wordings'].append({'id':'alternative','text':'Reworded parent','reviewStatus':'unreviewed'})
        state['versions'][0].update(wording={self.ids[0]:'alternative'},markReviewed=True)
        self.loaded=self.save(self.loaded,'joblinks')
        self.assertEqual(project(self.loaded['data'],self.loaded['state'],'joblinks')[0]['work'][0]['highlights'][0],'Reworded parent')
        self.assertEqual(self.loaded['state']['versions'][0]['reviewStatus'],'reviewed')
        self.assertEqual(self.loaded['state']['highlights'][self.ids[0]]['wordings'][1]['reviewStatus'],'reviewed')
        self.assertEqual(self.loaded['data'],self.data)
        self.loaded['state']['highlights'][self.ids[0]]['wordings'][1]['text']='Edited shared wording'
        with self.assertRaises(ValueError):self.save(self.loaded,'joblinks')
        self.loaded=self.save(self.loaded)
        self.assertEqual(self.loaded['state']['versions'][0]['reviewStatus'],'unreviewed')
        self.assertEqual(self.loaded['state']['highlights'][self.ids[0]]['wordings'][1]['reviewStatus'],'unreviewed')

    def test_new_highlights_excluded_and_defaults_overrides_order_and_prose(self):
        v=self.version();self.loaded=self.save(self.loaded)
        self.loaded['data']['work'][0]['highlights'].append('New information')
        self.loaded['state']['tree']['children']['work']['children'][0]['children']['highlights']['children'].append(tree('New information'))
        self.loaded=self.save(self.loaded)
        self.assertNotIn('New information',project(self.loaded['data'],self.loaded['state'],'joblinks')[0]['work'][0]['highlights'])
        state=self.loaded['state'];v=state['versions'][0];v['indent']={}
        state['masterIndent'].update({self.ids[1]:2,self.ids[2]:3,self.ids[4]:2})
        result,levels=project(self.loaded['data'],state,'joblinks')
        self.assertEqual(levels['work/0/highlights'],[0,1,2]);self.assertEqual(levels['projects/0/highlights'],[0,1])
        v['indent'][self.ids[2]]=0;self.assertEqual(project(self.loaded['data'],state,'joblinks')[1]['work/0/highlights'],[0,1,0])
        del v['indent'][self.ids[2]];v['excluded'].append(self.ids[0])
        self.assertEqual(project(self.loaded['data'],state,'joblinks')[1]['work/0/highlights'],[0,1])
        parent=state['tree']['children']['projects']['children'][0]['children']
        v['order']={parent['highlights']['id']:[self.ids[4],self.ids[3]]};v['prose']={parent['description']['id']:'Tailored description'}
        result,levels=project(self.loaded['data'],state,'joblinks')
        self.assertEqual(result['projects'][0]['highlights'],['Project child','Project parent']);self.assertEqual(result['projects'][0]['description'],'Tailored description')
        self.assertEqual(state['masterIndent'][self.ids[1]],2)

    def test_prose_customization_when_master_has_no_headline_or_entry_summary(self):
        version=self.version();basics=self.loaded['state']['tree']['children']['basics'];work=self.loaded['state']['tree']['children']['work']['children'][0]
        version['prose']={basics['id']+'-label':'Target headline',work['id']+'-summary':'Tailored entry summary'}
        result,_=project(self.loaded['data'],self.loaded['state'],'joblinks')
        self.assertEqual(result['basics']['label'],'Target headline');self.assertEqual(result['work'][0]['summary'],'Tailored entry summary')
        version['excluded'].append(work['id']+'-summary')
        self.assertNotIn('summary',project(self.loaded['data'],self.loaded['state'],'joblinks')[0]['work'][0])
        self.loaded=self.save(self.loaded,'joblinks');self.assertNotIn('label',self.loaded['data']['basics'])
        self.loaded['data']['basics']['label']='New master headline';self.loaded['state']['tree']['children']['basics']['children']['label']=tree('New master headline')
        self.loaded['data']['work'][0]['summary']='New master summary';self.loaded['state']['tree']['children']['work']['children'][0]['children']['summary']=tree('New master summary')
        self.loaded=self.save(self.loaded)
        projected=project(self.loaded['data'],self.loaded['state'],'joblinks')[0]
        self.assertEqual(projected['basics']['label'],'Target headline');self.assertNotIn('summary',projected['work'][0])

    def test_import_deduplicates_alternatives_preserves_order_and_is_idempotent(self):
        self.version();self.loaded=self.save(self.loaded)
        resume=copy.deepcopy(self.data);resume['work'][0]['highlights']=['Tailored child','Parent'];resume['basics']['label']='Target headline'
        resume['projects'][0]['description']='Tailored prose'
        refs={'work/0/highlights/0':[self.ids[1]],'work/0/highlights/1':[self.ids[0]],'projects/0/highlights/0':[self.ids[3]],'projects/0/highlights/1':[self.ids[4]]}
        self.documents(resume,refs)
        result=import_run(self.service,self.job['id'],self.run)
        loaded=self.store.load();self.assertEqual(project(loaded['data'],loaded['state'],result['versionId'])[0],resume)
        self.assertEqual(loaded['data']['work'][0]['highlights'],self.data['work'][0]['highlights'])
        self.assertEqual(len(loaded['state']['highlights'][self.ids[1]]['wordings']),2)
        self.assertTrue(import_run(self.service,self.job['id'],self.run)['alreadyImported'])
        # A second run uses the same alternative rather than duplicating wording.
        self.run='b'*32;self.folder=self.service.base(self.job['id'])/'runs'/self.run;self.documents(resume,refs)
        import_run(self.service,self.job['id'],self.run)
        self.assertEqual(len(self.store.load()['state']['highlights'][self.ids[1]]['wordings']),2)
        self.assertEqual(project(loaded['data'],loaded['state'],'joblinks')[0]['work'][0]['highlights'],['Parent','Child','Third'])

    def test_combined_unmatched_are_separate_and_excluded_from_existing_versions(self):
        self.version();self.loaded=self.save(self.loaded)
        resume=copy.deepcopy(self.data);resume['work'][0]['highlights']=['Combined','Unmatched']
        self.documents(resume,{'work/0/highlights/0':self.ids[:2],'work/0/highlights/1':[]})
        result=import_run(self.service,self.job['id'],self.run)
        loaded=self.store.load();self.assertEqual(project(loaded['data'],loaded['state'],result['versionId'])[0],resume)
        self.assertEqual(project(loaded['data'],loaded['state'],'joblinks')[0],self.data)
        new=[g for i,g in loaded['state']['highlights'].items() if i not in self.ids]
        self.assertEqual(len(new),2);self.assertTrue(all(g['wordings'][0]['reviewStatus']=='unreviewed' for g in new))

    def test_invalid_refs_and_concurrent_source_changes_pause_without_mutation(self):
        self.documents(refs={'work/0/highlights/0':['fake-id']})
        before=self.store.load()['revision']
        with self.assertRaises(ValueError):import_run(self.service,self.job['id'],self.run)
        self.assertEqual(before,self.store.load()['revision'])
        self.documents(refs={'work/0/highlights/0':[self.ids[0]]})
        loaded=self.store.load();loaded['data']['work'][0]['highlights'][0]='Changed during generation';self.save(loaded)
        revision=self.store.load()['revision']
        with self.assertRaises(ReconciliationRequired):import_run(self.service,self.job['id'],self.run)
        self.assertEqual(revision,self.store.load()['revision']);self.assertTrue((self.folder/'documents.json').exists())
        preview=import_run(self.service,self.job['id'],self.run,preview=True)
        self.assertTrue(preview['conflicts'])
        imported=import_run(self.service,self.job['id'],self.run,expected=preview['revision'],acknowledge=True)
        self.assertEqual(project(self.store.load()['data'],self.store.load()['state'],imported['versionId'])[0]['work'][0]['highlights'][0],'Parent')

    def test_disappeared_source_requires_explicit_reconciliation(self):
        self.documents(refs={'work/0/highlights/0':[self.ids[0]]})
        loaded=self.store.load();loaded['data']['work'][0]['highlights'].pop(0);loaded['state']['tree']['children']['work']['children'][0]['children']['highlights']['children'].pop(0);self.save(loaded)
        with self.assertRaises(ReconciliationRequired):import_run(self.service,self.job['id'],self.run)
        result=import_run(self.service,self.job['id'],self.run,acknowledge=True)
        loaded=self.store.load();self.assertEqual(project(loaded['data'],loaded['state'],result['versionId'])[0],self.data)
        additions=[g for i,g in loaded['state']['highlights'].items() if i not in self.ids]
        self.assertEqual(additions[0]['wordings'][0]['provenance']['sourceHighlights'],[self.ids[0]])

    def test_import_failure_rolls_back_and_retry_finishes_without_duplicate(self):
        resume=copy.deepcopy(self.data);resume['work'][0]['highlights']=['Rewritten']
        self.documents(resume,{'work/0/highlights/0':[self.ids[0]]})
        before=self.store.load()['revision'];write=self.store.write;failed=False
        def fail_once(path,body):
            nonlocal failed
            if path.parent==self.store.output and not failed:failed=True;raise OSError('Failed output')
            return write(path,body)
        with patch.object(self.store,'write',side_effect=fail_once):
            with self.assertRaises(OSError):import_run(self.service,self.job['id'],self.run)
        self.assertEqual(before,self.store.load()['revision'])
        import_run(self.service,self.job['id'],self.run)
        self.assertTrue(import_run(self.service,self.job['id'],self.run)['alreadyImported'])
        self.assertEqual(len(self.store.load()['state']['versions']),1)

    def test_historical_preview_uses_latest_draft_and_stale_preview_conflicts(self):
        self.documents(snapshot=False)
        draft=drafts.read(self.service,self.job['id'],self.run);draft['resume']['basics']['summary']='Saved job draft';drafts.save(self.service,self.job['id'],self.run,draft,draft['revision'])
        preview=import_run(self.service,self.job['id'],self.run,preview=True)
        self.assertEqual(preview['resume']['basics']['summary'],'Saved job draft');self.assertEqual(self.store.load()['state']['versions'],[])
        loaded=self.store.load();loaded['data']['basics']['summary']='Concurrent master edit';self.save(loaded)
        with self.assertRaises(ReconciliationRequired):import_run(self.service,self.job['id'],self.run,expected=preview['revision'])
        imported=import_run(self.service,self.job['id'],self.run)
        self.assertEqual(project(self.store.load()['data'],self.store.load()['state'],imported['versionId'])[0]['basics']['summary'],'Saved job draft')

    def test_shared_preview_zip_and_rendering_snapshot_detect_concurrent_save(self):
        self.documents();import_run(self.service,self.job['id'],self.run)
        loaded=self.store.load();version=loaded['state']['versions'][0];version['indent'][self.ids[1]]=1;version['summaryOverride']='Saved Studio objective';loaded=self.save(loaded,version['id'])
        draft=drafts.read(self.service,self.job['id'],self.run)
        projected,levels=project(loaded['data'],loaded['state'],version['id'])
        self.assertEqual(draft['resume'],projected);self.assertEqual(draft['levels'],levels)
        preview=drafts.preview(self.service,self.job['id'],self.run,draft)
        self.assertEqual(preview['resume'],server.html_doc(projected,levels))
        body,_=drafts.bundle(self.service,self.job['id'],self.run,draft['revision'])
        with zipfile.ZipFile(io.BytesIO(body)) as archive:self.assertEqual(archive.read('resume.pdf'),preview['resume'].encode())
        old=draft;loaded['state']['versions'][0]['summaryOverride']='Changed in Studio';self.save(loaded,version['id'])
        old['coverLetter']='Unsaved letter'
        with self.assertRaises(FileExistsError):drafts.save(self.service,self.job['id'],self.run,old,old['revision'])
        self.assertEqual(old['coverLetter'],'Unsaved letter')
        self.assertFalse(list(self.folder.glob('*.pdf')))
        current=drafts.read(self.service,self.job['id'],self.run)
        current['coverLetter']='Saved cover letter';drafts.save(self.service,self.job['id'],self.run,current,current['revision'])
        self.assertNotIn('resume',json.loads((self.folder/'draft.json').read_text()))
        self.assertTrue(all('resume' not in json.loads(p.read_text()) for p in (self.folder/'draft-history').glob('*.json')))
        def save_during_render(html):
            snapshot=self.store.load();snapshot['state']['versions'][0]['summaryOverride']='Changed while rendering';self.save(snapshot,version['id']);return html.encode()
        self.service.renderer.side_effect=save_during_render
        current=drafts.read(self.service,self.job['id'],self.run)
        with self.assertRaises(FileExistsError):drafts.bundle(self.service,self.job['id'],self.run,current['revision'])

    def test_rejected_history_dates_and_documents_survive(self):
        self.documents();applied=self.jobs.save({'stage':'waiting','appliedOn':'2026-10-01'},self.job['id'],self.job['revision'])
        rejected=self.jobs.save({'stage':'rejected'},applied['id'],applied['revision']);restored=self.jobs.save({'stage':'interview'},rejected['id'],rejected['revision'])
        self.assertEqual(restored['appliedOn'],'2026-10-01');self.assertEqual([h['to'] for h in restored['history']],['applying','waiting','rejected','interview']);self.assertTrue((self.folder/'documents.json').exists())

    def test_historical_import_http_retry_and_concurrent_preview(self):
        self.documents(snapshot=False)
        with patch.object(server,'STORE',self.store),patch.object(server,'JOBS',self.jobs),patch.object(server,'generation',return_value=self.service):
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{http.server_port}/api/jobs/{self.job["id"]}'
            def post(action,body):return urlopen(Request(base+'/'+action,json.dumps(body).encode(),{'Content-Type':'application/json'}))
            try:
                with post('preview-import',{'runId':self.run}) as response:preview=json.load(response)
                payload={'runId':self.run,'revision':preview['revision'],'draftRevision':preview['draftRevision']}
                draft=drafts.read(self.service,self.job['id'],self.run);draft['coverLetter']='Changed after preview';drafts.save(self.service,self.job['id'],self.run,draft,draft['revision'])
                with self.assertRaises(HTTPError) as error:post('import-studio',payload)
                self.assertEqual(error.exception.code,409)
                with post('preview-import',{'runId':self.run}) as response:preview=json.load(response)
                payload={'runId':self.run,'revision':preview['revision'],'draftRevision':preview['draftRevision']}
                with post('import-studio',payload) as response:result=json.load(response)
                with post('import-studio',payload) as response:self.assertEqual(json.load(response)['versionId'],result['versionId'])
                self.assertEqual(len(self.store.load()['state']['versions']),1)
                self.assertEqual(self.service.state(self.job['id'])['versionId'],result['versionId'])
            finally:http.shutdown();http.server_close()

    def test_idempotent_creation_is_atomic_and_survives_updates(self):
        data={'company':'Example','title':'Engineer','url':'https://example.com/separate'}
        with patch.object(self.jobs,'write',wraps=self.jobs.write) as write:
            job,created=self.jobs.create(data,allow_duplicate=True,idempotency_key='retry-key')
            self.assertTrue(created);self.assertEqual(write.call_count,1)
        self.jobs.save({'stage':'rejected'},job['id'],job['revision'])
        repeated,created=self.jobs.create(data,allow_duplicate=True,idempotency_key='retry-key')
        self.assertFalse(created);self.assertEqual(repeated['id'],job['id']);self.assertEqual(repeated['stage'],'rejected')
        self.assertEqual(len(self.jobs.list()),2)

    def test_assistant_api_creation_lookup_duplicates_idempotency_and_retry(self):
        with patch.object(server,'STORE',self.store),patch.object(server,'JOBS',self.jobs),patch.object(server,'generation',return_value=self.service),patch.object(self.service,'start',return_value={'status':'queued'}) as start:
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{http.server_port}'
            def post(path,body,key=None):
                headers={'Content-Type':'application/json'}
                if key:headers['Idempotency-Key']=key
                return urlopen(Request(base+path,json.dumps(body).encode(),headers))
            try:
                request={'job':{'url':'https://example.com/new?req=123&utm_source=assistant','notes':'Assistant'}}
                with post('/api/jobs',request,'create-123') as response:job=json.load(response);self.assertEqual(response.status,201)
                self.assertEqual(start.call_count,1)
                with post('/api/jobs',request,'create-123') as response:self.assertEqual(json.load(response)['id'],job['id']);self.assertEqual(response.status,200)
                with self.assertRaises(HTTPError) as error:post('/api/jobs',{'job':{'url':'https://example.com/different'}},'create-123')
                self.assertEqual(error.exception.code,409)
                with post('/api/jobs',{'job':{'url':'https://example.com/new?req=123&fbclid=ignore'}}) as response:self.assertEqual(json.load(response)['id'],job['id'])
                self.assertEqual(start.call_count,1)
                with urlopen(base+'/api/jobs?url='+quote('https://example.com/new?req=123')) as response:self.assertEqual([j['id'] for j in json.load(response)['jobs']],[job['id']])
                with urlopen(base+'/api/jobs?url='+quote('https://example.com/new?req=124')) as response:self.assertEqual(json.load(response),{'jobs':[]})
                with urlopen(base+'/api/jobs/'+job['id']) as response:self.assertIn('generationStatus',json.load(response))
                with self.assertRaises(HTTPError) as error:urlopen(base+'/api/jobs/'+'f'*32)
                self.assertEqual(error.exception.code,404)
                with post('/api/jobs',{**request,'allowDuplicate':True,'generate':False}) as response:duplicate=json.load(response)
                with self.assertRaises(HTTPError) as error:post('/api/jobs',request)
                self.assertEqual(error.exception.code,409);self.assertEqual({j['id'] for j in json.load(error.exception)['duplicates']},{job['id'],duplicate['id']})
                with post('/api/jobs/'+job['id']+'/generate',{}) as response:self.assertEqual(response.status,202)
                self.assertEqual(start.call_count,2)
            finally:http.shutdown();http.server_close()
