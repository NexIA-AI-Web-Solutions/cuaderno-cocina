from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
BASE=Path(__file__).resolve().parent/'generated'
class Preview(SimpleHTTPRequestHandler):
 def translate_path(self,path):
  from urllib.parse import urlsplit,unquote
  path=unquote(urlsplit(path).path).removeprefix('/cuaderno-cocina/video').lstrip('/') or 'index.html'
  if '..' in Path(path).parts:return str(BASE/'missing')
  p=BASE/path
  return str(p if p.exists() else Path('/var/www/cuaderno-promo')/path)
ThreadingHTTPServer(('127.0.0.1',18879),Preview).serve_forever()
