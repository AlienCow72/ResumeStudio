"""Local application records, independent of master résumé/version storage."""
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

STAGES = ('applying', 'waiting', 'interview', 'rejected')
LOCK = threading.RLock()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def posting_url(value):
    if not isinstance(value, str) or len(value) > 4000:
        raise ValueError('Enter a valid HTTP or HTTPS posting link.')
    value = value.strip()
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise ValueError('Enter a valid HTTP or HTTPS posting link.')
    if (parts.scheme not in ('http', 'https') or not parts.hostname
            or parts.username is not None or parts.password is not None
            or any(c.isspace() or ord(c) < 32 for c in value)):
        raise ValueError('Enter a valid HTTP or HTTPS posting link.')
    return value


def url_key(value):
    parts = urlsplit(posting_url(value))
    # Preserve requisition/query IDs; ignore only known campaign parameters.
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('gclid', 'fbclid', 'msclkid', 'dclid', 'mc_cid', 'mc_eid')]
    netloc = parts.netloc.lower()
    if (parts.scheme == 'https' and parts.port == 443) or (parts.scheme == 'http' and parts.port == 80):
        netloc = netloc.rsplit(':', 1)[0]
    return urlunsplit((parts.scheme, netloc, parts.path or '/', urlencode(sorted(query)), ''))


def fields(data):
    if not isinstance(data, dict):
        raise ValueError('Job details must be an object.')
    result = {}
    for key, limit in [('company', 200), ('title', 300), ('notes', 20000)]:
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f'{key.capitalize()} must be text under {limit + 1} characters.')
        result[key] = value.strip()
    if not result['company'] or not result['title']:
        raise ValueError('Company and role are required.')
    source_text = data.get('sourceText', '')
    if not isinstance(source_text, str) or len(source_text) > 120000:
        raise ValueError('Job description must be text under 120001 characters.')
    result['sourceText'] = source_text
    result['url'] = posting_url(data.get('url'))
    result['stage'] = data.get('stage', 'applying')
    if result['stage'] not in STAGES:
        raise ValueError('Choose Applying, Waiting on response, Interview, or Rejected.')
    result['appliedOn'] = data.get('appliedOn', '')
    if result['appliedOn']:
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', result['appliedOn']):
                raise ValueError()
            date.fromisoformat(result['appliedOn'])
        except (ValueError, TypeError):
            raise ValueError('Application date must be a valid YYYY-MM-DD date.')
    elif result['appliedOn'] != '':
        raise ValueError('Application date must be a date or an empty string.')
    return result


class DuplicateJob(ValueError):
    def __init__(self, jobs):
        super().__init__('This posting is already tracked. Open the existing job or add a separate application.')
        self.jobs = jobs


class JobStore:
    def __init__(self, root):
        self.directory = Path(root) / 'data' / 'jobs'

    def path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
            raise ValueError('Invalid job ID.')
        return self.directory / identifier / 'application.json'

    def read(self, identifier):
        body = self.path(identifier).read_bytes()
        record = json.loads(body)
        return {**record, 'revision': hashlib.sha256(body).hexdigest()}

    def list(self):
        with LOCK:
            if not self.directory.exists():
                return []
            return sorted((self.read(p.parent.name) for p in self.directory.glob('*/application.json')),
                          key=lambda job: (job['createdAt'], job['id']), reverse=True)

    def write(self, path, record):
        body = (json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def create(self, data, allow_duplicate=False, idempotency_key=None, request_input=None):
        with LOCK:
            if idempotency_key is not None and (not isinstance(idempotency_key,str) or not 1 <= len(idempotency_key) <= 200):
                raise ValueError('Idempotency-Key must contain 1–200 characters.')
            digest=hashlib.sha256(json.dumps(request_input if request_input is not None else data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            keyhash=hashlib.sha256(idempotency_key.encode()).hexdigest() if idempotency_key else None
            if keyhash:
                prior=next((j for j in self.list() if keyhash in j.get('creationKeys',{})),None)
                if prior:
                    if prior['creationKeys'][keyhash]!=digest: raise FileExistsError('Idempotency-Key was already used with different input.')
                    return prior,False
            clean=fields(data)
            matches=[j for j in self.list() if url_key(j['url'])==url_key(clean['url'])]
            if matches and not allow_duplicate:
                if len(matches)>1: raise DuplicateJob(matches)
                job=matches[0];created=False
            else:
                job=self.save(data,allow_duplicate=allow_duplicate,creation_keys={keyhash:digest} if keyhash else None);created=True
            if keyhash and not created:
                record={k:v for k,v in job.items() if k!='revision'}
                record.setdefault('creationKeys',{})[keyhash]=digest
                self.write(self.path(job['id']),record)
                job=self.read(job['id'])
            return job,created

    def save(self, data, identifier=None, expected=None, allow_duplicate=False, creation_keys=None):
        with LOCK:
            old = self.read(identifier) if identifier else None
            if old and expected != old['revision']:
                raise FileExistsError('This job changed in another tab. Reload the board before saving again; your unsaved details are still here.')
            clean = fields({**(old or {}), **data}) if isinstance(data, dict) else fields(data)
            duplicates = [job for job in self.list()
                          if job['id'] != identifier and url_key(job['url']) == url_key(clean['url'])]
            url_changed = old is None or url_key(old['url']) != url_key(clean['url'])
            if duplicates and url_changed and not allow_duplicate:
                raise DuplicateJob(duplicates)
            now = timestamp()
            identifier = identifier or uuid.uuid4().hex
            history = list(old['history']) if old else []
            if old is None or old['stage'] != clean['stage']:
                history.append({'at': now, 'from': old['stage'] if old else None, 'to': clean['stage']})
            record = {**{k:v for k,v in (old or {}).items() if k not in ('revision','generation')}, **clean, 'schemaVersion': 1, 'id': identifier,
                      'createdAt': old['createdAt'] if old else now,
                      'updatedAt': now, 'history': history}
            if creation_keys and not old:record['creationKeys']=creation_keys
            path = self.path(identifier)
            if old:
                backup = path.parent / 'backups' / (now.replace(':', '-') + '-' + uuid.uuid4().hex + '.json')
                self.write(backup, {k: v for k, v in old.items() if k != 'revision'})
            self.write(path, record)
            return self.read(identifier)
