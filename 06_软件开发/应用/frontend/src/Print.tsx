import {useEffect,useState} from 'react';
import {api,Paper} from './types';
import {MathText,QuestionBody} from './MathText';
declare global {interface Window {printReady?:boolean}}
export default function Print(){
  const params=new URLSearchParams(location.search);const id=params.get('print')!;const answers=params.get('kind')==='answers';
  const [paper,setPaper]=useState<Paper>();const [error,setError]=useState('');
  useEffect(()=>{api<Paper>(`/papers/${id}?exam=${!answers}`).then(setPaper).catch(e=>setError(String(e)));},[id,answers]);
  useEffect(()=>{if(paper){document.fonts.ready.then(()=>{requestAnimationFrame(()=>requestAnimationFrame(()=>{window.printReady=true;}));});}},[paper]);
  if(error)return <div className="math-error">{error}</div>;if(!paper)return <div>正在排版…</div>;
  const total=paper.items.reduce((s,i)=>s+(i.points||0),0);let section='';
  return <article className={'print-document '+(answers?'answers-document':'')}>
    <header className="paper-heading"><p>考研数学二 · 原创练习资料</p><h1>{paper.title}</h1><h2>{answers?'标准答案与解析':'数学（二）'}</h2><p>{paper.mode==='standard'?'满分150分　考试时间180分钟':`章节练习　${paper.items.length}题　${total?`计分题合计${total}分`:'不计分'}`}</p>{!answers&&<><p className="candidate">姓名：________________　学号：________________　日期：________________</p><p className="instructions">请独立作答。单项选择题每题只有一个正确选项；填空题将答案写在横线上；解答题写出必要的文字说明、证明过程或演算步骤。</p></>}</header>
    {paper.items.map(it=>{const q=it.question;const showSection=section!==q.type;section=q.type;return <div key={it.number}>
      {showSection&&!answers&&<h3 className="print-section">{q.type}</h3>}
      <section className="print-question"><div className="print-prompt"><div className="q-title"><b>{it.number}.</b> {it.points===null?'（不计分）':`（${it.points}分）`}</div><QuestionBody question={q}/>{answers&&<p><strong>标准答案：</strong><MathText text={q.answer}/></p>}</div>
      {!answers&&q.type==='填空题'&&<p className="blank-line">答案：________________________________</p>}
      {!answers&&q.type==='解答题'&&<div className="answer-space"/>}
      {answers&&<div className="solution"><h4>完整解题过程</h4><MathText text={q.solution}/><p><strong>关键步骤：</strong><MathText text={q.key||q.core||'待人工检查'}/></p><h4>评分参考</h4>{q.rubric?.length?<ol>{q.rubric.map((r,j)=><li key={j}><MathText text={r.step}/>（{r.points}分）</li>)}</ol>:<p>未录入分步评分；未虚构得分点。</p>}
      <p>知识点：{q.chapter||'待人工检查'} / {q.point||'待人工检查'} / {q.code||'未记录'}<br/>核心方法：<MathText text={q.method||'未记录'}/><br/>预估难度：{q.difficulty??'待人工检查'} / 5　推荐用时：{q.minutes?`${q.minutes}分钟（预估）`:'未实测，待人工检查'}</p><p><strong>常见错误：</strong><MathText text={q.errors||'未录入，待人工检查'}/></p>{q.alternative&&<p><strong>其他解法：</strong><MathText text={q.alternative}/></p>}<p className="source-foot">原始来源：{q.provenance||'原始来源未记录，待人工检查'}<br/>来源ID：{q.id}　修订：{q.revision}　原分值：{q.original_points??'未录入'}</p></div>}
      </section></div>;})}
  </article>;
}
