import katex from 'katex';
import {questionInsights,topicInsights} from './taskInsights';

// The approved design uses an isolated DOM controller; all question data comes from the application API.
export function mountAnalysis(host,rows,options){
  host.innerHTML="<div id=\"math2-analysis-two-parts\"><div class=\"research-toolbar\"><h2 id=\"analysis-current-heading\"></h2><label class=\"scope-label\">范围<select id=\"research-period\" aria-label=\"分析范围\"><option value=\"all\">2014—2026 · 全部13年</option><option value=\"current\">2021—2026 · 新卷式</option><option value=\"old\">2014—2020 · 旧卷式</option></select></label></div><div id=\"research-main\" aria-live=\"polite\"></div><footer class=\"research-footer\"><button type=\"button\" id=\"research-standards\" aria-expanded=\"false\">评级标准</button><button type=\"button\" id=\"analysis-selection\" hidden>查看已选题</button></footer><section id=\"standards-panel\" hidden aria-label=\"评级依据\"><div class=\"standard-columns\"><div><h3>难度：思维负担</h3><dl><dt>1级</dt><dd>定义或直接公式，几乎没有方法选择。</dd><dt>2级</dt><dd>标准短链，少量常规处理。</dd><dt>3级</dt><dd>需要方法识别、条件判断与多步连接。</dd><dt>4级</dt><dd>实质构造、分类讨论或较强证明。</dd><dt>5级</dt><dd>更强的整体构造与递推控制。</dd></dl></div><div><h3>计算量：手算负担</h3><dl><dt>低</dt><dd>运算短，展开与整理较少。</dd><dt>中</dt><dd>常规多步计算，规模适中。</dd><dt>高</dt><dd>较长展开、反复计算或多处分域。</dd></dl><p class=\"muted\">按合理、较简洁的考纲内主解法判断。等级仅作相对参考。</p></div></div></section></div>";
  const root=host.firstElementChild,DATA={rows:rows.map(q=>({...q})),insights:questionInsights,topics:topicInsights};
  let disposed=false,selection=options.selected||[],lastView=options.view;
  const loaded=new Set(),pending=new Set(),failures=new Map();
  const main=root.querySelector('#research-main');
  const topicNames={'导数定义与极限反推导数':'导数与差商','极值与拐点判定':'极值与拐点','凸性与等价命题':'凸性与证明','泰勒抵消与系数匹配':'泰勒与系数抵消'};
  const chapterOrder=['函数、极限与连续','一元函数微分学','一元函数积分学','多元函数微分学','二重积分','定积分应用','常微分方程','行列式','矩阵','向量与矩阵秩','线性方程组','特征值与相似','二次型'];
  const types=['选择题','填空题','解答题'];
  const state={view:'study',studyMode:'year',period:'all',topic:'导数定义与极限反推导数',question:'EXAM-M2-2025-18',year:2026,difficultyQuestion:'EXAM-M2-2026-22',yearChapter:'',questionFocus:'all',outlineType:'解答题',outlineQuestion:'',readerLayout:'stacked'};
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=value=>Number.isInteger(Number(value))?String(Number(value)):Number(value).toFixed(1);
  const points=rows=>rows.reduce((n,q)=>n+Number(q.original_points||0),0);
  const rowById=id=>DATA.rows.find(q=>q.id===id);
  const insight=q=>q&&DATA.insights[q.id]?.revision===q.revision?DATA.insights[q.id]:null;
  const inPeriod=q=>state.period==='all'||state.period==='current'&&q.year>=2021||state.period==='old'&&q.year<=2020;
  const scoped=()=>DATA.rows.filter(inPeriod);
  const topicRows=()=>scoped().filter(q=>q.model===state.topic).sort((a,b)=>b.year-a.year||a.original_number-b.original_number);
  const gradeNames=['','基础','较易','中等','较难','很难'];
  const costNames=['','低','中','高'];
  const difficulty=q=>q.difficulty==null?'未评级':`${num(q.difficulty)}级 · ${gradeNames[q.difficulty]||'待检查'}`;
  const cost=q=>q.calculation==null?'未评级':costNames[q.calculation]||'待检查';
  const math=text=>`<span class="math-text" data-math="${esc(text)}">${esc(text)}</span>`;
  function typeset(){
    if(disposed)return;
    for(const el of root.querySelectorAll('[data-math]')){
      const text=el.getAttribute('data-math')||'',pattern=/\$\$([\s\S]*?)\$\$|\$([^$]*?)\$|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)/g;
      let out='',last=0,match;
      while((match=pattern.exec(text))){out+=esc(text.slice(last,match.index));try{out+=`<span class="formula">${katex.renderToString(match[1]??match[2]??match[3]??match[4],{displayMode:match[1]!==undefined||match[3]!==undefined,throwOnError:true,trust:false,strict:'ignore',maxExpand:500})}</span>`;}catch(_){out+=`<span class="math-error">公式待人工检查：${esc(match[0])}</span>`;}last=pattern.lastIndex;}
      el.innerHTML=out+esc(text.slice(last));
    }
    requestAnimationFrame(fitFormulae);
  }
  function fitFormulae(){if(disposed)return;for(const el of root.querySelectorAll('.formula')){el.style.fontSize='';const available=el.parentElement?.getBoundingClientRect().width||0,width=el.getBoundingClientRect().width;if(available>0&&width>available)el.style.fontSize=`${Math.max(.8,Math.min(1,available/width))}em`;}}
  function save(){try{sessionStorage.setItem('math2-analysis-v2',JSON.stringify({modelContent:{page:'命题分析-软件-v2',view:state.view,studyMode:state.studyMode,period:state.period,topic:state.topic,question:state.view==='difficulty'?state.difficultyQuestion:state.studyMode==='year'?state.outlineQuestion:state.question,year:state.year,chapter:state.yearChapter,questionFocus:state.questionFocus,outlineType:state.outlineType},privateContent:{studyQuestion:state.question}}));}catch{}}
  function restore(snapshot){
    const m=snapshot?.modelContent,p=snapshot?.privateContent;if(m?.page!=='命题分析-软件-v2')return;
    if(['study','difficulty'].includes(m.view))state.view=m.view;
    if(['topic','year','outline'].includes(m.studyMode))state.studyMode=m.studyMode==='outline'?'year':m.studyMode;
    if(['all','current','old'].includes(m.period))state.period=m.period;
    if(DATA.rows.some(q=>q.model===m.topic))state.topic=m.topic;
    if(rowById(m.question)){if(state.view==='difficulty')state.difficultyQuestion=m.question;else if(state.studyMode==='year')state.outlineQuestion=m.question;else state.question=m.question;}
    if(rowById(p?.studyQuestion))state.question=p.studyQuestion;
    if(Number.isInteger(m.year)&&m.year>=2014&&m.year<=2026)state.year=m.year;
    if(typeof m.chapter==='string'&&(!m.chapter||DATA.rows.some(q=>q.chapter===m.chapter)))state.yearChapter=m.chapter;
    if(['all','hard','heavy'].includes(m.questionFocus))state.questionFocus=m.questionFocus;
    if(types.includes(m.outlineType))state.outlineType=m.outlineType;
    if(['stacked','parallel'].includes(p?.readerLayout))state.readerLayout=p.readerLayout;
  }
  function ensureQuestion(q){
    if(loaded.has(q.id)||pending.has(q.id)||failures.has(q.id))return;
    pending.add(q.id);
    options.loadQuestion(q.id).then(full=>{if(disposed)return;if(full.id!==q.id)throw new Error('题目记录不匹配');Object.assign(q,full);loaded.add(q.id);pending.delete(q.id);render();}).catch(error=>{if(disposed)return;pending.delete(q.id);failures.set(q.id,String(error));render();});
  }
  function questionBody(q){
    if(q.body_display_mode==='image'&&q.question_images?.length)return `<div class="source-question-images">${q.question_images.filter(x=>x.url?.startsWith('/api/question-images/')).map(x=>`<img src="${esc(x.url)}" alt="${q.year}年第${q.original_number}题原页，第${x.pdf_page}页" loading="lazy"/>`).join('')}</div>`;
    if(!q.eligible||!q.source_body_ready||!q.render_ready)return '<p class="pending">正文待核验。</p>';
    return `<div class="question-stem">${math(q.stem)}${q.parts?.length?`<ol class="question-parts">${q.parts.map(p=>`<li>${math(p)}</li>`).join('')}</ol>`:''}</div>${q.options?.length?`<div class="question-options">${q.options.map((o,i)=>`<div class="question-option"><b>${'ABCD'[i]}.</b>${math(o)}</div>`).join('')}</div>`:''}`;
  }
  function questionReader(q){
    if(!q)return '<div class="empty-state">请选择一道真题。</div>';
    ensureQuestion(q);
    if(failures.has(q.id))return `<article class="question-reader"><h3>${q.year}年 · 第${q.original_number}题</h3><p class="pending">读取题目失败：${esc(failures.get(q.id))}</p><button type="button" data-retry-question="${esc(q.id)}">重新读取</button></article>`;
    if(!loaded.has(q.id))return `<article class="question-reader" role="status"><h3>${q.year}年 · 第${q.original_number}题</h3><p>正在读取原题…</p></article>`;
    const idea=insight(q),fields=idea?`<dl><div><dt>考查任务</dt><dd>${esc(idea.objective)}</dd></div><div><dt>关键判断</dt><dd class="analysis-decision">${esc(idea.decision)}</dd></div><div><dt>容易忽略的条件</dt><dd>${esc(idea.pitfall)}</dd></div></dl>`:`<dl><div><dt>考查任务</dt><dd>${math(q.core||'暂未记录')}</dd></div><div><dt>主要解法</dt><dd>${math(q.method||'暂未记录')}</dd></div></dl>`;
    return `<article class="question-reader"><header class="reader-heading"><div><h3>${q.year}年 · 第${num(q.original_number)}题</h3><p class="reader-meta">${esc(q.type)} · ${num(q.original_points)}分 · ${esc(q.point)}</p></div></header><div class="reader-layout"><section>${questionBody(q)}</section><section class="analysis-body"><h4>${idea?'解题与命题分析':'题目索引'}</h4>${fields}</section></div><div class="ratings"><span class="rating-label">难度 ${difficulty(q)}</span><span class="rating-label">计算量 ${cost(q)}</span></div>${q.eligible?`<details class="solution"><summary>标准答案与已有解答</summary><div>${math(q.answer)}</div><div>${math(q.solution)}</div></details>`:''}${idea?`<section class="topic-selection"><h4>命题启发</h4><p>${esc(idea.selection)}</p></section>`:''}<div class="software-reader-actions"><button type="button" data-bank-question="${esc(q.id)}">在题库中查看</button><button type="button" data-add-question="${esc(q.id)}" ${!q.eligible||!q.source_body_ready||!q.render_ready||selection.includes(q.id)?'disabled':''}>${selection.includes(q.id)?'已加入选题':'加入选题'}</button></div></article>`;
  }
  function groups(){const map=new Map();for(const q of scoped()){if(!map.has(q.model))map.set(q.model,[]);map.get(q.model).push(q);}return map;}
  function navigation(){
    const map=groups(),selectedChapter=map.get(state.topic)?.[0]?.chapter,expanded=new Set([...root.querySelectorAll('.catalogue details[open]')].map(el=>el.dataset.catalogueChapter));
    return `<aside class="topic-navigation" aria-label="考法目录"><h3 class="navigation-heading">全部考法</h3><p class="catalogue-count">${map.size}类 · ${scoped().length}道真题</p><div class="catalogue">${chapterOrder.map(ch=>{const models=[...map].filter(([,qs])=>qs[0].chapter===ch).sort((a,b)=>b[1].length-a[1].length);return models.length?`<details data-catalogue-chapter="${esc(ch)}" ${ch===selectedChapter||expanded.has(ch)?'open':''}><summary>${esc(ch)}<span>${models.reduce((n,[,qs])=>n+qs.length,0)}题</span></summary>${models.map(([name,qs])=>`<button type="button" class="cursor-interaction" data-topic="${esc(name)}" aria-pressed="${state.topic===name}"><span>${esc(name)}</span><span class="catalogue-quantity">${qs.length}题</span></button>`).join('')}</details>`:'';}).join('')}</div></aside>`;
  }
  function renderTopic(){
    let rows=topicRows();if(!rows.length){const first=scoped()[0];if(first){state.topic=first.model;rows=topicRows();}}if(!rows.length)return '<p class="empty-state">没有对应真题。</p>';
    if(!rows.some(q=>q.id===state.question))state.question=(rows.find(q=>insight(q))||rows.find(q=>q.eligible)||rows[0]).id;
    const q=rowById(state.question),overview=DATA.topics[state.topic],years=new Set(rows.map(q=>q.year));
    const focus=overview?`<section class="research-focus"><p>${esc(overview.focus)}</p><div class="dimensions">${overview.decisions.map(d=>`<span>${esc(d)}</span>`).join('')}</div></section>`:'';
    return `<div class="topic-shell">${navigation()}<section class="topic-workspace"><p class="breadcrumb">${esc(rows[0].subject)} ／ ${esc(rows[0].chapter)}</p><h2>${esc(topicNames[state.topic]||state.topic)}</h2><p class="topic-meta">${rows.length}道真题 · 覆盖${years.size}年 · 累计${num(points(rows))}分</p>${focus}<div class="question-switcher" aria-label="对应真题">${rows.map(r=>`<button type="button" class="cursor-interaction" data-question="${esc(r.id)}" aria-pressed="${r.id===state.question}">${r.year} · 第${num(r.original_number)}题<span>${esc(r.type)} · ${num(r.original_points)}分</span></button>`).join('')}</div>${questionReader(q)}<div class="year-presence" aria-label="该考法在当前范围内的出现年份"><span>出现年份</span>${[...years].sort((a,b)=>a-b).map(y=>`<span class="presence">${y}</span>`).join('')}</div>${overview?`<section class="topic-selection"><h4>考法与任务差异</h4><p>${esc(overview.selection)}</p></section>`:''}</section></div>`;
  }
  function currentYears(){return [...new Set(scoped().map(q=>q.year))].sort((a,b)=>b-a);}
  function ensureYear(){const years=currentYears();if(!years.includes(state.year))state.year=years[0];return years;}
  function yearPicker(){return `<label class="scope-label">年份<select id="paper-year" aria-label="选择真题年份">${currentYears().map(y=>`<option value="${y}" ${y===state.year?'selected':''}>${y}年</option>`).join('')}</select></label>`;}
  function chapterDistribution(rows){
    const groups=[...new Set(rows.map(q=>q.chapter))].map(name=>({name,rows:rows.filter(q=>q.chapter===name)}));
    const ceiling=Math.ceil(Math.max(...groups.map(g=>points(g.rows)))/5)*5,total=points(rows);
    return `<section class="chapter-distribution"><h3>本卷考点分值</h3><div class="chapter-facets">${['高等数学','线性代数'].map(subject=>`<figure class="chapter-facet" aria-label="${subject}章节分值分布"><figcaption>${subject} · ${points(rows.filter(q=>q.subject===subject))}分</figcaption><div class="chapter-axis" aria-hidden="true"><span>0</span><span>${ceiling}分</span></div>${groups.filter(g=>g.rows[0].subject===subject).sort((a,b)=>points(b.rows)-points(a.rows)).map(g=>{const marks=points(g.rows),share=(marks/total*100).toFixed(1),label=`${g.name}，${g.rows.length}题，${marks}分，占本卷${share}%`;return `<button type="button" class="chapter-bar cursor-interaction" data-chapter="${esc(g.name)}" aria-pressed="${state.yearChapter===g.name}" aria-label="${esc(label)}" title="${esc(label)}"><span>${esc(g.name)}</span><span class="chapter-track" aria-hidden="true"><span class="chapter-fill" style="width:${marks/ceiling*100}%"></span></span><span class="chapter-value">${marks}分<small>${share}%</small></span></button>`;}).join('')}</figure>`).join('')}</div></section>`;
  }
  function outlineProfile(rows,key){
    const ps=parts(rows,key),total=points(rows),description=ps.map(b=>`${b.short}${b.points}分、${b.count}题`).join('；');
    return `<section class="outline-profile"><h4>${key==='difficulty'?'难度':'计算量'} · ${total}分</h4><div class="outline-mix" role="img" aria-label="${esc(description)}">${ps.filter(b=>b.points>0).map(b=>`<span class="${b.cls}" style="width:${b.points/total*100}%" aria-hidden="true">${b.points/total>=.16?num(b.points):''}</span>`).join('')}</div><div class="chart-legend">${ps.map(b=>`<span><i class="chart-swatch ${b.cls}" aria-hidden="true"></i>${b.short} ${b.points}分</span>`).join('')}</div></section>`;
  }
  function renderPaper(){
    ensureYear();const rows=scoped().filter(q=>q.year===state.year).sort((a,b)=>a.original_number-b.original_number);
    if(state.yearChapter&&!rows.some(q=>q.chapter===state.yearChapter))state.yearChapter='';
    const items=rows.filter(q=>state.yearChapter?q.chapter===state.yearChapter:q.type===state.outlineType),total=points(rows);
    const selected=items.find(q=>q.id===state.outlineQuestion)||items[0];state.outlineQuestion=selected.id;
    const listTitle=state.yearChapter||`${state.outlineType} · 第${items[0].original_number}—${items[items.length-1].original_number}题`;
    const allocation=types.map(type=>{const rs=rows.filter(q=>q.type===type);return `<button type="button" class="cursor-interaction" data-outline-type="${type}" style="flex:1" aria-pressed="${!state.yearChapter&&state.outlineType===type}" aria-label="${type}，${rs.length}题，${points(rs)}分"><span>${type}</span><small>${rs.length}题 · ${points(rs)}分</small></button>`;}).join('');
    return `<section><header class="paper-heading"><div><h2>${state.year}年 · 年度试卷</h2><p class="paper-meta">${rows.length}题 · ${total}分 · 高数${points(rows.filter(q=>q.subject==='高等数学'))}分 / 线代${points(rows.filter(q=>q.subject==='线性代数'))}分</p></div>${yearPicker()}</header><div class="paper-split"><aside class="paper-browser" aria-label="年度试卷选题"><h3 class="paper-structure-title">题型</h3><div class="outline-allocation" aria-label="题型选择">${allocation}</div>${chapterDistribution(rows)}</aside><section class="paper-detail" aria-label="对应题目与原题"><div class="outline-heading"><div><h3>${esc(listTitle)}</h3><p>${items.length}题 · ${points(items)}分</p></div>${state.yearChapter?'<button type="button" class="cursor-interaction" data-clear-chapter="true">清除章节筛选</button>':''}</div><div class="paper-questions" aria-label="${esc(state.yearChapter||state.outlineType)}对应题目">${items.map(q=>`<button type="button" class="paper-choice cursor-interaction" data-outline-question="${esc(q.id)}" aria-pressed="${selected.id===q.id}" aria-label="第${q.original_number}题，${esc(q.model)}，${q.original_points}分，难度${difficulty(q)}，计算量${cost(q)}"><span class="paper-choice-number">${num(q.original_number).padStart(2,'0')}</span></button>`).join('')}</div><div class="paper-reader-content">${questionReader(selected)}<div class="reader-route"><span>${esc(selected.model)}</span><button type="button" class="cursor-interaction" data-open-question="${esc(selected.id)}">查看同类考法 →</button></div></div></section></div></section>`;
  }
  function renderStudy(){return `<nav class="study-tabs" aria-label="试卷分析视图">${[{value:'year',label:'年度试卷'},{value:'topic',label:'考法研究'}].map(v=>`<button type="button" class="cursor-interaction" data-study-mode="${v.value}" aria-pressed="${state.studyMode===v.value}">${v.label}</button>`).join('')}</nav>${state.studyMode==='year'?renderPaper():renderTopic()}`;}
  const bands={difficulty:[{name:'1–2级 · 基础与较易',short:'1–2级',levels:[1,2],cls:'band-d0'},{name:'3级 · 中等',short:'3级',levels:[3],cls:'band-d1'},{name:'4–5级 · 较难与很难',short:'4–5级',levels:[4,5],cls:'band-d2'}],calculation:[{name:'低计算量',short:'低',levels:[1],cls:'band-c0'},{name:'中计算量',short:'中',levels:[2],cls:'band-c1'},{name:'高计算量',short:'高',levels:[3],cls:'band-c2'}]};
  function parts(rows,key){return bands[key].map(b=>({...b,points:points(rows.filter(q=>b.levels.includes(q[key]))),count:rows.filter(q=>b.levels.includes(q[key])).length}));}
  let comparisonCapacity=0;
  function annualColumnCapacity(){
    const rootWidth=root.clientWidth||976,available=(main.clientWidth||rootWidth)-(rootWidth<=580?32:52);
    return Math.max(3,Math.min(13,Math.floor((available-40)/48)));
  }
  function annualComparison(years){
    comparisonCapacity=annualColumnCapacity();const ordered=[...years].sort((a,b)=>a-b),panels=Math.ceil(ordered.length/comparisonCapacity),base=Math.floor(ordered.length/panels),extra=ordered.length%panels,batches=[];let offset=0;
    for(let i=0;i<panels;i++){const size=base+(i<extra?1:0);batches.push(ordered.slice(offset,offset+size));offset+=size;}
    const legend=key=>`<div class="assessment-legend-group"><span>${key==='difficulty'?'左柱 · 难度':'右柱 · 计算量'}</span>${bands[key].map(b=>`<span><i class="chart-swatch ${b.cls}" aria-hidden="true"></i>${b.short}</span>`).join('')}</div>`;
    const ticks=[0,50,100,150],bar=ps=>`<span class="assessment-column-stack" aria-hidden="true">${ps.filter(b=>b.points>0).map(b=>`<span class="${b.cls}" style="height:${b.points/150*100}%"></span>`).join('')}</span>`;
    return `<section class="year-comparison" aria-label="历年难度与计算量分值构成"><div class="comparison-title"><h3>历年对比</h3><span>分值 · 满分150</span></div><div class="assessment-column-legend">${legend('difficulty')}${legend('calculation')}</div>${batches.map(batch=>`<div class="assessment-column-panel" role="group" aria-label="${batch[0]}至${batch[batch.length-1]}年"><div class="assessment-column-axis" aria-hidden="true">${ticks.map(v=>`<span style="bottom:${v/150*100}%">${v}</span>`).join('')}</div><div class="assessment-column-area"><div class="assessment-column-grid" aria-hidden="true">${ticks.map(v=>`<span style="bottom:${v/150*100}%"></span>`).join('')}</div><div class="assessment-column-years" style="grid-template-columns:repeat(${batch.length},minmax(0,1fr))">${batch.map(y=>{const qs=scoped().filter(q=>q.year===y),ds=parts(qs,'difficulty'),cs=parts(qs,'calculation'),label=`${y}年，难度：${ds.map(b=>`${b.short}${b.points}分`).join('，')}；计算量：${cs.map(b=>`${b.short}${b.points}分`).join('，')}`;return `<button type="button" class="assessment-column-year cursor-interaction" data-year="${y}" aria-pressed="${state.year===y}" aria-label="${esc(label)}" title="${esc(label)}"><span class="assessment-column-pair">${bar(ds)}${bar(cs)}</span><span class="assessment-year-label">${y}</span></button>`;}).join('')}</div></div></div>`).join('')}</section>`;
  }
  function renderDifficulty(){
    const years=ensureYear(),qs=scoped().filter(q=>q.year===state.year).sort((a,b)=>a.original_number-b.original_number),ds=parts(qs,'difficulty'),cs=parts(qs,'calculation');
    const hard=qs.filter(q=>[4,5].includes(q.difficulty)),heavy=qs.filter(q=>q.calculation===3),shown=state.questionFocus==='hard'?hard:state.questionFocus==='heavy'?heavy:qs;
    if(!shown.some(q=>q.id===state.difficultyQuestion))state.difficultyQuestion=[...shown].sort((a,b)=>(b.difficulty??-1)-(a.difficulty??-1)||(b.calculation??-1)-(a.calculation??-1))[0]?.id||'';
    const q=rowById(state.difficultyQuestion);
    const map=types.map(type=>{const items=shown.filter(q=>q.type===type);if(!items.length)return '';return `<div class="question-map-line"><div class="question-map-type">${type}</div><div class="question-map-cells">${items.map(r=>`<button type="button" class="cursor-interaction grade-${r.difficulty||'pending'}" data-difficulty-question="${esc(r.id)}" aria-pressed="${r.id===state.difficultyQuestion}" aria-label="${r.year}年第${r.original_number}题，难度${difficulty(r)}，计算量${cost(r)}，${r.original_points}分" title="第${r.original_number}题 · ${difficulty(r)} · 计算量${cost(r)}">${String(r.original_number).padStart(2,'0')}</button>`).join('')}</div></div>`;}).join('');
    const quickFilters=`<div class="question-focus" aria-label="逐题定位范围">${[{value:'all',label:'全部题目',rows:qs},{value:'hard',label:'较难题 · 4–5级',rows:hard},{value:'heavy',label:'高计算量',rows:heavy}].map(f=>`<button type="button" class="cursor-interaction" data-question-focus="${f.value}" aria-pressed="${state.questionFocus===f.value}" ${!f.rows.length?'disabled':''}>${f.label} · ${f.rows.length}题</button>`).join('')}</div>`;
    const reading=q?`<div class="question-rating-selection"><strong>第${q.original_number}题 · ${esc(q.model)}</strong><span>${q.original_points}分 · 难度 ${difficulty(q)} · 计算量 ${cost(q)}</span></div><details class="rating-source"><summary>查看原题与解答</summary>${questionReader(q)}<div class="reader-route"><button type="button" class="cursor-interaction" data-open-question="${esc(q.id)}">查看同类考法 →</button></div></details>`:'';
    return `<section><header class="difficulty-heading"><div><p>${years[years.length-1]}—${years[0]} · ${years.length}年</p></div></header><div class="difficulty-assessment">${annualComparison(years)}<section class="difficulty-detail" aria-label="所选年份题目与评级"><header class="difficulty-year-heading"><h3>${state.year}年</h3><p>${qs.length}题 · ${num(points(qs))}分</p></header><div class="year-composition"><p>难度：1–2级 ${ds[0].points}分 / 3级 ${ds[1].points}分 / 4–5级 ${ds[2].points}分</p><p>计算量：低 ${cs[0].points}分 / 中 ${cs[1].points}分 / 高 ${cs[2].points}分</p></div>${quickFilters}<div class="question-map-heading"><h3>逐题难度</h3>${state.questionFocus!=='all'?`<span>${shown.length}题 · ${points(shown)}分</span>`:''}</div><div class="chart-legend" aria-label="逐题难度颜色说明">${[1,2,3,4,5].map(g=>`<span><i class="chart-swatch grade-${g}" aria-hidden="true"></i>${g}级 ${gradeNames[g]}</span>`).join('')}</div><div class="question-map" aria-label="${state.year}年按题型排列的题目难度">${map}</div>${reading||'<p class="empty-state">此年份暂无符合条件的题目。</p>'}<details class="reference-notes"><summary>统计口径与参考</summary><p>按整题分值统计，等级仅作相对参考。</p><p>参考 <a href="https://www.ocr.org.uk/administration/support-and-tools/active-results/reports/unit-reports/question-level-analysis-report/" target="_blank" rel="noopener noreferrer">OCR逐题分析</a>。</p></details></section></div></section>`;

  }
  function render(){
    if(disposed)return;
    const openSource=root.querySelector('.rating-source')?.open,previousQuestion=main.dataset.readerQuestion;
    const catalogueScroll=root.querySelector('.topic-navigation')?.scrollTop||0,readerScroll=root.querySelector('.topic-workspace')?.scrollTop||0;
    root.setAttribute('data-reader-layout',state.readerLayout);root.querySelector('#research-period').value=state.period;
    root.querySelector('#analysis-current-heading').textContent=state.view==='difficulty'?'难度评估':'试卷分析';
    main.innerHTML=state.view==='difficulty'?renderDifficulty():renderStudy();
    const currentQuestion=state.view==='difficulty'?state.difficultyQuestion:state.studyMode==='year'?state.outlineQuestion:state.question;main.dataset.readerQuestion=currentQuestion;
    if(openSource&&currentQuestion===previousQuestion&&root.querySelector('.rating-source'))root.querySelector('.rating-source').open=true;
    const basket=root.querySelector('#analysis-selection');basket.hidden=!selection.length;basket.textContent=`查看已选题 · ${selection.length}`;
    const view=state.view==='difficulty'?'难度评估':'试卷分析';if(view!==lastView){lastView=view;options.onView(view);}
    typeset();
    const catalogue=root.querySelector('.topic-navigation'),reader=root.querySelector('.topic-workspace');
    if(catalogue){catalogue.tabIndex=0;catalogue.scrollTop=catalogueScroll;}
    if(reader){reader.tabIndex=0;reader.setAttribute('aria-label','考法与对应真题');reader.scrollTop=currentQuestion===previousQuestion?readerScroll:0;}

  }
  const click=event=>{
    const action=event.target.closest('button');if(action&&root.contains(action)&&!action.disabled){
      if(action.dataset.bankQuestion){options.onOpenQuestion(action.dataset.bankQuestion);return;}
      if(action.dataset.addQuestion){options.onAdd(action.dataset.addQuestion);return;}
      if(action.dataset.retryQuestion){failures.delete(action.dataset.retryQuestion);render();return;}
      if(action.id==='analysis-selection'){options.onSelection();return;}
    }
    const button=event.target.closest('button');if(!button||!root.contains(button)||button.disabled)return;
    if(button.dataset.view){state.view=button.dataset.view;render();save();return;}
    if(button.dataset.studyMode){state.studyMode=button.dataset.studyMode;render();save();return;}
    if(button.dataset.topic){state.topic=button.dataset.topic;state.question='';state.view='study';state.studyMode='topic';render();if(window.matchMedia('(max-width:780px)').matches)root.querySelector('.topic-workspace')?.scrollIntoView({block:'start'});save();return;}
    if(button.dataset.question){state.question=button.dataset.question;render();save();return;}
    if(button.dataset.chapter){state.yearChapter=state.yearChapter===button.dataset.chapter?'':button.dataset.chapter;state.outlineQuestion='';render();save();return;}
    if(button.dataset.clearChapter){state.yearChapter='';render();save();return;}
    if(button.dataset.questionFocus){state.questionFocus=button.dataset.questionFocus;render();save();return;}
    if(button.dataset.outlineType){state.outlineType=button.dataset.outlineType;state.yearChapter='';state.outlineQuestion='';render();save();return;}
    if(button.dataset.outlineQuestion){state.outlineQuestion=button.dataset.outlineQuestion;render();save();return;}
    if(button.dataset.openQuestion){const q=rowById(button.dataset.openQuestion);state.topic=q.model;state.question=q.id;state.view='study';state.studyMode='topic';render();save();return;}
    if(button.dataset.year){state.year=Number(button.dataset.year);state.difficultyQuestion='';state.yearChapter='';state.outlineQuestion='';render();save();return;}
    if(button.dataset.difficultyQuestion){state.difficultyQuestion=button.dataset.difficultyQuestion;render();save();return;}
    if(button.id==='research-standards'){const panel=root.querySelector('#standards-panel');panel.hidden=!panel.hidden;button.setAttribute('aria-expanded',String(!panel.hidden));}
  };
  const change=event=>{
    if(event.target.id==='research-period'){state.period=event.target.value;state.yearChapter='';state.outlineQuestion='';render();save();}
    if(event.target.id==='paper-year'){state.year=Number(event.target.value);state.difficultyQuestion='';state.yearChapter='';state.outlineQuestion='';render();save();}
  };
  root.addEventListener('click',click);root.addEventListener('change',change);
  try{restore(JSON.parse(sessionStorage.getItem('math2-analysis-v2')||'null'));}catch{}
  state.view=options.view==='难度评估'?'difficulty':'study';lastView=options.view;
  if(!DATA.rows.length){main.innerHTML='<p class="empty-state">当前题库没有2014—2026年的数学二真题。</p>';return {setView(){},setSelection(){},dispose(){disposed=true;root.removeEventListener('click',click);root.removeEventListener('change',change);host.replaceChildren();}};}
  render();
  const observer=new ResizeObserver(()=>{fitFormulae();if(!disposed&&state.view==='difficulty'&&annualColumnCapacity()!==comparisonCapacity)render();});observer.observe(root);
  return {setView(view){const next=view==='难度评估'?'difficulty':'study';if(next!==state.view){state.view=next;lastView=view;render();save();}},setSelection(ids){selection=ids;render();},dispose(){disposed=true;observer.disconnect();root.removeEventListener('click',click);root.removeEventListener('change',change);host.replaceChildren();}};
}
