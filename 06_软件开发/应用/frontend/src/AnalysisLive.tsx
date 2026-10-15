import {useEffect,useRef,useState} from 'react';
import {api,Question} from './types';
import {mountAnalysis,AnalysisController} from './analysisController';
import './Analysis.css';
import './AnalysisLive.css';

type Props={view:string;onViewChange:(view:string)=>void;onOpenQuestion:(id:string)=>void;onAdd:(id:string)=>void;onSelection:()=>void;selected:string[]};

async function loadExams(){
  const path='/questions?source='+encodeURIComponent('历年真题')+'&size=100';
  const first=await api<{total:number;items:Question[]}>(path+'&page=1');
  const rest=await Promise.all(Array.from({length:Math.max(0,Math.ceil(first.total/100)-1)},(_,i)=>api<{items:Question[]}>(path+'&page='+(i+2))));
  return [first.items,...rest.map(p=>p.items)].flat().filter(q=>/^EXAM-M2-\d{4}-/.test(q.id)&&q.year!==null&&q.year>=2014&&q.year<=2026);
}

export default function AnalysisLive(props:Props){
  const host=useRef<HTMLDivElement>(null),controller=useRef<AnalysisController|null>(null),latest=useRef(props);
  const [error,setError]=useState(''),[retry,setRetry]=useState(0);
  latest.current=props;
  useEffect(()=>{
    let active=true;setError('');
    if(host.current)host.current.textContent='正在读取命题分析…';
    loadExams().then(rows=>{
      if(!active||!host.current)return;
      controller.current=mountAnalysis(host.current,rows,{
        view:latest.current.view,selected:latest.current.selected,
        loadQuestion:id=>api<Question>('/questions/'+encodeURIComponent(id)),
        onView:view=>latest.current.onViewChange(view),
        onOpenQuestion:id=>latest.current.onOpenQuestion(id),
        onAdd:id=>latest.current.onAdd(id),onSelection:()=>latest.current.onSelection(),
      });
    }).catch(e=>{if(active){setError(e instanceof Error?e.message:String(e));if(host.current)host.current.textContent='';}});
    return()=>{active=false;controller.current?.dispose();controller.current=null;};
  },[retry]);
  useEffect(()=>{controller.current?.setView(props.view)},[props.view]);
  useEffect(()=>{controller.current?.setSelection(props.selected)},[props.selected]);
  return <>{error&&<p className="analysis-live-error" role="alert">读取失败：{error} <button className="secondary" onClick={()=>setRetry(n=>n+1)}>重新读取</button></p>}<div className="analysis-live-host" ref={host}/></>;
}
