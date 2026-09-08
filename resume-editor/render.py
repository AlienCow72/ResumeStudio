"""Reference resume.html theme shared by preview, HTML, and browser PDF."""
import html
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime

ROOT = Path(__file__).resolve().parent

def esc(v): return html.escape(str(v)).replace('\n', '<br>')
def text(v):
    if isinstance(v, list): return ', '.join(text(x) for x in v)
    if isinstance(v, dict): return ' · '.join(text(x) for x in v.values() if x)
    return str(v)
def date(value):
    try:
        if len(value)==7: return datetime.strptime(value,'%Y-%m').strftime('%b %Y')
        if len(value)==10: return datetime.strptime(value,'%Y-%m-%d').strftime('%b %d, %Y')
    except (ValueError,TypeError): pass
    return value
def dates(e, ongoing=False):
    start,end=e.get('startDate'),e.get('endDate')
    return '–'.join(esc(date(v)) for v in [start,end or ('Present' if start and ongoing else None)] if v)
def heading(title, body): return '<section><h2>'+esc(title)+'</h2>'+body+'</section>' if body else ''
def extras(e,used):
    return ''.join('<p>'+esc(k)+': '+esc(text(v))+'</p>' for k,v in e.items() if k not in used and v)
def role(e,ongoing=False):
    position=e.get('position') or e.get('title') or e.get('name','')
    company=e.get('name') if e.get('position') else e.get('organization','')
    out='<article class="role"><div class="role-head"><div><h3>'+esc(position)+'</h3>'
    if company: out+='<p class="company">'+esc(company)+'</p>'
    out+='</div><p class="date">'+dates(e,ongoing)+'</p>'
    if e.get('location'): out+='<p class="location">'+esc(e['location'])+'</p>'
    out+='</div>'
    for k in ['summary','description','reference']:
        if e.get(k):out+='<p class="role-summary">'+esc(e[k])+'</p>'
    if e.get('highlights'):out+='<ul>'+''.join('<li>'+esc(x)+'</li>' for x in e['highlights'])+'</ul>'
    out+=extras(e,{'position','title','name','organization','startDate','endDate','location','summary','description','reference','highlights'})
    return out+'</article>'

def html_doc(data):
    b=data.get('basics',{})
    location=b.get('location',{})
    contact=[]
    if location: contact.append(esc(', '.join(str(location[k]) for k in ['address','city','region','postalCode'] if location.get(k)) or text(location)))
    for k in ['phone','email','url']:
        if b.get(k):contact.append(esc(b[k]))
    contact.extend(esc(text(p)) for p in b.get('profiles',[]))
    header='<header><div><h1>'+esc(b.get('name','Resume'))+'</h1>'
    if b.get('label'):header+='<p class="title">'+esc(b['label'])+'</p>'
    header+='</div><address class="contact">'+'<br>'.join(contact)+'</address></header>'
    skills=''
    for e in data.get('skills',[]):
        skills+='<div class="skill-group"><h3>'+esc(e.get('name',''))+'</h3><div class="tags">'+''.join('<span class="tag">'+esc(x)+'</span>' for x in e.get('keywords',[]))+'</div>'+extras(e,{'name','keywords'})+'</div>'
    education=''
    for e in data.get('education',[]):
        education+='<div class="education"><h3>'+esc(e.get('institution',''))+'</h3><p>'+esc(', '.join(e[k] for k in ['studyType','area'] if e.get(k)))+'<br>'+dates(e)+'</p>'+extras(e,{'institution','studyType','area','startDate','endDate'})+'</div>'
    aside=heading('Education',education)+heading('Skills',skills)
    main=heading('Profile','<p class="summary">'+esc(b['summary'])+'</p>' if b.get('summary') else '')
    main+=extras(b,{'name','label','location','phone','email','url','profiles','summary','image'})
    for key,entries in data.items():
        if key in {'basics','skills','education','meta','$schema'} or not entries:continue
        title={'work':'Experience','volunteer':'Volunteering'}.get(key,key.title())
        if not isinstance(entries,list):entries=[entries]
        main+=heading(title,''.join(role(e,key in {'work','volunteer'}) if isinstance(e,dict) else '<p>'+esc(text(e))+'</p>' for e in entries))
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+esc(b.get('name','Resume'))+' — Resume</title><style>'+(ROOT/'resume.css').read_text()+'</style></head><body><article class="page">'+header+'<div class="content"><aside>'+aside+'</aside><main>'+main+'</main></div></article></body></html>'

def pdf(data):
    chrome=os.environ.get('RESUME_CHROME') or shutil.which('google-chrome') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file():raise RuntimeError('PDF export requires Google Chrome. Install Chrome or set RESUME_CHROME to its executable.')
    with tempfile.TemporaryDirectory(prefix='resume-pdf-') as folder:
        root=Path(folder); source=root/'resume.html'; output=root/'resume.pdf'
        source.write_text(html_doc(data))
        node=shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')
        result=subprocess.run([node,str(ROOT/'pdf.cjs'),str(source),str(output),chrome],capture_output=True,timeout=60)
        if result.returncode or not output.exists():raise RuntimeError('PDF rendering failed: '+result.stderr.decode(errors='replace')[-500:])
        return output.read_bytes()
