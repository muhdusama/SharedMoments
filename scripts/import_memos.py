#!/usr/bin/env python3
"""Import approved shared Memos entries using existing APIs; never delete source data."""

import argparse
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests


IMAGES = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic', 'heif'}
VIDEOS = {'mp4', 'mov', 'avi', 'webm', 'mkv'}


def secure_url(url, allow_http=False):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' and not (
        parsed.scheme == 'http'
        and (allow_http or parsed.hostname in {'localhost', '127.0.0.1', '::1'})
    ):
        raise ValueError('Use HTTPS, or explicitly opt in to trusted-LAN HTTP')
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Invalid server URL')
    return url.rstrip('/')


def eligible(memo):
    return (
        memo.get('visibility') == 'PROTECTED'
        and memo.get('state', 'NORMAL') == 'NORMAL'
        and not re.search(r'\bNEED INPUT\b', memo.get('content') or '', re.IGNORECASE)
    )


def memory_day(memo, timezone):
    value = (memo.get('createTime') or '').replace('Z', '+00:00')
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise ValueError('Source memo has no timezone')
    return timestamp.astimezone(ZoneInfo(timezone)).date().isoformat()


def media_type(files):
    if not files:
        return 'text'
    first_ext = Path(files[0]).suffix.lower().lstrip('.')
    if first_ext not in IMAGES | VIDEOS:
        raise ValueError('Unsupported first attachment type')
    if len(files) > 1:
        return 'galleryStartWithImage' if first_ext in IMAGES else 'galleryStartWithVideo'
    if first_ext in IMAGES:
        return 'image'
    return 'video-mov' if first_ext == 'mov' else 'video'


class Source:
    def __init__(self, base, token, allow_http=False):
        self.base = secure_url(base, allow_http)
        self.http = requests.Session()
        self.http.headers['Authorization'] = f'Bearer {token}'

    def _pages(self, path):
        token = ''
        while True:
            params = {'pageSize': 1000}
            if token:
                params['pageToken'] = token
            reply = self.http.get(f'{self.base}{path}', params=params, timeout=(10, 90))
            reply.raise_for_status()
            result = reply.json()
            yield result
            token = result.get('nextPageToken', '')
            if not token:
                break

    def memos(self):
        return [
            memo for page in self._pages('/api/v1/memos')
            for memo in page.get('memos', [])
        ]

    def attachments(self, name):
        if not re.fullmatch(r'memos/[\w-]+', name):
            raise ValueError('Invalid memo identifier')
        memo_id = quote(name.split('/', 1)[1], safe='')
        return [
            attachment
            for page in self._pages(f'/api/v1/memos/{memo_id}/attachments')
            for attachment in page.get('attachments', [])
        ]

    def download(self, attachment, destination):
        if attachment.get('externalLink'):
            raise ValueError('External media links require manual review')
        name = attachment.get('name') or ''
        if not re.fullmatch(r'attachments/[\w-]+', name):
            raise ValueError('Invalid attachment identifier')
        filename = attachment.get('filename') or ''
        if not filename or Path(filename).suffix.lower().lstrip('.') not in IMAGES | VIDEOS:
            raise ValueError('Unsupported or unnamed attachment')
        url = f"{self.base}/file/{quote(name, safe='/')}/{quote(filename, safe='')}"
        with self.http.get(url, stream=True, timeout=(10, 180)) as reply:
            reply.raise_for_status()
            if reply.headers.get('Content-Type', '').lower().startswith('text/html'):
                raise ValueError('Received HTML instead of original attachment bytes')
            with destination.open('wb') as out:
                for chunk in reply.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out.write(chunk)
        expected_size = attachment.get('size')
        if not destination.stat().st_size or (
            expected_size is not None and int(expected_size) != destination.stat().st_size
        ):
            raise ValueError('Attachment is empty or does not match its expected size')
        return filename


class Destination:
    def __init__(self, base, email, password, allow_http=False):
        self.base = secure_url(base, allow_http)
        self.http = requests.Session()
        login = self.http.post(
            f'{self.base}/login',
            data={'email': email, 'password': password},
            timeout=(10, 30),
            allow_redirects=False,
        )
        if login.status_code != 200 or login.json().get('status') != 'success':
            raise PermissionError('SharedMoments login failed')

    def request(self, method, path, **kwargs):
        reply = self.http.request(
            method, f'{self.base}{path}', timeout=(10, 300), allow_redirects=False, **kwargs
        )
        if reply.status_code in (301, 302, 303, 401, 403):
            raise PermissionError('SharedMoments denied the operation')
        reply.raise_for_status()
        result = reply.json()
        if result.get('status') != 'success':
            raise RuntimeError('SharedMoments operation failed')
        return result['data']

    def create(self, content, day):
        return self.request('POST', '/api/v2/items', data={
            'title': f'Memory {day}', 'content': content,
            'contentType': 'text', 'contentURL': '', 'listType': 1,
            'dateCreated': day, 'edition': 'all',
        })['id']

    def upload(self, file_path, original_name):
        # Reuse SharedMoments' chunked endpoint instead of buffering large videos.
        total_size = file_path.stat().st_size
        chunk_size = 4 * 1024 * 1024
        total = max(1, (total_size + chunk_size - 1) // chunk_size)
        upload_id = uuid4().hex
        with file_path.open('rb') as source:
            for index in range(total):
                result = self.request(
                    'POST', '/api/v2/upload-chunk',
                    data=source.read(chunk_size),
                    headers={
                        'X-Upload-ID': upload_id,
                        'X-Chunk-Index': str(index),
                        'X-Total-Chunks': str(total),
                        'X-Filename': original_name,
                    },
                )
        if not result.get('filename'):
            raise RuntimeError('SharedMoments upload did not return a filename')
        return result['filename']

    def finish(self, item_id, content, day, uploaded):
        self.request('PUT', f'/api/v2/item/{item_id}', data={
            'title': f'Memory {day}', 'content': content,
            'contentType': media_type(uploaded), 'contentURL': ';'.join(uploaded),
            'listType': 1, 'dateCreated': day, 'edition': 'all',
        })


class State:
    def __init__(self, path):
        self.path = Path(path).expanduser()
        self.records = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as tmp:
            try:
                os.fchmod(tmp.fileno(), 0o600)
                json.dump(self.records, tmp, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
                temporary = tmp.name
            except Exception:
                os.unlink(tmp.name)
                raise
        os.replace(temporary, self.path)


def import_shared_memo(memo, source, destination, state, timezone):
    name = memo.get('name') or ''
    if not re.fullmatch(r'memos/[\w-]+', name):
        raise ValueError('Source memo has no stable ID')
    record = state.records.get(name)
    if record and record.get('status') == 'complete':
        return False
    if record and record.get('status') == 'creating' and not record.get('item_id'):
        raise RuntimeError('Creation result uncertain; manually reconcile before retrying')

    attachments = source.attachments(name)
    for attachment in attachments:
        if attachment.get('externalLink'):
            raise ValueError('External media links require manual review')
        if Path(attachment.get('filename') or '').suffix.lower().lstrip('.') not in IMAGES | VIDEOS:
            raise ValueError('Unsupported attachment; import stopped to avoid data loss')

    day = memory_day(memo, timezone)
    if record is None:
        record = {'status': 'creating', 'item_id': None, 'uploads': {}}
        state.records[name] = record
        state.save()
        record['item_id'] = destination.create(memo.get('content') or '', day)
        record['status'] = 'created'
        state.save()

    with tempfile.TemporaryDirectory(prefix='sharedmoments-memos-import-') as directory:
        for attachment in attachments:
            identity = attachment['name']
            if identity in record['uploads']:
                continue
            file_path = Path(directory) / uuid4().hex
            original_name = source.download(attachment, file_path)
            record['uploads'][identity] = destination.upload(file_path, original_name)
            state.save()

    names = [record['uploads'][attachment['name']] for attachment in attachments]
    destination.finish(record['item_id'], memo.get('content') or '', day, names)
    record['status'] = 'complete'
    state.save()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Create family-visible SharedMoments entries')
    parser.add_argument('--allow-http', action='store_true', help='Allow plaintext HTTP on a trusted LAN')
    parser.add_argument('--timezone', default='UTC', help='Timezone for the original memory dates')
    parser.add_argument(
        '--state',
        default=str(Path.home() / '.local/state/sharedmoments/memos-import.json'),
        help='Private, resumable import progress file',
    )
    args = parser.parse_args()

    source = Source(os.environ['MEMOS_URL'], os.environ['MEMOS_TOKEN'], args.allow_http)
    memos = source.memos()
    selected = [memo for memo in memos if eligible(memo)]
    print(f'Eligible protected entries: {len(selected)}; excluded: {len(memos) - len(selected)}')
    if not args.apply:
        print('Dry run only. No SharedMoments changes made.')
        return

    destination = Destination(
        os.environ['SHAREDMOMENTS_URL'],
        os.environ['SHAREDMOMENTS_EMAIL'],
        os.environ['SHAREDMOMENTS_PASSWORD'],
        args.allow_http,
    )
    state = State(args.state)
    imported = 0
    for memo in selected:
        if import_shared_memo(memo, source, destination, state, args.timezone):
            imported += 1
    print(f'Import completed: {imported} entries created; {len(selected) - imported} previously imported.')


if __name__ == '__main__':
    main()
