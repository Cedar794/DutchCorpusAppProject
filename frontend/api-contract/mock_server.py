#!/usr/bin/env python3
"""Local-only replay of captured API responses; no model or database connection."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs,urlparse

ROOT=Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass

    def send(self,status,body,headers=None):
        content=json.dumps(body,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        for key,value in (headers or {}).items():
            if key.lower() not in ('content-length','connection'): self.send_header(key,value)
        if not any(k.lower()=='content-type' for k in (headers or {})): self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Expose-Headers','Retry-After, X-Mock-Scenario')
        self.end_headers();self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type, X-Mock-Scenario')
        self.end_headers()

    def do_GET(self): self.replay()
    def do_POST(self): self.replay()

    def replay(self):
        parsed=urlparse(self.path)
        if parsed.path=='/__mock__/scenarios':
            return self.send(200,json.loads((ROOT/'mock/manifest.json').read_text()))
        # Static schema/fixture files are helpful for Swagger and design tools.
        if self.command=='GET' and (parsed.path.startswith('/mock/') or parsed.path in
                ('/openapi.json','/openapi.yaml','/API_SPEC.md','/README.md','/types.ts')):
            candidate=(ROOT/parsed.path.lstrip('/')).resolve()
            if candidate.is_relative_to(ROOT) and candidate.is_file():
                content=candidate.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','application/json' if candidate.suffix=='.json' else 'text/plain; charset=utf-8')
                self.send_header('Content-Length',str(len(content)))
                self.send_header('Access-Control-Allow-Origin','*')
                self.end_headers();self.wfile.write(content);return
        length=int(self.headers.get('Content-Length','0'))
        if length>65536: return self.send(413,{'detail':'Mock replay body exceeds 64 KiB'})
        raw=self.rfile.read(length) if length else b''
        try: body=json.loads(raw) if raw else None
        except ValueError: body=None
        manifest=json.loads((ROOT/'mock/manifest.json').read_text())
        selected=self.headers.get('X-Mock-Scenario')
        if selected:
            candidates=[s for s in manifest['scenarios'] if s['id']==selected]
        else:
            query={k:v[-1] for k,v in parse_qs(parsed.query,keep_blank_values=True).items()}
            defaults={}
            if parsed.path=='/lookup': defaults={'limit':'5'}
            elif parsed.path=='/suggest': defaults={'limit':'10'}
            elif parsed.path.startswith('/entries/'):
                defaults={key:str(value) for key,value in dict(sense_offset=0,sense_limit=20,
                    form_offset=0,form_limit=50,example_offset=0,example_limit=5,
                    expression_offset=0,expression_limit=20).items()}
            elif parsed.path.startswith('/senses/'): defaults={'offset':'0','limit':'10'}
            def matches(s):
                request=s['request']
                if request['method']!=self.command or request['path']!=parsed.path: return False
                if {**defaults,**{k:str(v) for k,v in request.get('query',{}).items()}}!={**defaults,**query}: return False
                if self.command=='POST':
                    if request.get('raw_body_description'): return len(raw)==8193
                    recorded=dict(request.get('json') or {})
                    actual=dict(body or {}) if isinstance(body,dict) else None
                    if parsed.path=='/semantic-search' and actual is not None:
                        for value in (recorded,actual):
                            value.setdefault('limit',10);value.setdefault('include_related',True)
                    return recorded==actual
                return True
            candidates=[s for s in manifest['scenarios'] if matches(s)]
            candidates.sort(key=lambda s:(not s.get('default_replay',False),s['response']['status']!=200,s['id']))
        if not candidates:
            return self.send(501,{'detail':'No captured fixture matches this request. Use /__mock__/scenarios or X-Mock-Scenario.'})
        chosen=candidates[0]['response']
        headers={**chosen.get('headers',{}),'X-Mock-Scenario':candidates[0]['id']}
        self.send(chosen['status'],json.loads((ROOT/chosen['body_file']).read_text()),headers)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8799)
    options=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',options.port),Handler)
    print(f'Mock replay listening at http://127.0.0.1:{options.port}; Ctrl-C to stop',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
