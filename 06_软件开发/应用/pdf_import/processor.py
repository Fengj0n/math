import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from .ocr import model_status, recognise_image
from .splitter import split_questions

log = logging.getLogger(__name__)


class Processor:
    def __init__(self, store, recogniser=None):
        self.store = store
        self.recogniser = recogniser or recognise_image
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='local-pdf')
        self.lock = threading.Lock()
        self.pending = {}
        self.cancel_flags = {}

    def submit(self, bid):
        with self.lock:
            if bid in self.pending and not self.pending[bid].done():
                return
            flag = threading.Event()
            self.cancel_flags[bid] = flag
            self.store.update_batch(bid, status='queued', error='', detail='等待本地识别。')
            self.pending[bid] = self.pool.submit(self.run, bid, flag)

    def cancel(self, bid):
        with self.lock:
            flag = self.cancel_flags.get(bid)
            if flag:
                flag.set()
                self.store.update_batch(bid, status='cancelling', detail='本页完成后停止，已完成页面会保留。')

    def close(self):
        for flag in self.cancel_flags.values():
            flag.set()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def cache_path(self, sid, page):
        fingerprint = model_status().get('fingerprint', 'test-engine')[:12]
        return self.store.root / 'pages' / f'{sid}-{page:04d}-{fingerprint}.json'

    def run(self, bid, flag):
        import pymupdf
        from PIL import Image
        batch = self.store.batch(bid, False)
        pages, source_id = batch['pages'], batch['source_id']
        results = []
        try:
            self.store.update_batch(bid, status='running', detail='正在加载本地识别模型。', error='')
            with pymupdf.open(self.store.root / 'sources' / f'{source_id}.pdf') as doc:
                for index, pnum in enumerate(pages):
                    if flag.is_set():
                        self.store.update_batch(bid, status='cancelled', detail='已停止，可从保存的页面继续。')
                        return
                    self.store.update_batch(bid, detail=f'正在识别PDF第{pnum}页（{index + 1}/{len(pages)}）。')
                    cache = self.cache_path(source_id, pnum)
                    if cache.exists():
                        result = json.loads(cache.read_text('utf-8'))
                    else:
                        page = doc[pnum - 1]
                        zoom = min(2.2, 2400 / max(page.rect.width, page.rect.height))
                        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False, colorspace=pymupdf.csRGB)
                        image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                        result = self.recogniser(image)
                        result['page'] = pnum
                        result['source_id'] = source_id
                        temp = cache.with_suffix('.json.tmp')
                        temp.write_text(json.dumps(result, ensure_ascii=False), 'utf-8')
                        temp.replace(cache)
                    results.append(result)
                    self.store.update_batch(bid, progress=index + 1)
            if flag.is_set():
                self.store.update_batch(bid, status='cancelled', detail='页面已保存，可继续拆题。')
                return
            self.store.update_batch(bid, detail='正在按题号整理题目与答案。')
            rows, unassigned = split_questions(results, source_id, batch['chapter'])
            self.store.save_drafts(bid, rows)
            raw_path = self.store.root / 'pages' / f'{bid}-unassigned.json'
            raw_path.write_text(json.dumps(unassigned, ensure_ascii=False, indent=2), 'utf-8')
            self.store.update_batch(bid, status='completed', detail=f'识别完成，整理出{len(rows)}道待核对题目。')
        except Exception as exc:
            log.exception('Local PDF recognition failed: %s', bid)
            self.store.update_batch(bid, status='failed', error=str(exc)[:1600], detail='识别未完成，已完成页面已保存。')
