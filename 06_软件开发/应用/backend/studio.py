"""Original-question workflow. Candidates stay outside the bank until an explicit review."""
import copy, json,re
from fastapi import APIRouter, HTTPException
from .domain import digest, normalize, number
from .store import dumps, now, uid

GATES=('数学正确性','答案唯一性或解集完整','条件充分与边界','范围','选项或评分','实质排重','公式显示','来源可靠')

def create_router(store,import_questions,policy_dir=None):
    router=APIRouter(prefix='/api/studio')
    with store.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,version INTEGER NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,version INTEGER NOT NULL,state TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candidate_history(id TEXT PRIMARY KEY,candidate_id TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS review_records(id TEXT PRIMARY KEY,candidate_id TEXT NOT NULL,candidate_version INTEGER NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL);
        ''')

    def require(ok,message,status=400):
        if not ok:raise HTTPException(status,detail=message)

    def read(table,identifier):
        with store.connect() as c:r=c.execute(f'SELECT payload FROM {table} WHERE id=?',(identifier,)).fetchone()
        require(r is not None,'任务或候选不存在',404);return json.loads(r[0])

    def candidates(tid=None):
        with store.connect() as c:
            rows=c.execute('SELECT payload FROM candidates'+(' WHERE task_id=?' if tid else '')+' ORDER BY created DESC', (tid,) if tid else ()).fetchall()
        return [json.loads(r[0]) for r in rows]

    @router.get('/summary')
    def summary():
        rows=candidates()
        with store.connect() as c:n=c.execute('SELECT count(*) FROM tasks').fetchone()[0]
        with store.connect() as c:r=c.execute("SELECT value FROM meta WHERE key='model_settings'").fetchone()
        configured=bool(r and json.loads(r[0]).get('has_key') and (store.path.parent/'模型凭据.dpapi').exists())
        return {'tasks':n,'candidates':len(rows),'approved':sum(r['state'] in ('已审核入库','AI自动审核入库') for r in rows),'pending':sum(r['state'] in ('待审题','AI审核中') for r in rows),
                'automatic_approved':sum(r['state']=='AI自动审核入库' for r in rows),'review_mode':'AI自动审核入库，无人工确认要求',
                'model_connected':configured,'model_status':'已配置（未等同连接验证）' if configured else '尚未配置模型API；当前可导出命题任务、导入生成结果','gates':GATES}

    @router.get('/tasks')
    def list_tasks():
        with store.connect() as c:rows=[json.loads(r[0]) for r in c.execute('SELECT payload FROM tasks ORDER BY created DESC')]
        counts={}
        for candidate in candidates():counts[candidate['task_id']]=counts.get(candidate['task_id'],0)+1
        return [dict(r,candidate_count=counts.get(r['id'],0)) for r in rows]

    @router.post('/tasks')
    def create_task(body:dict):
        subject=body.get('subject','高等数学');kind=body.get('type','选择题');chapter=str(body.get('chapter',''))
        require(subject in ('高等数学','线性代数') and kind in ('选择题','填空题','解答题'),'科目或题型错误')
        require(chapter and len(chapter)<=100,'请选择章节');difficulty=body.get('difficulty',3);count=body.get('candidate_count',3)
        require(type(difficulty) is int and 1<=difficulty<=5,'难度应为1—5');require(type(count) is int and 1<=count<=6,'候选数应为1—6')
        target=str(body.get('target','')).strip();require(5<=len(target)<=2000,'考查目标请填写5—2000字')
        points=body.get('points',5 if kind!='解答题' else 12);require(points in (5,10,12),'目标分值应为5、10或12')
        require((kind=='解答题')==(points in (10,12)),'题型和目标分值不匹配')
        pool=[q for q in store.questions() if q['eligible'] and q['subject']==subject and q['chapter']==chapter]
        pool.sort(key=lambda q:(q['source']!='历年真题',q['type']!=kind,-(number(q['year'],0) or 0),abs((q['difficulty'] or 3)-difficulty),q['id']))
        exams=[q for q in pool if q['source']=='历年真题'][:3];others=[q for q in pool if q['source'] in ('880','880习题')][:1]
        refs=[{k:q.get(k) for k in ('id','revision','source','year','chapter','type','stem','options','answer','solution','core','method','provenance','difficulty')} for q in exams+others]
        policy=[]
        if policy_dir and (policy_dir/'manifest.json').exists():
            manifest=json.loads((policy_dir/'manifest.json').read_text(encoding='utf-8'))
            for doc in manifest:
                content=(policy_dir/doc['file']).read_text(encoding='utf-8');windows=[content[:650]]
                for needle in (chapter,kind,'近5年','近五年','改编','计算量'):
                    match=re.search(re.escape(needle),content)
                    if match:windows.append(content[max(0,match.start()-100):match.start()+700])
                excerpt='\n...\n'.join(dict.fromkeys(windows))[:2300]
                policy.append({'source':doc['source'],'sha256':doc['sha256'],'read_scope':'实际摘读片段，不声称核读全文或官方大纲','excerpt':excerpt})
        task={'id':uid('TASK'),'version':1,'created':now(),'title':f'{chapter} · {kind}','subject':subject,'chapter':chapter,'type':kind,
              'difficulty':difficulty,'points':points,'candidate_count':count,'target':target,'references':refs,
              'reference_warning':None if exams else '该章节缺少可靠真题正文参考，不能宣称已有充分真题依据',
              'state':'等待候选结果','model_status':'尚未调用模型API','policy_evidence':policy}
        with store.connect() as c:c.execute('INSERT INTO tasks VALUES(?,?,?,?)',(task['id'],1,task['created'],dumps(task)));store.event(c,'task_created',{'id':task['id'],'refs':[r['id'] for r in refs]})
        return task

    @router.get('/tasks/{tid}')
    def get_task(tid:str):return dict(read('tasks',tid),candidates=candidates(tid))

    @router.get('/tasks/{tid}/prompt')
    def prompt(tid:str):
        t=read('tasks',tid)
        instructions=(f"命制{t['candidate_count']}道考研数学二风格的原创{t['type']}候选。科目：{t['subject']}；章节：{t['chapter']}；"
          f"目标难度{t['difficulty']}/5（预估）；分值{t['points']}。考查目标：{t['target']}。\n"
          '真题优先于训练书。每题说明考查价值、关键判断、暴露的误解及参考差异。不得复制原题或仅换数字，不以计算冗长与冷门技巧代替质量。\n'
          '完整求解；选择题四个选项并逐项检查，填空答案明确，解答题条件充分且评分步骤合计等于目标分值。'
          '未知标记待人工检查。生成结果只能作为待审题候选，不得自行声明已通过审核。\n'
          '只输出JSON对象：{"schema":"math2-candidates-1","candidates":[...]}。每个候选字段：'
          'stem（题干，公式用$...$）、options（选择题四项，其余空数组）、parts（分问数组）、answer、solution（完整过程字符串）、'
          'core、method、value、misconception、source_difference、difficulty（1—5）、calculation（1—3）、minutes（预估）、'
          'rubric（[{"step":"...","points":数值}]，不得虚构缺失信息）、risk、reference_ids（实际参考ID列表）。knowledge（二级知识点）、code（有依据的既有知识点代码）、alternative、errors、key可另列，未知留空并标记。\n'
          '选择题answer只填写A/B/C/D，说明写入solution。不要仅凭自评宣布达真题水平。\n'
          '已有蓝图、规范与880分析的实际摘读片段（引用范围仅限片段）：\n'+json.dumps(t.get('policy_evidence',[]),ensure_ascii=False,indent=2)+'\n'
          '已核验来源参考如下（只读取这些记录，不声明全库排重完成）：\n'+json.dumps(t['references'],ensure_ascii=False,indent=2))
        return {'task_id':tid,'prompt':instructions,'template_version':'studio-1','references_hash':digest(t['references']),
                'result_schema':{'schema':'math2-candidates-1','candidates':[]}}

    def validate_raw(raw,t):
        require(isinstance(raw,dict),'候选必须为JSON对象')
        for k in ('stem','answer','solution','core','value','source_difference'):
            require(isinstance(raw.get(k),str) and bool(raw[k].strip()) and len(raw[k])<30000,f'候选字段{k}缺失或格式错误')
        options=raw.get('options',[]);require(isinstance(options,list) and all(isinstance(x,str) and x.strip() for x in options),'选项格式错误')
        require((len(options)==4 if t['type']=='选择题' else len(options)==0),'选择题必须有四选项，其他题型不应包含选项')
        if t['type']=='选择题':require(raw['answer'].strip() in ('A','B','C','D'),'选择题标准答案只填A/B/C/D，说明写入solution')
        parts=raw.get('parts',[]);require(isinstance(parts,list) and all(isinstance(x,str) for x in parts),'分问格式错误')
        require(type(raw.get('difficulty')) is int and raw.get('difficulty') in (1,2,3,4,5) and type(raw.get('calculation')) is int and raw.get('calculation') in (1,2,3),'难度或计算量超出范围')
        require(isinstance(raw.get('minutes'),(int,float)) and 0<raw['minutes']<=90,'推荐用时应为0—90分钟的预估')
        rubric=raw.get('rubric',[]);require(isinstance(rubric,list),'评分步骤格式错误')
        if rubric:
            require(all(isinstance(x,dict) and isinstance(x.get('step'),str) and isinstance(x.get('points'),(int,float)) and x['points']>0 for x in rubric),'评分步骤需要文字和正分值')
            require(sum(x['points'] for x in rubric)==t['points'],'评分步骤合计与目标分值不一致')
        if t['type']=='解答题':require(bool(rubric),'解答题需完整评分步骤才能进入候选工作流')
        refs=raw.get('reference_ids',[]);require(isinstance(refs,list) and set(refs)<={r['id'] for r in t['references']},'包含本任务未核读的参考ID')
        return copy.deepcopy(raw)

    @router.post('/tasks/{tid}/candidates')
    def import_candidates(tid:str,body:dict):
        t=read('tasks',tid);require(body.get('schema')=='math2-candidates-1','结果schema应为math2-candidates-1')
        rows=body.get('candidates');require(isinstance(rows,list) and 1<=len(rows)<=6,'一次导入1—6道候选')
        validated=[validate_raw(raw,t) for raw in rows];created=[];dupes=[]
        with store.connect() as c:
            existing=[json.loads(r[0]) for r in c.execute('SELECT payload FROM candidates WHERE task_id=?',(tid,))]
            hashes={digest(r['raw']) for r in existing}
            for raw in validated:
                h=digest(raw)
                if h in hashes:dupes.append(h);continue
                candidate={'id':uid('CAND'),'task_id':tid,'version':1,'created':now(),'state':'待审题','raw':raw,'review':None,'bank_id':None,
                           'import_origin':'人工导入生成结果；模型身份未由软件验证'}
                c.execute('INSERT INTO candidates VALUES(?,?,?,?,?,?)',(candidate['id'],tid,1,'待审题',candidate['created'],dumps(candidate)))
                created.append(candidate);hashes.add(h)
            store.event(c,'candidate_import',{'task':tid,'created':[x['id'] for x in created],'duplicates':len(dupes)})
        return {'added':len(created),'duplicates':len(dupes),'candidates':created}

    @router.get('/candidates')
    def list_candidates():
        result=[]
        for v in candidates():
            t=read('tasks',v['task_id'])
            result.append({k:v[k] for k in ('id','task_id','version','state','created')}|{'stem':v['raw']['stem'],'type':t['type']})
        return result

    @router.get('/candidates/{cid}')
    def get_candidate(cid:str):
        candidate=read('candidates',cid)
        with store.connect() as c:history=[json.loads(r[0]) for r in c.execute('SELECT payload FROM review_records WHERE candidate_id=? ORDER BY created DESC',(cid,))]
        from .presentation import format_text
        # Display annotations only. Stored model responses and review evidence
        # remain unchanged, and admission never relies on these annotations.
        for record in [candidate.get('auto_review',{}),*history]:
            for entry in record.get('history',[]):
                for solve in entry.get('blind_solutions',[]):
                    solve['display_solution'],solve['display_issues']=format_text(solve.get('solution',''))
        return dict(candidate,task=read('tasks',candidate['task_id']),review_history=history)

    @router.put('/candidates/{cid}')
    def edit_candidate(cid:str,body:dict):
        with store.connect() as c:
            row=c.execute('SELECT payload FROM candidates WHERE id=?',(cid,)).fetchone();require(row is not None,'候选不存在',404);old=json.loads(row[0])
            require(body.get('version')==old['version'],'候选已在其他页面修改，请刷新',409)
            require(old['state'] not in ('已审核入库','AI自动审核入库','AI审核中'),'已入库或正在审核的版本不可改写，请等待或新建任务')
            t=read('tasks',old['task_id']);raw=validate_raw(body.get('raw'),t)
            c.execute('INSERT INTO candidate_history VALUES(?,?,?,?)',(uid('CH'),cid,now(),dumps(old)))
            new=dict(old,raw=raw,version=old['version']+1,state='待审题',review=None,derivation=None)
            c.execute('UPDATE candidates SET version=?,state=?,payload=? WHERE id=?',(new['version'],new['state'],dumps(new),cid))
        return new

    @router.get('/candidates/{cid}/blind')
    def blind(cid:str):
        v=read('candidates',cid);t=read('tasks',v['task_id']);raw=v['raw']
        d=v.get('derivation') or {}
        return {'candidate_id':cid,'version':v['version'],'type':t['type'],'points':t['points'],'stem':raw['stem'],'options':raw.get('options',[]),'parts':raw.get('parts',[]),'saved_derivation':d.get('text','') if d.get('version')==v['version'] else ''}

    @router.post('/candidates/{cid}/derivation')
    def save_derivation(cid:str,body:dict):
        with store.connect() as c:
            row=c.execute('SELECT payload FROM candidates WHERE id=?',(cid,)).fetchone();require(row is not None,'候选不存在',404);v=json.loads(row[0])
            require(body.get('version')==v['version'],'题面版本已变化，请重新解题',409)
            text=body.get('derivation','');require(isinstance(text,str) and 20<=len(text.strip())<=30000,'请保存20—30000字的真实重解推导')
            v['derivation']={'version':v['version'],'text':text,'created':now(),'origin':'用户题面重解'}
            c.execute('UPDATE candidates SET payload=? WHERE id=?',(dumps(v),cid))
        return {'saved':True,'version':v['version']}

    @router.get('/candidates/{cid}/compare')
    def compare(cid:str):
        v=read('candidates',cid);d=v.get('derivation') or {}
        require(d.get('version')==v['version'] and len(d.get('text',''))>=20,'请先保存当前题面的重解推导',409)
        return get_candidate(cid)

    @router.post('/candidates/{cid}/review')
    def review(cid:str,body:dict):
        with store.connect() as c:
            row=c.execute('SELECT payload FROM candidates WHERE id=?',(cid,)).fetchone();require(row is not None,'候选不存在',404);candidate=json.loads(row[0])
            require(body.get('version')==candidate['version'],'审核题面版本冲突，请重新打开',409)
            require(candidate['state'] not in ('已审核入库','AI自动审核入库','AI审核中'),'此版本已入库或正在自动审核',409)
            decision=body.get('decision','暂缓');require(decision in ('通过','修改','淘汰','暂缓'),'审核结论不支持')
            gates=body.get('gates',{});require(isinstance(gates,dict) and set(gates)<=set(GATES),'审核项目格式错误')
            derivation=str(body.get('derivation','')).strip();note=str(body.get('note','')).strip();ratings=body.get('ratings',{})
            require(len(derivation)<=30000 and len(note)<=5000,'审核记录超过长度限制')
            if decision=='通过':
                require(all(gates.get(k) is True for k in GATES),'全部准入项须明确勾选通过，否则暂缓或退回')
                require(len(derivation)>=20 and len(note)>=5,'通过需保存题面重解推导和采纳依据')
                saved=candidate.get('derivation') or {}
                require(saved.get('version')==candidate['version'] and saved.get('text')==derivation,'请先保存当前版本的题面重解推导',409)
                require(ratings.get('style') in (1,2,3,4,5) and ratings.get('value') in (1,2,3,4,5),'请输入风格和考查价值评级')
                require(ratings.get('similarity') in ('低','中'),'高风险或未知相似性不能入库')
            record={'id':uid('REVIEW'),'candidate_id':cid,'candidate_version':candidate['version'],'created':now(),'decision':decision,'gates':gates,
                    'derivation':derivation,'note':note,'ratings':ratings,'origin':'用户人工审核；不是系统数学正确性证明'}
            c.execute('INSERT INTO review_records VALUES(?,?,?,?,?)',(record['id'],cid,candidate['version'],record['created'],dumps(record)))
            candidate.update(review=record,state={'通过':'已审核入库','修改':'退回修改','淘汰':'已淘汰','暂缓':'待人工检查'}[decision])
            if decision=='通过':
                t=read('tasks',candidate['task_id']);raw=candidate['raw'];bankraw=dict(raw,ID='ORIGINAL-'+cid,type=t['type'],points=t['points'],subject=t['subject'],chapter=t['chapter'],
                    origin='AI候选经用户人工审核；具体模型由任务记录确认',category='B',studio_task=t['id'],studio_candidate=cid,studio_review=record)
                q=normalize(bankraw,original=True,verified_original=True);q['source']='审核后原创题';q['review']='用户人工审核通过';q['provenance']=f"任务{t['id']} / 候选{cid} / 审核{record['id']}"
                q['idea']=raw['value'];q['errors']=raw.get('misconception','');q['references_snapshot']=t['references']
                q['ratings']=ratings;q['import_hash']=digest(bankraw);q['revision']=uid('R')
                c.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(q['revision'],q['id'],q['payload_hash'],now(),dumps(q)))
                c.execute('INSERT INTO questions VALUES(?,?)',(q['id'],q['revision']));candidate['bank_id']=q['id']
            c.execute('UPDATE candidates SET state=?,payload=? WHERE id=?',(candidate['state'],dumps(candidate),cid));store.event(c,'candidate_review',{'candidate':cid,'decision':decision})
        return candidate

    return router
