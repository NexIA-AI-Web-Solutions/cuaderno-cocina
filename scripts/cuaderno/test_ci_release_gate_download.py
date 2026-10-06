"""Download transport must identify its client and retain exact artifact hashes."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from scripts.cuaderno.ci_release_gate import download


PAYLOAD = b'fixed synthetic scanner artifact\n'


class DownloadTransportTests(unittest.TestCase):
    def setUp(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get('User-Agent') != 'cuaderno-ci-audit/1.0':
                    self.send_error(403)
                    return
                self.send_response(200)
                self.send_header('Content-Length', str(len(PAYLOAD)))
                self.end_headers()
                self.wfile.write(PAYLOAD)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.directory = tempfile.TemporaryDirectory(prefix='cuaderno-download-test-')
        self.destination = Path(self.directory.name) / 'artifact'
        self.url = f'http://127.0.0.1:{self.server.server_port}/artifact'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.directory.cleanup()

    def test_identifies_client_and_accepts_only_exact_bytes(self):
        download(self.url, self.destination, hashlib.sha256(PAYLOAD).hexdigest())
        self.assertEqual(self.destination.read_bytes(), PAYLOAD)

    def test_transport_success_does_not_bypass_hash_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'no coincide con su pin'):
            download(self.url, self.destination, '0' * 64)


if __name__ == '__main__':
    unittest.main()
