"""Create a read-only analysis snapshot for the source and portable UI."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT.parent
REPORTS = [
    ('blueprint', '近15年数学二命题蓝图.md', '命题蓝图', '范围、章节、知识点、题型及近五年比较'),
    ('difficulty', '真题难度分布.md', '难度分布', '评级口径、年度分布与难度边界'),
    ('audit', '真题分析质量审核报告.md', '质量审核', '分类修正、来源冲突及仍然存在的不确定性'),
    ('materials', '命题素材完整核验报告.md', '素材核验', '完整正文、答案与来源的分批核验记录'),
    ('rules', '数学二模拟卷命题规范.md', '命题规范', '覆盖、计算量、时间、改编与数学检查规则'),
    ('scoring', '模拟卷质量评分标准.md', '质量评分', '整卷审核指标及适用边界'),
]


def build():
    source = PROJECT / '02_题库/数学二题库.json'
    data = json.loads(source.read_text(encoding='utf-8-sig'))
    original_files = {}
    for path in (PROJECT / '01_原始资料').rglob('*.pdf'):
        original_files.setdefault(path.name, []).append(path)

    def origin(r):
        provenance = r.get('原始文件来源') or ''
        result = {'id': r['ID'], 'source': r.get('来源', ''), 'year': r.get('年份'),
                  'number': r.get('原题编号'), 'provenance': provenance,
                  'stage_source': r.get('来源阶段数据') or ''}
        for role, title in [('question', '题干'), ('answer', '答案')]:
            filename = r.get(title + '文件') or ''
            recorded = re.findall(r'01_原始资料/[^，；\n]+\.pdf', provenance)
            paths = [PROJECT / name for name in recorded if Path(name).name == filename]
            if not paths:
                paths = original_files.get(filename, [])
            path = paths[0] if len(set(paths)) == 1 else None
            result[role + '_file'] = filename
            result[role + '_path'] = path.relative_to(PROJECT).as_posix() if path else ''
            result[role + '_available'] = bool(path and path.is_file())
            result[role + '_pages'] = r.get(title + 'PDF页') or []
        return result

    origins = {r['ID']: origin(r) for r in data['items']}
    records = [r for r in data['items'] if r.get('来源') == '历年真题']
    assert len(records) == 293 and sum(r['分值'] for r in records) == 1950
    assert len({r['ID'] for r in records}) == len(records)
    years = sorted({r['年份'] for r in records})
    assert years == list(range(2014, 2027))
    assert all(sum(r['分值'] for r in records if r['年份'] == y) == 150 for y in years)
    rows = []
    for r in records:
        rows.append({
            **origins[r['ID']],
            'id': r['ID'], 'year': r['年份'], 'number': r['原题编号'],
            'subject': r['科目'], 'chapter': r['一级知识点'], 'point': r['二级知识点'],
            'model': r['三级知识点'], 'type': r['题型'], 'points': r['分值'],
            'difficulty': r.get('难度'), 'calculation': r.get('计算量'),
            'core': r.get('核心考法', ''), 'method': r.get('主要解法', ''),
            'secondary': r.get('次级知识点', ''), 'provenance': r.get('原始文件来源', ''),
            'state': r.get('核验状态', '待人工检查'), 'issue': r.get('数学疑点说明', ''),
        })
    documents = []
    for key, filename, title, description in REPORTS:
        path = PROJECT / '03_命题分析' / filename
        documents.append({'id': key, 'name': filename, 'title': title,
                          'description': description, 'path': path.relative_to(PROJECT).as_posix(),
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'content': path.read_text(encoding='utf-8-sig')})
    # Report text is preserved verbatim; discrepancies are surfaced, not silently rewritten.
    models = len({r['model'] for r in rows})
    warnings = []
    if models != 108:
        warnings.append(f'三级标签口径存在差异：统一题库当前为{models}个，蓝图原文为108个。图表按统一题库统计，差异待人工检查；原报告未修改。')
    warnings.append('报告中存在后续修订前的历史表述。具体题目结论以当前统一题库及核验记录为准，阅读原报告时须结合修订说明。')
    snapshot = {'schema': 1, 'updated': data.get('updated_on'), 'years': years,
                'project_root': str(PROJECT), 'origins': origins,
                'source': source.relative_to(PROJECT).as_posix(),
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'rows': rows, 'documents': documents, 'warnings': warnings,
                'accounting': '每题一个主标签，整题分值归主标签；次级标签不重复分配分值。难度与计算量为预估评级。',
                'frequency': '按所选年份中的覆盖年数：高频≥5年，中频3—4年，低频1—2年。频次不是未来命题概率。'}
    output = ROOT / '应用/frontend/public/analysis.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({'questions': len(rows), 'points': sum(r['points'] for r in rows),
                      'years': years, 'models': models, 'documents': len(documents),
                      'difficulty': dict(Counter(r['difficulty'] for r in rows)),
                      'warnings': warnings}, ensure_ascii=False))


if __name__ == '__main__':
    build()
