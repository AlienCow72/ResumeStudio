import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import server
from versions import Store,project,tree,validate

SAMPLE={'basics':{'name':'Test Person','summary':'Default summary'},'work':[{'name':'Company','position':'Developer','highlights':['Parent','Child','Hidden']},{'name':'Second','highlights':['Other']}],'skills':[{'name':'Languages','keywords':['Python','SQL']}]}
class VersionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name);self.root=self.project/'data';self.originals=self.root/'originals';self.originals.mkdir(parents=True);self.output=self.project/'output';(self.originals/'resume.json').write_text(json.dumps(SAMPLE));self.store=Store(self.project);self.loaded=self.store.load();self.data=self.loaded['data'];self.state=self.loaded['state'];self.rev=self.loaded['revision']
    def tearDown(self):self.temp.cleanup()
    def add_version(self):
        t=self.state['tree']['children'];v={'id':'developer','name':'Developer','excluded':[t['work']['children'][0]['children']['highlights']['children'][2]['id'],t['work']['children'][1]['id'],t['skills']['children'][0]['children']['keywords']['children'][1]['id']],'indent':{t['work']['children'][0]['children']['highlights']['children'][1]['id']:1},'summaryOverride':'Custom summary'};self.state['versions'].append(v);return v
    def test_migration_and_save_with_backup(self):
        before=(self.originals/'resume.json').read_bytes();self.assertEqual(self.store.source.read_bytes(),before);self.add_version();out=self.store.save(self.data,self.state,self.rev,'developer');self.assertEqual((self.originals/'resume.json').read_bytes(),before);self.assertEqual(json.loads(self.store.source.read_text()),SAMPLE)
        generated=json.loads((self.output/'resume-developer.json').read_text());self.assertEqual(generated['basics']['summary'],'Custom summary');self.assertEqual(generated['work'][0]['highlights'],['Parent','Child']);self.assertEqual(generated['skills'][0]['keywords'],['Python']);self.assertEqual(len(generated['work']),1)
        backup=next((self.root/'backups').iterdir());self.assertEqual(json.loads((backup/'resume.json').read_text()),SAMPLE)
        with self.assertRaises(FileExistsError):self.store.save(self.data,self.state,self.rev,'developer')
    def test_save_rolls_back_data_and_output_on_failure(self):
        self.add_version()
        loaded=self.store.save(self.data,self.state,self.rev,'developer')
        paths=[self.store.source,self.store.settings,self.output/'resume-developer.json']
        before={p:p.read_bytes() for p in paths}
        self.data['basics']['name']='Changed'
        write=self.store.write
        failed=False
        def fail_output_once(path,body):
            nonlocal failed
            if path.parent==self.output and not failed:
                failed=True
                raise OSError('Simulated output write failure')
            write(path,body)
        with patch.object(self.store,'write',side_effect=fail_output_once):
            with self.assertRaises(OSError):
                self.store.save(self.data,self.state,loaded['revision'],'master')
        self.assertTrue(failed)
        self.assertEqual({p:p.read_bytes() for p in paths},before)
        self.assertEqual(self.store.load()['revision'],loaded['revision'])

    def test_stable_ids_reordering_and_master_edits(self):
        v=self.add_version();t=self.state['tree']['children'];self.data['work'].reverse();t['work']['children'].reverse();self.data['work'][1]['highlights'].reverse();t['work']['children'][1]['children']['highlights']['children'].reverse();self.data['work'][1]['highlights'][1]='Edited child'
        d,levels=project(self.data,self.state,'developer');self.assertEqual(len(d['work']),1);self.assertEqual(d['work'][0]['highlights'],['Edited child','Parent']);self.assertEqual(levels['work/0/highlights'],[0,0]);self.assertEqual(project(self.data,self.state)[0],self.data)
    def test_parent_selection_override_reset_and_indentation(self):
        v=self.add_version();section=self.state['tree']['children']['work']['id'];v['excluded'].append(section);d,_=project(self.data,self.state,'developer');self.assertNotIn('work',d);v['excluded'].remove(section);d,levels=project(self.data,self.state,'developer');self.assertEqual(d['work'][0]['highlights'],['Parent','Child']);self.assertEqual(levels['work/0/highlights'],[0,1]);html=server.html_doc(d,levels);self.assertIn('<li>Parent<ul><li>Child</li></ul></li>',html);self.assertIn('  - Child',server.markdown(d,levels));del v['summaryOverride'];self.assertEqual(project(self.data,self.state,'developer')[0]['basics']['summary'],'Default summary')
    def test_version_cannot_change_master_and_external_changes_detected(self):
        self.add_version();changed=copy.deepcopy(self.data);changed['basics']['summary']='Not allowed'
        with self.assertRaises(ValueError):self.store.save(changed,self.state,self.rev,'developer')
        self.store.source.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):self.store.load()
    def test_rename_delete_and_regeneration(self):
        v=self.add_version();loaded=self.store.save(self.data,self.state,self.rev,'developer');v['id']='support';v['name']='Support';loaded=self.store.save(self.data,self.state,loaded['revision'],'support');self.assertFalse((self.output/'resume-developer.json').exists());self.assertTrue((self.output/'resume-support.json').exists());self.data['basics']['name']='Updated name';loaded=self.store.save(self.data,self.state,loaded['revision'],'master');self.assertEqual(json.loads((self.output/'resume-support.json').read_text())['basics']['name'],'Updated name');self.state['versions']=[];self.store.save(self.data,self.state,loaded['revision'],'master');self.assertFalse((self.output/'resume-support.json').exists())
    def test_missing_summary_override_and_excluded_end_date(self):
        self.data={'basics':{'name':'Name'},'work':[{'name':'Past employer','startDate':'2020','endDate':'2022','highlights':['A']}]}
        self.state={'schemaVersion':1,'tree':tree(self.data),'versions':[]};t=self.state['tree']['children'];v={'id':'test','name':'Test','excluded':[t['work']['children'][0]['children']['endDate']['id']],'indent':{},'summaryOverride':'Alternate summary'};self.state['versions'].append(v)
        d,levels=project(self.data,self.state,'test');self.assertEqual(d['basics']['summary'],'Alternate summary');self.assertNotIn('Present',server.html_doc(d,levels));self.assertNotIn('Present',server.markdown(d,levels))
        v['excluded'].append(t['basics']['id']+'-summary');self.assertNotIn('summary',project(self.data,self.state,'test')[0]['basics'])
    def test_api(self):
        old=server.STORE;server.STORE=self.store;http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
        def post(path):return urlopen(Request(f'http://127.0.0.1:{http.server_port}/api/{path}',json.dumps({'data':self.data,'state':self.state,'active':'developer','revision':self.rev}).encode(),{'Content-Type':'application/json'}))
        try:
            self.add_version()
            for kind in ['json','md','html']:
                r=post('export/'+kind);self.assertIn('resume-developer.',r.headers['Content-Disposition']);self.assertTrue(r.read())
            self.assertEqual(json.loads(self.store.source.read_text()),SAMPLE)
            post('save').close()
            with self.assertRaises(HTTPError) as e:post('save')
            self.assertEqual(e.exception.code,409)
        finally:http.shutdown();http.server_close();server.STORE=old
if __name__=='__main__':unittest.main()
