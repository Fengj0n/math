import React from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';

export function MathText({text='',className=''}:{text?:string;className?:string}){
  const segments:React.ReactNode[]=[];
  const plain=(s:string,key:string|number)=>/[\$∫∬²³⁴]|\^|\bsqrt\s*\(|_[{(]/.test(s)
    ?<span key={key} className="math-error" title="未进入公式渲染；禁止静默作为普通文字打印">公式排版待检查：{s}</span>:s;
  const pattern=/\$\$([\s\S]*?)\$\$|\$([^$]*?)\$|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)/g;
  let last=0;let m:RegExpExecArray|null;
  while((m=pattern.exec(text))!==null){
    segments.push(plain(text.slice(last,m.index),'plain-'+m.index));
    try{const html=katex.renderToString(m[1]??m[2]??m[3]??m[4],{displayMode:m[1]!==undefined||m[3]!==undefined,throwOnError:true,trust:false,strict:'warn',maxExpand:500,maxSize:15,output:'htmlAndMathml'});segments.push(<span key={m.index} className="formula" dangerouslySetInnerHTML={{__html:html}}/>);}
    catch(e){segments.push(<span key={m.index} className="math-error" title={String(e)}>公式待人工检查：{m[0]}</span>);}
    last=pattern.lastIndex;
  }
  segments.push(plain(text.slice(last),'tail'));
  return <span className={'math-text '+className}>{segments}</span>;
}

export function QuestionBody({question:q}:{question:{stem:string;options?:string[];parts?:string[];presentation_issues?:{reason:string}[]}}){return <div className="question-body"><MathText text={q.stem}/>{q.parts?.length?<ol className="parts">{q.parts.map((p,i)=><li key={i}><MathText text={p}/></li>)}</ol>:null}{q.options?.length?<div className={'options '+(q.options.some(o=>o.length>100)?'options-long':'')}>{q.options.map((o,i)=><div key={i}><b>{'ABCD'[i]}.</b> <MathText text={o}/></div>)}</div>:null}{q.presentation_issues?.length?<p className="math-error">待人工检查：{Array.from(new Set(q.presentation_issues.map(x=>x.reason))).join('；')}。此题暂不参与组卷。</p>:null}</div>;}
