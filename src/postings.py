"""Capture public posting text without exposing local-network services."""
import http.client
import ipaddress
import json
import re
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import certifi
from jobs import posting_url, timestamp


class PostingUnavailable(ValueError):
    pass


class PostingHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.scripts = []
        self.skip = 0
        self.script = None

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.skip += 1
            if tag == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
                self.script = []
        elif tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'section') and not self.skip:
            self.text.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg'):
            if tag == 'script' and self.script is not None:
                self.scripts.append(''.join(self.script))
                self.script = None
            self.skip = max(0, self.skip - 1)
        elif tag in ('p', 'div', 'li') and not self.skip:
            self.text.append('\n')

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        elif not self.skip:
            self.text.append(data)


def extract_text(html):
    parser = PostingHTML()
    parser.feed(html)
    def postings(value):
        if isinstance(value, list):
            return [item for child in value for item in postings(child)]
        if isinstance(value, dict):
            kind = value.get('@type', [])
            if kind == 'JobPosting' or isinstance(kind, list) and 'JobPosting' in kind:
                return [value]
            return [item for child in value.values() for item in postings(child)]
        return []
    structured = []
    for script in parser.scripts:
        try:
            structured.extend(postings(json.loads(script)))
        except (ValueError, TypeError):
            pass
    # Capture the visible text too: JSON-LD may omit material qualifications.
    visible = '\n'.join(re.sub(r'\s+', ' ', line).strip() for line in ''.join(parser.text).splitlines())
    visible = re.sub(r'\n{3,}', '\n\n', visible).strip()
    prefix = 'JobPosting structured data:\n' + json.dumps(structured, ensure_ascii=False) + '\n\nPage text:\n' if structured else ''
    return prefix + visible


def public_addresses(host, port):
    addresses = list(dict.fromkeys(info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise PostingUnavailable('Use a public job posting link, or paste the description below.')
    return addresses


def capture(url):
    original = posting_url(url)
    current = original
    try:
        for _ in range(6):
            parts = urlsplit(posting_url(current))
            host = parts.hostname.encode('idna').decode('ascii')
            port = parts.port or (443 if parts.scheme == 'https' else 80)
            if port not in (80, 443):
                raise PostingUnavailable('Posting links must use standard HTTP or HTTPS ports.')
            addresses = public_addresses(host, port)
            connection = http.client.HTTPConnection(host, port, timeout=25)
            # Pin the connection to an already checked IP; TLS still verifies the hostname.
            connection.sock = socket.create_connection((addresses[0], port), timeout=25)
            try:
                if parts.scheme == 'https':
                    connection.sock = ssl.create_default_context(cafile=certifi.where()).wrap_socket(connection.sock, server_hostname=host)
                connection.request('GET', (parts.path or '/') + ('?' + parts.query if parts.query else ''),
                                   headers={'User-Agent': 'Mozilla/5.0 (compatible; ResumeStudio/1.0)', 'Accept': 'text/html,application/json,text/plain', 'Accept-Encoding': 'identity'})
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location:
                        raise PostingUnavailable('The posting redirected without a destination.')
                    current = urljoin(current, location)
                    continue
                if response.status != 200:
                    raise PostingUnavailable(f'The posting site returned HTTP {response.status}. Paste the full description to continue.')
                mime = response.getheader('Content-Type', '').lower()
                if not any(kind in mime for kind in ('text/html', 'text/plain', 'application/json', 'application/xhtml')):
                    raise PostingUnavailable('This link did not return a readable posting. Paste the description to continue.')
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise PostingUnavailable('This page is too large. Paste the job description to continue.')
                charset = response.headers.get_content_charset() or 'utf-8'
                content = raw.decode(charset, errors='replace')
                text = extract_text(content) if 'html' in mime else content
                if len(text.strip()) < 150 or len(text) > 120000:
                    raise PostingUnavailable('The posting text could not be isolated. Paste the full description to continue.')
                return text, {'url': original, 'finalUrl': current, 'capturedAt': timestamp(), 'method': 'public-url'}
            finally:
                connection.close()
        raise PostingUnavailable('Too many posting redirects. Paste the description to continue.')
    except PostingUnavailable:
        raise
    except (OSError, ValueError, http.client.HTTPException, LookupError) as error:
        raise PostingUnavailable('Could not read the posting site. Paste the full description to continue.') from error
