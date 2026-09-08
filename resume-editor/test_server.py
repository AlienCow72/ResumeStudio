import json, tempfile, threading, unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import server

class EditorTests(unittest.TestCase):
    def test_save_backup_conflict_and_exports(self):
        original_root, original_source = server.ROOT, server.SOURCE
        with tempfile.TemporaryDirectory() as directory:
            server.ROOT = Path(directory)
            server.SOURCE = server.ROOT / 'resume.json'
            initial = {'basics': {'name': 'Original'}, 'custom': [{'name': 'Preserved'}]}
            server.SOURCE.write_text(json.dumps(initial))
            http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            def post(path, data, revision):
                req = Request(f'http://127.0.0.1:{http.server_port}/api/{path}', json.dumps({'data':data,'revision':revision}).encode(), {'Content-Type':'application/json'})
                return urlopen(req)
            try:
                revision = server.revision()
                changed = {**initial, 'basics':{'name':'Updated'}}
                for kind in ['json', 'md', 'html', 'pdf']:
                    body = post('export/'+kind, changed, revision).read()
                    self.assertTrue(body)
                    if kind=='pdf': self.assertTrue(body.startswith(b'%PDF'))
                self.assertEqual(json.loads(server.SOURCE.read_text()), initial)
                post('save', changed, revision).close()
                self.assertEqual(json.loads(server.SOURCE.read_text()), changed)
                self.assertEqual(json.loads(next((server.ROOT/'backups').iterdir()).read_text()), initial)
                with self.assertRaises(HTTPError) as e: post('save', initial, revision)
                self.assertEqual(e.exception.code, 409)
                with self.assertRaises(HTTPError): post('export/json', {'work':'invalid'}, revision)
                self.assertEqual(json.loads(server.SOURCE.read_text()), changed)
            finally:
                http.shutdown(); http.server_close()
                server.ROOT, server.SOURCE = original_root, original_source

if __name__ == '__main__': unittest.main()
