#!/usr/bin/env python3
"""Loopback-only resume editor. PDF rendering uses the local Chrome browser."""
import argparse, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
from versions import Store, LOCK, validate as validate_version, project
STORE = Store(ROOT.parent)
from jobs import JobStore, DuplicateJob
JOBS = JobStore(ROOT.parent)
_generation_services = {}
def generation():
    from generation import GenerationService
    with LOCK:
        key=(id(JOBS),id(STORE))
        if key not in _generation_services:_generation_services[key]=GenerationService(JOBS,STORE)
        return _generation_services[key]
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

from render import html_doc, pdf, pdf_preview

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
            elif self.path in ('/jobs', '/jobs/'):
                self.respond(200,(ROOT/'jobs.html').read_bytes(),'text/html; charset=utf-8')
            elif self.path in ('/jobs.js', '/jobs.css', '/application-review.js'):
                self.respond(200,(ROOT/self.path[1:]).read_bytes(),'text/javascript; charset=utf-8' if self.path.endswith('.js') else 'text/css; charset=utf-8')
            elif self.path=='/api/jobs':
                self.respond(200,json.dumps({'jobs':[{**job,'generation':generation().state(job['id'])} for job in JOBS.list()]}))
            elif self.path.startswith('/api/jobs/') and '/drafts/' in self.path:
                import application_drafts
                parts=self.path.strip('/').split('/')
                if len(parts)!=5 or parts[3]!='drafts':raise ValueError('Invalid draft URL.')
                self.respond(200,json.dumps(application_drafts.read(generation(),parts[2],parts[4])))
            elif self.path.startswith('/api/jobs/') and '/files/' in self.path:
                parts=self.path.strip('/').split('/')
                if len(parts)!=6 or parts[3]!='files':raise ValueError('Invalid document URL.')
                body,mime,filename=generation().download(parts[2],parts[4],parts[5])
                self.respond(200,body,mime,filename)
            elif self.path=='/app.js': self.respond(200,(ROOT/'app.js').read_bytes(),'text/javascript; charset=utf-8')
            elif self.path=='/api/resume':
                with LOCK:self.respond(200,json.dumps(STORE.load()))
            else:self.respond(404,'{}')
        except FileNotFoundError:self.respond(404,json.dumps({'error':'This file is not ready or does not exist.'}))
        except Exception as e:self.respond(400,json.dumps({'error':str(e)}))
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host',''):raise ValueError('Cross-origin requests are not allowed.')
            if not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('JSON required.')
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=5_000_000:raise ValueError('Request must be under 5 MB.')
            request=json.loads(self.rfile.read(length))
            if not isinstance(request,dict):raise ValueError('Request must be an object.')
            if self.path.startswith('/api/jobs/') and self.path.rsplit('/',1)[-1] in ('save-drafts','preview-drafts','download-application'):
                import application_drafts
                parts=self.path.strip('/').split('/')
                if len(parts)!=4:raise ValueError('Invalid draft action URL.')
                identifier,action=parts[2],parts[3]
                service=generation();run_id=request.get('runId')
                if action=='download-application':
                    body,filename=application_drafts.bundle(service,identifier,run_id,request.get('revision'))
                    self.respond(200,body,'application/zip',filename)
                elif action=='save-drafts':
                    result=application_drafts.save(service,identifier,run_id,request.get('draft'),request.get('revision'))
                    self.respond(200,json.dumps(result))
                else:self.respond(200,json.dumps(application_drafts.preview(service,identifier,run_id,request.get('draft'),request.get('document'))))
                return
            if self.path.startswith('/api/jobs/') and self.path.rsplit('/',1)[-1] in ('generate','cancel'):
                parts=self.path.strip('/').split('/')
                if len(parts)!=4:raise ValueError('Invalid generation URL.')
                identifier=parts[2]
                result=generation().cancel(identifier) if parts[3]=='cancel' else generation().start(identifier,request.get('sourceText',''),request.get('regenerate') is True)
                self.respond(202,json.dumps(result));return
            if self.path=='/api/jobs' or self.path.startswith('/api/jobs/'):
                identifier=None if self.path=='/api/jobs' else self.path[len('/api/jobs/'):]
                job=request.get('job')
                auto=not identifier and request.get('generate') is not False
                if auto and isinstance(job,dict):
                    job={**job,'company':job.get('company') or 'Pending extraction','title':job.get('title') or 'New application'}
                result=JOBS.save(job,identifier,request.get('revision'),request.get('allowDuplicate') is True)
                if auto:
                    try:result['generation']=generation().start(result['id'],request.get('sourceText',''))
                    except Exception as error:
                        result['generation']={'status':'failed','files':[],'message':str(error)}
                        JOBS.write(JOBS.path(result['id']).parent/'generation.json',result['generation'])
                else:result['generation']=generation().state(result['id'])
                self.respond(200 if identifier else 201,json.dumps(result));return
            data=request['data'];state=request.get('state');active=request.get('active','master')
            validate_version(data,state)
            if self.path=='/api/save':
                result=STORE.save(data,state,request.get('revision'),active)
                self.respond(200,json.dumps(result));return
            selected,levels=project(data,state,active)
            if self.path=='/api/preview':self.respond(200,html_doc(selected,levels),'text/html; charset=utf-8')
            elif self.path=='/api/preview/pdf':self.respond(200,json.dumps(pdf_preview(selected,levels)))
            elif self.path.startswith('/api/export/'):
                kind=self.path.rsplit('/',1)[1]
                content,mime={'json':(lambda:json.dumps(selected,ensure_ascii=False,indent=2)+'\n','application/json'),'md':(lambda:markdown(selected,levels),'text/markdown; charset=utf-8'),'html':(lambda:html_doc(selected,levels),'text/html; charset=utf-8'),'pdf':(lambda:pdf(selected,levels),'application/pdf')}[kind]
                name='resume' if active=='master' else 'resume-'+active
                self.respond(200,content(),mime,name+'.'+kind)
            else:self.respond(404,'{}')
        except DuplicateJob as e:self.respond(409,json.dumps({'error':str(e),'duplicates':[{'id':j['id'],'company':j['company'],'title':j['title']} for j in e.jobs]}))
        except FileExistsError as e:self.respond(409,json.dumps({'error':str(e)}))
        except FileNotFoundError:self.respond(404,json.dumps({'error':'Job not found. Reload the board.'}))
        except Exception as e:self.respond(400,json.dumps({'error':str(e)}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    STORE.initialize()
    with ThreadingHTTPServer(('127.0.0.1',args.port),Handler) as http:
        print(f'Resume editor: http://127.0.0.1:{args.port}',flush=True);http.serve_forever()
