"""Pure import, eligibility, grading and paper-rule functions. No source mutations."""
import copy, hashlib, json, re, random
from collections import Counter, defaultdict
from fractions import Fraction
from .presentation import prepare

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def text(value):
    if value is None:return ''
    return '\n'.join(map(str,value)) if isinstance(value,list) else str(value)

def number(value, default=None):
    try:return float(value) if value is not None else default
    except (ValueError,TypeError):return default

def normalize(raw, original=False, verified_original=False):
    """Preserve raw payload and create a separate, conservative layout revision."""
    get=lambda cn,en,default='':raw.get(en if original else cn,default)
    stem=text(get('题干','stem')); options=get('选项','options',[]) or []
    if not isinstance(options,list):options=[]
    if not options:
        hits=list(re.finditer(r'(?<![A-Za-z])([ABCD])[.．、]',stem))
        if [m.group(1) for m in hits]==list('ABCD'):
            options=[stem[h.end():hits[i+1].start() if i<3 else len(stem)].strip('；; \n。') for i,h in enumerate(hits)]
            stem=stem[:hits[0].start()].strip()
    source='项目原创示例' if original else text(raw.get('来源','其他资料'))
    ready=verified_original or (not original and raw.get('正文可程序化使用') is True)
    blocked=not ready or raw.get('题目类别A/B/C/D')=='D'
    answer=text(get('标准答案','answer')); solution=get('解析','solution')
    q={'id':text(raw.get('ID')), 'origin_id':text(raw.get('origin_id',raw.get('ID'))),
       'source':source,'year':raw.get('年份',2027 if original else None),'original_number':raw.get('原题编号',raw.get('number')),
       'subject':get('科目','subject'),'chapter':get('一级知识点','chapter'),'point':get('二级知识点','knowledge'),
       'model':get('三级知识点','core'),'code':get('知识点代码','code'),'secondary':get('次级知识点','secondary_codes'),
       'type':get('题型','type'),'original_points':number(get('分值','points',None)),
       'difficulty':number(get('难度','difficulty',None)),'calculation':number(get('计算量','calculation',None)),
       'integration':get('综合程度','comprehensive_level'),'core':get('核心考法','core'),'method':get('主要解法','method'),
       'alternative':get('可选解法','alternative'),'stem':stem,'options':list(map(str,options)),
       'parts':raw.get('parts',[]) if original else [],'answer':answer,'solution':text(solution),
       'key':raw.get('key',''),'errors':raw.get('errors',''),'rubric':raw.get('rubric',[]),
       'minutes':number(raw.get('minutes')),'signature':raw.get('decisive_signature',''),
       'category':get('题目类别A/B/C/D','category','B' if original else ''),'idea':get('可借鉴命题思想','origin'),
       'provenance':get('原始文件来源','origin'),'references':raw.get('reference_ids',[]),
       'source_body_ready':ready,'review':'已核验来源' if ready and not blocked else '待人工检查',
       'render_ready':bool(stem and (get('题型','type')!='选择题' or len(options)==4)),
       'source_assets':raw.get('_source_assets',{}),'similarity_groups':raw.get('关联组ID',[]),
       'raw_payload':copy.deepcopy(raw),'notes':text(raw.get('备注',''))}
    if not q['id'] or q['type'] not in ('选择题','填空题','解答题'):raise ValueError('缺少稳定ID或题型不支持')
    if len(q['stem'])>30000 or len(q['solution'])>100000:raise ValueError('单题正文超过安全长度')
    match=re.match(r'^\s*([ABCD])(?:\b|[；;，,、：:\s]|$)',answer)
    q['correct_option']=match.group(1) if q['type']=='选择题' and len(options)==4 and match else None
    q['accepted_answers']=raw.get('accepted_answers',[]) if isinstance(raw.get('accepted_answers',[]),list) else []
    q['auto_grade_ready']=bool(q['correct_option'] or (q['type']=='填空题' and (numeric(answer) is not None or q['accepted_answers'])))
    q['eligible']=bool(ready and not blocked and q['render_ready'] and answer and q['solution'])
    q['compatibility']=q['original_points'] in (5,10,12) and (original or (source=='历年真题' and number(q['year'],0)>=2021))
    q['payload_hash']=digest(raw)
    return prepare(q)

def parse_source(data, trusted_original=False):
    if isinstance(data,list):rows=data
    else:rows=data.get('items',data.get('questions',[]))
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('题目列表格式错误或超过10000题')
    ids=[r.get('ID') for r in rows if isinstance(r,dict)]
    if len(ids)!=len(set(ids)):raise ValueError('同一文件中有重复ID，未提交导入')
    original=bool(rows and 'stem' in rows[0] and '题干' not in rows[0])
    result=[]; errors=[]
    for i,r in enumerate(rows):
        try:result.append(normalize(r,original,verified_original=trusted_original and original))
        except (ValueError,TypeError,AttributeError) as e:errors.append({'row':i+1,'id':r.get('ID') if isinstance(r,dict) else None,'error':str(e)})
    if errors:raise ValueError('导入被取消：'+json.dumps(errors[:10],ensure_ascii=False))
    return result

def numeric(value):
    s=str(value).strip().replace('−','-')
    if len(s)>100 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d+)?|\d+/[+-]?\d+)',s):return None
    try:return Fraction(s)
    except (ValueError,ZeroDivisionError):return None

def grade(q,response,points):
    if not str(response).strip():return {'state':'未作答','score':0 if points is not None else None,'origin':'自动','response':response}
    if q['type']=='选择题' and q.get('correct_option'):
        if str(response) not in 'ABCD' or len(str(response))!=1:raise ValueError('选择题只能填写A/B/C/D')
        correct=response==q['correct_option']
    elif q['type']=='填空题':
        accepted=q.get('accepted_answers',[])
        if accepted:correct=str(response).strip() in accepted
        elif numeric(q.get('grading_answer',q['answer'])) is not None and numeric(response) is not None:correct=numeric(response)==numeric(q.get('grading_answer',q['answer']))
        else:return {'state':'待人工检查','score':None,'origin':'待评分','response':response}
    else:return {'state':'待人工检查','score':None,'origin':'待评分','response':response}
    return {'state':'正确' if correct else '错误','score':points if correct else (0 if points is not None else None),'origin':'自动','response':response}

def slot(n):
    return {'type':'选择题' if n<=10 else '填空题' if n<=16 else '解答题',
            'subject':'线性代数' if n in (8,9,10,16,22) else '高等数学','points':5 if n<=16 else 10 if n==17 else 12}

def duplicate_key(q):return q.get('origin_id',q['id'])

def conflicts(q,used):
    if any(duplicate_key(q)==duplicate_key(u) or digest(q['stem'])==digest(u['stem']) for u in used):return True
    confirmed=set(g for g in q.get('similarity_groups',[]) if g.startswith(('DUP-','EXACT-')))
    return bool(confirmed.intersection(g for u in used for g in u.get('similarity_groups',[])))

def structure(items,mode):
    errors=[]; seen=[]
    if mode=='standard' and len(items)!=22:errors.append('标准卷必须恰好22题')
    for i,it in enumerate(items,1):
        q=it['question'];p=it.get('points')
        if not q.get('eligible'):errors.append(f'第{i}题正文、答案、核验或显示条件不满足')
        if conflicts(q,seen):errors.append(f'第{i}题与前题重复或属于已确认重复组')
        seen.append(q)
        if mode=='standard':
            s=slot(i)
            if any(q[k]!=s[k] for k in ('type','subject')) or p!=s['points']:errors.append(f'第{i}题题型、科目或分值不符合模板')
            if not q.get('compatibility') or q.get('original_points')!=p:errors.append(f'第{i}题缺少当前赋分适配依据')
        if p is not None and (not isinstance(p,(int,float)) or p<0 or p>150):errors.append(f'第{i}题分值不合法')
        rubric=q.get('rubric')
        if rubric and (p is None or sum(number(r.get('points'),0) for r in rubric)!=p):errors.append(f'第{i}题评分步骤与卷面分值不一致')
    return {'passed':not errors,'errors':errors,'count':len(items),'points':sum(it.get('points') or 0 for it in items),
            'subjects':dict(sum_subjects(items))}

def sum_subjects(items):
    c=defaultdict(float)
    for it in items:c[it['question']['subject']]+=it.get('points') or 0
    return c

CHAPTERS={'函数、极限与连续':'函数极限连续','一元函数微分学':'一元微分','一元函数积分学':'一元积分','定积分应用':'定积分应用','多元函数微分学':'多元微分','常微分方程':'微分方程'}
def design(items,rules):
    qs=[it['question'] for it in items];scores=[it.get('points') or 0 for it in items];total=sum(scores)
    warnings=[];unknown=['2027官方大纲正文逐条范围：待人工检查','按评分步骤分配跨知识点分值及H6完整任务：待人工检查','题意正确性与题间答案泄露：需人工审卷']
    chapters=defaultdict(float);codes=Counter();methods=Counter();models=Counter()
    for q,p in zip(qs,scores):
        chapters[CHAPTERS.get(q['chapter'],q['chapter'])]+=p;codes[q.get('code','')]+=1
        if q.get('signature'):methods[q['signature']]+=1
        if q.get('model'):models[q['model']]+=1
    for chapter,limits in rules.get('coverage',{}).get('high_math_primary_points',{}).items():
        if not limits[0]<=chapters[chapter]<=limits[1]:warnings.append(f'{chapter}主标签{chapters[chapter]:g}分，建议{limits[0]}—{limits[1]}分')
    d=[q.get('difficulty') for q in qs];c=[q.get('calculation') for q in qs];t=[q.get('minutes') for q in qs]
    def check(value,bounds,label):
        if not bounds[0]<=value<=bounds[1]:warnings.append(f'{label}{value:.2f}，建议{bounds[0]}—{bounds[1]}')
    dist=Counter('基础' if x and x<=2 else '中档' if x==3 else '较难' if x else '未知' for x in d)
    mean=None;weighted=None
    if all(x is not None for x in d) and d:
        mean=sum(d)/len(d);weighted=sum(x*p for x,p in zip(d,scores))/total if total else None
        check(mean,rules['difficulty']['mean'],'难度均值')
        if weighted is not None:check(weighted,rules['difficulty']['weighted_mean'],'分值加权难度')
        for label,key in [('基础','basic'),('中档','medium'),('较难','hard')]:
            check(dist[label],rules['difficulty'][key+'_count'],label+'题数')
            if total:check(sum(p for x,p in zip(d,scores) if ('基础' if x<=2 else '中档' if x==3 else '较难')==label)/total,rules['difficulty'][key+'_share'],label+'分值占比')
    else:unknown.append('难度指标存在未知')
    calc_mean=None
    if all(x is not None for x in c) and c:
        calc_mean=sum(c)/len(c);check(calc_mean,rules['computation']['mean'],'计算量均值')
        if c.count(1)<rules['computation']['low_count_min']:warnings.append('低计算量题数不足')
        if c.count(3)>rules['computation']['high_count_max']:warnings.append('高计算量题数过多')
        if any(q['type']!='解答题' and x==3 for q,x in zip(qs,c)):warnings.append('小题存在高计算量')
        if any(c[i]==c[i+1]==3 for i in range(len(c)-1)):warnings.append('相邻题存在高计算量')
    else:unknown.append('计算量指标存在未知')
    minutes=sum(t) if t and all(x is not None for x in t) else None
    if minutes is None:unknown.append('用时未齐全，不作零分钟估算')
    else:
        check(minutes,rules['time']['question_sum'],'作答预估分钟')
        for typ,k in [('选择题','choice'),('填空题','fill'),('解答题','answer')]:check(sum(x for q,x in zip(qs,t) if q['type']==typ),rules['time'][k],typ+'预估分钟')
    if any(v>rules['duplicates']['same_primary_code_max'] for k,v in codes.items() if k):warnings.append('同主知识点代码超过建议重复次数')
    if any(v>rules['duplicates']['same_third_level_model_max'] for v in models.values()):warnings.append('同三级模型重复，请核对任务是否实质不同')
    if any(v>rules['duplicates']['same_decisive_method_signature_max'] for v in methods.values()):warnings.append('同关键方法签名重复过多')
    primary_points=defaultdict(float)
    for q,p in zip(qs,scores):primary_points[q.get('code','')]+=p
    for family in rules['coverage']['minimum_families']:
        pts=sum(primary_points[k] for k in family['codes'])
        if pts<family['minimum_points']:warnings.append(f"{family['id']}主标签覆盖{pts:g}分；最低{family['minimum_points']}分须按有效得分步骤复核")
    if any(q.get('source')=='880习题' for q in qs):unknown.append('880具体任务赋分与改编价值需人工确认')
    if any(not q.get('signature') for q in qs):unknown.append('部分题缺少关键判断签名；不能证明任务无重复')
    return {'chapters':dict(chapters),'codes':dict(codes),'sources':dict(Counter(q['source'] for q in qs)),
            'difficulty':dict(dist),'mean_difficulty':mean,'weighted_difficulty':weighted,'calculation_mean':calc_mean,
            'minutes_estimate':minutes,'warnings':warnings,'pending':unknown,'rule_version':rules['version'],
            'quality_statement':'结构通过不等于数学审卷通过或真题水平；难度与用时均为预估'}

def assemble(questions,seed,rules,locked=None,budget=3000,cancel=lambda:False):
    locked=locked or {}; rng=random.Random(str(seed)); pools={};counts={}
    for n in range(1,23):
        s=slot(n);pool=[q for q in sorted(questions,key=lambda x:x['id']) if q['eligible'] and q['compatibility'] and q['original_points']==s['points'] and q['type']==s['type'] and q['subject']==s['subject']]
        rng.shuffle(pool)
        if n in locked:pool=[q for q in pool if q['id']==locked[n]]
        pools[n]=pool;counts[n]=len(pool)
    if any(not p for p in pools.values()):return {'status':'候选不足','counts':counts,'reason':'存在题位没有可靠候选，未放宽规则'}
    order=sorted(pools,key=lambda n:(len(pools[n]),n));nodes=0;best=None;bestpenalty=10**9
    def walk(depth,picked):
        nonlocal nodes,best,bestpenalty
        if nodes>=budget or cancel():return
        nodes+=1
        if depth==22:
            items=[{'number':n,'question':picked[n],'points':slot(n)['points'],'locked':n in locked} for n in range(1,23)]
            result=design(items,rules);penalty=len(result['warnings'])
            if penalty<bestpenalty:best=items;bestpenalty=penalty
            return
        n=order[depth]
        for q in pools[n]:
            if conflicts(q,list(picked.values())):continue
            picked[n]=q;walk(depth+1,picked);picked.pop(n)
            if nodes>=budget or cancel():break
    walk(0,{})
    if cancel():return {'status':'已取消','nodes':nodes,'counts':counts}
    if best:return {'status':'已生成','items':best,'nodes':nodes,'counts':counts,'search_complete':nodes<budget,'design':design(best,rules)}
    return {'status':'预算耗尽' if nodes>=budget else '约束冲突','nodes':nodes,'counts':counts,'reason':'预算内未找到结果，不代表已证明无解' if nodes>=budget else '所有合法组合已检查，重复/锁定等硬约束冲突'}
