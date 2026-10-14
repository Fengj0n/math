import {useEffect,useState} from 'react';
import {api} from './types';
import {MathText,QuestionBody} from './MathText';
declare global {interface Window {auditReady?:boolean}}
export default function AuditPreview(){
 const cid=new URLSearchParams(location.search).get('audit');const [candidate,setCandidate]=useState<any>();const [error,setError]=useState('');
 useEffect(()=>{api(`/studio/candidates/${cid}`).then(setCandidate).catch(e=>setError(String(e)))},[cid]);
 useEffect(()=>{if(candidate||error)document.fonts.ready.then(()=>requestAnimationFrame(()=>{window.auditReady=true}))},[candidate,error]);
 if(error)return <div className="math-error">{error}</div>;if(!candidate)return <p>正在核验公式…</p>;
 const q=candidate.raw;
 return <article className="print-document" data-audit-version={candidate.version}><QuestionBody question={q}/>{['answer','solution','core','method','value','source_difference','misconception','key','errors','alternative'].map(k=><div key={k}><MathText text={q[k]||''}/></div>)}{q.rubric?.map((r:any,i:number)=><div key={i}><MathText text={r.step}/></div>)}</article>;
}
