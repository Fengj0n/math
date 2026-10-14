"""Lossless legacy notation layout. Never fills missing mathematical conditions.

The source transcription is kept separately. Conversion changes typography only;
ambiguous shorthand is reported rather than interpreted as a derivative or index.
"""
import copy
import re

VERSION = 'legacy-layout-3'
DELIMITERS = re.compile(r'\$\$[\s\S]*?\$\$|\$[^$]*?\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)')
GREEK = dict(zip('αβγδεθλμπρσφψωΓΔΘΛΠΣΦΩ',
                ['alpha','beta','gamma','delta','epsilon','theta','lambda','mu','pi','rho','sigma','varphi','psi','omega','Gamma','Delta','Theta','Lambda','Pi','Sigma','Phi','Omega']))
SYMBOLS = {'∞':r'\infty','→':r'\to','⇒':r'\Rightarrow','⇔':r'\Leftrightarrow',
           '≤':r'\le','≥':r'\ge','≠':r'\ne','∈':r'\in','∉':r'\notin','×':r'\times',
           '·':r'\cdot','…':r'\ldots','−':'-','′':"'",'″':"''",'‴':"'''",'∂':r'\partial'}
FUNCTIONS = ('arcsin','arccos','arctan','sinh','cosh','sqrt','sin','cos','tan','cot','ln','log','exp','lim','det','diag','rank','tr')


class NotationError(ValueError):
    pass


def group(s, i):
    """Return a balanced original group; do not synthesize its contents."""
    pairs = {'(':')','[':']','{':'}'}
    end = pairs.get(s[i]); stack = [end]
    if not end: raise NotationError('缺少分组符')
    j = i + 1
    while j < len(s):
        c = s[j]
        if c in pairs: stack.append(pairs[c])
        elif c in ')]}':
            if c != stack.pop(): raise NotationError('括号不匹配')
            if not stack: return s[i+1:j], j+1
        j += 1
    raise NotationError('括号未闭合')


def split_top(s, sep=','):
    result=[]; start=0; i=0
    while i<len(s):
        if s[i] in '([{': _,i=group(s,i);continue
        if s[i]==sep:result.append(s[start:i]);start=i+1
        i+=1
    result.append(s[start:]);return result


def atom(s,i):
    if i>=len(s):raise NotationError('上下标或根号缺少内容')
    if s[i] in '([{':
        inner,j=group(s,i);return inner,j
    if s.startswith('sqrt',i):
        inner,j=atom(s,i+4);return 'sqrt('+inner+')',j
    for f in ('arcsin','arccos','arctan','sin','cos','tan','ln'):
        if s.startswith(f,i):
            j=i+len(f)
            while j<len(s) and s[j]==' ':j+=1
            inner,j=atom(s,j);return f+'('+inner+')',j
    match=re.match(r'[+-]?\d+(?:\.\d+)?',s[i:])
    if match:return match[0],i+len(match[0])
    if s[i] in '+-' and i+1<len(s):
        inner,j=atom(s,i+1);return s[i]+inner,j
    if s[i]=='∞':return '∞',i+1
    if s[i].isalpha():
        j=i+1
        while j<len(s) and s[j].isdigit():j+=1
        return s[i:j],j
    raise NotationError('无法明确识别上下标边界')


def tex(s):
    """Lexical translation: preserves order and operators, no algebraic rewriting."""
    s=re.sub(r"([A-Za-z])([′″‴']+)(?=[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺^])",r'(\1\2)',s)
    superscript=str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺','0123456789-+')
    s=re.sub(r'[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+',lambda m:'^{'+m[0].translate(superscript)+'}',s)
    out=[];i=0
    while i<len(s):
        c=s[i]
        if c.isspace():out.append(' ');i+=1;continue
        if s.startswith('[[',i):
            inner,j=group(s,i);rows=split_top(inner)
            cells=[];width=None
            for row in rows:
                row=row.strip()
                if not row.startswith('['):raise NotationError('矩阵行格式不完整')
                inside,finish=group(row,0)
                if finish!=len(row):raise NotationError('矩阵行含未知内容')
                entries=split_top(inside)
                if width is None:width=len(entries)
                if len(entries)!=width:raise NotationError('矩阵各行列数不一致')
                cells.append(' & '.join(tex(x) for x in entries))
            out.append(r'\begin{bmatrix}'+r' \\ '.join(cells)+r'\end{bmatrix}');i=j;continue
        if c in '()[]{}':
            out.append('\\'+c if c in '{}' else c);i+=1;continue
        if c in '_^':
            blank=re.match(r'_{2,}',s[i:]) if c=='_' else None
            if blank:out.append(r'\underline{\qquad\qquad}');i+=len(blank[0]);continue
            inner,j=atom(s,i+1)
            if c=='^' and s[i+1]=='(' and re.fullmatch(r'(?:[+-]?\d+|n(?:[+-]\d+)?)',inner):inner='('+inner+')'
            out.append(c+'{'+tex(inner)+'}');i=j;continue
        if c in '²³⁴':out.append('^{'+str('²³⁴'.index(c)+2)+'}');i+=1;continue
        if c in GREEK:
            out.append('\\'+GREEK[c]+' ');i+=1
            m=re.match(r'[0-9]+',s[i:])
            if m:out.append('_{'+m[0]+'}');i+=len(m[0])
            continue
        if c in SYMBOLS:out.append(SYMBOLS[c]+' ');i+=1;continue
        if c=='∫':out.append(r'\int ');i+=1;continue
        if c in ('∬','Σ','∑'):
            out.append(r'\iint ' if c=='∬' else r'\sum ');i+=1
            if c=='∬' and i<len(s) and s[i] not in '_^ ':
                inner,i=atom(s,i);out.append('_{'+tex(inner)+'}')
            continue
        if c=='*':
            if i>0 and s[i-1] in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' and (i+1==len(s) or s[i+1] in ' ,)=+-'):
                out.append('^{*}')
            else:out.append(r'\cdot ')
            i+=1;continue
        f=next((f for f in FUNCTIONS if s.startswith(f,i)),None)
        if f:
            if f=='sqrt':
                j=i+4
                while j<len(s) and s[j]==' ':j+=1
                inner,j=atom(s,j);out.append(r'\sqrt{'+tex(inner)+'}');i=j;continue
            out.append('\\'+f+' ' if f in FUNCTIONS[:13] or f in ('lim','det') else r'\operatorname{'+f+'}')
            i+=len(f);continue
        # Explicit numeric index notation from the project: x1, alpha1, a11.
        # Two-letter indices aij / bij are deliberately left unchanged.
        if c.isalpha() and i+1<len(s) and s[i+1] in '0123456789':
            m=re.match(r'\d+',s[i+1:]);out.append(c+'_{'+m[0]+'}');i+=1+len(m[0]);continue
        if c=='\\':raise NotationError('未定界的LaTeX命令')
        if c=='$':raise NotationError('公式分隔符不完整')
        out.append(c);i+=1
    result=''.join(out)
    # Only unambiguous simple integer ratios are promoted to stacked fractions.
    result=re.sub(r'(?<![\w.])(\d+)\s*/\s*(\d+)(?![\d.A-Za-zα-ω]|\s*\^)',r'\\frac{\1}{\2}',result)
    return result


def format_text(value):
    """Split Chinese prose and existing delimited TeX before converting legacy runs."""
    value=str(value or '');issues=[];out=[];last=0
    def plain(s):
        pieces=re.split(r'([\u3400-\u9fff，。；：？！、“”‘’①②③④⑤⑥\n]+)',s)
        result=[]
        for p in pieces:
            if not p:continue
            if re.search(r'[\u3400-\u9fff，。；：？！、“”‘’①②③④⑤⑥\n]',p):result.append(p);continue
            # Chinese parentheses are punctuation. Convert them to ASCII pairs
            # within a math run without modifying formula contents.
            p=p.replace('（','(').replace('）',')')
            if not re.search(r'[A-Za-zα-ωΑ-Ω∫∬Σ∑∞≤≥≠∈²³⁴^_→=]',p) and not (re.search(r'\d',p) and re.fullmatch(r'[0-9\s(){}\[\],.+\-*/|]+',p)):result.append(p);continue
            leading=p[:len(p)-len(p.lstrip())];trailing=p[len(p.rstrip()):]
            chunk=p.strip()
            if not chunk:result.append(p);continue
            try:result.append(leading+'$'+tex(chunk)+'$'+trailing)
            except NotationError as e:
                issues.append({'text':chunk[:120],'reason':str(e)});result.append(p)
        return ''.join(result)
    for m in DELIMITERS.finditer(value):
        out.append(plain(value[last:m.start()]));out.append(m[0]);last=m.end()
    out.append(plain(value[last:]));return ''.join(out),issues


def prepare(q):
    """Create an application-only layout revision; retain source and old snapshots."""
    q=copy.deepcopy(q)
    if q.get('presentation_version')==VERSION:return q
    fields=('stem','answer','solution','core','method','alternative','key','errors')
    if q.get('presentation_original'):
        for k,v in q['presentation_original'].items():q[k]=copy.deepcopy(v)
        q.update(q.get('presentation_base_flags',{}))
    q['presentation_base_flags']=q.get('presentation_base_flags',{k:q.get(k) for k in ('eligible','render_ready','review')})
    q['grading_answer']=q.get('grading_answer',q.get('answer',''))
    q['presentation_original']={k:q.get(k,'') for k in fields}
    q['presentation_original'].update(options=copy.deepcopy(q.get('options',[])),parts=copy.deepcopy(q.get('parts',[])),rubric=copy.deepcopy(q.get('rubric',[])))
    issues=[]
    from .verified_layouts import LAYOUTS
    checked=LAYOUTS.get(q.get('id'))
    if checked:
        if checked['hash']==q.get('payload_hash'):
            q['presentation_source_check']={k:checked[k] for k in ('page','page_sha256','change')}
            for k in fields+('options',):
                if k in checked:q[k]=copy.deepcopy(checked[k])
            def replace_symbols(s):
                for old,new in checked.get('symbols',{}).items():s=re.sub(r'(?<![A-Za-z0-9_])'+old+r'(?![A-Za-z0-9_])',lambda _:new,str(s))
                return s
            for k in fields:q[k]=replace_symbols(q.get(k,''))
            for k in ('options','parts'):q[k]=[replace_symbols(x) for x in q.get(k,[])]
        else:issues.append({'field':'stem','reason':'原题指纹已变化，既有原页修正不能套用，待人工检查'})
    working={k:copy.deepcopy(q.get(k,[])) for k in ('options','parts')}
    for k in fields:
        q[k],found=format_text(q.get(k,''));issues.extend(dict(x,field=k) for x in found)
    for k in ('options','parts'):
        q[k]=[]
        for n,value in enumerate(working[k]):
            result,found=format_text(value);q[k].append(result);issues.extend(dict(x,field=f'{k}.{n}') for x in found)
    for r in q.get('rubric',[]):
        r['step'],found=format_text(r.get('step',''));issues.extend(dict(x,field='rubric') for x in found)
    q['presentation_version']=VERSION;q['presentation_issues']=issues
    # The simplified transfer notation cannot distinguish these symbols safely.
    for k in fields+('options',):
        value=q[k]
        value=' '.join(value) if isinstance(value,list) else value
        if re.search(r'(?<![A-Za-z0-9_])(?:xn|yn|fx|fy|fz|fxx|fxy|fyy)(?![A-Za-z0-9_])',value):issues.append({'field':k,'reason':'连写符号可能表示下标、偏导或乘积，待人工检查'})
    if issues:
        q['eligible']=False;q['render_ready']=False;q['review']='待人工检查（正文排版或符号）'
    return q
