import {useEffect,useRef,useState} from 'react';
import {api,Question} from './types';
import {QuestionBody,MathText} from './MathText';
import AnalysisDrawer from './AnalysisDrawer';

export default function SelectionBasket({ids,onRemove,onClose,onSave,onLock,busy}:{ids:string[];onRemove:(id:string)=>void;onClose:()=>void;onSave:()=>void;onLock:(questions:Question[],locks:Record<string,string>)=>void;busy:boolean}){
  const cache=useRef(new Map<string,Question>());
  const [questions,setQuestions]=useState<Map<string,Question>>(new Map()),[errors,setErrors]=useState<Map<string,string>>(new Map()),[loading,setLoading]=useState(false);
  useEffect(()=>{
    let active=true;setLoading(true);
    Promise.all(ids.map(async id=>{
      try{const q=cache.current.get(id)||await api<Question>(`/questions/${encodeURIComponent(id)}`);cache.current.set(id,q);return {id,q,error:''}}
      catch(e){return {id,q:undefined,error:String(e)}}
    })).then(results=>{if(active){setQuestions(new Map(results.flatMap(r=>r.q?[[r.id,r.q] as const]:[])));setErrors(new Map(results.filter(r=>r.error).map(r=>[r.id,r.error])));setLoading(false)}});
    return()=>{active=false};
  },[ids.join('|')]);
  const current=ids.flatMap(id=>{const q=questions.get(id);return q?[q]:[]});
  const ready=!loading&&ids.length>0&&current.length===ids.length&&current.every(q=>q.eligible)&&!errors.size;
  const locks:Record<string,string>={},problems:string[]=[];
  if(ready)for(const q of current){
    const label=q.source==='历年真题'?`${q.year}年第${q.original_number}题`:`${q.source}第${q.original_number}题`;
    if(!q.compatibility){problems.push(`${label}尚无当前标准卷赋分适配依据，可以保留用于练习。`);continue}
    const n=Array.from({length:22},(_,i)=>i+1).find(n=>!locks[n]&&q.type===(n<=10?'选择题':n<=16?'填空题':'解答题')&&q.subject===([8,9,10,16,22].includes(n)?'线性代数':'高等数学')&&q.original_points===(n<=16?5:n===17?10:12));
    if(n)locks[n]=q.id;else problems.push(`${label}没有剩余的匹配题位；未改变原分值。`);
  }
  return <AnalysisDrawer title="已选题" subtitle={`${ids.length}道题`} onClose={onClose}>
    {!ids.length&&<div className="empty"><p>还没有选题，可从考法分析或素材库加入。</p></div>}
    {loading&&<p role="status">正在读取选题…</p>}
    <div className="selection-list">{ids.map((id,i)=>{const q=questions.get(id);return <article key={id}><header><div><b>{i+1}. {q?(q.source==='历年真题'?`${q.year}年 · 第${q.original_number}题`:`${q.source} · 第${q.original_number}题`):'题目读取中'}</b>{q&&<small>{q.type} · {q.original_points??'未记录'}分 · {q.point}</small>}</div><button className="secondary" disabled={busy} onClick={()=>onRemove(id)}>移出</button></header>{q&&<><QuestionBody question={q}/>{!q.eligible&&<p className="error-text">此题当前不可用于组卷，请移出或重新核验。</p>}<details><summary>答案与解答</summary><p><MathText text={q.answer}/></p><MathText text={q.solution}/></details></>}{errors.get(id)&&<p className="error-text">{errors.get(id)}</p>}</article>})}</div>
    {problems.length>0&&<details className="selection-problems"><summary>标准组卷暂不可用 · {problems.length}项</summary>{problems.map((p,i)=><p key={i}>{p}</p>)}</details>}
    {ids.length>0&&<div className="selection-actions"><button disabled={!ready||busy||ids.length>100} onClick={onSave}>保存为练习</button><button className="secondary" disabled={!ready||busy||problems.length>0||ids.length>22} onClick={()=>onLock(current,locks)}>用于标准组卷</button></div>}
  </AnalysisDrawer>;
}
