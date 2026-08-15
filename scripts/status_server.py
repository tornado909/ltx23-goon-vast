#!/usr/bin/env python3
import html, http.server, os, pathlib, socketserver
PORT=int(os.environ.get('STATUS_PORT','18188'))
LOG=pathlib.Path(os.environ.get('STATUS_LOG','/var/log/portal/ltx-suite.log'))
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try: text=LOG.read_text(errors='replace')[-16000:]
        except Exception as e: text=str(e)
        body=f'''<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="5"><title>LTX Suite bootstrap</title><style>body{{font:15px system-ui;background:#111;color:#eee;margin:32px}}pre{{white-space:pre-wrap;background:#1b1b1b;padding:18px;border-radius:12px}}.ok{{color:#7ee787}}</style></head><body><h2>LTX 2.3 / Goon Machine — Vast bootstrap</h2><p>Модели и сервисы готовятся автоматически. Страница обновляется каждые 5 секунд. Когда ComfyUI будет готов, этот адрес автоматически переключится на его интерфейс.</p><pre>{html.escape(text)}</pre></body></html>'''.encode()
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*a): pass
class S(socketserver.TCPServer): allow_reuse_address=True
with S(('127.0.0.1',PORT),H) as s: s.serve_forever()
