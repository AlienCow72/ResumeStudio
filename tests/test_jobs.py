import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server
from jobs import DuplicateJob, JobStore


SAMPLE = {'company': 'Example', 'title': 'Platform Engineer',
          'url': 'https://example.com/jobs?id=123', 'notes': 'Follow up next week.'}


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = JobStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_persistence_history_backup_and_master_isolation(self):
        master = self.root / 'data' / 'resume.json'
        master.parent.mkdir()
        master.write_text('{"basics":{"name":"Original"}}')
        original = master.read_bytes()
        job = self.store.save(SAMPLE)
        self.assertEqual(job['stage'], 'applying')
        updated = self.store.save({'stage': 'waiting', 'appliedOn': '2026-09-15'}, job['id'], job['revision'])
        reloaded = JobStore(self.root).list()[0]
        self.assertEqual(updated, reloaded)
        self.assertEqual([item['to'] for item in reloaded['history']], ['applying', 'waiting'])
        edited = self.store.save({'notes': 'Interview next week'}, job['id'], updated['revision'])
        self.assertEqual(len(edited['history']), 2)
        self.assertEqual(edited['appliedOn'], '2026-09-15')
        self.assertEqual(master.read_bytes(), original)
        backups = list((self.store.path(job['id']).parent / 'backups').glob('*.json'))
        self.assertEqual(len(backups), 2)
        self.assertTrue(any(json.loads(path.read_text())['stage'] == 'applying' for path in backups))

    def test_duplicates_ignore_tracking_but_preserve_requisition(self):
        job = self.store.save(SAMPLE)
        with self.assertRaises(DuplicateJob):
            self.store.save({**SAMPLE, 'url': SAMPLE['url'] + '&utm_source=search#details'})
        self.store.save({**SAMPLE, 'url': 'https://example.com/jobs?id=124'})
        separate = self.store.save(SAMPLE, allow_duplicate=True)
        self.assertNotEqual(job['id'], separate['id'])
        self.store.save({'notes': 'Separate application'}, separate['id'], separate['revision'])
        self.assertEqual(len(self.store.list()), 3)

    def test_description_survives_reload_updates_and_can_be_cleared(self):
        text = '  Platform Engineer\n\nResponsibilities:\n• Build integrations.\n'
        job = self.store.save({**SAMPLE, 'sourceText': text})
        self.assertEqual(JobStore(self.root).read(job['id'])['sourceText'], text)
        updated = self.store.save({'stage': 'interview'}, job['id'], job['revision'])
        self.assertEqual(updated['sourceText'], text)
        cleared = self.store.save({'sourceText': ''}, job['id'], updated['revision'])
        self.assertEqual(JobStore(self.root).read(job['id'])['sourceText'], '')
        backups = (self.store.path(job['id']).parent / 'backups').glob('*.json')
        self.assertTrue(any(json.loads(path.read_text())['sourceText'] == text for path in backups))

    def test_invalid_inputs_and_path_traversal(self):
        for update in [{'url': 'javascript:alert(1)'}, {'url': 'https://user:pass@example.com'},
                       {'url': 'https://example.com:wrong'}, {'company': '  '}, {'title': []},
                       {'stage': 'offered'}, {'appliedOn': '2026-02-30'}, {'appliedOn': False},
                       {'notes': 'x' * 20001}, {'sourceText': None}, {'sourceText': 'x' * 120001}]:
            with self.subTest(update=list(update)):
                with self.assertRaises(ValueError):
                    self.store.save({**SAMPLE, **update})
        with self.assertRaises(ValueError):
            self.store.read('../../resume')
        self.assertEqual(self.store.list(), [])

    def test_stale_and_concurrent_saves(self):
        job = self.store.save(SAMPLE)
        outcomes = []
        def update(stage):
            try:
                self.store.save({'stage': stage}, job['id'], job['revision'])
                outcomes.append('saved')
            except FileExistsError:
                outcomes.append('conflict')
        threads = [threading.Thread(target=update, args=(stage,)) for stage in ['waiting', 'interview']]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertCountEqual(outcomes, ['saved', 'conflict'])

    def test_failed_replace_preserves_previous_record(self):
        job = self.store.save(SAMPLE)
        replace = os.replace
        def fail_record(source, destination):
            if destination == self.store.path(job['id']):
                raise OSError('Disk failure')
            replace(source, destination)
        with patch('jobs.os.replace', side_effect=fail_record):
            with self.assertRaises(OSError):
                self.store.save({'notes': 'Changed'}, job['id'], job['revision'])
        self.assertEqual(self.store.read(job['id']), job)

    def test_http_routes_errors_and_origin(self):
        with patch.object(server, 'JOBS', self.store):
            http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{http.server_port}'
            def post(path, body, origin=None):
                body = {**body, 'generate': False}
                headers = {'Content-Type': 'application/json'}
                if origin: headers['Origin'] = origin
                return urlopen(Request(base + path, json.dumps(body).encode(), headers))
            try:
                for path in ['/jobs', '/jobs.js', '/jobs.css']:
                    with urlopen(base + path) as response: self.assertEqual(response.status, 200)
                with post('/api/jobs', {'job': SAMPLE, 'sourceText': 'Original description\n'}) as response:
                    self.assertEqual(response.status, 201)
                    job = json.load(response)
                    self.assertEqual(job['sourceText'], 'Original description\n')
                with post('/api/jobs/' + job['id'], {'job': SAMPLE, 'revision': job['revision'], 'sourceText': 'Updated description\n'}) as response:
                    job = json.load(response)
                with urlopen(base + '/api/jobs') as response:
                    jobs = json.load(response)['jobs']
                    self.assertEqual(len(jobs), 1)
                    self.assertEqual(jobs[0]['sourceText'], 'Updated description\n')
                with post('/api/jobs', {'job': SAMPLE}) as response:
                    self.assertEqual(response.status,200)
                    self.assertEqual(json.load(response)['id'],job['id'])
                with post('/api/jobs/' + job['id'], {'job': {'stage': 'interview'}, 'revision': job['revision']}) as response:
                    self.assertEqual(json.load(response)['stage'], 'interview')
                with self.assertRaises(HTTPError) as error:
                    post('/api/jobs/' + job['id'], {'job': {'stage': 'waiting'}, 'revision': job['revision']})
                self.assertEqual(error.exception.code, 409)
                with self.assertRaises(HTTPError) as error:
                    post('/api/jobs', {'job': SAMPLE}, 'https://untrusted.example')
                self.assertEqual(error.exception.code, 400)
                with self.assertRaises(HTTPError) as error:
                    post('/api/jobs/' + '0' * 32, {'job': SAMPLE})
                self.assertEqual(error.exception.code, 404)
            finally:
                http.shutdown()
                http.server_close()


if __name__ == '__main__':
    unittest.main()
