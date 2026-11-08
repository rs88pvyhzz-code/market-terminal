#!/usr/bin/env python3
"""Market Terminal 2026-11-08: source-data repair and compact UI upgrade.
Upload this file to the repository root; see publish.yml for two stages.
--pre: fix official Eurostat dataset mappings before data collection.
--post: add period-return analysis, compact calendar, tab-specific quality audit.
All market prices and existing ETF records are left untouched.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import hashlib

def repair(source):
    if "'prc_hicp_minr'" in source and "'coicop18':'TOTAL'" in source and "'age':'TOTAL'" in source:
        return source, False
    fixes = [
        ("'prc_hicp_manr'", "'prc_hicp_minr'", 2),
        ("'coicop':'CP00'", "'coicop18':'TOTAL','unit':'RCH_A'", 2),
        ("'age':'Y15-74'", "'age':'TOTAL'", 2),
    ]
    for old,new,count in fixes:
        found=source.count(old)
        if found!=count:
            raise ValueError(f'Eurostat source layout changed: expected {count} occurrence(s) of {old}, found {found}')
        source=source.replace(old,new)
    # Add two well-defined, official euro-area comparisons without extending
    # hundreds of source requests to every member country.
    anchor="    ('namq_10_gdp', {'geo':'EA21','na_item':'B1GQ','s_adj':'SCA','unit':'CLV_PCH_PRE'}, 'eu_gdp_qoq', 'Euro-area real GDP (q/q)', 'quarterly'),\n]"
    if source.count(anchor)!=1:
        raise ValueError('Could not locate Eurostat macro series insertion point')
    insert="""    ('namq_10_gdp', {'geo':'EA21','na_item':'B1GQ','s_adj':'SCA','unit':'CLV_PCH_PRE'}, 'eu_gdp_qoq', 'Euro-area real GDP (q/q)', 'quarterly'),
    ('namq_10_gdp', {'geo':'EA21','na_item':'B1GQ','s_adj':'SCA','unit':'CLV_PCH_SM'}, 'eu_gdp_yoy', 'Euro-area real GDP (y/y)', 'quarterly'),
    ('une_rt_m', {'geo':'EA21','sex':'T','age':'Y_LT25','s_adj':'SA','unit':'PC_ACT'}, 'eu_youth_unemployment', 'Euro-area youth unemployment (under 25)', 'monthly'),
]"""
    return source.replace(anchor,insert,1),True


TOKEN='window.MT_DATA = '

def snapshot_hash(s):
    i=s.index(TOKEN)+len(TOKEN);j=s.index(';</script>',i)
    return hashlib.sha256(s[i:j].encode('utf-8')).hexdigest()

def upgrade(s,css,js):
    if 'mt-clarity-upgrade-css' in s:raise ValueError('Clarity layer already installed; refusing duplicate')
    baseline=snapshot_hash(s)
    anchor='function renderReal(){'
    if s.count(anchor)!=1:raise ValueError('Calendar/scoreboard script insertion anchor missing or repeated')
    if s.count('function renderScore(){')!=1 or s.count('function renderCalendar(){')!=1:
        raise ValueError('Scoreboard or calendar implementation changed; refusing unsafe patch')
    if '</head>' not in s:raise ValueError('HTML head not found')
    s=s.replace(anchor,js+'\n'+anchor,1)
    s=s.replace('</head>','<style id="mt-clarity-upgrade-css">\n'+css+'\n</style>\n</head>',1)
    if snapshot_hash(s)!=baseline:raise ValueError('Market data changed during UI upgrade')
    for item in ['mt-mover-row','mt-quality-focus','mt-calendar-topic','mt-quality-tab-filter']:
        # JS source contains all needed parts except an optional helper name.
        if item!='mt-calendar-topic' and item not in s:raise ValueError('Missing '+item)
    return s

CSS=r'''/* Style normalization and compact data-focused views. No global value sizes distorted. */
.panel h2,.workspace-title h1{font-size:clamp(17px,1.4vw,20px);line-height:1.3}
.panel h3{font-size:clamp(13px,1.05vw,16px);line-height:1.35}
.panel p.note,.note{font-size:12px;line-height:1.5}
.panel .mini,.panel small{font-size:11px;line-height:1.45}
.panel input,.panel select,.panel button{font-size:12px}
.macro{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:8px!important}
.macro button{min-width:0;text-align:left}
.macro .mv{font-size:20px;line-height:1.35;font-variant-numeric:tabular-nums}
#score-panel{min-width:0}
.mt-period-controls{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
#score{display:grid;gap:4px;min-width:0}
.mt-mover-row{display:grid;grid-template-columns:minmax(128px,205px) minmax(0,1fr) 75px;gap:10px;align-items:center;min-height:27px;font-size:12px}
.mt-mover-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mt-mover-track{display:flex;position:relative;height:12px;min-width:0;background:#25242e;overflow:hidden;border-radius:2px}
.mt-mover-track:after{content:"";position:absolute;left:50%;top:0;bottom:0;width:1px;background:#7a7482;opacity:.9}
.mt-mover-half{width:50%;height:100%;display:flex;align-items:stretch}
.mt-mover-negative{justify-content:flex-end}
.mt-mover-positive{justify-content:flex-start}
.mt-mover-loss{display:block;background:#ff605f;height:100%;border-radius:2px}
.mt-mover-gain{display:block;background:#4fcb91;height:100%;border-radius:2px}
.mt-mover-row>span:last-child{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.mt-period-table-wrap{margin-top:14px}
.mt-table-scroll{overflow-x:auto;max-width:100%}
.mt-return-table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:12px;min-width:610px}
.mt-return-table th,.mt-return-table td{padding:7px 6px;border-bottom:1px solid #2e2d35;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.mt-return-table th:first-child,.mt-return-table td:first-child{text-align:left;width:25%;overflow:hidden;text-overflow:ellipsis}
.mt-cal-row{min-width:0;padding:8px 0}
.mt-event-details>summary{cursor:pointer;color:var(--accent,#f7a329)}
.mt-event-details ul{padding-left:20px;margin:9px 0 1px}
.mt-event-details li{padding:3px 0}
.mt-quality-focus{border:1px solid #34313b;padding:16px;border-radius:8px;margin:0 0 20px}
.mt-quality-headline{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:12px 0}
.mt-quality-kpi{border:1px solid #34313b;border-radius:5px;padding:10px;min-width:0;display:flex;flex-direction:column;gap:8px}
.mt-quality-kpi span{font-size:11px;color:#acaab4}
.mt-quality-kpi strong{font-size:21px;font-weight:500;font-variant-numeric:tabular-nums}
.mt-quality-focus>label{display:flex;gap:8px;align-items:center;max-width:360px}
.mt-quality-issue-list{display:grid;gap:1px;margin-top:12px}
.mt-quality-issue{display:grid;grid-template-columns:110px 70px minmax(0,1fr);gap:10px;align-items:center;border-bottom:1px solid #302f36;padding:8px 0;font-size:12px}
.mt-quality-section{color:#f7a329}
.mt-quality-severity{color:#aaa8b5}
.mt-full-audit{margin:8px 0}
.mt-full-audit>summary{cursor:pointer;padding:12px;color:#f7a329;border:1px solid #34313b}
.mt-audit-content{padding:12px 0}
.mt-quality-link{margin-left:auto;font-size:10px!important;white-space:nowrap}
.mt-quality-more{margin-top:12px}
.mt-quality-more summary{cursor:pointer}
@media(max-width:860px){.macro{grid-template-columns:repeat(2,minmax(0,1fr))!important}.mt-quality-headline{grid-template-columns:repeat(2,minmax(0,1fr))}.mt-mover-row{grid-template-columns:minmax(90px,155px) minmax(0,1fr) 66px;gap:7px}}
@media(max-width:510px){.mt-mover-row{grid-template-columns:minmax(90px,125px) minmax(0,1fr) 64px}.mt-quality-issue{grid-template-columns:1fr 65px;gap:3px}.mt-quality-issue span:last-child{grid-column:1 / -1}.macro .mv{font-size:18px}}

#mt-other-audits{margin-top:12px;border:1px solid #34313b;border-radius:5px;padding:10px}
#mt-other-audits>summary{cursor:pointer;color:#f7a329;padding:4px 0 10px}
#mt-other-audits>.panel{margin-top:14px}
'''
JS=r'''// Market Terminal clarity: same tab count and source data; uses existing closure.
// Period returns are local-currency PRICE changes; long-horizon figures are annualised.
const mtMovePeriods=['1M','3M','6M','YTD','1Y','3Y','5Y'];
let mtMovePeriod='YTD',mtMoveHistory=null;
function mtMoveIndex(){
 if(mtMoveHistory)return mtMoveHistory;
 mtMoveHistory=new Map();
 const eligible=new Set((D.quotes||[]).map(q=>q.symbol));
 for(const point of D.history||[]){
  if(!eligible.has(point.symbol)||!(Number(point.close)>0)||!/^\d{4}-\d\d-\d\d$/.test(point.date||''))continue;
  if(!mtMoveHistory.has(point.symbol))mtMoveHistory.set(point.symbol,[]);
  mtMoveHistory.get(point.symbol).push(point);
 }
 for(const points of mtMoveHistory.values())points.sort((a,b)=>a.date.localeCompare(b.date));
 return mtMoveHistory;
}
function mtMoveReturn(q,range){
 const hist=mtMoveIndex().get(q.symbol)||[];
 if(hist.length<2)return range==='YTD'&&Number.isFinite(Number(q.ytdPct))?Number(q.ytdPct):null;
 const latest=hist.at(-1),end=new Date(latest.date+'T12:00:00Z');
 if(!Number.isFinite(end.valueOf()))return null;
 let target;
 if(range==='YTD')target=new Date(Date.UTC(end.getUTCFullYear()-1,11,31,12));
 else if(range==='1M'||range==='3M'||range==='6M')target=new Date(end.getTime()-({"1M":30,"3M":91,"6M":182}[range])*86400000);
 else{target=new Date(end.getTime());target.setUTCFullYear(target.getUTCFullYear()-({"1Y":1,"3Y":3,"5Y":5}[range]||1));}
 const key=target.toISOString().slice(0,10);
 let l=0,r=hist.length;
 while(l<r){const mid=(l+r)>>1;if(hist[mid].date<=key)l=mid+1;else r=mid;}
 const start=hist[l-1];if(!start)return null;
 const days=(end-new Date(start.date+'T12:00:00Z'))/86400000;
 if((target-new Date(start.date+'T12:00:00Z'))/86400000>9 || !(days>0)||!(Number(start.close)>0))return null;
 const years=range==='3Y'?3:range==='5Y'?5:0;
 if(years&&days<years*340)return null;
 // Do not imply the close-to-close move of a discontinuous data series is reliable.
 const first=l-1;let prev=hist[first];
 for(let i=first+1;i<hist.length;i++){const next=hist[i];if(Math.abs(Number(next.close)/Number(prev.close)-1)>.55)return null;prev=next;}
 const gross=Number(latest.close)/Number(start.close);
 if(!Number.isFinite(gross)||gross<=0)return null;
 return 100*(years?Math.pow(gross,365.25/days)-1:gross-1);
}
function mtMoveFormat(v){return v==null?'—':(v>0?'+':'')+fmt(v,1)+'%';}
function renderScore(){
 const host=$('score');if(!host)return;
 const parent=host.closest('#score-panel')||host.parentElement;
 let controls=$('mt-movers-periods');
 if(!controls){
  controls=el('div','mt-period-controls');controls.id='mt-movers-periods';
  for(const period of mtMovePeriods){const b=el('button','btn',period);b.type='button';b.dataset.mtPeriod=period;
   b.onclick=()=>{mtMovePeriod=period;renderScore();};controls.append(b);}
  host.before(controls);
 }
 for(const b of controls.querySelectorAll('button'))b.classList.toggle('active',b.dataset.mtPeriod===mtMovePeriod);
 const heading=parent?.querySelector('h2');if(heading)heading.textContent='PRICE MOVES BY PERIOD';
 const note=parent?.querySelector('p.note');if(note)note.textContent='Local-currency price changes, excluding income; 3Y and 5Y figures are annualised. Futures and currencies are not directly comparable investment returns.';
 const list=(D.quotes||[]).filter(q=>(!state.group||q.group===state.group)&&q.kind!=='yield'&&q.kind!=='volatility')
  .map(q=>({q,value:mtMoveReturn(q,mtMovePeriod)})).filter(r=>Number.isFinite(r.value))
  .sort((a,b)=>b.value-a.value);
 host.replaceChildren();
 if(!list.length){host.append(el('div','empty','No sufficient historical prices for this period.'));return;}
 const selected=list.length>12?[...list.slice(0,6),...list.slice(-6)]:list;
 const scale=Math.max(1,...selected.map(r=>Math.abs(r.value)));
 for(const {q,value} of selected){
  const row=el('div','mt-mover-row');const name=el('span','mt-mover-name',q.name);name.title=q.symbol;
  const track=el('div','mt-mover-track');const neg=el('div','mt-mover-half mt-mover-negative');const pos=el('div','mt-mover-half mt-mover-positive');
  const bar=el('span',value<0?'mt-mover-loss':'mt-mover-gain');bar.style.width=Math.max(.6,Math.abs(value)/scale*100).toFixed(2)+'%';
  (value<0?neg:pos).append(bar);track.append(neg,pos);
  const amount=el('span',value<0?'down':'up',mtMoveFormat(value));row.append(name,track,amount);host.append(row);
 }
 let details=$('mt-movers-table');
 if(!details){details=document.createElement('details');details.id='mt-movers-table';details.className='mt-period-table-wrap';
  details.append(el('summary','','All period percentages for the selected instruments'));
  const div=el('div','mt-table-scroll');const table=el('table','mt-return-table');
  const thead=el('thead');const hr=el('tr');for(const label of ['Instrument',...mtMovePeriods])hr.append(el('th','',label));thead.append(hr);
  table.append(thead);const tbody=el('tbody');tbody.id='mt-movers-matrix';table.append(tbody);div.append(table);details.append(div);host.after(details);
 }
 const tbody=$('mt-movers-matrix');tbody.replaceChildren();
 for(const {q} of selected){const tr=el('tr');tr.append(el('td','',q.name));
  for(const period of mtMovePeriods){const v=mtMoveReturn(q,period);tr.append(el('td',v==null?'':v<0?'down':'up',mtMoveFormat(v)));}
  tbody.append(tr);
 }
 const footer=details.querySelector('.mt-mover-footnote');if(footer)footer.remove();
 details.append(el('p','note mt-mover-footnote','3Y and 5Y percentages are compounded annual growth rates, not cumulative returns. Prices exclude dividends, roll costs and FX conversion.'));
}
function mtCalendarTopic(title){
 const t=String(title).toLowerCase();
 if(/unemployment|employment|labour|earnings|paye|job openings|payroll|wage/.test(t))return 'Labour market';
 if(/consumer price|inflation|cpi|hicp|producer price/.test(t))return 'Inflation & prices';
 if(/gdp|gross domestic|index of production|index of services|construction output|business investment|uk trade|retail sales|production|trade balance/.test(t))return 'Growth & activity';
 if(/bank rate|policy decision|monetary policy|fomc|governing council/.test(t))return 'Monetary policy';
 return String(title).replace(/\s+/g,' ').trim().toLowerCase();
}
function renderCalendar(){
 const host=$('calendar-items'),filters=$('calendar-filters');if(!host||!filters)return;
 host.replaceChildren();filters.replaceChildren();
 for(const [key,label] of [['ALL','All regions'],['UK','UK'],['EU','Euro area'],['US','US']]){
  const b=el('button','btn'+(key===state.calendarRegion?' active':''),label);b.onclick=()=>{state.calendarRegion=key;renderCalendar();};filters.append(b);
 }
 const today=(D.generatedAt||'').slice(0,10)||new Date().toISOString().slice(0,10);
 const events=(D.calendar||[]).filter(x=>x.date>=today&&(state.calendarRegion==='ALL'||x.region===state.calendarRegion))
  .sort((a,b)=>a.date.localeCompare(b.date));
 const merged=new Map();
 for(const e of events){
  const topic=mtCalendarTopic(e.title),key=[e.date,e.region,topic].join('|');
  if(!merged.has(key))merged.set(key,{date:e.date,region:e.region,topic,events:[],seen:new Set()});
  const g=merged.get(key),signature=(e.title||'').toLowerCase().replace(/[^a-z0-9]+/g,' ');
  if(!g.seen.has(signature)){g.events.push(e);g.seen.add(signature);}
 }
 const groups=[...merged.values()].slice(0,12);
 if(!groups.length){host.append(el('div','empty','No confirmed future releases for this region.'));return;}
 for(const g of groups){
  const box=el('div','calendar-item mt-cal-row');
  const day=el('div','day',datefmt(g.date)+' · '+g.region);box.append(day);
  if(g.events.length===1){const e=g.events[0];
   if((e.url||'').startsWith('https://')){const link=el('a','',e.title);link.href=e.url;link.target='_blank';link.rel='noopener noreferrer';box.append(link);}
   else box.append(el('strong','',e.title));
   box.append(el('div','mini',e.source+' · '+(e.time||'official calendar')));
  }else{
   const details=el('details','mt-event-details');details.append(el('summary','',g.topic+' — '+g.events.length+' related releases'));
   const ul=el('ul');for(const e of g.events){const li=el('li');
    if((e.url||'').startsWith('https://')){const a=el('a','',e.title);a.href=e.url;a.target='_blank';a.rel='noopener noreferrer';li.append(a);}else li.textContent=e.title;
    li.append(el('small','', ' · '+(e.time||e.source||'')));ul.append(li);
   }details.append(ul);box.append(details);
  }
  host.append(box);
 }
 let tip=$('mt-calendar-tip');if(!tip){tip=el('p','note');tip.id='mt-calendar-tip';host.after(tip);}
 const saved=events.length-groups.reduce((n,g)=>n+g.events.length,0);
 tip.textContent='Showing '+groups.length+' grouped events · '+events.length+' individual future releases. Related releases remain accessible inside each group.';
}
function mtBuildQuality(){
 const panel=$('quality-panel');if(!panel||$('mt-quality-focus'))return;
 const quality=D.quality||{},issues=[],add=(tab,severity,msg)=>issues.push({tab,severity,msg});
 const quoteMissing=Math.max(0,(quality.requested||0)-(quality.quoted||0));
 if(quoteMissing)add('Markets','Attention',quoteMissing+' market instruments without a validated quote');
 const stale=quality.staleQuotes||[];if(stale.length)add('Markets','Attention',stale.length+' stale market quotes: '+stale.slice(0,7).join(', '));
 const macros=D.macro||[],found=new Set(macros.map(m=>m.key));
 for(const [key,name] of [['eu_inflation','Euro-area HICP inflation'],['eu_unemployment','Euro-area unemployment'],['eu_gdp_qoq','Euro-area GDP'],['eu_policy','ECB deposit rate']])if(!found.has(key))add('Economics','Missing',name+' not retrieved; check official Eurostat/ECB source');
 const forecasts=(D.economicPrints||[]).filter(x=>x.forecast!=null).length;
 if(!forecasts)add('Economics','Limited','No independently recorded pre-release consensus forecasts; surprise fields unavailable');
 const calendars=D.calendar||[];const calendarKeys=new Set(calendars.map(e=>e.date+'|'+e.region+'|'+mtCalendarTopic(e.title)));
 if(calendars.length>calendarKeys.size)add('Economics','Display',String(calendars.length-calendarKeys.size)+' same-day related releases are grouped in the calendar');
 const ge=D.gilt_history||[],dateCount=new Set(ge.map(x=>x.date)).size;
 if(dateCount<2)add('Bonds & Rates','Missing','Gilt offer-price history needs more than one dated observation');
 const risk=D.marketAnalytics||{};if(!risk||!Object.keys(risk).length)add('Analytics','Limited','Some historical breadth/risk analysis has limited coverage');
 const watch=quality.personalWatchlist||{};
 if((watch.quoteEligible||0)>(watch.quoted||0))add('My Watchlist','Attention','Some watchlist prices are unavailable');
 if((watch.priceAnomalies||0)>0)add('My Watchlist','Review',watch.priceAnomalies+' watchlist history anomalies flagged');
 const etfs=D.etfTracker||{},funds=etfs.funds||etfs.records||[],etfq=etfs.coverage||{};
 if(funds.length){const lack=funds.filter(f=>f.terPct==null&&f.ter==null&&f.ocf==null).length;
  if(lack)add('ETF Trackers','Limited',lack+' fund charges absent from the compiled catalogue');}
 if((quality.retrievalWarnings||0)>0)add('Data Quality','Review',quality.retrievalWarnings+' download/source warnings available in the full audit');
 if((quality.fundamentalsEligible||0)>(quality.fundamentalsCovered||0))add('Equities','Limited',((quality.fundamentalsEligible||0)-(quality.fundamentalsCovered||0))+' company fundamental records missing');
 if(!issues.length)add('Data Quality','OK','No major coverage exceptions detected');
 const original=[...panel.children];const container=document.createElement('div');container.id='mt-quality-focus';container.className='mt-quality-focus';
 const h=el('h3','','DATA QUALITY — PRIORITY EXCEPTIONS');container.append(h);
 const intro=el('p','note','Actionable exceptions, grouped by tab. Full raw checks remain below, collapsed by default.');container.append(intro);
 const stats=el('div','mt-quality-headline');
 for(const [label,val] of [['Quoted markets',(quality.quoted??'—')+' / '+(quality.requested??'—')],['Issues requiring review',issues.filter(x=>x.severity!=='Display'&&x.severity!=='OK').length],['Missing euro indicators',issues.filter(x=>x.tab==='Economics'&&x.severity==='Missing').length],['Source warnings',quality.retrievalWarnings??(D.warnings||[]).length]]){
  const box=el('div','mt-quality-kpi');box.append(el('span','',label),el('strong','',String(val)));stats.append(box);
 }
 container.append(stats);
 const selector=el('select','field');selector.id='mt-quality-tab-filter';
 for(const tab of ['All tabs','Markets','Equities','Company Research','Bonds & Rates','Analytics','ETF Trackers','Economics','My Watchlist','Data Quality'])selector.add(new Option(tab,tab));
 const label=el('label','mini','FILTER BY TAB ');label.append(selector);container.append(label);
 const body=el('div','mt-quality-issue-list');body.id='mt-quality-list';container.append(body);
 const detail=el('details','mt-full-audit');detail.id='mt-full-audit';detail.append(el('summary','','Full source audit, missing data and retrieval logs'));
 const inside=el('div','mt-audit-content');for(const child of original)inside.append(child);detail.append(inside);
 panel.append(container,detail);
 function draw(){body.replaceChildren();const chosen=selector.value==='All tabs'?issues:issues.filter(x=>x.tab===selector.value);
  for(const item of chosen.slice(0,8)){const row=el('div','mt-quality-issue');row.append(el('span','mt-quality-section',item.tab),el('span','mt-quality-severity',item.severity),el('span','',item.msg));body.append(row);}
  let more=container.querySelector('.mt-quality-more');if(more)more.remove();
  if(chosen.length>8){more=el('details','mt-quality-more');more.append(el('summary','',String(chosen.length-8)+' additional exceptions'));
   for(const item of chosen.slice(8))more.append(el('p','note',item.tab+': '+item.msg));container.append(more);}
  if(!chosen.length)body.append(el('p','note','No recorded exceptions for this tab.'));
 }
 selector.addEventListener('change',draw);draw();
 for(const [id,tab] of [['macro','Economics'],['calendar','Economics'],['company-events-panel','Company Research'],['score-panel','Analytics'],['personal-watchlist-panel','My Watchlist'],['etf-tracker-panel','ETF Trackers'],['gilts','Bonds & Rates']]){
  const sec=$(id);if(!sec||sec.querySelector('.mt-quality-link'))continue;
  const a=el('button','btn mt-quality-link','DATA CHECKS');a.type='button';a.onclick=()=>{
   activateWorkspace('quality');selector.value=tab;draw();
   container.scrollIntoView({behavior:'smooth',block:'start'});
  };
  const header=sec.querySelector('.row')||sec;header.append(a);
 }
 const macroNote=$('macro-method');if(macroNote)macroNote.textContent='Official economic series; dates refer to observation periods. Data gaps and sources are summarised in Data Quality.';
 // Other installers may insert long ETF issuer-audit or source panels above this
 // panel after the main init. Move them into a single optional disclosure.
 window.setTimeout(mtReorderQualityPanels,50);
 $('tab-quality')?.addEventListener('click',mtReorderQualityPanels);
}
function mtReorderQualityPanels(){
 const view=$('view-quality'),panel=$('quality-panel');if(!view||!panel)return;
 let more=$('mt-other-audits');
 if(!more){more=el('details','mt-full-audit');more.id='mt-other-audits';
  more.append(el('summary','','ETF issuer audit, source inventory and full data tables'));
  view.append(more);
 }
 for(const child of [...view.children]){
  if(child===panel||child===more||child.classList.contains('workspace-title'))continue;
  more.append(child);
 }
 const heading=view.querySelector('.workspace-title');
 if(heading&&panel.previousElementSibling!==heading)view.insertBefore(panel,heading.nextSibling);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mtBuildQuality);
else mtBuildQuality();
'''

def main():
    parser=argparse.ArgumentParser()
    phases=parser.add_mutually_exclusive_group(required=True)
    phases.add_argument('--pre',action='store_true',help='Correct official macro API definitions before building')
    phases.add_argument('--post',action='store_true',help='Apply UI enhancements after market-data validation')
    parser.add_argument('--repo',default='.')
    parser.add_argument('--html',default='terminal.html')
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    if args.pre:
        file=Path(args.repo)/'regional_data.py';original=file.read_text(encoding='utf-8')
        revised,changed=repair(original)
        compile(revised,str(file),'exec')
        if changed and not args.check_only:file.write_text(revised,encoding='utf-8')
        print('Eurostat official source correction:', 'updated' if changed else 'already corrected')
    else:
        file=Path(args.html);original=file.read_text(encoding='utf-8')
        revised=upgrade(original,CSS,JS)
        if not args.check_only:file.write_text(revised,encoding='utf-8')
        print('Terminal clarity: period returns, source-audited EU macro data, grouped calendar, compact data quality. Existing snapshot preserved.')

if __name__=='__main__':main()
