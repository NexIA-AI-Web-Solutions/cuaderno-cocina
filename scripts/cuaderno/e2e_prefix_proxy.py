"""CI-only loopback TLS ingress matching the production prefix/forwarding contract."""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import ssl

PREFIX = '/cuaderno-cocina/'


class PrefixHandler(BaseHTTPRequestHandler):
    def handle_request(self):
        if not self.path.startswith(PREFIX):
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', '0'))
        if length < 0 or length > 54525952:
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else None
        headers = {key: value for key, value in self.headers.items()
                   if key.lower() not in {'connection', 'host', 'transfer-encoding'}
                   and not key.lower().startswith('x-forwarded-')
                   and key.lower() not in {'x-script-name', 'x-scheme'}}
        headers.update({'Host': '127.0.0.1:18443', 'X-Forwarded-Host': '127.0.0.1:18443',
                        'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '127.0.0.1',
                        'X-Script-Name': '/cuaderno-cocina'})
        backend = http.client.HTTPConnection('127.0.0.1', 18081, timeout=30)
        try:
            backend.request(self.command, '/' + self.path[len(PREFIX):], body, headers)
            response = backend.getresponse()
            payload = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in {'connection', 'transfer-encoding', 'content-length'}:
                    self.send_header(key, value)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(payload)
        finally:
            backend.close()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = handle_request

    def log_message(self, *_args):
        pass  # URLs/cookies/credentials never enter CI artifacts.


def main():
    if os.environ.get('CI') != 'true' and os.environ.get('CI') != '1':
        raise SystemExit('Este proxy se limita al runner CI aislado.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--cert', required=True)
    parser.add_argument('--key', required=True)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', 18443), PrefixHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.cert, args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
