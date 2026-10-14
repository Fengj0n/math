import copy,json,hashlib
from pathlib import Path
from backend.presentation import format_text,tex,prepare
from backend.domain import normalize,grade

def test_formula_precedence_and_derivative_square():
    # Layout must not change 8/(40^(3/2)) into (8/40)^(3/2).
    assert r'\frac{8}{40}' not in tex('8/40^(3/2)')
    assert "(y' )^{2}" in tex('y′²')
    assert tex('x⁻²')=='x^{-2}'
    assert tex('f^(5)(1)')=='f^{(5)}(1)'

def test_integral_limits_matrix_and_adjugate():
    result,_=format_text('∫_(-1)^1 f(x)dx=2。A^T=kA*，A=[[1,2],[3,4]]。')
    assert r'\int _{-1}^{1}' in result
    assert r'A^{T}=kA^{*}' in result
    assert r'\begin{bmatrix}1 & 2 \\ 3 & 4\end{bmatrix}' in result
    option,issues=format_text('[[0,1/2],[1/2,0]]')
    assert not issues and r'\begin{bmatrix}' in option and r'\frac{1}{2}' in option

def test_delimited_latex_blank_and_intervals_preserved():
    value=r'设$f(x)=\frac{1}{x}$，x∈[0,+∞)，f(1)=____。'
    result,issues=format_text(value)
    assert r'$f(x)=\frac{1}{x}$' in result and not issues
    assert r'\underline' in result and r'\infty' in result

def test_ambiguous_shorthand_cannot_be_admitted():
    q=normalize({'ID':'TEST-SHORTHAND','来源':'880','科目':'高等数学','题型':'选择题',
                 '题干':'f(x,y)=e^x/(x-y)，x≠y。','选项':['fx+fy=0','fx-fy=0','fx-fy=f','fx+fy=f'],
                 '标准答案':'D','解析':'偏导计算，待确认符号。','正文可程序化使用':True})
    assert not q['eligible'] and q['presentation_issues']
    assert q['raw_payload']['选项'][0]=='fx+fy=0'

def test_layout_keeps_numeric_grading_and_source_hash():
    raw={'ID':'TEST-FILL','题型':'填空题','题干':'1+1=____。','标准答案':'2','解析':'1+1=2。','正文可程序化使用':True}
    original=copy.deepcopy(raw);q=normalize(raw)
    assert grade(q,'2',5)['score']==5 and grade(q,'3',5)['score']==0
    assert raw==original and q['raw_payload']==original
    assert prepare(q)==q

def test_verified_source_corrections_are_hash_bound():
    path=Path(r'D:\数学二\02_题库\数学二题库.json')
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    rows=data if isinstance(data,list) else data['items']
    source=next(r for r in rows if r['ID']=='EXAM-M2-2022-06')
    q=normalize(source)
    assert '已知数列' in q['stem'] and '\\lim' in q['options'][0] and q['eligible']
    assert q['raw_payload']['题干']==source['题干']
    other=copy.deepcopy(source);other['题干']='xn数据已被变更'
    assert not normalize(other)['eligible']

def test_migration_keeps_snapshots_and_is_idempotent(tmp_path,monkeypatch):
    import importlib
    monkeypatch.setenv('MATH2_HOME',str(tmp_path))
    from backend import main
    m=importlib.reload(main)
    q=m.store.questions()[0]
    # Simulate an old pre-layout record without rewriting its raw payload.
    q.pop('presentation_version');q.pop('presentation_issues')
    q['stem']='f(x)=x²。';q['revision']='R-legacy'
    with m.store.connect() as c:
        c.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(q['revision'],q['id'],q['payload_hash'],m.now(),m.dumps(q)))
        c.execute('UPDATE questions SET current_rev=? WHERE id=?',(q['revision'],q['id']))
        before=c.execute('SELECT payload FROM papers').fetchall()
    m.migrate_layout();first=m.store.question(q['id']);m.migrate_layout()
    assert first['revision']==m.store.question(q['id'])['revision']
    assert '$' in first['stem'] and first['previous_revision']=='R-legacy'
    with m.store.connect() as c:
        assert [r[0] for r in before]==[r[0] for r in c.execute('SELECT payload FROM papers')]
    assert list(m.BACKUP.glob('*.zip'))
