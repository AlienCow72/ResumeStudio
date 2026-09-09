#!/usr/bin/env python3
"""Loopback-only resume editor. PDF rendering uses the local Chrome browser."""
import argparse, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'resume.json'
from versions import Store, LOCK, validate as validate_version, project
STORE = Store(ROOT)
TITLES = {'work':'Experience', 'education':'Education', 'basics':'Objective', 'volunteer':'Volunteering'}
def label(s):
    import re
    return TITLES.get(s, re.sub(r'([a-z])([A-Z])', r'\1 \2', s).replace('_',' ').title())
def flat(value):
    if isinstance(value, dict): return ' · '.join(str(v) for v in value.values() if v and not isinstance(v,(list,dict)))
    if isinstance(value,list): return ', '.join(flat(v) for v in value)
    return str(value)

def blocks(data, levels=None):
    levels=levels or {}
    b = data.get('basics', {})
    out = [('h1', b.get('name','Resume'))]
    if b.get('label'): out.append(('subtitle',b['label']))
    contact = [flat(b[k]) for k in ['email','phone','url','location'] if b.get(k)]
    if contact: out.append(('contact',' · '.join(contact)))
    for p in b.get('profiles',[]): out.append(('contact',flat(p)))
    if b.get('summary'): out.extend([('h2','Objective'),('p',b['summary'])])
    for k,v in b.items():
        if k not in ['name','label','email','phone','url','location','profiles','summary','image'] and v: out.append(('p',label(k)+': '+flat(v)))
    for section, entries in data.items():
        if section in ['basics','meta','$schema'] or not entries: continue
        out.append(('h2',label(section)))
        if not isinstance(entries,list): entries=[entries]
        for entry_index,e in enumerate(entries):
            if not isinstance(e,dict): out.append(('p',flat(e))); continue
            titlekeys=[k for k in ['position','name','institution','title','organization','language'] if e.get(k)]
            if titlekeys: out.append(('h3',' | '.join(str(e[k]) for k in titlekeys)))
            dates=' – '.join(str(e[k]) for k in ['startDate','endDate'] if e.get(k))
            if e.get('startDate') and not e.get('endDate') and section in ['work','volunteer'] and not levels.get(f'{section}/{entry_index}/hidePresent'): dates+=' – Present'
            if dates: out.append(('contact',dates))
            for k,v in e.items():
                if k in titlekeys+['startDate','endDate'] or not v: continue
                if k in ['highlights','courses'] and isinstance(v,list):
                    depths=levels.get(f'{section}/{entry_index}/{k}',[])
                    out.extend(('li'+str(depths[i] if i<len(depths) else 0),flat(x)) for i,x in enumerate(v))
                elif k in ['summary','description','reference']: out.append(('p',flat(v)))
                else: out.append(('p',label(k)+': '+flat(v)))
    return out

from render import html_doc, pdf

def markdown(data,levels=None):
    return '\n\n'.join(('  '*int(k[2:])+'- ' if k.startswith('li') else {'h1':'# ','h2':'## ','h3':'### '}.get(k,''))+str(v).replace('<','&lt;') for k,v in blocks(data,levels))+'\n'
class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, mime='application/json', filename=None):
        if not isinstance(body,bytes): body=body.encode()
        self.send_response(status); self.send_header('Content-Type',mime); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store')
        if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        try:
            if self.path=='/': self.respond(200,(ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
            elif self.path=='/app.js': self.respond(200,(ROOT/'app.js').read_bytes(),'text/javascript; charset=utf-8')
            elif self.path=='/api/resume':
                with LOCK:self.respond(200,json.dumps(STORE.load()))
            else:self.respond(404,'{}')
        except Exception as e:self.respond(400,json.dumps({'error':str(e)}))
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host',''):raise ValueError('Cross-origin requests are not allowed.')
            if not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('JSON required.')
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=5_000_000:raise ValueError('Request must be under 5 MB.')
            request=json.loads(self.rfile.read(length))
            data=request['data'];state=request.get('state');active=request.get('active','master')
            validate_version(data,state)
            if self.path=='/api/save':
                result=STORE.save(data,state,request.get('revision'),active)
                self.respond(200,json.dumps(result));return
            selected,levels=project(data,state,active)
            if self.path=='/api/preview':self.respond(200,html_doc(selected,levels),'text/html; charset=utf-8')
            elif self.path.startswith('/api/export/'):
                kind=self.path.rsplit('/',1)[1]
                content,mime={'json':(lambda:json.dumps(selected,ensure_ascii=False,indent=2)+'\n','application/json'),'md':(lambda:markdown(selected,levels),'text/markdown; charset=utf-8'),'html':(lambda:html_doc(selected,levels),'text/html; charset=utf-8'),'pdf':(lambda:pdf(selected,levels),'application/pdf')}[kind]
                name='resume' if active=='master' else 'resume-'+active
                self.respond(200,content(),mime,name+'.'+kind)
            else:self.respond(404,'{}')
        except FileExistsError as e:self.respond(409,json.dumps({'error':str(e)}))
        except Exception as e:self.respond(400,json.dumps({'error':str(e)}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    STORE.initialize()
    with ThreadingHTTPServer(('127.0.0.1',args.port),Handler) as http:
        print(f'Resume editor: http://127.0.0.1:{args.port}',flush=True);http.serve_forever()
