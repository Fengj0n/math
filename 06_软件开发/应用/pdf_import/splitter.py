"""Conservative split suggestions from OCR lines, retaining source rectangles."""
import hashlib
import json
import re
import unicodedata

NUMBER = re.compile(r'^\s*(?:\$\s*)?(?:(?:例题?|习题)\s*)?(\d{1,3})(?:\s*\$)?\s*[.．、](?!\d)\s*')
ANSWER = re.compile(r'[【\[［（(]?\s*(?:参考答案|答案|答)\s*[】\]］）):：]')
SOLUTION = re.compile(r'[【\[［（(]?\s*(?:解析|详解|解答|证明|解)\s*[】\]］）):：]')
CHOICES = re.compile(r'(?<![a-zA-Z])(?:[（(]\s*([ABCD])\s*[）)]|([ABCD])[.．、])\s*')


def parse_pages(value, total):
    if not str(value or '').strip():
        return list(range(1, total + 1))
    pages = set()
    for part in re.split(r'[,，、\s]+', str(value).strip()):
        match = re.fullmatch(r'(\d+)(?:\s*-\s*(\d+))?', part)
        if not match:
            raise ValueError('页码格式错误，请填写例如 1,3-5。')
        start, end = int(match[1]), int(match[2] or match[1])
        if not 1 <= start <= end <= total:
            raise ValueError(f'页码超出范围，该PDF共{total}页。')
        pages.update(range(start, end + 1))
    return sorted(pages)


def body_hash(stem, options):
    value = unicodedata.normalize('NFKC', json.dumps([stem, options], ensure_ascii=False))
    return hashlib.sha256(re.sub(r'\s+', '', value).encode()).hexdigest()


def fields_from_text(text):
    answer_match, solution_match = ANSWER.search(text), SOLUTION.search(text)
    cuts = [m.start() for m in (answer_match, solution_match) if m]
    stem = text[:min(cuts)] if cuts else text
    answer = ''
    solution = ''
    if answer_match:
        end = solution_match.start() if solution_match and solution_match.start() > answer_match.end() else len(text)
        answer = text[answer_match.end():end].strip()
    if solution_match:
        solution = text[solution_match.end():].strip()
    matches = list(CHOICES.finditer(stem))
    options = []
    if [m.group(1) or m.group(2) for m in matches] == list('ABCD'):
        options = [stem[m.end():matches[i + 1].start() if i < 3 else len(stem)].strip() for i, m in enumerate(matches)]
        stem = stem[:matches[0].start()].strip()
    kind = '选择题' if options or matches else '填空题' if re.search(r'_{2,}|＿{2,}|填空', stem) else '解答题'
    return {'stem': stem.strip(), 'options': options, 'answer': answer, 'solution': solution, 'type': kind}


def split_questions(pages, source_id, chapter='未归类'):
    """Do not infer a missing answer, chapter, or mathematical conclusion."""
    candidates, current, unassigned = [], None, []
    last_page = None
    for page in pages:
        pnum, width, height = page['page'], page['width'], page['height']
        if last_page is not None and pnum > last_page + 1:
            if current:
                current['issues'].append('所选页码不连续，本题后续内容可能位于未选页面，请核对。')
            current = None
        for line in page['lines']:
            text = line['text'].strip()
            if not text:
                continue
            x0, y0, x1, y1 = line['box']
            # Keep raw page OCR intact in the page cache; suppress only obvious running matter.
            if y0 < height * .09 and re.search(r'全国硕士|研究生招生|试题及参考|万学海文|考研数学', text):
                continue
            if y0 > height * .94 and re.fullmatch(r'[\s\d\-—]+', text):
                continue
            match = NUMBER.match(text)
            # Normalised line geometry avoids treating a continuation formula as a question number.
            starts = bool(match and int(match[1]) > 0 and x0 < width * .3)
            if starts:
                current = {'number': int(match[1]), 'texts': [], 'fragments': [], 'issues': []}
                candidates.append(current)
                text = text[match.end():]
            if current is None:
                unassigned.append({'page': pnum, 'text': text, 'box': line['box']})
                continue
            if current['fragments'] and current['fragments'][-1]['page'] == pnum:
                fragment = current['fragments'][-1]
                fragment['box'][0] = min(fragment['box'][0], max(0, x0 / width - .015))
                fragment['box'][1] = min(fragment['box'][1], max(0, y0 / height - .008))
                fragment['box'][2] = max(fragment['box'][2], min(1, x1 / width + .015))
                fragment['box'][3] = max(fragment['box'][3], min(1, y1 / height + .008))
            else:
                current['fragments'].append({'page': pnum, 'box': [max(0, x0 / width - .015), max(0, y0 / height - .008), min(1, x1 / width + .015), min(1, y1 / height + .008)]})
                if last_page is not None and pnum != last_page and not starts:
                    current['issues'].append('跨页内容已连接，请核对是否属于同一道题。')
            current['texts'].append(text)
            last_page = pnum
        last_page = pnum
    if not candidates:
        for page in pages:
            text = '\n'.join(line['text'] for line in page['lines'])
            if text.strip():
                candidates.append({'number': None, 'texts': [text], 'fragments': [{'page': page['page'], 'box': [0, 0, 1, 1]}], 'issues': ['未找到可靠题号，按页暂存，请手动拆分或合并。']})
        unassigned = []
    records, occurrences = [], {}
    for index, row in enumerate(candidates):
        raw = '\n'.join(row.pop('texts'))
        fields = fields_from_text(raw)
        first_page = row['fragments'][0]['page']
        key = (first_page, row['number'])
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        origin = f'{source_id}:{first_page}:{row["number"]}:{occurrence}'
        if not fields['answer']:
            row['issues'].append('未匹配到参考答案。')
        if fields['type'] == '选择题' and len(fields['options']) != 4:
            row['issues'].append('选项未完整拆分，请核对原页。')
        if index == len(candidates) - 1:
            row['issues'].append('位于所选页段末尾，请核对题目或解析是否在下一页续写。')
        records.append(dict(row, **fields, chapter=chapter, point='', model='', raw_ocr=raw,
                            question_id='PDF-' + hashlib.sha256(origin.encode()).hexdigest()[:24],
                            status='pending', math_verified=False))
    return records, unassigned
