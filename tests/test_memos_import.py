"""Synthetic, offline checks for importing only approved shared entries."""

import json
import stat

import pytest

from scripts import import_memos


MEMO = {
    'name': 'memos/synthetic-1',
    'visibility': 'PROTECTED',
    'state': 'NORMAL',
    'createTime': '2026-10-16T13:30:00Z',
    'content': 'A synthetic family memory',
}
ATTACHMENTS = [
    {'name': 'attachments/a', 'filename': 'sample.jpg', 'size': 4},
    {'name': 'attachments/b', 'filename': 'clip.mov', 'size': 4},
]


class FakeSource:
    def attachments(self, name):
        assert name == MEMO['name']
        return ATTACHMENTS

    def download(self, attachment, destination):
        destination.write_bytes(b'test')
        return attachment['filename']


class FakeDestination:
    def __init__(self):
        self.created = []
        self.uploaded = []
        self.finished = []
        self.fail_once = False

    def create(self, content, day):
        self.created.append((content, day))
        return 123

    def upload(self, file_path, name):
        if self.fail_once and name == 'clip.mov':
            self.fail_once = False
            raise RuntimeError('Synthetic upload failure')
        self.uploaded.append(name)
        return f'generated-{name}'

    def finish(self, item_id, content, day, filenames):
        self.finished.append((item_id, content, day, filenames, import_memos.media_type(filenames)))


def test_only_protected_non_placeholder_memories_are_eligible():
    assert import_memos.eligible(MEMO)
    assert not import_memos.eligible({**MEMO, 'visibility': 'PRIVATE'})
    assert not import_memos.eligible({**MEMO, 'state': 'DELETED'})
    assert not import_memos.eligible({**MEMO, 'content': 'NEED INPUT'})
    assert not import_memos.eligible({**MEMO, 'content': 'Diary: NEED INPUT\n#daily-diary'})


def test_copies_once_and_keeps_private_resume_file(tmp_path):
    path = tmp_path / 'state.json'
    state = import_memos.State(path)
    destination = FakeDestination()
    assert import_memos.import_shared_memo(MEMO, FakeSource(), destination, state, 'Australia/Sydney')
    assert destination.created == [('A synthetic family memory', '2026-10-17')]
    assert destination.uploaded == ['sample.jpg', 'clip.mov']
    assert destination.finished[0][-1] == 'galleryStartWithImage'
    assert import_memos.State(path).records[MEMO['name']]['status'] == 'complete'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert 'A synthetic family memory' not in path.read_text()

    assert not import_memos.import_shared_memo(MEMO, FakeSource(), destination, state, 'Australia/Sydney')
    assert len(destination.created) == 1
    assert len(destination.uploaded) == 2


def test_retry_resumes_after_partial_media_failure(tmp_path):
    state = import_memos.State(tmp_path / 'state.json')
    destination = FakeDestination()
    destination.fail_once = True

    with pytest.raises(RuntimeError, match='Synthetic upload failure'):
        import_memos.import_shared_memo(MEMO, FakeSource(), destination, state, 'UTC')
    assert len(destination.created) == 1
    assert destination.uploaded == ['sample.jpg']
    assert state.records[MEMO['name']]['status'] == 'created'

    assert import_memos.import_shared_memo(MEMO, FakeSource(), destination, state, 'UTC')
    assert len(destination.created) == 1
    assert destination.uploaded == ['sample.jpg', 'clip.mov']


def test_unknown_create_result_fails_closed(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text(json.dumps({MEMO['name']: {
        'status': 'creating', 'item_id': None, 'uploads': {}
    }}))
    with pytest.raises(RuntimeError, match='manually reconcile'):
        import_memos.import_shared_memo(
            MEMO, FakeSource(), FakeDestination(), import_memos.State(path), 'UTC'
        )


def test_requires_https_except_explicit_trusted_lan():
    with pytest.raises(ValueError, match='HTTPS'):
        import_memos.secure_url('http://example.invalid')
    assert import_memos.secure_url('https://example.invalid/') == 'https://example.invalid'
    assert import_memos.secure_url('http://localhost:5230') == 'http://localhost:5230'
    assert import_memos.secure_url('http://example.invalid', allow_http=True) == 'http://example.invalid'
    with pytest.raises(ValueError, match='Invalid server URL'):
        import_memos.secure_url('https://user:password@example.invalid')
