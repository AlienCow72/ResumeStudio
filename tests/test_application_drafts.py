import copy
import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import application_drafts as drafts
import server
from generation import GenerationService
from jobs import JobStore
from versions import Store
from test_generation import MASTER, POSTING, LETTER


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        original=self.root/'data'/'originals';original.mkdir(parents=True)
        (original/'resume.json').write_text(json.dumps(MASTER))
        self.master=Store(self.root);self.master.load();self.jobs=JobStore(self.root)
        self.job=self.jobs.save({'company':POSTING['company'],'title':POSTING['title'],'url':'https://example.com/job'})
        self.renderer=Mock(side_effect=lambda content: b'%PDF-'+content.encode())
        self.service=GenerationService(self.jobs,self.master,renderer=self.renderer)
        self.run='a'*32;self.folder=self.service.base(self.job['id'])/'runs'/self.run
        self.jobs.write(self.folder/'documents.json',{'resume':MASTER,'coverLetter':LETTER,'reviewNotes':''})
        self.jobs.write(self.folder/'job-description.json',POSTING)
        self.service.persist(self.job['id'],{'status':'ready','runId':self.run,'sourceUrl':self.job['url'],'files':[]})
        self.original=self.master.source.read_bytes()

    def tearDown(self):self.temp.cleanup()

    def read(self):return drafts.read(self.service,self.job['id'],self.run)
    def save(self,data):return drafts.save(self.service,self.job['id'],self.run,data,data['revision'])

    def test_save_preview_do_not_render_and_edits_survive_reload(self):
        draft=self.read();draft['resume']['basics']['summary']='My reviewed summary';draft['coverLetter']='My reviewed letter.'
        saved=self.save(draft)
        self.assertNotEqual(saved['revision'],draft['revision'])
        self.assertEqual(self.read()['coverLetter'],'My reviewed letter.')
        preview=drafts.preview(self.service,self.job['id'],self.run,saved)
        self.assertIn('My reviewed summary',preview['resume']);self.assertIn('My reviewed letter.',preview['coverLetter'])
        self.renderer.assert_not_called();self.assertEqual(self.master.source.read_bytes(),self.original)
        self.assertEqual(len(list((self.folder/'draft-history').glob('*.json'))),1)

    def test_pdf_preview_matches_export_without_saving(self):
        draft=self.read();draft['coverLetter']='Unsaved preview text'
        before={path: path.read_bytes() for path in self.folder.rglob('*') if path.is_file()}
        with patch.object(drafts, 'pdf_pages', side_effect=lambda content: {'pdf':content}):
            resume=drafts.preview(self.service,self.job['id'],self.run,draft,'resume')
            letter=drafts.preview(self.service,self.job['id'],self.run,draft,'coverLetter')
        self.assertIn(b'Unsaved preview text',letter['pdf'])
        self.assertEqual(before,{path:path.read_bytes() for path in self.folder.rglob('*') if path.is_file()})
        saved=self.save(draft)
        body,_=drafts.bundle(self.service,self.job['id'],self.run,saved['revision'])
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(resume['pdf'],archive.read('resume.pdf'))
            self.assertEqual(letter['pdf'],archive.read('cover-letter.pdf'))
        with self.assertRaises(ValueError):
            drafts.preview(self.service,self.job['id'],self.run,draft,'invalid')

    def test_zip_contains_exact_files_with_latest_edits(self):
        draft=self.read();draft['resume']['basics']['summary']='Reviewed résumé';draft['coverLetter']='Reviewed cover letter.'
        saved=self.save(draft)
        body,filename=drafts.bundle(self.service,self.job['id'],self.run,saved['revision'])
        self.assertTrue(filename.endswith('-application.zip'))
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(set(archive.namelist()),{'job-description.json','resume.pdf','cover-letter.pdf'})
            self.assertEqual(json.loads(archive.read('job-description.json')),POSTING)
            self.assertIn('Reviewed résumé',archive.read('resume.pdf').decode())
            self.assertIn('Reviewed cover letter.',archive.read('cover-letter.pdf').decode())
        self.assertEqual(self.renderer.call_count,2)

    def test_stale_save_and_export_are_rejected(self):
        first=self.read();second=copy.deepcopy(first);first['coverLetter']='Saved by first tab';self.save(first)
        with self.assertRaises(FileExistsError):self.save(second)
        with self.assertRaises(FileExistsError):drafts.bundle(self.service,self.job['id'],self.run,second['revision'])
        self.renderer.assert_not_called()

    def test_render_failure_preserves_drafts_and_retry_uses_no_ai(self):
        saved=self.save(self.read());self.renderer.side_effect=RuntimeError('No Chrome')
        with self.assertRaises(RuntimeError):drafts.bundle(self.service,self.job['id'],self.run,saved['revision'])
        self.assertEqual(self.read()['revision'],saved['revision'])
        self.renderer.side_effect=lambda html:b'%PDF test'
        self.assertTrue(drafts.bundle(self.service,self.job['id'],self.run,saved['revision'])[0])

    def test_edits_during_render_reject_outdated_download(self):
        initial=self.read()
        def render(content):
            if self.renderer.call_count==1:
                changed=self.read();changed['coverLetter']='Changed during rendering';self.save(changed)
            return b'%PDF'
        self.renderer.side_effect=render
        with self.assertRaises(FileExistsError):drafts.bundle(self.service,self.job['id'],self.run,initial['revision'])

    def test_user_corrections_allowed_and_invalid_drafts_rejected(self):
        draft=self.read();draft['resume']['work'][0]['endDate']='';draft['resume']['basics']['email']='corrected@example.com'
        saved=self.save(draft);self.assertNotIn('endDate',saved['resume']['work'][0])
        saved['coverLetter']=' '
        with self.assertRaises(ValueError):self.save(saved)
        with self.assertRaises(ValueError):drafts.read(self.service,self.job['id'],'../../')

    def test_http_review_save_preview_and_zip(self):
        with patch.object(server,'generation',return_value=self.service):
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            base=f'http://127.0.0.1:{http.server_port}/api/jobs/{self.job["id"]}'
            def post(action,data):return urlopen(Request(base+'/'+action,json.dumps(data).encode(),{'Content-Type':'application/json'}))
            try:
                with urlopen(base+'/drafts/'+self.run) as response:draft=json.load(response)
                draft['coverLetter']='HTTP-reviewed letter'
                data={'runId':self.run,'revision':draft['revision'],'draft':draft}
                with post('preview-drafts',data) as response:self.assertIn('HTTP-reviewed',json.load(response)['coverLetter'])
                self.renderer.assert_not_called()
                with patch.object(drafts, 'pdf_pages', return_value={'pageCount':1,'pages':[]}):
                    with post('preview-drafts',{**data,'document':'coverLetter'}) as response:
                        self.assertEqual(json.load(response)['pageCount'],1)
                self.assertIn('HTTP-reviewed',self.renderer.call_args.args[0])
                with post('save-drafts',data) as response:saved=json.load(response)
                with post('download-application',{'runId':self.run,'revision':saved['revision']}) as response:
                    self.assertEqual(response.headers['Content-Type'],'application/zip')
                    self.assertEqual(len(zipfile.ZipFile(io.BytesIO(response.read())).namelist()),3)
                with self.assertRaises(HTTPError) as error:post('save-drafts',data)
                self.assertEqual(error.exception.code,409)
            finally:http.shutdown();http.server_close()


if __name__=='__main__':unittest.main()
