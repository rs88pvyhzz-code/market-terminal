// ETF TRACKERS — optional, snapshot-only extension using the existing chart and FX helpers.
const ETF_DATA = D.etfTracker || {funds:[],history:[],coverage:{}};
const ETF_FUNDS = ETF_DATA.funds || [];
const ETF_BY_SYMBOL = new Map(ETF_FUNDS.map(f=>[f.symbol,f]));
const ETF_HISTORY = new Map((ETF_DATA.history||[]).map(r=>[r.symbol,r.points||[]]));
const etfState = {selected:ETF_FUNDS[0]?.symbol||'',compared:new Set(),range:'5Y',basis:'adjusted_gbp'};

function etfText(value){return value==null||value===''?'—':String(value);}
function etfPct(value){return value==null||!Number.isFinite(+value)?'—':fmt(value,2)+'%';}
function etfFee(f){return f.terPct==null?'—':fmt(f.terPct,2)+'%';}
function etfCell(row,value,cls){const cell=el('td',cls||'',value);row.append(cell);return cell;}
function etfStatistic(host,label,value,detail){
  const stat=el('div','etf-stat');stat.append(el('div','k',label),el('div','v',etfText(value)));
  if(detail)stat.append(el('div','d',detail));host.append(stat);
}
function etfFiltered(){
  const term=$('etf-search').value.trim().toLowerCase(),category=$('etf-category').value,market=$('etf-market').value;
  const replication=$('etf-replication').value,maxRaw=$('etf-maxfee').value.trim(),maximum=maxRaw===''?null:Number(maxRaw),sort=$('etf-sort').value;
  const rows=ETF_FUNDS.filter(f=>{
    if(category!=='all'&&f.category!==category)return false;
    if(market!=='all'&&f.market!==market)return false;
    if(replication==='physical'&&!f.replication?.startsWith('Physical'))return false;
    if(replication==='synthetic'&&!f.replication?.startsWith('Synthetic'))return false;
    if(replication==='unknown'&&f.replication)return false;
    if(maximum!=null&&Number.isFinite(maximum)&&(f.terPct==null||f.terPct>maximum))return false;
    return !term||[f.name,f.symbol,f.market,f.benchmark,f.note,f.isin].some(v=>String(v||'').toLowerCase().includes(term));
  });
  const compareNumber=(a,b,key,direction)=>{
    const x=a[key],y=b[key];return x==null&&y==null?0:x==null?1:y==null?-1:direction*(Number(x)-Number(y));
  };
  rows.sort((a,b)=>{
    if(sort==='name')return a.name.localeCompare(b.name);
    if(sort==='fee')return compareNumber(a,b,'terPct',1)||a.name.localeCompare(b.name);
    if(sort==='one')return compareNumber(a,b,'return1Y',-1)||a.name.localeCompare(b.name);
    if(sort==='three')return compareNumber(a,b,'return3Y',-1)||a.name.localeCompare(b.name);
    if(sort==='five')return compareNumber(a,b,'return5Y',-1)||a.name.localeCompare(b.name);
    return a.market.localeCompare(b.market)||compareNumber(a,b,'terPct',1)||a.name.localeCompare(b.name);
  });
  return rows;
}
function etfMarkets(){
  const picker=$('etf-market'),old=picker.value,category=$('etf-category').value;
  const markets=[...new Set(ETF_FUNDS.filter(f=>category==='all'||f.category===category).map(f=>f.market))].sort((a,b)=>a.localeCompare(b));
  picker.replaceChildren(new Option('All markets','all'));
  for(const market of markets)picker.add(new Option(market,market));
  picker.value=markets.includes(old)?old:'all';
}
function etfRows(f,range=etfState.range,basis=etfState.basis){
  const raw=ETF_HISTORY.get(f.symbol)||[],adjusted=basis.startsWith('adjusted'),toGBP=basis.endsWith('gbp');
  const points=raw.map(p=>{
    const val=Number(adjusted?p[2]:p[1]);
    if(!(val>0)||!Number.isFinite(val))return null;
    const price=toGBP?priceToGBP(val,f.quote?.currency||'',p[0]):val;
    return price!=null&&price>0&&Number.isFinite(price)?{date:p[0],v:price}:null;
  }).filter(Boolean);
  if(!points.length)return [];
  const start=startOf(points.at(-1).date,range);
  return points.filter(p=>p.date>=start);
}
function etfPerformance(f,range='1Y',basis=etfState.basis){
  const all=etfRows(f,range,basis);
  if(all.length<2)return null;
  const elapsed=(Date.parse(all.at(-1).date+'T12:00:00Z')-Date.parse(all[0].date+'T12:00:00Z'))/86400000/365.25;
  const years=range==='1Y'?1:range==='3Y'?3:range==='5Y'?5:range==='10Y'?10:0;
  if(years&&elapsed<years*0.90)return null;
  return 100*(Math.pow(all.at(-1).v/all[0].v,1/Math.max(elapsed,1/365.25))-1);
}
function etfRisk(f){
  const one=etfRows(f,'1Y',etfState.basis),period=etfRows(f,etfState.range,etfState.basis),returns=[];
  for(let i=1;i<one.length;i++){
    const days=(Date.parse(one[i].date)-Date.parse(one[i-1].date))/86400000;
    if(days>=1&&days<=5)returns.push(one[i].v/one[i-1].v-1);
  }
  let volatility=null;
  if(returns.length>=150){
    const mean=returns.reduce((s,x)=>s+x,0)/returns.length;
    volatility=100*Math.sqrt(returns.reduce((s,x)=>s+(x-mean)**2,0)/(returns.length-1))*Math.sqrt(252);
  }
  let peak=0,drawdown=null;
  for(const item of period){peak=Math.max(peak,item.v);if(peak>0)drawdown=Math.min(drawdown??0,100*(item.v/peak-1));}
  return {volatility,drawdown,n:returns.length,period:period.length};
}
function etfReference(f){
  if(!f.reference||!qMap.has(f.reference))return null;
  const q=qMap.get(f.reference),basis=etfState.basis,raw=histMap.get(f.reference)||[];
  const toGBP=basis.endsWith('gbp');
  const points=raw.map(p=>{
    const val=Number(p.v);
    const value=toGBP?priceToGBP(val,q.currency,p.date):val;
    return value>0&&Number.isFinite(value)?{date:p.date,v:value}:null;
  }).filter(Boolean);
  if(!points.length)return null;
  const cutoff=startOf(points.at(-1).date,etfState.range);
  return {name:q.name+' (index/reference level)',points:points.filter(p=>p.date>=cutoff)};
}
function etfDrawChart(){
  const primary=ETF_BY_SYMBOL.get(etfState.selected);
  if(!primary){empty('etf-chart','No ETF selected');return;}
  const symbols=[primary.symbol,...etfState.compared].filter((s,i,arr)=>arr.indexOf(s)===i).slice(0,4);
  const sources=[],rejected=[];
  for(const sym of symbols){
    const fund=ETF_BY_SYMBOL.get(sym);if(!fund)continue;
    const points=etfRows(fund);
    if(points.length<2){rejected.push(sym+': missing dated prices or FX/adjusted data');continue;}
    sources.push({name:sym,points});
  }
  if($('etf-reference').checked){
    const ref=etfReference(primary);
    if(ref&&ref.points.length>1)sources.push(ref);
    else rejected.push('Reference index price or GBP conversion unavailable');
  }
  $('etf-chart-stamp').textContent=etfState.range+' · '+(etfState.basis.endsWith('gbp')?'GBP converted':'Quoted currency')+' · '+sources.length+' series';
  if(!sources.length){empty('etf-chart','No matching data for selected price, currency and period.');$('etf-chart-note').textContent=rejected.join(' · ');return;}
  // Require exact matched observation dates. Do not forward-fill missing markets.
  let common=new Set(sources[0].points.map(p=>p.date));
  for(const s of sources.slice(1)){const dates=new Set(s.points.map(p=>p.date));common=new Set([...common].filter(d=>dates.has(d)));}
  const dates=[...common].sort();
  if(dates.length<2){empty('etf-chart','No overlapping dated observations for this comparison.');$('etf-chart-note').textContent=rejected.join(' · ');return;}
  const sets=sources.map((source,i)=>{
    const values=new Map(source.points.map(p=>[p.date,p.v])),base=values.get(dates[0]);
    return {name:source.name,color:PALETTE[i%PALETTE.length],pts:dates.map(date=>({date,v:100*values.get(date)/base}))};
  });
  chart('etf-chart',sets,{format:v=>fmt(v,1),aria:'ETF indexed performance starting at 100 on '+dates[0]});
  $('etf-chart-note').textContent='Rebased to 100 on '+datefmt(dates[0])+'. '+dates.length+' exact matched dates. '
    +(etfState.basis.startsWith('adjusted')?'Yahoo adjusted close is an unofficial total-return proxy. ':'PRICE returns exclude distributions. ')
    +(etfState.basis.endsWith('gbp')?'Dated spot FX conversion to GBP; missing FX omitted. ':'Quoted currencies may differ: cross-currency comparisons are invalid. ')
    +($('etf-reference').checked?'Index/reference series may use a different dividend method and index definition; NOT a tracking-difference calculation. ':'')
    +(rejected.length?' Missing: '+rejected.join(' · '):'');
}
function etfDetails(){
  const fund=ETF_BY_SYMBOL.get(etfState.selected);if(!fund)return;
  const q=fund.quote||{};
  $('etf-selected').textContent=fund.name+' ['+fund.symbol+']';
  $('etf-selected-meta').textContent=fund.category+' · '+fund.market+' · '+(fund.domicile||'Domicile not verified')+' · '+(fund.isin||'ISIN not recorded');
  const issuer=$('etf-facts-link');issuer.href=fund.issuerFactsUrl||'https://www.justetf.com/uk/';issuer.textContent=fund.issuerFactsUrl?'CHECK ETF PROFILE':'SEARCH ETF FACTS';
  $('etf-quote-link').href='https://finance.yahoo.com/quote/'+encodeURIComponent(fund.symbol)+'/';
  const stats=$('etf-detail-stats');stats.replaceChildren();
  etfStatistic(stats,'Annual OCF / TER',etfFee(fund),'Editorial snapshot dated '+(fund.factsAsOf||'not checked'));
  etfStatistic(stats,'Replication',fund.replication||'Unverified',fund.replication.startsWith('Synthetic')?'Swap counterparty/collateral exposure':'Fund legal structure');
  etfStatistic(stats,'Benchmark',fund.benchmark||'Unverified','Not necessarily chart reference');
  etfStatistic(stats,'Income',fund.distribution||'Unverified','Acc = reinvested; Dist = paid out');
  etfStatistic(stats,'Trading currency',q.currency||'Unavailable',fund.hedged?'Currency hedge: '+fund.hedged:'FX hedge not verified');
  etfStatistic(stats,'Last quotation',q.price==null?'Unavailable':fmt(q.price,Math.abs(q.price)<2?4:2),(q.asOf||'').slice(0,16)+' · '+(q.source||'No source'));
  etfStatistic(stats,'Fund size','Unavailable','Current issuer AUM not retrieved');
  etfStatistic(stats,'Bid-offer spread','Unavailable','No validated live two-way quotes');
  $('etf-warning').textContent=(fund.note||'')+(fund.note?' · ':'')+(fund.quoteStatus!=='Quoted'?'No confirmed current Yahoo price; fund stays in the catalogue. ':'')
    +'Charges, replication, fund size, share-class currency and trading line must be checked with the issuer or broker. No yield or tracking difference is manufactured.';
  const risk=etfRisk(fund),host=$('etf-risk-stats');host.replaceChildren();
  etfStatistic(host,'1Y volatility',etfPct(risk.volatility),risk.n>=150?risk.n+' daily observed returns':'Requires at least 150 daily returns');
  etfStatistic(host,'Max drawdown',etfPct(risk.drawdown),'Within selected '+etfState.range+' chart window');
  etfStatistic(host,'1Y annualised',etfPct(etfPerformance(fund,'1Y')),'Selected chart basis');
  etfStatistic(host,'3Y annualised',etfPct(etfPerformance(fund,'3Y')),'Selected chart basis');
  etfStatistic(host,'5Y annualised',etfPct(etfPerformance(fund,'5Y')),'Selected chart basis');
  etfStatistic(host,'Income yield','Unavailable','No validated issuer distribution yield');
  etfStatistic(host,'Tracking difference','Unavailable','Official index total-return data required');
  const peers=ETF_FUNDS.filter(f=>f.market===fund.market).sort((a,b)=>(a.terPct==null?Infinity:a.terPct)-(b.terPct==null?Infinity:b.terPct));
  const parent=$('etf-cost-peers');parent.replaceChildren();
  parent.append(el('p','note','OTHER CANDIDATES IN THIS MARKET — lowest KNOWN TER first. Same market does not imply the same index or return basis.'));
  const table=el('table','watch'),head=el('thead'),tr=el('tr');
  for(const label of ['ETF','Benchmark','Annual OCF / TER','Replication','Quote status'])tr.append(el('th','',label));head.append(tr);table.append(head);
  const body=el('tbody');for(const peer of peers.slice(0,12)){
    const row=el('tr');etfCell(row,peer.symbol+' — '+peer.name);etfCell(row,peer.benchmark);
    etfCell(row,etfFee(peer));etfCell(row,peer.replication||'Unverified');etfCell(row,peer.quoteStatus||'Unavailable');body.append(row);
  }table.append(body);parent.append(table);
  etfDrawChart();
}
function renderEtfTracker(){
  if(!$('etf-rows'))return;
  const coverage=ETF_DATA.coverage||{};
  $('etf-coverage').textContent=(coverage.quoted||0)+'/'+(coverage.catalogued||ETF_FUNDS.length)+' quoted · '+(coverage.withHistory||0)+' charts';
  const stats=$('etf-stats');stats.replaceChildren();
  etfStatistic(stats,'CATALOGUED',ETF_FUNDS.length,'ETF / bond candidates');
  etfStatistic(stats,'MARKETS',[...new Set(ETF_FUNDS.map(f=>f.market))].length,'Countries, regions, bond sectors');
  etfStatistic(stats,'QUOTE COVERAGE',coverage.quoted||0,'Unavailable quotes shown openly');
  etfStatistic(stats,'REPLICATION VERIFIED',ETF_FUNDS.filter(f=>f.replication).length,'Missing values not assumed');
  const filtered=etfFiltered();
  $('etf-result-count').textContent=filtered.length+' funds matching filters · 1Y / 3Y / 5Y values are annualised';
  const body=$('etf-rows');body.replaceChildren();
  for(const fund of filtered){
    const row=el('tr',fund.symbol===etfState.selected?'etf-active':'');row.title='Select '+fund.name;
    const name=etfCell(row,'','');name.append(el('span','etf-name',fund.name),el('span','etf-market',fund.market));
    etfCell(row,fund.symbol);etfCell(row,fund.benchmark||'—');etfCell(row,etfFee(fund),'n');
    etfCell(row,fund.replication||'Unverified',fund.replication.startsWith('Synthetic')?'etf-swap':'etf-unknown');
    etfCell(row,fund.distribution||'—');
    etfCell(row,fund.quote?.price==null?'—':fmt(fund.quote.price,Math.abs(fund.quote.price)<2?4:2)+' '+(fund.quote.currency||''),'n');
    etfCell(row,etfPct(fund.return1Y),'n');etfCell(row,etfPct(fund.return3Y),'n');etfCell(row,etfPct(fund.return5Y),'n');
    etfCell(row,(fund.quote?.asOf||'').slice(0,10)||'Unavailable');
    const td=etfCell(row,'');const check=el('input');check.type='checkbox';check.checked=etfState.compared.has(fund.symbol);
    check.setAttribute('aria-label','Compare '+fund.symbol);check.onchange=()=>{
      if(check.checked){if(etfState.compared.size>=3){check.checked=false;return;}etfState.compared.add(fund.symbol);}
      else etfState.compared.delete(fund.symbol);
      etfDrawChart();
    };td.append(check);
    row.onclick=e=>{if(e.target.closest('input,a'))return;etfState.selected=fund.symbol;renderEtfTracker();};body.append(row);
  }
  if(!ETF_BY_SYMBOL.has(etfState.selected))etfState.selected=ETF_FUNDS[0]?.symbol||'';
  etfDetails();
}
function etfExport(){
  const columns=['market','category','symbol','name','benchmark','terPct','replication','distribution','domicile','isin','hedged','return1Y','return3Y','return5Y','quoteStatus','note'];
  const cell=x=>'"'+String(x==null?'':x).replace(/"/g,'""')+'"';
  const csv=[columns.map(cell).join(','),...etfFiltered().map(f=>columns.map(k=>cell(f[k])).join(','))].join('\r\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=el('a');
  a.href=url;a.download='etf-trackers-'+(D.generatedAt||'snapshot').slice(0,10)+'.csv';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),250);
}
function initEtfTracker(){
  etfMarkets();
  $('etf-search').oninput=renderEtfTracker;
  $('etf-category').onchange=()=>{etfMarkets();renderEtfTracker();};
  for(const id of ['etf-market','etf-replication','etf-sort'])$(id).onchange=renderEtfTracker;
  $('etf-maxfee').oninput=renderEtfTracker;
  $('etf-period').onchange=e=>{etfState.range=e.target.value;etfDetails();};
  $('etf-basis').value=etfState.basis;
  $('etf-basis').onchange=e=>{etfState.basis=e.target.value;etfDetails();};
  $('etf-reference').onchange=etfDrawChart;
  $('etf-clear-comparisons').onclick=()=>{etfState.compared.clear();renderEtfTracker();};
  $('etf-export').onclick=etfExport;
}
