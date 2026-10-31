'use strict';
(() => {
  const DEPARTMENTS = [
    {id:'cis',name:'통상협력총괄과',countries:['러시아','우크라이나','카자흐스탄','투르크메니스탄','우즈베키스탄','아제르바이잔','아르메니아','몽골','키르기스스탄','타지키스탄','조지아','몰도바','벨라루스']},
    {id:'neasia',name:'동북아통상과',countries:['중국','일본','홍콩','대만']},
    {id:'india',name:'인도통상협력과',countries:['인도','서남아']},
    {id:'asean',name:'아주통상과',countries:['필리핀','싱가포르','인도네시아','말레이시아','베트남','라오스','기타 아세안']},
    {id:'mea',name:'중동아프리카통상과',countries:['UAE','쿠웨이트','이집트','사우디','이란','이스라엘','기타 중동·아프리카']}
  ];
  const CATEGORIES=['국제·외교','정책·규제','경제동향','산업동향','대외교역','중동정세'];
  const ALIASES={india:{'서남아':['파키스탄','방글라데시','스리랑카','네팔','부탄','몰디브','아프가니스탄']},asean:{'기타 아세안':['태국','캄보디아','미얀마','브루나이','동티모르']},mea:{'UAE':['아랍에미리트'],'사우디':['사우디아라비아'],'기타 중동·아프리카':['카타르','오만','이라크','예멘','콩고민주공화국','리비아','튀르키예','터키','바레인','요르단','레바논','시리아','팔레스타인','남아프리카공화국','나이지리아','케냐','에티오피아','모로코','알제리','튀니지','가나','수단','남수단','앙골라','탄자니아','세네갈','콩고','코트디부아르','모잠비크','우간다','르완다','잠비아','짐바브웨','카메룬','마다가스카르','모리셔스','보츠와나','나미비아']}};
  function matches(issue,dept,country){return (issue.countries||[]).some(c=>c===country||(ALIASES[dept]?.[country]||[]).includes(c));}
  function orderSections(data,prefs={}){
    const selected=DEPARTMENTS.find(d=>d.id===prefs.department);
    const country=selected?.countries.includes(prefs.country)?prefs.country:'';
    const order=selected?[selected,...DEPARTMENTS.filter(d=>d.id!==selected.id)]:DEPARTMENTS;
    const result=[];
    order.forEach(d=>{const issues=data.departments?.find(x=>x.id===d.id)?.issues||[];
      if(d.id===selected?.id&&country){result.push({kind:'country',deptId:d.id,issues:issues.filter(i=>matches(i,d.id,country))});result.push({kind:'dept',deptId:d.id,issues:issues.filter(i=>!matches(i,d.id,country))});}
      else result.push({kind:'dept',deptId:d.id,issues:[...issues]});
    });return result;
  }
  window.TradeBrief={orderSections};
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeUrl=url=>{try{const u=new URL(url);return ['https:','http:'].includes(u.protocol)?u.href:'';}catch{return '';}};
  const source=b=>{const label=`(${esc(b.source)})`,url=safeUrl(b.url);return url?`<a class="source" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${label}</a>`:`<span class="source">${label}</span>`;};
  const dotted=s=>String(s||'').replaceAll('-','.');
  let data=null,prefs={department:'',country:''};
  try{const saved=JSON.parse(localStorage.getItem('tradeBrief.prefs'));if(saved&&DEPARTMENTS.some(d=>d.id===saved.department)){prefs.department=saved.department;prefs.country=DEPARTMENTS.find(d=>d.id===saved.department).countries.includes(saved.country)?saved.country:'';}}catch{}
  DEPARTMENTS.forEach(d=>$('department').add(new Option(d.name,d.id)));
  function controls(){ $('department').value=prefs.department;const country=$('country');country.replaceChildren(new Option('전체',''));const dept=DEPARTMENTS.find(d=>d.id===prefs.department);country.disabled=!dept;dept?.countries.forEach(c=>country.add(new Option(c,c)));country.value=prefs.country; }
  function save(){try{localStorage.setItem('tradeBrief.prefs',JSON.stringify(prefs));}catch{}controls();if(data)render();}
  $('department').addEventListener('change',e=>{prefs={department:e.target.value,country:''};save();});
  $('country').addEventListener('change',e=>{prefs.country=e.target.value;save();});
  $('reset').addEventListener('click',()=>{prefs={department:'',country:''};save();});controls();
  const tabs=[$('brief-tab'),$('country-tab')];
  function tab(index){tabs.forEach((t,i)=>{t.setAttribute('aria-selected',String(i===index));t.tabIndex=i===index?0:-1;$(i===0?'brief':'country-info').hidden=i!==index;});}
  tabs.forEach((t,i)=>{t.addEventListener('click',()=>tab(i));t.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?1:1-i;tab(n);tabs[n].focus();}});});
  const bullets=items=>`<ul>${items.map(b=>`<li class="bullet">${esc(b.text)} ${source(b)}</li>`).join('')}</ul>`;
  function issueHTML(i){return `<article class="issue"><div class="meta">[${esc(i.countries.join(', '))}, <span class="badge cat-${CATEGORIES.indexOf(i.category)}">${esc(i.category)}</span>]</div><h3>${esc(i.title)}</h3>${bullets(i.bullets)}</article>`;}
  function render(){
    const date=dotted(data.date);const day=new Date(data.date+'T00:00:00+09:00');
    // Explicit timezone formatting keeps timestamps correct outside Korea.
    const weekday=new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',weekday:'long'}).format(day);
    $('report-date').textContent=`${date} (${weekday})`;
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(data.generatedAt));const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));
    $('updated').textContent=`업데이트: ${p.year}.${p.month}.${p.day} ${p.hour}:${p.minute} KST`;
    let html=`<p class="coverage">${esc(data.coverage)}</p><article class="card top"><h2>★ Global Top Issues (${date})</h2>${bullets(data.topIssues)}</article><h2>★ 일일보도동향 (${date})</h2>`;
    orderSections(data,prefs).forEach(s=>{const d=DEPARTMENTS.find(d=>d.id===s.deptId);const title=s.kind==='country'?`★ ${prefs.country} 관련 이슈`:`□ ${d.name}`;html+=`<section class="card ${s.deptId===prefs.department?'selected':''} ${s.kind==='country'?'country-section':''}"><h2>${esc(title)}</h2>${s.issues.length?s.issues.map(issueHTML).join(''):`<p class="muted">${s.kind==='country'?`금일 ${esc(prefs.country)} 관련 이슈 없음`:'금일 반영 이슈 없음'}</p>`}</section>`;});
    if(data.reports?.length)html+=`<section class="card"><h2>주요 경제단체 보고서</h2><ul>${data.reports.map(r=>`<li class="bullet">${esc(r.org)}, ${esc(r.title)} (${esc(r.date)}) ${safeUrl(r.url)?`<a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">PDF</a>`:''}</li>`).join('')}</ul></section>`;
    if(data.notes?.length)html+=`<footer class="notes">${data.notes.map(n=>`<p>${esc(n)}</p>`).join('')}</footer>`;
    $('brief').innerHTML=html;$('copy').disabled=false;
  }
  function plainText(){const date=dotted(data.date),lines=[`★ Global Top Issues (${date})`,'',...data.topIssues.map(b=>`ㅇ ${b.text} (${b.source})`),'',`★ 일일보도동향 (${date})`,''];orderSections(data,prefs).forEach(s=>{lines.push(s.kind==='country'?`★ ${prefs.country} 관련 이슈`:`□ ${DEPARTMENTS.find(d=>d.id===s.deptId).name}`);if(!s.issues.length)lines.push(s.kind==='country'?`금일 ${prefs.country} 관련 이슈 없음`:'금일 반영 이슈 없음');s.issues.forEach(i=>lines.push(`[${i.countries.join(', ')}, ${i.category}] ${i.title}`,...i.bullets.map(b=>`ㅇ ${b.text} (${b.source})`)));lines.push('');});if(data.reports?.length)lines.push('주요 경제단체 보고서',...data.reports.map(r=>`ㅇ ${r.org}, ${r.title} (${r.date})${safeUrl(r.url)?' PDF: '+r.url:''}`),'');lines.push(...(data.notes||[]));return lines.join('\n');}
  $('copy').addEventListener('click',async()=>{const text=plainText();try{try{await navigator.clipboard.writeText(text);}catch{const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.append(area);area.select();try{if(!document.execCommand('copy'))throw Error('copy');}finally{area.remove();$('copy').focus();}}$('status').textContent='보고서 텍스트를 복사했습니다.';}catch{$('status').textContent='자동 복사를 사용할 수 없습니다. 아래 텍스트를 선택하여 복사해 주세요.';const area=document.createElement('textarea');area.value=text;area.setAttribute('aria-label','복사할 보고서');area.style.width='100%';area.rows=12;$('status').append(area);area.select();}});
  function usable(d){return d&&/^\d{4}-\d{2}-\d{2}$/.test(d.date)&&Number.isFinite(Date.parse(d.date))&&Number.isFinite(Date.parse(d.generatedAt))&&typeof d.coverage==='string'&&Array.isArray(d.topIssues)&&d.topIssues.length===5&&d.topIssues.every(b=>typeof b.text==='string'&&typeof b.source==='string')&&Array.isArray(d.departments)&&d.departments.every(d=>DEPARTMENTS.some(x=>x.id===d.id)&&Array.isArray(d.issues)&&d.issues.every(i=>Array.isArray(i.countries)&&CATEGORIES.includes(i.category)&&typeof i.title==='string'&&Array.isArray(i.bullets)&&i.bullets.every(b=>typeof b.text==='string'&&typeof b.source==='string')))&&Array.isArray(d.reports)&&d.reports.every(r=>r&&typeof r.title==='string')&&(!d.notes||Array.isArray(d.notes));}
  (async()=>{try{try{const response=await fetch('data/report.json?v='+Date.now());if(!response.ok)throw Error('HTTP');const json=await response.json();if(!usable(json))throw Error('schema');data=json;}catch{if(!usable(window.REPORT_DATA))throw Error('missing');data=window.REPORT_DATA;}render();}catch{$('report-date').textContent='보고서 확인 필요';$('brief').innerHTML='<article class="card"><h2>아직 보고서를 불러올 수 없습니다</h2><p>보고서 파일이 준비되지 않았거나 형식이 올바르지 않습니다. data/report.json과 data/report.js가 생성되었는지 확인한 후 다시 열어 주세요.</p><p class="muted">로컬에서 파일을 직접 열었다면 python3 tools/build_report_js.py 실행 후 새로고침해 주세요.</p></article>';}})();
})();
