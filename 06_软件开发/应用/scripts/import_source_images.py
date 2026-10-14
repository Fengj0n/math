"""Build a resumable, deduplicated image catalogue without rewriting source data.

Execution rule: retain source pixels, stable question IDs and existing labels;
use colour anchors and the established page index for 880, fall back to full
pages when a layout cannot be separated safely. Extraction is not a new
mathematical verification or an automatic assembly approval.
"""
import argparse, hashlib, io, json, os, subprocess
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

DEV = Path(__file__).resolve().parents[2]
PROJECT = DEV.parent
OUT = DEV / '应用/assets/question-images'
TEMP = DEV / '构建/题图临时'
VERSION = 'source-images-1'
POPPLER = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def save(index):
    temp = OUT / 'index.json.tmp'
    temp.write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    os.replace(temp, OUT / 'index.json')

def markers(image):
    """Ignore horizontal blank lines; retain connected green number glyphs."""
    a = np.asarray(image.convert('RGB')).astype('int16'); h, w = a.shape[:2]
    mask = ((a[:, :, 1] > a[:, :, 0] * 1.2) & (a[:, :, 1] > a[:, :, 2] * 1.08)
            & (a[:, :, 1] < 230) & (a[:, :, 1] > 50) & ((a[:, :, 1] - a[:, :, 0]) > 20))
    mask[:int(h * .09)] = False; mask[:, int(w * .20):] = False
    cells = set(zip(*np.nonzero(mask))); boxes = []
    while cells:
        seed = cells.pop(); stack = [seed]; points = [seed]
        while stack:
            y, x = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if not dx and not dy: continue
                    point = (y + dy, x + dx)
                    if point in cells: cells.remove(point); stack.append(point); points.append(point)
        ys, xs = zip(*points); x1, x2 = min(xs), max(xs) + 1; y1, y2 = min(ys), max(ys) + 1
        if y2 - y1 >= 6 and .106 * w <= x1 <= .18 * w and x2 - x1 <= .025 * w:
            boxes.append(list(map(int, (x1, y1, x2, y2))))
    groups = []
    for b in sorted(boxes, key=lambda b: (b[1] + b[3]) / 2):
        if groups and abs((b[1] + b[3] - groups[-1][1] - groups[-1][3]) / 2) < 8:
            prev = groups[-1]; groups[-1] = [min(prev[0], b[0]), min(prev[1], b[1]), max(prev[2], b[2]), max(prev[3], b[3])]
        else: groups.append(b)
    if groups:
        median = float(np.median([b[0] for b in groups]))
        groups = [b for b in groups if b[0] >= median - .012 * w and b[2] - b[0] < .045 * w]
    return groups

def boundary(image, y):
    """Cut in an interline gap, retaining raised fractions and integral limits."""
    a = np.asarray(image.convert('RGB')); h, w = a.shape[:2]
    ink = (a[:, int(.075*w):int(.95*w)].min(axis=2) < 180).sum(axis=1)
    lo, hi = max(int(.09*h), y - 48), max(int(.09*h), y - 4)
    groups = []; current = []
    for row in range(lo, hi):
        if ink[row] <= 2: current.append(row)
        else:
            if len(current) >= 7: groups.append(current)
            current = []
    if len(current) >= 7: groups.append(current)
    return int((groups[-1][0] + groups[-1][-1]) / 2) if groups else max(int(.09*h), y - 22)

def save_image(image, index):
    image = image.convert('RGB')
    buf = io.BytesIO(); image.save(buf, 'WEBP', quality=94, method=4)
    content = buf.getvalue(); checksum = hashlib.sha256(content).hexdigest(); name = checksum[:32] + '.webp'
    path = OUT / name
    if not path.exists(): path.write_bytes(content)
    index['files'][name] = {'sha256': checksum, 'width': image.width, 'height': image.height}
    return {'url': '/api/question-images/' + name, 'width': image.width, 'height': image.height}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--rendered-880', action='store_true'); args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True); TEMP.mkdir(parents=True, exist_ok=True)
    bank = PROJECT / '02_题库/数学二题库.json'; raw = json.loads(bank.read_text('utf-8-sig')); rows = raw['items']
    source_refs = {}
    for row in rows:
        for role in ('question', 'answer_reference'):
            for ref in row.get('_source_assets', {}).get(role, []):
                source_refs[(ref['file'], ref['pdf_page'])] = ref
    sources = {}
    for name in sorted({key[0] for key in source_refs}):
        path = PROJECT / '01_原始资料' / name; sources[name] = sha(path)
        known = {r['pdf_sha256'] for k, r in source_refs.items() if k[0] == name and r.get('pdf_sha256')}
        if known and known != {sources[name]}: raise RuntimeError('源PDF指纹变化，待人工检查：' + name)
    index_path = OUT / 'index.json'
    index = json.loads(index_path.read_text('utf-8')) if index_path.exists() else {}
    if index.get('version') != VERSION or index.get('source_bank_sha256') != sha(bank):
        index = {'version': VERSION, 'source_bank_sha256': sha(bank), 'sources': sources, 'files': {}, 'questions': {}, 'page_assets': {}, 'batches': []}
    elif index['sources'] != sources: raise RuntimeError('源资料变化，不能沿用旧裁切')
    ll = [r for r in rows if r['来源'] == '880']; starts = defaultdict(list); previews = {}; anchors = {}; cuts = {}
    for row in ll: starts[row['题干PDF页'][0]].append(row)
    for page, expected in starts.items():
        preview = Image.open(PROJECT / f'02_题库/阶段03_880分析/预览/Q{page:03}.png').convert('RGB')
        previews[page] = preview; marks = markers(preview)
        # These source layouts were visually checked: single unnumbered items,
        # and one section heading whose glyph can resemble a numeric marker.
        if page == 53: marks = [[98, 259, 115, 277], [97, 534, 114, 552]]
        if page == 67: marks = [b for b in marks if not 495 < b[1] < 520]
        if page == 81: marks.append([106, 938, 124, 956]); marks.sort(key=lambda b: b[1])
        if page == 83: marks = [[101, 200, 122, 217]]
        if len(marks) != len(expected):
            anchors[page] = None; cuts[page] = []; continue
        anchors[page] = dict(zip([r['ID'] for r in expected], marks))
        cuts[page] = [boundary(preview, b[1]) for b in marks]
    index['anchor_pages'] = {str(p): {'ids': list(a) if a else [], 'cuts': cuts[p], 'size': list(previews[p].size)} for p, a in anchors.items()}
    save(index)
    if not args.rendered_880:
        subprocess.run([str(POPPLER), '-f', '9', '-l', '106', '-scale-to', '1800', '-png', str(PROJECT/'01_原始资料/27李林精讲精练880题-试题（数二）.pdf'), str(TEMP/'880')], check=True)
    page_cache = {}
    def page_asset(ref):
        key = ref['file'] + '|' + str(ref['pdf_page'])
        if key in index['page_assets']: return index['page_assets'][key]
        source = PROJECT / ref['image_path']
        if source.exists():
            if ref.get('image_sha256') and sha(source) != ref['image_sha256']: raise RuntimeError('原图指纹变化：' + ref['image_path'])
            image = Image.open(source).convert('RGB')
        else:
            prefix = TEMP / ('page-' + sources[ref['file']][:10])
            subprocess.run([str(POPPLER), '-f', str(ref['pdf_page']), '-l', str(ref['pdf_page']), '-scale-to', '1800', '-png', str(PROJECT/'01_原始资料'/ref['file']), str(prefix)], check=True)
            image = Image.open(next(TEMP.glob(prefix.name + '-*.png'))).convert('RGB')
        if ref['file'] == '27李林精讲精练880题-试题（数二）.pdf': image = Image.open(TEMP/f'880-{ref["pdf_page"]:03}.png').convert('RGB')
        result = dict(save_image(image, index), pdf_page=ref['pdf_page'])
        index['page_assets'][key] = result; return result
    for number, row in enumerate(rows, 1):
        qid = row['ID']
        if qid in index['questions']: continue
        assets = row.get('_source_assets', {}); refs = assets.get('question', [])
        if not refs: continue
        pages = [page_asset(ref) for ref in refs]
        answers = [page_asset(ref) for ref in assets.get('answer_reference', [])]
        entry = {'question_images': pages, 'reference_images': pages, 'answer_images': answers, 'mode': 'pages',
                 'source_signature': [[r['file'], r['pdf_page'], r.get('pdf_sha256', '')] for r in refs],
                 'status': '原页候选', 'source': row['来源'], 'category': row['题目类别A/B/C/D']}
        if row['来源'] == '880':
            first, last = row['题干PDF页'][0], row['题干PDF页'][-1]
            precise = anchors.get(first) is not None and all(anchors.get(p) is not None for p in row['题干PDF页'])
            # Figure 2-1 is shared spatially with following stems; a horizontal
            # crop would silently cut the diagram, so retain the whole page.
            shared_figure = {f'LL27-M2-C02-JC-T-{n:03}' for n in range(5, 10)} | {'LL27-M2-C02-ZH-T-005', 'LL27-M2-C02-ZH-T-006'}
            if qid in shared_figure: precise = False; entry['layout_issue'] = '图形横跨邻题区域，保留整页'
            if precise:
                images = []; regions = []
                for p in row['题干PDF页']:
                    preview = previews[p]; w, h = preview.size; ids = list(anchors[p]); page_cuts = cuts[p]
                    if p == first: pos = ids.index(qid); top = page_cuts[pos]; bottom = page_cuts[pos+1] if pos+1 < len(ids) else int(.94*h)
                    else: top = int(.09*h); bottom = page_cuts[0] if page_cuts else int(.94*h)
                    image = Image.open(TEMP/f'880-{p:03}.png').convert('RGB'); sx, sy = image.width/w, image.height/h
                    box = [int(.075*image.width), int(top*sy), int(.95*image.width), int(bottom*sy)]
                    if box[3] <= box[1] + 12: precise = False; break
                    clip = image.crop(box)
                    arr = np.asarray(clip); ink_rows = np.where((arr.min(axis=2) < 180).sum(axis=1) > 3)[0]
                    if len(ink_rows): clip = clip.crop((0, max(0,int(ink_rows[0])-10),clip.width,min(clip.height,int(ink_rows[-1])+12)))
                    images.append(dict(save_image(clip, index), pdf_page=p)); regions.append({'page': p, 'box': box, 'canvas': list(image.size)})
                if precise: entry.update(question_images=images, mode='single', status='单题原图候选', regions=regions)
        index['questions'][qid] = entry
        if number % 60 == 0:
            index['batches'].append({'through': qid, 'count': len(index['questions'])}); save(index)
            print(f'已保存 {len(index["questions"])} 道题的图像关联', flush=True)
    for name, checksum in sources.items():
        if sha(PROJECT/'01_原始资料'/name) != checksum: raise RuntimeError('原PDF被改动：' + name)
    if sha(bank) != index['source_bank_sha256']: raise RuntimeError('上游题库被改动')
    index['summary'] = {'questions':len(index['questions']), 'single_question':sum(v['mode']=='single' for v in index['questions'].values()),
                        '880':sum(v['source']=='880' for v in index['questions'].values()), 'exams':sum(v['source']=='历年真题' for v in index['questions'].values()),
                        'files':len(index['files']), 'bytes':sum((OUT/n).stat().st_size for n in index['files']), 'source_unchanged':True}
    index['complete'] = len(index['questions']) == len(rows); save(index)
    print(json.dumps(index['summary'], ensure_ascii=False), flush=True)

if __name__ == '__main__': main()
