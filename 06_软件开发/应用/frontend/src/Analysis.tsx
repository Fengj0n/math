import {useEffect, useMemo, useState} from 'react';
import {BookOpen, Search} from 'lucide-react';
import {loadAnalysis, SourceRecord} from './Source';
import './Analysis.css';
import TaskResearch from './TaskResearch';
import {MaterialFilter} from './types';
import AnalysisDrawer from './AnalysisDrawer';

type ExamRow = SourceRecord & {id:string;year:number;number:number;subject:string;chapter:string;point:string;model:string;type:string;points:number;difficulty:number|null;calculation:number|null;core:string;method:string;secondary:string;provenance:string;state:string;issue:string};
type SourceDocument = {id:string;name:string;title:string;description:string;path:string;sha256:string;content:string};
type Snapshot = {project_root:string;origins:Record<string,SourceRecord>;updated:string;years:number[];source:string;source_sha256:string;rows:ExamRow[];documents:SourceDocument[];warnings:string[];accounting:string;frequency:string};
type Group = {name:string;count:number;points:number;years:Set<number>;rows:ExamRow[]};
const TYPES=['选择题','填空题','解答题'];
const DIFFICULTY=['基础','较易','中等','较难','高区分度'];
const DIFFICULTY_BANDS=[
  {label:'1–2级',name:'基础与较易',levels:[0,1],className:'foundation'},
  {label:'3级',name:'中等',levels:[2],className:'middle'},
  {label:'4–5级',name:'较难及高区分度',levels:[3,4],className:'advanced'},
];

function aggregate(rows:ExamRow[], key:'chapter'|'point'|'model'):Group[]{
  const groups=new Map<string,Group>();
  for(const row of rows){const name=row[key]||'未标注';let group=groups.get(name);if(!group){group={name,count:0,points:0,years:new Set(),rows:[]};groups.set(name,group)}group.count++;group.points+=row.points;group.years.add(row.year);group.rows.push(row)}
  return [...groups.values()].sort((a,b)=>b.count-a.count||b.points-a.points||a.name.localeCompare(b.name,'zh-CN'));
}
const sum=(rows:ExamRow[])=>rows.reduce((n,r)=>n+r.points,0);
const freq=(n:number)=>n>=5?'高频':n>=3?'中频':'低频';

type YearStat={year:number;levels:number[];pending:number};
function makeYearStats(rows:ExamRow[]):YearStat[]{
  return [...new Set(rows.map(r=>r.year))].sort((a,b)=>a-b).map(year=>{
    const items=rows.filter(r=>r.year===year);
    return {year,levels:[1,2,3,4,5].map(n=>items.filter(r=>r.difficulty===n).length),pending:items.filter(r=>r.difficulty===null).length};
  });
}

function percentile(values:number[],fraction:number){
  const sorted=[...values].sort((a,b)=>a-b),position=(sorted.length-1)*fraction,lower=Math.floor(position),upper=Math.ceil(position);
  return sorted[lower]+(sorted[upper]-sorted[lower])*(position-lower);
}

function makeDifficultyProfile(stats:YearStat[]){
  const rated=stats.filter(stat=>stat.levels.some(count=>count>0));
  if(rated.length<3)return {yearCount:rated.length,bands:[]};
  const yearlyShares=rated.map(stat=>{
    const total=stat.levels.reduce((sum,count)=>sum+count,0);
    return {stat,shares:DIFFICULTY_BANDS.map(band=>band.levels.reduce((sum,index)=>sum+stat.levels[index],0)/total*100)};
  });
  const medians=DIFFICULTY_BANDS.map((_,index)=>percentile(yearlyShares.map(year=>year.shares[index]),.5));
  const representative=[...yearlyShares].sort((a,b)=>{
    const distance=(year:{shares:number[]})=>year.shares.reduce((sum,share,index)=>sum+Math.abs(share-medians[index]),0);
    return distance(a)-distance(b)||b.stat.year-a.stat.year;
  })[0];
  return {yearCount:rated.length,representativeYear:representative.stat.year,bands:DIFFICULTY_BANDS.map((band,index)=>{
    const shares=yearlyShares.map(year=>year.shares[index]);
    return {...band,share:representative.shares[index],lower:percentile(shares,.25),upper:percentile(shares,.75)};
  })};
}

function DifficultyProfile({stats}:{stats:YearStat[]}){
  const profile=makeDifficultyProfile(stats);
  if(profile.yearCount<3)return null;
  return <section className="difficulty-profile-summary" aria-label="逐年单卷难度结构摘要">
    <header><h3>代表性单卷难度结构</h3><span>{profile.yearCount}年样本 · 选取最接近年度中位结构的{profile.representativeYear}年试卷</span></header>
    <div className="difficulty-profile-grid">{profile.bands.map(band=><article className={`difficulty-profile-band ${band.className}`} key={band.label}>
      <div className="difficulty-profile-label"><b>{band.name}</b><span>{band.label}</span></div>
      <strong>{band.share.toFixed(1)}%</strong>
      <small>中间50%年份：{band.lower.toFixed(1)}%–{band.upper.toFixed(1)}%</small>
    </article>)}</div>
  </section>;
}

function PositionPattern({rows,onSelect}:{rows:ExamRow[];onSelect:(group:Group)=>void}){
  const years=[...new Set(rows.map(r=>r.year))].sort((a,b)=>b-a);
  const positions=[...new Set(rows.map(r=>r.number))].sort((a,b)=>a-b);
  const cells=new Map<string,ExamRow[]>();
  for(const row of rows){const key=`${row.year}-${row.number}`;cells.set(key,[...(cells.get(key)||[]),row])}
  const columns=`58px repeat(${Math.max(positions.length,1)}, minmax(30px, 1fr))`;
  function selectPosition(number:number,items:ExamRow[]){onSelect({name:`第${number}题`,count:items.length,points:sum(items),years:new Set(items.map(r=>r.year)),rows:items})}
  return <section className="panel position-pattern">
    <div className="section-heading"><div><h2>题位难度图</h2><p>按年份与题号呈现难度评级，比较题位变化。</p></div><span className="subtle-label">{years.length}个年份 · {positions.length}个题位</span></div>
    {positions.length?<>
      <div className="position-legend" aria-label="难度颜色说明">{DIFFICULTY.map((label,i)=><span key={label}><i className={`level-${i+1}`}/>{i+1}级</span>)}<span><i className="level-pending"/>待评级</span></div>
      <div className="position-matrix-wrap"><div className="position-matrix" role="table" aria-label="各年份题号难度分布">
        <div className="position-matrix-row position-matrix-head" role="row" style={{gridTemplateColumns:columns}}><b role="columnheader">年份</b>{positions.map(n=><span role="columnheader" key={n}>{n}</span>)}</div>
        {years.map(year=><div className="position-matrix-row" role="row" key={year} style={{gridTemplateColumns:columns}}><b className="position-matrix-year" role="rowheader">{year}</b>{positions.map(number=>{const items=cells.get(`${year}-${number}`)||[];if(!items.length)return <span key={number} className="position-cell missing" role="cell" aria-label={`${year}年第${number}题无记录`}>·</span>;const difficulty=items.length===1?items[0].difficulty:null;const levelClass=items.length>1?'duplicate':difficulty===null?'pending':`level-${difficulty}`;const text=items.length>1?`${items.length}题`:difficulty===null?'待':String(difficulty);const description=items.map(r=>`${r.year}年第${r.number}题，${r.subject}，${r.chapter}，难度${r.difficulty??'待评级'}级，计算量${r.calculation??'待评级'}`).join('；');return <button type="button" role="cell" key={number} className={`position-cell ${levelClass}`} title={description} aria-label={description} onClick={()=>selectPosition(number,items)}>{text}</button>})}</div>)}
      </div></div>
      <details className="analysis-help position-notes"><summary>评级与空白说明</summary><p>1—5级为预估难度；“待”表示尚未评级，空白表示当前筛选范围没有对应记录。重复记录会单独标出。</p></details>
    </>:<div className="empty"><p>当前筛选范围没有可展示的题位记录。</p></div>}
  </section>;
}

function AnnualComposition({stats}:{stats:YearStat[]}){
  const legend=DIFFICULTY.map((name,i)=>({name:`${i+1}级 ${name}`,className:`level-${i+1}`}));
  return <figure className="annual-composition" aria-label="逐年难度等级构成图">
    <figcaption className="chart-caption"><b>逐年难度构成</b><span>各等级占当年已评级真题的比例</span></figcaption>
    <div className="annual-composition-legend">{legend.map(item=><span key={item.name}><i className={item.className}/>{item.name}</span>)}</div>
    <div className="annual-bar-list">{stats.map(stat=>{const rated=stat.levels.reduce((total,count)=>total+count,0);const percent=(value:number)=>rated?value/rated*100:0;return <div className="annual-bar-row" key={stat.year}>
      <b className="annual-bar-year">{stat.year}</b>
      <div className="annual-bar-track" role="img" aria-label={rated?`${stat.year}年已评级真题的难度构成：${stat.levels.map((n,i)=>`${i+1}级${percent(n).toFixed(1)}%`).join('，')}`:`${stat.year}年没有已评级真题`}>
        {stat.levels.map((count,i)=>count>0&&<span key={i} className={`annual-bar-segment level-${i+1}`} style={{width:`${percent(count)}%`}} title={`${stat.year}年 · ${i+1}级 ${percent(count).toFixed(1)}%`}/>)}
      </div>
    </div>})}</div>
  </figure>;
}

function KnowledgeFrequencyChart({groups,onSelect}:{groups:Group[];onSelect:(g:Group)=>void}){
  const top=groups.slice(0,10),maximum=Math.max(1,...top.map(g=>g.count));
  if(!top.length)return null;
  return <figure className="topic-frequency-chart">
    <figcaption className="chart-caption"><b>高频考点</b><span>按真题题数排序 · 点击考点查看对应真题</span></figcaption>
    <div className="topic-chart-rows">{top.map((g,i)=><button type="button" className={`topic-chart-row${i<3?` topic-chart-row-top-${i+1}`:''}`} key={g.name} onClick={()=>onSelect(g)} title={`${g.name}：${g.count}道真题`}>
      <span className="topic-chart-rank">{String(i+1).padStart(2,'0')}</span><b className="topic-chart-name">{g.name}</b>
      <span className="topic-chart-track"><i style={{width:`${g.count/maximum*100}%`}}/></span><strong>{g.count}<small>题</small></strong>
    </button>)}</div>
  </figure>;
}

function Evidence({rows}:{rows:ExamRow[]}){
  const [page,setPage]=useState(1);
  useEffect(()=>setPage(1),[rows]);
  useEffect(()=>{document.querySelector('.evidence-drawer-body')?.scrollTo({top:0})},[page]);
  return <div className="evidence-list">{rows.slice((page-1)*12,page*12).map(r=><article key={r.id}><div className="evidence-heading"><b>{r.year} · 第{r.number}题</b><span>{r.type} · {r.points}分 · 难度{r.difficulty??'未知'}（预估）</span></div><p>{r.core||'考法待补'}</p><small>主要方法：{r.method||'待人工检查'}</small>{r.issue&&<small className="evidence-issue">核验备注：{r.issue}</small>}</article>)}{rows.length>12&&<div className="pagination"><span>{rows.length}条证据</span><button className="secondary" disabled={page===1} onClick={()=>setPage(page-1)}>上一页</button><span>{page}</span><button className="secondary" disabled={page*12>=rows.length} onClick={()=>setPage(page+1)}>下一页</button></div>}</div>;
}

function EvidenceDrawer({group,onClose}:{group:Group;onClose:()=>void}){
  return <AnalysisDrawer title={group.name} subtitle={`${group.count}道对应真题`} onClose={onClose}><Evidence key={group.name} rows={group.rows}/></AnalysisDrawer>;
}

export default function Analysis({view,onFind,onAdd,onSelection,selected}:{view:string;onFind:(filter:MaterialFilter)=>void;onAdd:(id:string)=>void;onSelection:()=>void;selected:string[]}){
  const [data,setData]=useState<Snapshot>(),[error,setError]=useState('');
  const [period,setPeriod]=useState('all'),[subject,setSubject]=useState(''),[type,setType]=useState('');
  const [level,setLevel]=useState<'chapter'|'point'|'model'>('point'),[search,setSearch]=useState(''),[frequency,setFrequency]=useState(''),[group,setGroup]=useState<Group>();
  useEffect(()=>{let active=true;loadAnalysis().then(v=>{if(active)setData(v)}).catch(e=>{if(active)setError(String(e))});return()=>{active=false}},[]);
  useEffect(()=>setGroup(undefined),[period,subject,type,view]);
  const rows=useMemo(()=>data?.rows.filter(r=>(period==='all'||period==='recent'&&r.year>=2022||String(r.year)===period)&&(!subject||r.subject===subject)&&(!type||r.type===type))||[],[data,period,subject,type]);
  const groups=useMemo(()=>aggregate(rows,level).filter(g=>g.name.includes(search)&&(!frequency||freq(g.years.size)===frequency)),[rows,level,search,frequency]);
  const yearStats=useMemo(()=>makeYearStats(rows),[rows]);
  const pendingDifficultyCount=yearStats.reduce((total,stat)=>total+stat.pending,0);
  if(error)return <div className="alert error" role="alert">{error}</div>;
  if(!data)return <section className="panel empty" role="status"><BookOpen size={44}/><p>正在读取本地命题分析资料…</p></section>;
  const findScoped=(filter:MaterialFilter)=>onFind({...filter,subject:filter.subject??(subject||undefined),type:filter.type??(type||undefined)});
  return <div className="analysis-page">
    {selected.length>0&&<header className="analysis-header"><button className="secondary" onClick={onSelection}>查看已选题 · {selected.length}</button></header>}
    <section className="analysis-scope" aria-label="统计范围筛选">
      <div className="scope-controls">
        <label><span>年份</span><select aria-label="分析年份" value={period} onChange={e=>setPeriod(e.target.value)}><option value="all">2014—2026 · 全部13年</option><option value="recent">近5年 · 2022—2026</option>{data.years.map(y=><option key={y} value={y}>{y}年</option>)}</select></label>
        <label><span>科目</span><select aria-label="分析科目" value={subject} onChange={e=>setSubject(e.target.value)}><option value="">全部科目</option><option>高等数学</option><option>线性代数</option></select></label>
        <label><span>题型</span><select aria-label="分析题型" value={type} onChange={e=>setType(e.target.value)}><option value="">全部题型</option>{TYPES.map(t=><option key={t}>{t}</option>)}</select></label>
      </div>
      <details className="analysis-help statistics-help"><summary>分析口径</summary><ul className="analysis-basis"><li>真题样本：{data.years[0]}—{data.years[data.years.length-1]}年。880与项目原创题不参与真题规律统计。</li><li>主知识点承接整题分值；次级知识点只表示参与关系，不重复分配分值。</li><li>难度与计算量分开预估。历史覆盖年份表示样本事实，不是未来出题概率。</li><li>专题提炼区分考查目标、关键判断和选题用途；未提炼题只保留分析索引，不编造理由。</li></ul><details><summary>历史数据的待复核项</summary>{data.warnings.map(w=><p key={w}>{w}</p>)}</details></details>
    </section>
    {view==='考法选题'&&<TaskResearch rows={rows} onFind={findScoped} onAdd={onAdd} selected={selected}/>}
    {view==='考点分布'&&<section className="panel"><div className="section-heading"><div><h2>知识点与真题证据</h2></div><span className="subtle-label">{groups.length}个标签</span></div><div className="toolbar"><div className="search"><Search size={17}/><input aria-label="搜索分析知识点" placeholder="搜索知识点或具体考法" value={search} onChange={e=>setSearch(e.target.value)}/></div><select aria-label="知识点层级" value={level} onChange={e=>{setLevel(e.target.value as typeof level);setGroup(undefined)}}><option value="chapter">一级 · 章节</option><option value="point">二级 · 知识点</option><option value="model">三级 · 具体考法</option></select><select aria-label="考点频次" value={frequency} onChange={e=>setFrequency(e.target.value)}><option value="">全部频次</option>{['高频','中频','低频'].map(v=><option key={v}>{v}</option>)}</select></div><KnowledgeFrequencyChart groups={groups} onSelect={setGroup}/><div className="table-wrap analysis-table"><table><thead><tr><th>知识点</th><th>题目数量</th><th>累计分值</th><th>平均分值</th><th>年份覆盖</th><th>选择 / 填空 / 解答</th><th>对应真题</th></tr></thead><tbody>{groups.map(g=><tr key={g.name} className={group?.name===g.name?'selected-row':''}><td><b>{g.name}</b><small className={"frequency-tag "+(freq(g.years.size)==='高频'?'high':'normal')}>{freq(g.years.size)}</small></td><td>{g.count}</td><td>{g.points}</td><td>{(g.points/g.count).toFixed(2)}</td><td>{g.years.size}年</td><td>{TYPES.map(t=>g.rows.filter(r=>r.type===t).length).join(' / ')}</td><td><button className="secondary" onClick={()=>setGroup(g)}>查看</button></td></tr>)}</tbody></table></div>{!groups.length&&<div className="empty"><Search size={40}/><p>当前筛选范围没有匹配的知识点</p></div>}</section>}
    {view==='题位规律'&&<PositionPattern rows={rows} onSelect={setGroup}/>}
    {view==='年度难度'&&<section className="panel yearly-difficulty-panel">
      <div className="section-heading"><h2>逐年难度分布</h2><span className="subtle-label">按年份倒序 · 占比基于已评级题目{pendingDifficultyCount>0?` · 待评 ${pendingDifficultyCount} 题，未计入比例`:''}</span></div>
      <DifficultyProfile stats={yearStats}/>
      <div className="annual-visual-grid"><AnnualComposition stats={[...yearStats].reverse()}/></div>
      <div className="table-wrap analysis-table yearly-difficulty-table"><table><thead><tr><th>年份</th>{DIFFICULTY.map((label,i)=><th key={label}>{i+1}级 · {label}</th>)}</tr></thead><tbody>{[...yearStats].reverse().map(stat=>{const rated=stat.levels.reduce((total,count)=>total+count,0);const percent=(count:number)=>rated?`${(count/rated*100).toFixed(1)}%`:'—';return <tr key={stat.year}><td><b>{stat.year}</b></td>{stat.levels.map((count,i)=><td key={i}>{percent(count)}</td>)}</tr>})}</tbody></table></div>
      <details className="analysis-help"><summary>评级说明</summary><ul className="quiet-list"><li>难度依据题目所需的理解、判断与推导步骤作预估，未使用考生作答数据。</li><li>各档占比以当年已评级真题为分母；未评级题不计入，存在时在标题旁提示。</li></ul></details>
    </section>}
    {group&&<EvidenceDrawer group={group} onClose={()=>setGroup(undefined)}/>}
  </div>;
}
