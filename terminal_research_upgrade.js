/* Market Terminal research upgrade: UI improvements only; no fabricated observations. */
(function(){
'use strict';
const D=window.MT_DATA||{};
const make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;};
const fmt=(x,d=2)=>Number.isFinite(x)?x.toLocaleString('en-GB',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
function dollars(x){return Number.isFinite(x)?fmt(x,2)+'%':'—';}
function setupBondNav(){
  const view=document.getElementById('view-bonds');if(!view||view.querySelector('#mt-bond-nav'))return;
  const nav=make('nav','mt-bond-nav');nav.id='mt-bond-nav';nav.setAttribute('aria-label','Bonds and rates sections');
  const tabs=[['gilts','UK Gilts'],['us-treasuries','US Treasuries'],['rates','Yield Curves'],['corporate-credit','Credit'],['sovereign','Sovereign Yields']];
  for(const [id,label] of tabs){if(!document.getElementById(id))continue;
    const b=make('button','btn',label);b.type='button';b.onclick=()=>{document.querySelectorAll('#mt-bond-nav button').forEach(x=>x.classList.remove('active'));b.classList.add('active');const section=document.getElementById(id);const details=section?.querySelector(':scope > details.mt-collapse');if(details)details.open=true;section?.scrollIntoView({behavior:'smooth',block:'start'});};nav.append(b);}
  const h=view.querySelector('.workspace-title');h?.insertAdjacentElement('afterend',nav);
}
function collapseTechnicalPanel(id,label){
 const panel=document.getElementById(id);if(!panel||panel.querySelector(':scope > details.mt-collapse'))return;
 const nodes=[...panel.children];if(nodes.length<=2)return;
 const details=make('details','mt-collapse');const summary=make('summary','',label);details.append(summary);
 for(const child of nodes.slice(1))details.append(child);panel.append(details);
}
function setupMacro(){
 const data=D.economicPrints||[],hasForecast=data.some(x=>x.forecast!=null);
 const panel=document.getElementById('macro-surprise');if(!panel)return;
 const heading=panel.querySelector('h2');if(!hasForecast){
   if(heading)heading.textContent='ECONOMIC INDICATORS — ACTUAL VS PRIOR';panel.classList.add('mt-no-consensus');
   const note=make('p','mt-inline-notice','No independently sourced pre-release consensus forecasts are loaded. Forecast and surprise columns are hidden; official actual and previous observations remain available.');
   (panel.querySelector('.row')||panel).insertAdjacentElement('afterend',note);
 }else{
   const note=make('p','mt-inline-notice','Forecast surprises are shown only when the forecast was recorded before release and has a verified source.');
   (panel.querySelector('.row')||panel).insertAdjacentElement('afterend',note);
 }
 const eventPanel=document.getElementById('company-events-panel');
 const issuer=D.companyEventCoverage?.issuerSourced??0;
 if(eventPanel&&issuer===0){const p=make('p','mt-inline-notice','No issuer-confirmed event dates were loaded. Any provider diary entries are estimates; use the issuer link before relying on a date.');eventPanel.insertBefore(p,eventPanel.children[1]||null);}
}
function panelForRisk(){
 const view=document.getElementById('view-analytics');if(!view)return;
 const panel=make('section','panel mt-risk-panel');panel.id='mt-risk-comparison';
 panel.innerHTML='<div class="row"><div><h2>COMPARABLE MARKET RISK & RETURNS</h2><p class="note">Price-only index performance; excludes dividends. Returns are annualised, volatility uses daily log returns. No figures are filled when price history is too short.</p></div><label class="mini" for="mt-risk-period">PERIOD <select class="field" id="mt-risk-period"><option>1Y</option><option>3Y</option><option>5Y</option></select></label></div><div class="small-scroll"><table class="watch mt-risk-table"><thead><tr><th>Market</th><th class="n">Ann. price return</th><th class="n">Volatility</th><th class="n">Max drawdown</th><th class="n">Observations</th></tr></thead><tbody id="mt-risk-rows"></tbody></table></div><p class="note" id="mt-risk-note">Indexes are in native currencies; not FX-converted, not total returns. Historical index-membership breadth elsewhere is subject to survivorship bias.</p>';
 const first=view.querySelector('#analytics-breadth');first?view.insertBefore(panel,first):view.append(panel);
 const selected=new Set(['^FTSE','^FTMC','^GSPC','^IXIC','^STOXX50E','^GDAXI','^N225','^NSEI']);
 const quotes=new Map((D.quotes||[]).filter(q=>selected.has(q.symbol)).map(q=>[q.symbol,q]));
 const prices=new Map([...selected].map(sym=>[sym,[]]));
 for(const row of D.history||[]){const a=prices.get(row.symbol);if(!a)continue;const p=Number(row.close);if(Number.isFinite(p)&&p>0&&/^\d{4}-\d\d-\d\d$/.test(row.date||''))a.push({date:row.date,p});}
 for(const a of prices.values())a.sort((x,y)=>x.date.localeCompare(y.date));
 function metrics(arr,years){
   if(arr.length<years*155)return null;
   const last=arr[arr.length-1],target=new Date(last.date+'T12:00:00Z');target.setUTCFullYear(target.getUTCFullYear()-years);
   const startT=target.toISOString().slice(0,10),start=arr.findIndex(x=>x.date>=startT);
   if(start<0||start>=arr.length-30||Math.abs((new Date(arr[start].date+'T12:00:00Z')-target)/86400000)>9)return null;
   const window=arr.slice(start);if(window.length<years*155)return null;
   const days=(new Date(last.date+'T12:00:00Z')-new Date(window[0].date+'T12:00:00Z'))/86400000;
   if(days<years*340)return null;
   const gaps=[],ret=[];let max=window[0].p,dd=0;
   for(let i=1;i<window.length;i++){const gap=(new Date(window[i].date+'T12:00:00Z')-new Date(window[i-1].date+'T12:00:00Z'))/86400000;
     if(gap<=0)return null;gaps.push(gap);
     const r=Math.log(window[i].p/window[i-1].p);if(Math.abs(r)>Math.log(1.55))return null;ret.push(r);
     max=Math.max(max,window[i].p);dd=Math.min(dd,window[i].p/max-1);
   }
   const abnormal=gaps.filter(x=>x>6).length;if(abnormal>Math.max(2,gaps.length*0.01))return null;
   const mean=ret.reduce((a,b)=>a+b,0)/ret.length;
   const variance=ret.reduce((a,b)=>a+(b-mean)**2,0)/(ret.length-1);
   return {growth:100*((last.p/window[0].p)**(365.25/days)-1),vol:Math.sqrt(variance*252)*100,draw:dd*100,n:window.length};
 }
 function paint(){const years={'1Y':1,'3Y':3,'5Y':5}[document.getElementById('mt-risk-period').value]||1;
  const tbody=document.getElementById('mt-risk-rows');tbody.replaceChildren();
  for(const symbol of ['^FTSE','^FTMC','^GSPC','^IXIC','^STOXX50E','^GDAXI','^N225','^NSEI']){
    const r=metrics(prices.get(symbol)||[],years),row=make('tr');const cells=[quotes.get(symbol)?.name||symbol,r?dollars(r.growth):'—',r?dollars(r.vol):'—',r?dollars(r.draw):'—',r?String(r.n):'Insufficient'];
    cells.forEach((value,i)=>row.append(make('td',i?'n':'',value)));tbody.append(row);
  }
  const note=document.getElementById('mt-risk-note');note.textContent='Native-currency price returns over '+years+' year'+(years>1?'s':'')+'. Indices exclude dividend income; comparisons across countries include different currencies. Current constituents used elsewhere can introduce survivorship bias.';
 }
 document.getElementById('mt-risk-period').addEventListener('change',paint);paint();
}
function setupQuality(){
 const panel=document.getElementById('quality-panel');if(!panel)return;
 const q=D.quality||{},stale=q.staleQuotes||[],warnings=D.warnings||[];
 const summary=make('section','mt-quality-summary');summary.id='mt-quality-exceptions';
 const heading=make('h3','', 'PRIORITY DATA EXCEPTIONS');summary.append(heading);
 const strip=make('div','mt-quality-grid');
 for(const [label,val] of [
  ['Market quotes',(q.quoted??'—')+' / '+(q.requested??'—')],
  ['Stale quotes',stale.length],
  ['Gilt quote dates',(D.gilts||[]).length?new Set((D.gilts||[]).map(x=>x.asOf)).size+' date(s)':'None'],
  ['Verified consensus',(D.economicPrints||[]).filter(x=>x.forecast!=null).length],
  ['Issuer-confirmed events',D.companyEventCoverage?.issuerSourced??0],
  ['Download warnings',warnings.length]
 ]){const card=make('div','mt-quality-card');card.append(make('span','',label),make('strong','',String(val)));strip.append(card);}summary.append(strip);
 const errors=make('p','note',stale.length?'Stale: '+stale.slice(0,10).join(', ')+(stale.length>10?' …':''):'No stale quote tickers reported.');summary.append(errors);
 const warn=make('details','mt-quality-alerts');warn.append(make('summary','',`Read ${warnings.length} collection warnings`));const list=make('ul');warnings.slice(0,30).forEach(s=>list.append(make('li','',String(s))));warn.append(list);summary.append(warn);
 const tiles=document.getElementById('dq-tiles');tiles?.insertAdjacentElement('beforebegin',summary);
 for(const id of ['dq-indices','dq-history','dq-alerts']){const target=document.getElementById(id);if(!target)continue;
  const wrapper=id==='dq-alerts'?target:target.parentElement;if(!wrapper||wrapper.closest('details.mt-quality-drilldown'))continue;
  const details=make('details','mt-quality-drilldown');const label=wrapper.querySelector('h3')?.textContent||'Detailed source and coverage information';details.append(make('summary','',label));wrapper.parentNode.insertBefore(details,wrapper);details.append(wrapper);
 }
}
function setupCompany(){
 const table=document.getElementById('peer-table');if(!table)return;
 const panel=document.getElementById('peer-panel');const p=make('p','mt-inline-notice','Absolute accounting figures can be converted using dated snapshot FX, but fiscal periods may differ. Compare ratios separately from monetary totals; conversion does not make unlike periods comparable.');panel?.append(p);
 const select=document.getElementById('mt-peer-currency');select?.addEventListener('change',()=>document.getElementById('peer0')?.dispatchEvent(new Event('change',{bubbles:true})));
}
function setupOverview(){
 const list=document.getElementById('news-list');if(!list)return;
 const p=make('p','mt-inline-notice','News and price changes are separate evidence; headlines do not establish why a share price moved.');list.insertAdjacentElement('afterend',p);
}
window.addEventListener('DOMContentLoaded',()=>{
  try{setupBondNav();collapseTechnicalPanel('us-treasuries','US Treasury security details and model calculations');
     collapseTechnicalPanel('sovereign','Sovereign yield source tables');setupMacro();panelForRisk();setupQuality();setupCompany();setupOverview();}
  catch(error){console.error('Market Terminal research upgrade:',error);}
});
})();
