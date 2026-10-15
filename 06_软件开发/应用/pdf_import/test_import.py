import hashlib
import json
import threading

import pymupdf
import pytest
from fastapi.testclient import TestClient

from .service import create_app
from .splitter import parse_pages, split_questions
from .store import Conflict, Store


def page(n, *texts):
    return {'page': n, 'width': 800, 'height': 1000,
            'lines': [{'text': text, 'box': [80, 100 + i * 60, 680, 150 + i * 60]} for i, text in enumerate(texts)]}


def sample_rows():
    return split_questions([page(1, '1. 求极限', '(A) 0 (B) 1 (C) 2 (D) 3', '【答案】A', '【解析】参考过程', '2. 第二题', '【答案】1')], 'a' * 64)[0]


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / 'trial')
    result.add_source('a' * 64, '试卷.pdf', 4)
    batch = result.create_batch('a' * 64, [1, 2], '未归类')
    result.save_drafts(batch['id'], sample_rows())
    result.update_batch(batch['id'], status='completed')
    return result, batch['id']


def test_page_ranges_and_cross_page_boundaries():
    assert parse_pages('1,3-4,3', 5) == [1, 3, 4]
    for value in ('0', '5-2', '2-6', 'abc'):
        with pytest.raises(ValueError):
            parse_pages(value, 5)
    rows, spare = split_questions([page(1, '1. 第一题'), page(2, '接上页', '【答案】1')], 'source')
    assert len(rows) == 1 and len(rows[0]['fragments']) == 2 and rows[0]['answer'] == '1'
    rows, spare = split_questions([page(1, '1. 第一题'), page(3, '第三页残段', '2. 第二题')], 'source')
    assert len(rows[0]['fragments']) == 1 and spare[0]['text'] == '第三页残段'
    assert all(not q['math_verified'] and q['status'] == 'pending' for q in rows)
    full, _ = split_questions([page(1, '1. 第一题'), page(2, '2. 第二题')], 'source')
    partial, _ = split_questions([page(2, '2. 第二题')], 'source')
    assert full[1]['question_id'] == partial[0]['question_id']


def test_review_commit_dedup_and_revision_conflicts(store):
    db, bid = store
    first, second = db.batch(bid)['drafts']
    assert first['options'] == ['0', '1', '2', '3'] and first['answer'] == 'A'
    assert db.commit(bid)['pending'] == 2 and db.bank() == []
    checked = db.set_review(first['id'], 1, 'confirmed')
    with pytest.raises(Conflict):
        db.edit_draft(first['id'], 1, {'stem': 'stale'})
    assert db.commit(bid)['added'] == [first['question_id']]
    assert db.commit(bid)['duplicates'] == [first['question_id']]
    bank = db.bank()
    assert len(bank) == 1 and bank[0]['transcription_reviewed'] and not bank[0]['math_verified']
    edited = db.edit_draft(first['id'], checked['revision'], {'stem': '修改题干'})
    assert edited['status'] == 'pending'
    bad = db.edit_draft(second['id'], 1, {'type': '选择题', 'options': []})
    with pytest.raises(ValueError, match='四个选项'):
        db.set_review(second['id'], bad['revision'], 'confirmed')
    # Model retries cannot overwrite manual edits.
    db.save_drafts(bid, sample_rows())
    assert db.draft(first['id'])['stem'] == '修改题干'


def test_manual_split_merge_keep_source_and_raw(store):
    db, bid = store
    first, _ = db.batch(bid)['drafts']
    split = db.split_draft(first['id'], 1, 1)
    rows = db.batch(bid)['drafts']
    assert len(rows) == 3 and rows[1]['number'] is None
    assert rows[1]['fragments'] == first['fragments'] and rows[1]['raw_ocr'] == first['raw_ocr']
    assert split['answer'] == 'A' and rows[1]['answer'] == ''
    with pytest.raises(ValueError, match='下一题'):
        db.merge_draft(first['id'], split['revision'], rows[2]['id'], rows[2]['revision'])
    merged = db.merge_draft(first['id'], split['revision'], rows[1]['id'], rows[1]['revision'])
    assert merged['status'] == 'pending' and db.draft(rows[1]['id'])['status'] == 'merged'
    assert len([q for q in db.batch(bid)['drafts'] if q['status'] != 'merged']) == 2


def make_pdf(count=2):
    with pymupdf.open() as doc:
        for _ in range(count):
            doc.new_page().insert_text((80, 80), 'PDF OCR test')
        return doc.tobytes()


def test_real_api_intake_review_export_and_origin(tmp_path):
    calls = []
    def recognise(image):
        calls.append(image.size)
        return dict(page(1, '1. 求值', '(A) 0 (B) 1 (C) 2 (D) 3', '【答案】B'), blocks=[], seconds=0)
    app = create_app(tmp_path / 'isolated', recognise)
    original = make_pdf(1)
    digest = hashlib.sha256(original).hexdigest()
    with TestClient(app) as client:
        assert client.get('/api/health', headers={'Host': 'outside.example'}).status_code == 403
        assert client.post('/api/batches', json={}, headers={'Origin': 'https://outside.example'}).status_code == 403
        assert client.post('/api/sources', files={'file': ('bad.pdf', b'bad', 'application/pdf')}).status_code == 400
        response = client.post('/api/sources', files={'file': ('test.pdf', original, 'application/pdf')})
        assert response.status_code == 200
        source = response.json()
        assert source['id'] == digest
        batch = client.post('/api/batches', json={'source_id': source['id'], 'pages': '1'}).json()
        app.state.processor.pending[batch['id']].result(timeout=20)
        batch = client.get('/api/batches/' + batch['id']).json()
        assert batch['status'] == 'completed' and len(batch['drafts']) == 1 and len(calls) == 1
        draft = batch['drafts'][0]
        assert client.get(f'/api/sources/{digest}/page/1').headers['content-type'] == 'image/png'
        assert client.get(f'/api/sources/{digest}/page/1?x0=.9&x1=.1').status_code == 400
        assert client.post(f"/api/batches/{batch['id']}/commit", json={}).status_code == 400
        assert client.post(f"/api/drafts/{draft['id']}/review", json={'revision': 1, 'status': 'confirmed'}).status_code == 200
        assert len(client.post(f"/api/batches/{batch['id']}/commit", json={'accept_review': True}).json()['added']) == 1
        exported = client.get('/api/bank/export').json()['items'][0]
        assert exported['正文可程序化使用'] is False and exported['数学疑点状态'] == '待人工检查'
        assert exported['_pdf_import']['source_sha256'] == digest
        assert 'PDF导入' in client.get('/bank').text
        # Resume a completed batch is idempotent.
        client.post(f"/api/batches/{batch['id']}/resume")
        assert len(calls) == 1
    assert hashlib.sha256((tmp_path / 'isolated' / 'sources' / (digest + '.pdf')).read_bytes()).hexdigest() == digest


def test_cancel_then_resume_uses_page_cache(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def recognise(image):
        calls.append(1)
        if len(calls) == 1:
            entered.set()
            assert release.wait(10)
        return dict(page(1, '1. 求值', '【答案】1'), blocks=[], seconds=0)
    app = create_app(tmp_path / 'cancel', recognise)
    with TestClient(app) as client:
        source = client.post('/api/sources', files={'file': ('test.pdf', make_pdf(), 'application/pdf')}).json()
        bid = client.post('/api/batches', json={'source_id': source['id']}).json()['id']
        assert entered.wait(10)
        client.post(f'/api/batches/{bid}/cancel')
        release.set()
        app.state.processor.pending[bid].result(timeout=20)
        assert client.get(f'/api/batches/{bid}').json()['status'] == 'cancelled'
        client.post(f'/api/batches/{bid}/resume')
        app.state.processor.pending[bid].result(timeout=20)
        assert client.get(f'/api/batches/{bid}').json()['status'] == 'completed'
        assert len(calls) == 2  # First page reused, only the second page recognised.
