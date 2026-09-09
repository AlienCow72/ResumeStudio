"""Master storage and version projections. IDs and formatting never enter resume JSON."""
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path

LOCK = threading.RLock()

def encoded(value): return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()
def uid(): return uuid.uuid4().hex

def tree(value):
    node={'id':uid()}
    if isinstance(value,dict): node['children']={k:tree(v) for k,v in value.items()}
    elif isinstance(value,list): node['children']=[tree(v) for v in value]
    return node

def check_tree(value,node,seen=None):
    seen=set() if seen is None else seen
    if not isinstance(node,dict) or not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',str(node.get('id',''))) or node['id'] in seen: raise ValueError('Invalid or duplicate item ID. Reload the editor.')
    seen.add(node['id'])
    children=node.get('children')
    if isinstance(value,dict):
        if not isinstance(children,dict) or set(value)!=set(children): raise ValueError('Field IDs do not match master data.')
        for k,v in value.items(): check_tree(v,children[k],seen)
    elif isinstance(value,list):
        if not isinstance(children,list) or len(value)!=len(children): raise ValueError('Entry IDs do not match master data.')
        for v,n in zip(value,children): check_tree(v,n,seen)
    return seen

def validate(data,state):
    if not isinstance(data,dict): raise ValueError('Master must be a JSON object.')
    if 'basics' in data and not isinstance(data['basics'],dict): raise ValueError('basics must be an object.')
    for k in ['work','skills','education','projects','volunteer','awards','certificates','publications','languages','interests','references']:
        if k in data and (not isinstance(data[k],list) or any(not isinstance(v,dict) for v in data[k])):raise ValueError(k+' must be an array of objects.')
    def strings(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if k in {'highlights','keywords','courses','roles'} and (not isinstance(x,list) or any(not isinstance(y,str) for y in x)):raise ValueError(k+' must contain strings.')
                strings(x)
        elif isinstance(v,list):
            for x in v:strings(x)
    strings(data)
    if not isinstance(state,dict) or state.get('schemaVersion')!=1:raise ValueError('Refresh the editor to load the new versions workflow.')
    check_tree(data,state['tree'])
    names=set(); identifiers=set()
    for version in state['versions']:
        if not isinstance(version,dict):raise ValueError('Invalid version.')
        ident=version.get('id',''); name=version.get('name','')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',ident) or len(ident)>60 or ident=='master' or ident in identifiers:raise ValueError('Version IDs must be unique lowercase names with hyphens.')
        if not isinstance(name,str) or not name.strip() or len(name)>80 or name.casefold() in names:raise ValueError('Version names must be unique and 1–80 characters.')
        identifiers.add(ident); names.add(name.casefold())
        if not isinstance(version.get('excluded',[]),list) or any(not isinstance(x,str) for x in version.get('excluded',[])):raise ValueError('Invalid selections.')
        if not isinstance(version.get('indent',{}),dict) or any(type(x)!=int or not 0<=x<=3 for x in version.get('indent',{}).values()):raise ValueError('Indentation must be between 0 and 3.')
        if 'summaryOverride' in version and not isinstance(version['summaryOverride'],str):raise ValueError('Summary must be text.')
    return data,state

def project(data,state,active='master'):
    version=next((v for v in state['versions'] if v['id']==active),None)
    if active!='master' and version is None:raise ValueError('Unknown version.')
    version=version or {}; excluded=set(version.get('excluded',[])); levels={}
    def visit(value,node,path):
        if node['id'] in excluded:return None
        if path==('basics','summary') and 'summaryOverride' in version:value=version['summaryOverride']
        if isinstance(value,dict):
            result={}
            for k,v in value.items():
                item=visit(v,node['children'][k],path+(k,))
                if item is not None:result[k]=item
            if len(path)==2 and path[0] in {'work','volunteer'} and value.get('endDate') and not result.get('endDate'):
                levels['/'.join(map(str,path))+'/hidePresent']=True
            return result or None
        if isinstance(value,list):
            result=[]; indents=[]
            for v,n in zip(value,node['children']):
                item=visit(v,n,path+(len(result),))
                if item is not None:
                    result.append(item)
                    desired=version.get('indent',{}).get(n['id'],0)
                    # Excluding a parent bullet must never create an orphaned nested list.
                    indents.append(min(desired,indents[-1]+1) if indents else 0)
            if path and path[-1]=='highlights':levels['/'.join(map(str,path))]=indents
            return result or None
        return value if value!='' else None
    result=visit(data,state['tree'],()) or {}
    # Permit an override when the master has no summary yet.
    if 'summaryOverride' in version and 'summary' not in data.get('basics',{}):
        basics=state['tree'].get('children',{}).get('basics',{})
        if basics.get('id') not in excluded and str(basics.get('id'))+'-summary' not in excluded and version['summaryOverride']:result.setdefault('basics',{})['summary']=version['summaryOverride']
    return result,levels

class Store:
    def __init__(self,root):self.root=Path(root);self.source=self.root/'resume.json';self.settings=self.root/'versions.json'
    def initialize(self):
        with LOCK:
            if not self.source.exists():shutil.copy2(self.root.parent/'resume.json',self.source)
            if not self.settings.exists():
                data=json.loads(self.source.read_text())
                self.write(self.settings,encoded({'schemaVersion':1,'tree':tree(data),'versions':[],'masterHash':hashlib.sha256(self.source.read_bytes()).hexdigest()}))
    def write(self,path,body):
        fd,name=tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
            os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)
    def revision(self):return hashlib.sha256(self.source.read_bytes()+b'\0'+self.settings.read_bytes()).hexdigest()
    def load(self):
        self.initialize()
        data=json.loads(self.source.read_text());state=json.loads(self.settings.read_text())
        # Never guess new ID mappings after external structural changes.
        warning=''
        if state.get('masterHash')!=hashlib.sha256(self.source.read_bytes()).hexdigest():
            raise ValueError('Master changed outside the editor. Restore resume.json and versions.json from the same backup, or re-import your changes through the master editor to preserve version IDs.')
        validate(data,state)
        return {'data':data,'state':state,'revision':self.revision(),'warning':warning}
    def save(self,data,state,expected,active):
        with LOCK:
            old=self.load()
            if expected!=old['revision']:raise FileExistsError('Files changed on disk. Export your draft, then reload before saving.')
            validate(data,state)
            if active!='master' and not any(v['id']==active for v in state['versions']):raise ValueError('Unknown version.')
            if active!='master' and (data!=old['data'] or state['tree']!=old['state']['tree']):raise ValueError('Edit master content in Master, then save before switching versions.')
            payload=encoded(data);state=copy.deepcopy(state);state['masterHash']=hashlib.sha256(payload).hexdigest()
            writes={self.source:payload,self.settings:encoded(state)}
            for v in state['versions']:writes[self.root/f'resume-{v["id"]}.json']=encoded(project(data,state,v['id'])[0])
            removed={self.root/f'resume-{v["id"]}.json' for v in old['state']['versions']}-{p for p in writes}
            previous={p:p.read_bytes() if p.exists() else None for p in set(writes)|removed}
            backup=self.root/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f');backup.mkdir(parents=True)
            for p,body in previous.items():
                if body is not None:(backup/p.name).write_bytes(body)
            try:
                for p,body in writes.items():self.write(p,body)
                for p in removed:p.unlink(missing_ok=True)
            except Exception:
                for p,body in previous.items():
                    if body is None:p.unlink(missing_ok=True)
                    else:self.write(p,body)
                raise
            return self.load()
