import {useEffect,useRef} from 'react';
import {X} from 'lucide-react';

export default function AnalysisDrawer({title,subtitle,children,onClose,wide=false}:{title:string;subtitle?:string;children:React.ReactNode;onClose:()=>void;wide?:boolean}){
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{
    const previous=document.activeElement instanceof HTMLElement?document.activeElement:null;
    const overflow=document.body.style.overflow,padding=document.body.style.paddingRight;
    const gap=window.innerWidth-document.documentElement.clientWidth;
    if(gap)document.body.style.paddingRight=`${parseFloat(getComputedStyle(document.body).paddingRight)+gap}px`;
    document.body.style.overflow='hidden';ref.current?.showModal();
    return()=>{document.body.style.overflow=overflow;document.body.style.paddingRight=padding;previous?.focus({preventScroll:true})};
  },[]);
  return <dialog ref={ref} className={'evidence-drawer'+(wide?' comparison-drawer':'')} aria-labelledby="analysis-drawer-title" onClose={onClose} onClick={e=>{
    if(e.target!==e.currentTarget)return;
    const r=e.currentTarget.getBoundingClientRect();
    if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose();
  }}><header className="evidence-drawer-header"><div><h2 id="analysis-drawer-title">{title}</h2>{subtitle&&<p>{subtitle}</p>}</div><button className="drawer-close" aria-label="关闭真题详情" onClick={onClose}><X size={20}/></button></header><div className="evidence-drawer-body">{children}</div></dialog>;
}
