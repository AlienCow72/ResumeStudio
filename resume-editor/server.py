#!/usr/bin/env python3
"""Loopback-only resume editor. PDF rendering uses the local Chrome browser."""
import argparse, hashlib, html, io, json, os, shutil, tempfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'resume.json'
TITLES = {'work':'Experience', 'education':'Education', 'basics':'Profile', 'volunteer':'Volunteering'}
def label(s):
    import re
    return TITLES.get(s, re.sub(r'([a-z])([A-Z])', r'\1 \2', s).replace('_',' ').title())
def validate(data):
    if not isinstance(data, dict): raise ValueError('Resume must be a JSON object.')
    if 'basics' in data and not isinstance(data['basics'], dict): raise ValueError('basics must be an object.')
    for key in ['work','education','skills','volunteer','projects','awards','certificates','publications','languages','interests','references']:
        if key in data and (not isinstance(data[key], list) or any(not isinstance(x,dict) for x in data[key])):
            raise ValueError(key + ' must be an array of objects.')
    return data

def flat(value):
    if isinstance(value, dict): return ' · '.join(str(v) for v in value.values() if v and not isinstance(v,(list,dict)))
    if isinstance(value,list): return ', '.join(flat(v) for v in value)
    return str(value)

def blocks(data):
    b = data.get('basics', {})
    out = [('h1', b.get('name','Resume'))]
    if b.get('label'): out.append(('subtitle',b['label']))
    contact = [flat(b[k]) for k in ['email','phone','url','location'] if b.get(k)]
    if contact: out.append(('contact',' · '.join(contact)))
    for p in b.get('profiles',[]): out.append(('contact',flat(p)))
    if b.get('summary'): out.extend([('h2','Profile'),('p',b['summary'])])
    for k,v in b.items():
        if k not in ['name','label','email','phone','url','location','profiles','summary','image'] and v: out.append(('p',label(k)+': '+flat(v)))
    for section, entries in data.items():
        if section in ['basics','meta','$schema'] or not entries: continue
        out.append(('h2',label(section)))
        if not isinstance(entries,list): entries=[entries]
        for e in entries:
            if not isinstance(e,dict): out.append(('p',flat(e))); continue
            titlekeys=[k for k in ['position','name','institution','title','organization','language'] if e.get(k)]
            if titlekeys: out.append(('h3',' | '.join(str(e[k]) for k in titlekeys)))
            dates=' – '.join(str(e[k]) for k in ['startDate','endDate'] if e.get(k))
            if e.get('startDate') and not e.get('endDate') and section in ['work','volunteer']: dates+=' – Present'
            if dates: out.append(('contact',dates))
            for k,v in e.items():
                if k in titlekeys+['startDate','endDate'] or not v: continue
                if k in ['highlights','courses'] and isinstance(v,list): out.extend(('li',flat(x)) for x in v)
                elif k in ['summary','description','reference']: out.append(('p',flat(v)))
                else: out.append(('p',label(k)+': '+flat(v)))
    return out

from render import html_doc, pdf

def markdown(data):
    return '\n\n'.join({'h1':'# ','h2':'## ','h3':'### ','li':'- '}.get(k,'')+str(v).replace('<','&lt;') for k,v in blocks(data))+'\n'
def revision(): return hashlib.sha256(SOURCE.read_bytes()).hexdigest()
class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, mime='application/json', filename=None):
        if not isinstance(body,bytes): body=body.encode()
        self.send_response(status); self.send_header('Content-Type',mime); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store')
        if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path=='/': self.respond(200,(ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
        elif self.path=='/api/resume': self.respond(200,json.dumps({'data':json.loads(SOURCE.read_text()),'revision':revision()}))
        else: self.respond(404,'{}')
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host',''): raise ValueError('Cross-origin requests are not allowed.')
            if not self.headers.get('Content-Type','').startswith('application/json'): raise ValueError('JSON required.')
            length=int(self.headers.get('Content-Length',0))
            if length>2_000_000: raise ValueError('Resume exceeds 2 MB limit.')
            request=json.loads(self.rfile.read(length)); data=validate(request['data'])
            if self.path=='/api/save':
                if request.get('revision')!=revision(): self.respond(409,json.dumps({'error':'resume.json changed on disk. Reload the page before saving; export your draft first.'})); return
                backup=ROOT/'backups'; backup.mkdir(exist_ok=True)
                shutil.copy2(SOURCE,backup/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json'))
                fd,tmp=tempfile.mkstemp(dir=SOURCE.parent)
                with os.fdopen(fd,'w') as f: json.dump(data,f,ensure_ascii=False,indent=2); f.write('\n')
                os.replace(tmp,SOURCE)
                self.respond(200,json.dumps({'revision':revision()}))
            elif self.path=='/api/preview': self.respond(200,html_doc(data),'text/html; charset=utf-8')
            elif self.path.startswith('/api/export/'):
                kind=self.path.rsplit('/',1)[1]
                content,mime={'json':(lambda:json.dumps(data,ensure_ascii=False,indent=2)+'\n','application/json'),'md':(lambda:markdown(data),'text/markdown; charset=utf-8'),'html':(lambda:html_doc(data),'text/html; charset=utf-8'),'pdf':(lambda:pdf(data),'application/pdf')}[kind]
                self.respond(200,content(),mime,'resume.'+kind)
            else: self.respond(404,'{}')
        except Exception as e: self.respond(400,json.dumps({'error':str(e)}))
if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8765); args=parser.parse_args()
    print(f'Resume editor: http://127.0.0.1:{args.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
