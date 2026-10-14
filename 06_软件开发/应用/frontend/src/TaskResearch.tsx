import {useEffect,useMemo,useState} from 'react';
import {ArrowRight,Search} from 'lucide-react';
import {api,MaterialFilter,Paper,Question} from './types';
import {MathText,QuestionBody} from './MathText';
import AnalysisDrawer from './AnalysisDrawer';
import {currentInsight, topicInsights} from './taskInsights';

export type ResearchRow={id:string;year:number;number:number;subject:string;chapter:string;point:string;model:string;type:string;points:number;difficulty:number|null;calculation:number|null;core:string;method:string;secondary:string;issue:string};
type Index={total:number;items:Question[]};
let indexPromise:Promise<Map<string,Question>>|undefined;
const detailCache=new Map<string,Promise<Question>>();
function loadIndex(){
  if(!indexPromise)indexPromise=(async()=>{
    const first=await api<Index>('/questions?source=历年真题&size=100&page=1');
    const rest=await Promise.all(Array.from({length:Math.ceil(first.total/100)-1},(_,i)=>api<Index>(`/questions?source=历年真题&size=100&page=${i+2}`)));
    return new Map([first,...rest].flatMap(p=>p.items).map(q=>[q.id,q]));
  })().catch(e=>{indexPromise=undefined;throw e});
  return indexPromise;
}
function loadDetail(row:ResearchRow,index?:Question){
  const key=row.id+'|'+(index?.revision||'');
  if(!detailCache.has(key))detailCache.set(key,api<Question>(`/questions/${encodeURIComponent(row.id)}`).then(q=>{
    if(q.source!=='历年真题'||q.year!==row.year||Number(q.original_number)!==row.number)throw new Error('题目对应关系待人工检查');
    return q;
  }).finally(()=>detailCache.delete(key)));
  return detailCache.get(key)!;
}
function usable(q?:Question){return !!q?.eligible&&q.source_body_ready!==false&&q.render_ready!==false&&!q.presentation_issues?.length}
const level=(n:number|null|undefined)=>n==null?'待人工检查':`${n}级 · ${['','基础','较易','中等','较难','高区分度'][n]||'待人工检查'}`;
const cost=(n:number|null|undefined)=>n==null?'待人工检查':`${n}级 · ${['','低','中','高'][n]||'待人工检查'}`;
function AnalysisFields({row,q}:{row:ResearchRow;q?:Question}){
  const insight=q&&usable(q)?currentInsight(row.id,q.revision):undefined;
  return <section className="question-insight">{insight?<>
    <div className="insight-heading"><h3>解题要点</h3></div>
    <p className="decisive-insight">{insight.decision}</p>
    <p className="insight-pitfall"><b>易错点</b><span>{insight.pitfall}</span></p>
    <details className="insight-full"><summary>查看完整分析</summary><dl className="task-analysis-fields"><div><dt>给定信息</dt><dd>{insight.conditions}</dd></div><div><dt>作答目标</dt><dd>{insight.objective}</dd></div><div><dt>难度来源</dt><dd>{insight.difficultyReason}</dd></div><div><dt>选题用途</dt><dd>{insight.selection}</dd></div></dl>
      <details className="original-analysis"><summary>已有分析记录</summary><dl className="task-analysis-fields"><div><dt>原考法记录</dt><dd>{row.core||'待人工检查'}</dd></div><div><dt>主要方法</dt><dd>{row.method||'待人工检查'}</dd></div><div><dt>综合知识点</dt><dd>{row.secondary||'未记录额外知识点'}</dd></div>{q?.idea&&<div><dt>原命题思想记录</dt><dd>{q.idea}</dd></div>}</dl></details>
    </details>
  </>:<p className="task-pending">这道题的关键判断与评级理由尚未完成专题提炼，待人工检查；可先阅读题干与已有解答。</p>}
  <div className="insight-rating">难度 {level(q?.difficulty??row.difficulty)} · 计算量 {cost(q?.calculation??row.calculation)}</div>
  </section>;
}
function QuestionAnalysis({row,index,onFind,onAdd,selected}:{row:ResearchRow;index?:Question;onFind:(filter:MaterialFilter)=>void;onAdd:(id:string)=>void;selected:boolean}){
  const [q,setQ]=useState<Question>(),[error,setError]=useState('');
  useEffect(()=>{let active=true;setQ(undefined);setError('');loadDetail(row,index).then(v=>{if(active)setQ(v)}).catch(e=>{if(active)setError(String(e))});return()=>{active=false}},[row.id,index?.revision]);
  return <><div className="task-question-meta">{row.type} · {row.points}分 · {row.chapter}</div>{error?<p className="error-text">{error}</p>:!q?<p role="status">正在读取题目…</p>:usable(q)?<section className="task-stem"><QuestionBody question={q}/></section>:<p className="task-pending">正文暂不用于展示与选题，待人工检查。</p>}<AnalysisFields row={row} q={q}/>{q&&usable(q)&&<details className="task-solution"><summary>标准答案与解答</summary><p><MathText text={q.answer}/></p><MathText text={q.solution}/></details>}<div className="actions"><button className="secondary" onClick={()=>onFind({search:row.model,chapter:row.chapter,subject:row.subject,type:row.type,difficulty:row.difficulty})}>筛选同类素材</button><button disabled={!usable(q)} onClick={()=>onAdd(row.id)}>{selected?'已加入选题':'加入选题'}</button></div></>;
}
function TaskComparison({rows,index,onFind}:{rows:ResearchRow[];index:Map<string,Question>;onFind:(filter:MaterialFilter)=>void}){
  const [questions,setQuestions]=useState<Question[]>([]),[error,setError]=useState('');
  useEffect(()=>{let active=true;Promise.all(rows.map(r=>loadDetail(r,index.get(r.id)))).then(q=>{if(active)setQuestions(q)}).catch(e=>{if(active)setError(String(e))});return()=>{active=false}},[rows.map(r=>r.id).join('|')]);
  if(error)return <p className="error-text">{error}</p>;
  if(questions.length!==2)return <p role="status">正在读取两题…</p>;
  if(questions.some(q=>!usable(q)))return <p className="task-pending">所选题的正文使用状态已变化，暂不进行比较。待人工检查。</p>;
  const ideas=rows.map((r,i)=>currentInsight(r.id,questions[i].revision));
  return <>{ideas.every(Boolean)&&<section className="comparison-focus"><h3>先比较考查任务</h3><p>{ideas[0]!.family===ideas[1]!.family?`两题的主要任务同属“${ideas[0]!.family}”，但条件与判断链仍需比较。`:`两题分别考查“${ideas[0]!.family}”与“${ideas[1]!.family}”，不能只按共同知识点互换。`}</p><div className="comparison-columns">{ideas.map((idea,i)=><div key={rows[i].id}><b>{rows[i].year}年 · 第{rows[i].number}题</b><p>{idea!.decision}</p><small>{idea!.selection}</small></div>)}</div></section>}<div className="comparison-columns">{rows.map((r,i)=><article key={r.id}><h3>{r.year} · 第{r.number}题</h3><span className="task-question-meta">{r.type} · {r.points}分</span><QuestionBody question={questions[i]}/><AnalysisFields row={r} q={questions[i]}/><details className="task-solution"><summary>标准答案与解答</summary><p><MathText text={questions[i].answer}/></p><MathText text={questions[i].solution}/></details></article>)}</div><div className="comparison-note">考法标签{rows[0].model===rows[1].model?'相同':'不同'}，请对照条件、所求和关键步骤判断是否重复考查；本页未自动判定数学任务等价。</div><button className="secondary" onClick={()=>onFind({search:rows[0].point,chapter:rows[0].chapter,subject:rows[0].subject,type:rows[0].type,difficulty:rows[0].difficulty})}>到素材库筛选替换题</button></>;
}

export default function TaskResearch({rows,onFind,onAdd,selected}:{rows:ResearchRow[];onFind:(filter:MaterialFilter)=>void;onAdd:(id:string)=>void;selected:string[]}){
  const [index,setIndex]=useState<Map<string,Question>>(),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const [chapter,setChapter]=useState('一元函数微分学'),[point,setPoint]=useState(''),[difficulty,setDifficulty]=useState(''),[search,setSearch]=useState(''),[model,setModel]=useState('');
  const [open,setOpen]=useState<ResearchRow>(),[comparison,setComparison]=useState<string[]>([]),[comparing,setComparing]=useState(false),[notice,setNotice]=useState('');
  useEffect(()=>{let active=true;loadIndex().then(v=>{if(active){setIndex(v);setError('')}}).catch(e=>{if(active)setError(String(e))});return()=>{active=false}},[retry]);
  const chapters=useMemo(()=>[...new Set(rows.map(r=>r.chapter))],[rows]);
  const current=chapters.includes(chapter)?chapter:chapters[0]||'';
  const points=useMemo(()=>[...new Set(rows.filter(r=>r.chapter===current).map(r=>r.point))],[rows,current]);
  const currentPoint=points.includes(point)?point:'';
  const comparedRows=comparison.flatMap(id=>{const r=rows.find(r=>r.id===id);return r?[r]:[]});
  const filtered=useMemo(()=>rows.filter(r=>r.chapter===current&&(!currentPoint||r.point===currentPoint)&&(!difficulty||String(r.difficulty)===difficulty)&&(!search||[r.model,r.core,r.method].join(' ').includes(search))),[rows,current,currentPoint,difficulty,search]);
  const tasks=useMemo(()=>{
    const map=new Map<string,ResearchRow[]>();for(const r of filtered){const list=map.get(r.model)||[];list.push(r);map.set(r.model,list)}
    return [...map].map(([name,rs])=>({name,rows:rs,ready:rs.filter(r=>index?.get(r.id)?.eligible).length,insights:rs.filter(r=>index?.get(r.id)?.eligible&&currentInsight(r.id,index?.get(r.id)?.revision)).length})).sort((a,b)=>b.insights-a.insights||b.ready-a.ready||b.rows.length-a.rows.length||a.name.localeCompare(b.name,'zh-CN'));
  },[filtered,index]);
  const task=tasks.find(t=>t.name===model)||tasks[0];
  const readyRows=(task?.rows||[]).filter(r=>index?.get(r.id)?.eligible).sort((a,b)=>b.year-a.year||a.number-b.number);
  const explained=readyRows.filter(r=>currentInsight(r.id,index?.get(r.id)?.revision));
  const overview=explained.length&&task?topicInsights[task.name]:undefined;
  const representatives:ResearchRow[]=[];
  for(const r of explained)if(representatives.length<4)representatives.push(r);
  for(const r of readyRows)if(representatives.length<3&&!representatives.some(x=>x.id===r.id))representatives.push(r);
  useEffect(()=>{setOpen(undefined);setComparing(false);setComparison(ids=>ids.filter(id=>rows.some(r=>r.id===id)))},[rows]);
  function compare(id:string){setNotice('');setComparison(ids=>{if(ids.includes(id))return ids.filter(x=>x!==id);if(ids.length===2){setNotice('一次比较两道题，请先移除一题。');return ids}return [...ids,id]})}
  return <section className="task-research">
    <div className="task-filters"><label>章节<select aria-label="考法章节" value={current} onChange={e=>{setChapter(e.target.value);setPoint('');setModel('');setComparison([]);setNotice('')}}>{chapters.map(c=><option key={c}>{c}</option>)}</select></label><label>考点<select aria-label="考法考点" value={currentPoint} onChange={e=>{setPoint(e.target.value);setModel('')}}><option value="">全部考点</option>{points.map(p=><option key={p}>{p}</option>)}</select></label><label>预估难度<select aria-label="考法难度" value={difficulty} onChange={e=>{setDifficulty(e.target.value);setModel('')}}><option value="">全部难度</option>{[1,2,3,4,5].map(d=><option value={d} key={d}>{level(d)}</option>)}</select></label><div className="search"><Search size={17}/><input aria-label="搜索考查任务" placeholder="搜索设问或解法" value={search} onChange={e=>{setSearch(e.target.value);setModel('')}}/></div></div>
    {error&&<div role="alert" className="alert error">题目使用状态读取失败。<button className="secondary" onClick={()=>setRetry(n=>n+1)}>重试</button></div>}
    <div className="task-workspace"><aside className="task-navigation"><h2>真实考法</h2>{tasks.map(t=><button key={t.name} className={'task-model-button'+(t===task?' active':'')} aria-pressed={t===task} onClick={()=>setModel(t.name)}><b>{t.name||'考法待人工检查'}</b>{t.insights>0&&<span className="insight-tag">已提炼</span>}<small>{t.rows.length}道真题{index?` · ${t.ready}道正文可用`:''}</small></button>)}{!tasks.length&&<p className="task-pending">当前筛选没有对应考法。</p>}</aside>
    <div className="task-content">{task?<><header className="task-content-header"><h2>{task.name||'考法待人工检查'}</h2><button className="secondary" onClick={()=>onFind({search:task.name,chapter:current,difficulty:difficulty?Number(difficulty):null})}>筛选同类素材 <ArrowRight size={15}/></button></header>
      {overview&&<section className="topic-insight"><h3>考法特征</h3><p>{overview.focus}</p><div className="topic-aspects-label">主要考查维度</div><ol>{overview.decisions.map(d=><li key={d}>{d}</li>)}</ol><div className="topic-selection"><b>题目任务差异</b><p>{overview.selection}</p></div></section>}
      {representatives.map(r=><article className="representative-question" key={r.id}><header><b>{r.year} · 第{r.number}题</b><span>{r.type} · {r.points}分</span></header><p>{currentInsight(r.id,index?.get(r.id)?.revision)?.objective||r.core||'考查任务待人工检查'}</p>{currentInsight(r.id,index?.get(r.id)?.revision)&&<div className="representative-decision"><b>关键判断</b><span>{currentInsight(r.id,index?.get(r.id)?.revision)!.decision}</span></div>}<div className="representative-meta"><span>难度 {level(r.difficulty)}</span><span>计算量 {cost(r.calculation)}</span></div><div className="actions"><button className="secondary" onClick={()=>setOpen(r)}>查看题干与分析</button><button className="secondary" aria-pressed={comparison.includes(r.id)} onClick={()=>compare(r.id)}>{comparison.includes(r.id)?'移出比较':'加入比较'}</button></div></article>)}
      {!index&&!error&&<p role="status">正在读取可用真题…</p>}{index&&!representatives.length&&<p className="task-pending">此考法目前只有分析索引，可靠正文仍待补核。</p>}
      <details className="task-all-questions"><summary>全部对应真题 · {task.rows.length}道</summary>{[...task.rows].sort((a,b)=>b.year-a.year||a.number-b.number).map(r=><div className="task-index-row" key={r.id}><span>{r.year} · 第{r.number}题 · {r.type}</span><button className="text-button" onClick={()=>setOpen(r)}>查看分析</button><button className="text-button" disabled={!index?.get(r.id)?.eligible} onClick={()=>compare(r.id)}>{comparison.includes(r.id)?'移出比较':'加入比较'}</button></div>)}</details>
    </>:<div className="empty"><Search size={32}/><p>没有匹配的考查任务</p></div>}</div></div>
    {comparedRows.length>0&&<div className="task-comparison-bar"><div>{comparedRows.map(r=><button className="secondary" key={r.id} onClick={()=>compare(r.id)}>{r.year} · 第{r.number}题 ×</button>)}</div><button disabled={comparedRows.length!==2} onClick={()=>setComparing(true)}>比较两题</button><button className="text-button" onClick={()=>{setComparison([]);setNotice('')}}>清空</button>{notice&&<span role="status">{notice}</span>}</div>}
    {open&&rows.some(r=>r.id===open.id)&&<AnalysisDrawer title={`${open.year}年 · 第${open.number}题`} subtitle={open.model} onClose={()=>setOpen(undefined)}><QuestionAnalysis row={open} index={index?.get(open.id)} onFind={onFind} onAdd={onAdd} selected={selected.includes(open.id)}/></AnalysisDrawer>}
    {comparing&&comparedRows.length===2&&index&&<AnalysisDrawer title="真题任务比较" onClose={()=>setComparing(false)} wide><TaskComparison rows={comparedRows} index={index} onFind={onFind}/></AnalysisDrawer>}
  </section>;
}

export function YearReference({rows,onFind,onAdd,selected}:{rows:ResearchRow[];onFind:(filter:MaterialFilter)=>void;onAdd:(id:string)=>void;selected:string[]}){
  const [year,setYear]=useState<number>(),[open,setOpen]=useState<ResearchRow>(),[index,setIndex]=useState<Map<string,Question>>(),[error,setError]=useState('');
  useEffect(()=>{let active=true;loadIndex().then(v=>{if(active)setIndex(v)}).catch(()=>{if(active)setError('题目正文使用状态读取失败，当前只显示分析索引。')});return()=>{active=false}},[]);
  useEffect(()=>setOpen(undefined),[rows]);
  const years=[...new Set(rows.map(r=>r.year))].sort((a,b)=>b-a);
  const current=year&&years.includes(year)?year:years[0];
  const annual=rows.filter(r=>r.year===current).sort((a,b)=>a.number-b.number);
  return <section className="year-reference"><div className="section-heading"><h2>年度题位与考查任务</h2><select aria-label="参照试卷年份" value={current||''} onChange={e=>{setYear(Number(e.target.value));setOpen(undefined)}}>{years.map(y=><option value={y} key={y}>{y}年真题</option>)}</select></div>{error&&<p className="task-pending">{error}</p>}
    {['选择题','填空题','解答题'].map(type=>{const items=annual.filter(r=>r.type===type);return items.length?<section className="year-type" key={type}><header><h3>{type}</h3><span>{items.length}题 · {items.reduce((n,r)=>n+r.points,0)}分</span></header><div className="year-slots">{items.map(r=><button className="year-slot" key={r.id} onClick={()=>setOpen(r)}><div><b>第{r.number}题</b><span>{r.points}分 · {r.subject==='高等数学'?'高数':'线代'}</span></div><strong>{r.model||r.point}</strong><p>{r.core||'考查任务待人工检查'}</p><small>难度 {level(r.difficulty)} · 计算量 {cost(r.calculation)}</small></button>)}</div></section>:null})}
    {!annual.length&&<div className="empty"><p>当前筛选没有对应年度真题。</p></div>}
    {open&&rows.some(r=>r.id===open.id)&&<AnalysisDrawer title={`${open.year}年 · 第${open.number}题`} subtitle={open.model} onClose={()=>setOpen(undefined)}><QuestionAnalysis row={open} index={index?.get(open.id)} onFind={onFind} onAdd={onAdd} selected={selected.includes(open.id)}/></AnalysisDrawer>}
  </section>;
}

export function PaperReview({paper,onFind}:{paper:Paper;onFind:(filter:MaterialFilter)=>void}){
  const [focus,setFocus]=useState<number[]>([]);
  useEffect(()=>setFocus([]),[paper.id,paper.version]);
  const groups=new Map<string,number[]>();for(const item of paper.items){const name=item.question.model;if(name){const g=groups.get(name)||[];g.push(item.number);groups.set(name,g)}}
  const repeated=[...groups].filter(([,ns])=>ns.length>1);
  const heavy=paper.items.filter(i=>i.question.calculation===3).map(i=>i.number);
  const adjacent=paper.items.slice(1).filter((it,i)=>it.question.calculation===3&&paper.items[i].question.calculation===3).map(it=>[it.number-1,it.number]);
  return <section className="paper-review"><h3>整卷搭配检查</h3><details><summary>结构检查 · {paper.checks.passed?'通过':'存在问题'}</summary>{paper.checks.errors.map(e=><p key={e}>{e}</p>)}{!paper.checks.errors.length&&<p>题数、题型、分值与当前规则一致；这不等于数学与命题质量已通过。</p>}</details>
    <div className="review-issues">{repeated.map(([name,numbers])=><button className="review-issue" key={name} onClick={()=>setFocus(numbers)}><b>考法标签重复：{name}</b><span>第{numbers.join('、')}题 · 对照题面与关键步骤</span><ArrowRight size={16}/></button>)}{adjacent.map(ns=><button className="review-issue" key={ns.join('-')} onClick={()=>setFocus(ns)}><b>相邻题计算量均较高</b><span>第{ns.join('、')}题 · 计算量为人工预估</span><ArrowRight size={16}/></button>)}</div>
    {!repeated.length&&!adjacent.length&&<p>未发现相同考法标签或相邻高计算量题；其他任务重复仍需结合题面检查。</p>}
    <details><summary>难度、计算量与覆盖建议</summary><p>预估难度：{[1,2,3,4,5].map(d=>`${d}级${paper.items.filter(i=>i.question.difficulty===d).length}题`).join(' · ')}</p><p>高计算量：{heavy.length?`第${heavy.join('、')}题`:'未记录'}；难度未标注：{paper.items.filter(i=>i.question.difficulty==null).length}题。</p>{(paper.design.warnings||[]).map((w,i)=><p key={i}>{w}</p>)}<p>以上阈值来自软件组卷规范，评级与用时均为预估。</p>{(paper.design.pending||[]).map((w,i)=><p key={i}>{w}</p>)}</details>
    {focus.length>0&&<AnalysisDrawer title={`第${focus.join('、')}题任务复核`} onClose={()=>setFocus([])} wide><div className="comparison-columns">{paper.items.filter(i=>focus.includes(i.number)).map(it=><article key={it.number}><h3>第{it.number}题 · {it.points}分</h3><QuestionBody question={it.question}/><p><b>考查任务：</b>{it.question.core||'待人工检查'}</p><p><b>主要方法：</b>{it.question.method||'待人工检查'}</p><p>难度 {level(it.question.difficulty)} · 计算量 {cost(it.question.calculation)}</p><button className="secondary" onClick={()=>onFind({search:it.question.point,chapter:it.question.chapter,subject:it.question.subject,type:it.question.type,difficulty:it.question.difficulty})}>筛选替换素材</button></article>)}</div></AnalysisDrawer>}
  </section>;
}
