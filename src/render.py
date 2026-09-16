"""Reference resume.html theme shared by preview, HTML, and browser PDF."""
import html
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from string import Template
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
def role(e,ongoing=False,depths=None):
    position=e.get('position') or e.get('title') or e.get('name','')
    company=e.get('name') if e.get('position') else e.get('organization','')
    out='<article class="role"><div class="role-head"><div><h3>'+esc(position)+'</h3>'
    if company: out+='<p class="company">'+esc(company)+'</p>'
    out+='</div><div class="role-meta"><p class="date">'+dates(e,ongoing)+'</p>'
    if e.get('location'): out+='<p class="location">'+esc(e['location'])+'</p>'
    out+='</div></div>'
    for k in ['summary','description','reference']:
        if e.get(k):out+='<p class="role-summary">'+esc(e[k])+'</p>'
    if e.get('highlights'):out+=highlight_list(e['highlights'],depths or [])
    out+=extras(e,{'position','title','name','organization','startDate','endDate','location','summary','description','reference','highlights'})
    return out+'</article>'

def highlight_list(items,depths):
    result='<ul>';last=0
    for i,value in enumerate(items):
        depth=min(depths[i] if i<len(depths) else 0,last+1) if i else 0
        if i:
            if depth>last:result+='<ul>'
            else:result+='</li>'+('</ul></li>'*(last-depth))
        result+='<li>'+esc(value);last=depth
    return result+'</li>'+('</ul></li>'*last)+'</ul>'

def contact_html(b, include_profiles=True):
    """Escape contact details; each template chooses whether to show profiles."""
    location=b.get('location',{})
    contact=[]
    if location: contact.append(esc(', '.join(str(location[k]) for k in ['address','city','region','postalCode'] if location.get(k)) or text(location)))
    for k in ['phone','email','url']:
        if b.get(k):contact.append(esc(b[k]))
    if include_profiles:
        contact.extend(esc(text(p)) for p in b.get('profiles',[]))
    return '<br>'.join(contact)

def render_template(template_name, **values):
    template = Template((ROOT / 'templates' / template_name).read_text())
    return template.substitute(styles=(ROOT / 'resume.css').read_text(), **values)

def html_doc(data,levels=None):
    levels=levels or {}
    b=data.get('basics',{})
    skills=''
    for e in data.get('skills',[]):
        skills+='<div class="skill-group"><h3>'+esc(e.get('name',''))+'</h3><div class="tags">'+''.join('<span class="tag">'+esc(x)+'</span>' for x in e.get('keywords',[]))+'</div>'+extras(e,{'name','keywords'})+'</div>'
    education=''
    for e in data.get('education',[]):
        education+='<div class="education"><h3>'+esc(e.get('institution',''))+'</h3><p>'+esc(', '.join(e[k] for k in ['studyType','area'] if e.get(k)))+'<br>'+dates(e)+'</p>'+extras(e,{'institution','studyType','area','startDate','endDate'})+'</div>'
    aside=heading('Education',education)+heading('Skills',skills)
    main=heading('Objective','<p class="summary">'+esc(b['summary'])+'</p>' if b.get('summary') else '')
    main+=extras(b,{'name','label','location','phone','email','url','profiles','summary','image'})
    for key,entries in data.items():
        if key in {'basics','skills','education','meta','$schema'} or not entries:continue
        title={'work':'Experience','volunteer':'Volunteering'}.get(key,key.title())
        if not isinstance(entries,list):entries=[entries]
        main+=heading(title,''.join(role(e,key in {'work','volunteer'} and not levels.get(f'{key}/{i}/hidePresent'),levels.get(f'{key}/{i}/highlights',[])) if isinstance(e,dict) else '<p>'+esc(text(e))+'</p>' for i,e in enumerate(entries)))
    return render_template('resume.html', name=esc(b.get('name','Resume')),
                           label='<p class="title">'+esc(b['label'])+'</p>' if b.get('label') else '',
                           contact=contact_html(b), aside=aside, main=main)

def pdf(data,levels=None):
    return pdf_from_html(html_doc(data,levels))

def pdf_from_html(content):
    chrome=os.environ.get('RESUME_CHROME') or shutil.which('google-chrome') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file():raise RuntimeError('PDF export requires Google Chrome. Install Chrome or set RESUME_CHROME to its executable.')
    with tempfile.TemporaryDirectory(prefix='resume-pdf-') as folder:
        root=Path(folder); source=root/'resume.html'; output=root/'resume.pdf'
        source.write_text(content)
        node=shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')
        result=subprocess.run([node,str(ROOT/'pdf.cjs'),str(source),str(output),chrome],capture_output=True,timeout=60)
        if result.returncode or not output.exists():raise RuntimeError('PDF rendering failed: '+result.stderr.decode(errors='replace')[-500:])
        return output.read_bytes()


_preview_lock = threading.Lock()

def pdf_preview(data, levels=None):
    """Rasterize the actual export PDF for consistent previews in any browser."""
    import json
    with _preview_lock:
        return _pdf_preview_cached(json.dumps(data), json.dumps(levels or {}))


from functools import lru_cache

@lru_cache(maxsize=4)
def _pdf_preview_cached(data_json, levels_json):
    import json
    return pdf_pages(pdf(json.loads(data_json), json.loads(levels_json)))


_raster_lock = threading.Lock()

def pdf_pages(content):
    """Rasterize PDF bytes; PDFium must not be used concurrently."""
    with _raster_lock:
        return _pdf_pages(content)


def _pdf_pages(content):
    import base64
    import io
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RuntimeError('PDF preview requires pypdfium2 and Pillow. Install them with: python3 -m pip install pypdfium2 Pillow')
    pages = []
    document = pdfium.PdfDocument(content)
    try:
        for index in range(len(document)):
            page = document[index]
            bitmap = None
            try:
                width, height = page.get_size()
                bitmap = page.render(scale=1.3)
                stream = io.BytesIO()
                bitmap.to_pil().save(stream, format='PNG')
                pages.append({'image': 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode(), 'width': width, 'height': height})
            finally:
                if bitmap is not None: bitmap.close()
                page.close()
    finally:
        document.close()
    return {'pageCount': len(pages), 'pages': pages, 'paper': 'US Letter (8.5 × 11 in)'}
