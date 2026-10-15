import hashlib
import json
import os
import threading
import time
from collections import defaultdict

from .config import CACHE, MANIFEST, MODELS, configure_environment

_engine = None
_lock = threading.Lock()


def model_config():
    return {
        'languages': ('en', 'ch_sim'),
        'mfd': {'root': str(MODELS / 'pix2text'), 'model_name': 'mfd-1.5', 'model_backend': 'onnx'},
        'text': {'rec_root': str(MODELS / 'cnocr'), 'det_root': str(MODELS / 'cnstd'),
                 'det_model_name': 'ch_PP-OCRv3_det'},
        'formula': {'root': str(MODELS / 'pix2text'), 'model_name': 'mfr-1.5', 'model_backend': 'onnx'},
    }


def model_status():
    if not MANIFEST.exists():
        return {'ready': False, 'message': '本地识别模型尚未准备完成。'}
    try:
        manifest = json.loads(MANIFEST.read_text('utf-8'))
        for item in manifest['files']:
            path = (MODELS / item['path']).resolve()
            if not path.is_relative_to(MODELS) or not path.is_file() or path.stat().st_size != item['size']:
                return {'ready': False, 'message': '本地模型文件不完整，请重新准备模型。'}
        return {'ready': True, 'message': '本地公式与文字识别模型已就绪', 'engine': 'Pix2Text 1.1.4 · ONNX CPU', 'fingerprint': manifest['fingerprint']}
    except (OSError, ValueError, KeyError):
        return {'ready': False, 'message': '本地模型记录无法读取。'}


def get_engine(allow_download=False):
    global _engine
    with _lock:
        if _engine is not None:
            return _engine
        configure_environment()
        if not allow_download:
            status = model_status()
            if not status['ready']:
                raise RuntimeError(status['message'])
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
        from pix2text import TextFormulaOCR
        import torch
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        _engine = TextFormulaOCR.from_config(model_config(), device='cpu', enable_spell_checker=False)
        return _engine


def recognise_image(image):
    started = time.monotonic()
    engine = get_engine()
    raw = engine.recognize(image, return_text=False, resized_shape=1024, mfr_batch_size=1,
                           formula_rec_kwargs={'rec_config': {'max_new_tokens': 384}})
    blocks = []
    for item in raw:
        position = item['position'].tolist() if hasattr(item['position'], 'tolist') else item['position']
        blocks.append({'text': str(item.get('text', '')), 'type': item.get('type', 'text'),
                       'score': float(item.get('score', 0)), 'position': position,
                       'line_number': int(item.get('line_number', len(blocks)))})
    groups = defaultdict(list)
    for block in blocks:
        groups[block['line_number']].append(block)
    lines = []
    for number in sorted(groups):
        items = sorted(groups[number], key=lambda v: min(point[0] for point in v['position']))
        texts, xs, ys = [], [], []
        for item in items:
            value = item['text']
            if item['type'] == 'embedding':
                value = r'\(' + value + r'\)'
            elif item['type'] == 'isolated':
                value = r'\[' + value + r'\]'
            texts.append(value)
            xs.extend(point[0] for point in item['position'])
            ys.extend(point[1] for point in item['position'])
        lines.append({'text': ' '.join(texts), 'box': [min(xs), min(ys), max(xs), max(ys)],
                      'score': min(v['score'] for v in items)})
    return {'width': image.width, 'height': image.height, 'blocks': blocks, 'lines': lines,
            'seconds': round(time.monotonic() - started, 2), 'engine': model_status().get('engine')}


def write_manifest():
    files = []
    for path in sorted(MODELS.rglob('*')):
        if path.is_file() and path.suffix in ('.onnx', '.json', '.txt', '.yaml', '.yml') and '.cache' not in path.parts:
            if 'ultralytics' in path.parts or 'matplotlib' in path.parts:
                continue
            files.append({'path': path.relative_to(MODELS).as_posix(), 'size': path.stat().st_size,
                          'sha256': file_hash(path)})
    if not any(item['path'].endswith('.onnx') for item in files):
        raise RuntimeError('没有准备完成的模型。')
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    MANIFEST.write_text(json.dumps({'engine': 'Pix2Text 1.1.4', 'files': files, 'fingerprint': fingerprint}, ensure_ascii=False, indent=2), 'utf-8')
    return fingerprint


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
