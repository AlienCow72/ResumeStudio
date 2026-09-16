import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server
from codex_generate import CodexRunner, GenerationCancelled
from generation import GenerationService, validate_resume, validate_schema
from jobs import JobStore
from postings import PostingUnavailable, capture, extract_text, public_addresses
from versions import Store

MASTER = {'basics': {'name': 'Test Person', 'email': 'test@example.com', 'summary': 'Software developer'},
          'work': [{'name': 'Example', 'position': 'Developer', 'startDate': '2020', 'endDate': '2025', 'highlights': ['Built Python integrations.']}],
          'skills': [{'name': 'Languages', 'keywords': ['Python', 'SQL']}]}
POSTING = {'title': 'Platform Engineer', 'company': 'Hiring Company', 'description': 'Build and maintain Python integrations, investigate support requests, and work with business teams to deliver reliable services.',
           'responsibilities': ['Maintain integrations.'], 'qualifications': ['Experience with Python.']}
SOURCE = 'Hiring Company is hiring a Platform Engineer. ' + POSTING['description']
LETTER = 'Dear Hiring Team,\n\nI am applying for the Platform Engineer position at Hiring Company. My experience building Python integrations aligns with your work on reliable services.\n\nAt Example, I worked as a Developer and built Python integrations. I would welcome a conversation about how this experience could contribute to your team.\n\nThank you for your consideration.\n\nSincerely,\nTest Person'


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        originals = self.root/'data'/'originals'
        originals.mkdir(parents=True)
        (originals/'resume.json').write_text(json.dumps(MASTER))
        self.master = Store(self.root)
        self.master.load()
        self.jobs = JobStore(self.root)
        self.job = self.jobs.save({'company':'Hiring Company','title':'Platform Engineer','url':'https://example.com/job'})
        self.runner = Mock(side_effect=self.respond)
        self.fetcher = Mock(return_value=(SOURCE, {'url':self.job['url'], 'method':'test'}))
        self.renderer = Mock(return_value=b'%PDF-1.4\nTest fixture')
        self.service = GenerationService(self.jobs,self.master,self.runner,self.fetcher,self.renderer)

    def tearDown(self):
        for thread, cancel in list(self.service.workers.values()):
            cancel.set()
            thread.join(5)
        self.temp.cleanup()

    def respond(self, prompt, keys, cancel):
        if 'documentJson' in keys:
            self.assertIn('json-job-description', prompt)
            return {'documentJson':json.dumps(POSTING),'error':''}
        self.assertIn('json-resume', prompt)
        # Application generation must not precede validated posting persistence.
        self.assertTrue(list(self.service.base(self.job['id']).glob('runs/*/job-description.json')))
        return {'resumeJson':json.dumps(MASTER),'coverLetter':LETTER,'reviewNotes':'Emphasized integration experience.','error':''}

    def finish(self):
        worker = self.service.workers.get(self.job['id'])
        if worker:
            worker[0].join(5)
            self.assertFalse(worker[0].is_alive())
        return self.service.state(self.job['id'])

    def test_complete_pipeline_downloads_and_master_preservation(self):
        before = self.master.source.read_bytes()
        self.service.start(self.job['id'])
        state = self.finish()
        self.assertEqual(state['status'],'ready',state)
        self.assertEqual(set(state['files']), {'job-description.json', 'resume.json', 'cover-letter.md', 'resume.pdf', 'cover-letter.pdf'})
        self.assertEqual(self.runner.call_count,2)
        self.assertEqual(self.renderer.call_count,2)
        for name in state['files']:
            body,mime,filename = self.service.download(self.job['id'],state['runId'],name)
            self.assertTrue(body)
            self.assertTrue(filename.startswith('Hiring-Company-Platform-Engineer-'))
        self.assertEqual(self.master.source.read_bytes(),before)
        with self.assertRaises(ValueError):
            self.service.download(self.job['id'],'../','master-snapshot.json')
        self.assertEqual(self.service.start(self.job['id'])['runId'],state['runId'])

    def test_blocked_capture_can_resume_with_pasted_text(self):
        self.fetcher.side_effect = PostingUnavailable('Paste posting text.')
        self.service.start(self.job['id'])
        self.assertEqual(self.finish()['status'],'needs_input')
        self.runner.assert_not_called()
        self.service.start(self.job['id'],SOURCE)
        self.assertEqual(self.finish()['status'],'ready')
        self.assertEqual(self.fetcher.call_count,1)

    def test_extraction_validation_prevents_downstream_generation(self):
        self.runner.side_effect = None
        self.runner.return_value = {'documentJson':json.dumps({**POSTING,'remote':'Sometimes'}),'error':''}
        self.service.start(self.job['id'])
        state = self.finish()
        self.assertEqual(state['status'],'failed')
        self.assertNotIn('job-description.json',state['files'])
        self.assertEqual(self.runner.call_count,1)
        self.renderer.assert_not_called()

    def test_new_set_reuses_pasted_source_and_takes_fresh_master_snapshot(self):
        self.service.start(self.job['id'], SOURCE)
        first = self.finish()
        loaded = self.master.load()
        loaded['data']['basics']['summary'] = 'Updated verified summary'
        self.master.save(loaded['data'],loaded['state'],loaded['revision'],'master')
        self.service.start(self.job['id'],regenerate=True)
        second = self.finish()
        self.assertEqual(second['status'],'ready')
        self.assertNotEqual(first['masterHash'],second['masterHash'])
        self.fetcher.assert_not_called()
        folder=self.service.base(self.job['id'])/'runs'/second['runId']
        self.assertEqual((folder/'source.txt').read_text(),SOURCE)

    def test_pdf_failure_retry_reuses_completed_ai_work(self):
        self.renderer.side_effect = RuntimeError('Chrome unavailable')
        initial = self.service.start(self.job['id'])
        state = self.finish()
        self.assertEqual(state['status'],'failed')
        self.assertIn('resume.json',state['files'])
        self.renderer.side_effect = None
        self.service.start(self.job['id'])
        state = self.finish()
        self.assertEqual(state['status'],'ready')
        self.assertEqual(state['runId'],initial['runId'])
        self.assertEqual(self.runner.call_count,2)

    def test_document_failure_does_not_repeat_extraction(self):
        def fail_documents(prompt, keys, cancel):
            if 'documentJson' in keys:return self.respond(prompt,keys,cancel)
            raise RuntimeError('Temporary generation failure')
        self.runner.side_effect = fail_documents
        self.service.start(self.job['id'])
        state = self.finish()
        self.assertEqual(state['files'],['job-description.json'])
        self.runner.side_effect = self.respond
        self.service.start(self.job['id'])
        self.assertEqual(self.finish()['status'],'ready')
        self.assertEqual(self.runner.call_count,3)

    def test_regeneration_retains_old_files_and_detects_changed_source(self):
        self.service.start(self.job['id'])
        old = self.finish()
        old_pdf = self.service.download(self.job['id'],old['runId'],'resume.pdf')[0]
        saved = self.jobs.read(self.job['id'])
        self.jobs.save({'url':'https://example.com/another-job'},saved['id'],saved['revision'])
        self.assertTrue(self.service.state(self.job['id'])['sourceChanged'])
        self.service.start(self.job['id'])
        current = self.finish()
        self.assertNotEqual(old['runId'],current['runId'])
        self.assertEqual(current['previous']['runId'],old['runId'])
        self.assertEqual(self.service.download(self.job['id'],old['runId'],'resume.pdf')[0],old_pdf)

    def test_cancel_and_restart_recovery(self):
        began = threading.Event()
        def wait_for_cancel(prompt, keys, cancel):
            began.set(); cancel.wait(5); raise GenerationCancelled()
        self.runner.side_effect = wait_for_cancel
        state = self.service.start(self.job['id'])
        self.assertTrue(began.wait(3))
        self.assertEqual(self.service.start(self.job['id'])['runId'],state['runId'])
        self.service.cancel(self.job['id'])
        self.assertEqual(self.finish()['status'],'cancelled')
        state = self.service.state(self.job['id'])
        state['status'] = 'writing'
        self.service.persist(self.job['id'],state)
        self.assertEqual(self.service.state(self.job['id'])['status'],'interrupted')

    def test_changed_candidate_facts_are_rejected(self):
        for change in ['name','position','endDate','skill']:
            candidate = copy.deepcopy(MASTER)
            if change == 'name':candidate['basics']['name']='Someone Else'
            elif change == 'skill':candidate['skills'][0]['keywords'].append('Unsupported technology')
            else:candidate['work'][0][change]='Changed'
            with self.assertRaises(ValueError):validate_resume(candidate,MASTER)

    def test_api_auto_generation_and_download(self):
        with patch.object(server,'JOBS',self.jobs), patch.object(server,'STORE',self.master), patch.object(server,'generation',return_value=self.service):
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            base=f'http://127.0.0.1:{http.server_port}'
            try:
                request=Request(base+'/api/jobs',json.dumps({'job':{'url':'https://example.com/new'},'sourceText':SOURCE}).encode(),{'Content-Type':'application/json'})
                # This test's responder tracks the newly created job as soon as it runs.
                original = self.runner.side_effect
                def respond_new(prompt,keys,cancel):
                    if 'documentJson' not in keys:
                        return {'resumeJson':json.dumps(MASTER),'coverLetter':LETTER,'reviewNotes':'','error':''}
                    return original(prompt,keys,cancel)
                self.runner.side_effect=respond_new
                with urlopen(request) as response: created=json.load(response)
                self.assertIn(created['generation']['status'],['queued','extracting'])
                self.job=created
                state=self.finish()
                self.assertEqual(state['status'],'ready')
                self.assertEqual(self.jobs.read(created['id'])['company'],'Hiring Company')
                url=base+f'/api/jobs/{created["id"]}/files/{state["runId"]}/resume.pdf'
                with urlopen(url) as response:
                    self.assertEqual(response.headers['Content-Type'],'application/pdf')
                    self.assertIn('resume.pdf',response.headers['Content-Disposition'])
                    self.assertTrue(response.read().startswith(b'%PDF'))
                with self.assertRaises(HTTPError) as error:
                    urlopen(url.replace('resume.pdf','master-snapshot.json'))
                self.assertEqual(error.exception.code,400)
            finally:http.shutdown();http.server_close()


class PostingTests(unittest.TestCase):
    def test_html_extracts_visible_content_and_jobposting(self):
        text=extract_text('<script>alert("hidden")</script><script type="application/ld+json">{"@type":"JobPosting","title":"Engineer"}</script><h1>Engineer</h1><p>Build integrations.</p><style>hidden</style>')
        self.assertIn('JobPosting',text)
        self.assertIn('Build integrations.',text)
        self.assertNotIn('hidden',text)

    def test_private_addresses_and_redirects_are_blocked(self):
        with self.assertRaises(PostingUnavailable):capture('http://127.0.0.1/internal')
        with patch('postings.socket.getaddrinfo',return_value=[(None,None,None,None,('10.0.0.1',443))]):
            with self.assertRaises(PostingUnavailable):public_addresses('public.example',443)

    def test_codex_refuses_api_key_authentication(self):
        with patch('codex_generate.shutil.which',return_value='/bin/codex'), patch('codex_generate.subprocess.run') as run:
            run.return_value=Mock(returncode=0,stdout='Logged in using API key',stderr='')
            with self.assertRaisesRegex(RuntimeError,'ChatGPT'):
                CodexRunner()('prompt',('result',),threading.Event())


if __name__=='__main__':unittest.main()
