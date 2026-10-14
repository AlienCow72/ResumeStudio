"""Editable application drafts and explicit, revision-specific ZIP exports."""
import copy
import hashlib
import io
import json
import re
import uuid
import zipfile

from generation import encoded, html_doc, letter_html, validate_schema
from jobs import timestamp, url_key
from render import pdf_pages
from versions import LOCK, project


def folder_for(service, identifier, run_id):
    service.jobs.read(identifier)
    if not isinstance(run_id, str) or not re.fullmatch('[a-f0-9]{32}', run_id):
        raise ValueError('Invalid application run.')
    folder = service.base(identifier) / 'runs' / run_id
    if not (folder/'documents.json').exists():
        raise ValueError('Application drafts are not ready yet.')
    return folder


def read(service, identifier, run_id):
    with service.lock, LOCK:
        folder = folder_for(service, identifier, run_id)
        path = folder/'draft.json'
        source = path if path.exists() else folder/'documents.json'
        raw = source.read_bytes()
        data = json.loads(raw)
        loaded=service.master.load()
        version=next((v for v in loaded['state']['versions'] if v.get('provenance',{}).get('jobId')==identifier and v.get('provenance',{}).get('runId')==run_id),None)
        resume,levels=project(loaded['data'],loaded['state'],version['id']) if version else (data['resume'],{})
        if version: raw+=loaded['revision'].encode()
        return {'resume': resume, 'levels':levels, 'versionId':version['id'] if version else None,
                'studioRevision':loaded['revision'], 'reviewStatus':version.get('reviewStatus','unreviewed') if version else 'unreviewed', 'coverLetter': data['coverLetter'],
                'revision': hashlib.sha256(raw).hexdigest(), 'runId': run_id,
                'reviewNotes': data.get('reviewNotes', ''),
                'jobDescription': json.loads((folder/'job-description.json').read_text())}


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('Drafts must be an object.')
    def clean(value):
        if isinstance(value, dict):
            return {key: result for key, child in value.items() if (result := clean(child)) not in ('', [], {})}
        if isinstance(value, list):
            return [result for child in value if (result := clean(child)) not in ('', [], {})]
        return value
    resume, letter = clean(data.get('resume')), data.get('coverLetter')
    validate_schema(resume, 'schema.json', 'Edited résumé')
    if not resume.get('basics', {}).get('name', '').strip():
        raise ValueError('The résumé needs a name.')
    if not isinstance(letter, str) or not letter.strip() or len(letter) > 50000:
        raise ValueError('Enter cover-letter text under 50,001 characters.')
    # Manual corrections are intentional; enforce schema, not master equality.
    return {'resume': copy.deepcopy(resume), 'coverLetter': letter}


def check_current(service, identifier, run_id):
    state = service.state(identifier)
    if state.get('runId') != run_id or state['status'] != 'ready':
        raise FileExistsError('A different generation run is active. Reopen the current application drafts; your edits are still here.')
    if state.get('sourceChanged'):
        raise FileExistsError('The posting link changed. Generate drafts for the new posting before saving or downloading.')


def save(service, identifier, run_id, data, revision):
    with service.lock, LOCK:
        check_current(service, identifier, run_id)
        old = read(service, identifier, run_id)
        if old['revision'] != revision:
            raise FileExistsError('These drafts changed in another tab. Your edits are still here; reopen the drafts to load the latest version.')
        if old.get('versionId') and data.get('resume')!=old['resume']:
            raise FileExistsError('Edit the linked résumé in Studio. Your cover-letter edits are retained; reconcile with the saved Studio version.')
        clean=validate({**data,'resume':old['resume']} if old.get('versionId') else data)
        if old.get('versionId'):clean.pop('resume')
        folder = folder_for(service, identifier, run_id)
        clean['reviewNotes'] = old['reviewNotes']
        clean['savedAt'] = timestamp()
        history={k:v for k,v in old.items() if k in ('coverLetter','reviewNotes','revision','runId')} if old.get('versionId') else old
        service.jobs.write(folder/'draft-history'/(uuid.uuid4().hex+'.json'), history)
        # Studio owns linked résumés; this file stores their cover letters.
        service.jobs.write(folder/'draft.json', clean)
        return read(service, identifier, run_id)


def preview(service, identifier, run_id, data, document=None):
    with service.lock, LOCK:
        current=read(service,identifier,run_id)
        clean = validate({**data,'resume':current['resume']} if current.get('versionId') else data)
        levels=current['levels']
    folder = folder_for(service, identifier, run_id)
    posting = json.loads((folder/'job-description.json').read_text())
    if document not in (None, 'resume', 'coverLetter'):
        raise ValueError('Choose a résumé or cover letter to preview.')
    documents = {'resume': html_doc(clean['resume'],levels),
                 'coverLetter': letter_html(clean['coverLetter'], clean['resume'], posting)}
    if document is not None:
        # Render unsaved edits using the exact same HTML and renderer as export.
        # PDF bytes exist only in memory; preview never saves drafts or exports.
        return pdf_pages(service.renderer(documents[document]))
    return documents


def bundle(service, identifier, run_id, revision):
    with service.lock, LOCK:
        check_current(service, identifier, run_id)
        draft = read(service, identifier, run_id)
        if draft['revision'] != revision:
            raise FileExistsError('The drafts changed before download. Save your latest edits and try again.')
        source_url = service.jobs.read(identifier)['url']
    # Render an immutable in-memory snapshot. Preview and save do not persist PDF files.
    rendered = [service.renderer(html_doc(draft['resume'],draft['levels'])),
                service.renderer(letter_html(draft['coverLetter'], draft['resume'], draft['jobDescription']))]
    with service.lock, LOCK:
        check_current(service, identifier, run_id)
        if read(service, identifier, run_id)['revision'] != revision or url_key(service.jobs.read(identifier)['url']) != url_key(source_url):
            raise FileExistsError('The application changed during PDF rendering. Save and download the latest version.')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('job-description.json', encoded(draft['jobDescription']))
        archive.writestr('resume.pdf', rendered[0])
        archive.writestr('cover-letter.pdf', rendered[1])
    posting = draft['jobDescription']
    prefix = re.sub('[^a-zA-Z0-9-]+', '-', posting['company']+'-'+posting['title']).strip('-')[:100]
    return stream.getvalue(), prefix+'-application.zip'
