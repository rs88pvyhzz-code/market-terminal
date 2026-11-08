#!/usr/bin/env python3
"""Post-build market-terminal research/UI upgrade.

Run AFTER verify_snapshot.py and BEFORE preparing GitHub Pages. No source datasets
are modified; no prices, forecasts or earnings dates are created. Existing
terminal embeds its snapshot in window.MT_DATA, which is byte-for-byte preserved.

Usage: python terminal_research_upgrade.py terminal.html
"""
from __future__ import annotations
import argparse
import hashlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
STYLE_ID = 'mt-research-upgrade-css'
JS_ID = 'mt-research-upgrade-js'
MARKER = 'window.MT_DATA = '

# This fragment runs inside the terminal's existing application closure so it
# can reuse its bond cashflow model and historical FX data without duplicating
# the main data collector.
INLINE_HELPERS = r'''
// Research upgrade: interest tax on conventional UK gilts only. Estimates are
// not tax advice; accrued-income rules/ex-dividend settlement are not modeled.
function mtNetGiltYield(b,clean,rate,asOf,quotedDirty){
 if(b.indexLinked||!(clean>0)||!(rate>=0&&rate<=100))return null;
 const data=giltCashflows(b,asOf);if(!data)return null;
 const cost=Number.isFinite(Number(quotedDirty))&&Number(quotedDirty)>0?Number(quotedDirty):clean+data.accrued;
 const coupon=b.coupon/2;
 const pv=y=>data.flows.reduce((sum,p)=>sum+(p.amount-coupon*rate/100)/Math.pow(1+y/200,2*p.t),0);
 let lo=-49,hi=149;
 if(pv(lo)<cost||pv(hi)>cost)return null;
 for(let i=0;i<72;i++){const mid=(lo+hi)/2;if(pv(mid)>cost)lo=mid;else hi=mid;}
 return (lo+hi)/2;
}
function mtRenderGiltTax(selected,selectedPrice,manual){
 const panel=document.getElementById('mt-gilt-tax'),body=document.getElementById('mt-gilt-tax-rows');
 const select=document.getElementById('mt-gilt-tax-rate');if(!panel||!body||!select)return;
 if(!select.dataset.wired){select.dataset.wired='1';select.onchange=()=>renderGilts();}
 const rate=Number(select.value);body.replaceChildren();
 if(selected.indexLinked){panel.hidden=true;return;}panel.hidden=false;
 const sourceDate=selected.asOf||(D.generatedAt||'').slice(0,10);
 const selectedMaturity=Date.parse(selected.maturity+'T12:00:00Z');
 const choices=giltList.filter(g=>!g.indexLinked&&g.quoted&&g.askClean>0&&g.asOf===selected.asOf)
  .sort((a,b)=>Math.abs(Date.parse(a.maturity+'T12:00:00Z')-selectedMaturity)-Math.abs(Date.parse(b.maturity+'T12:00:00Z')-selectedMaturity)).slice(0,6);
 if(!choices.some(g=>g.isin===selected.isin))choices.unshift(selected);
 const peers=choices.slice(0,6);
 for(const g of peers){const chosen=g.isin===selected.isin;const clean=chosen&&manual?selectedPrice:g.askClean;
  const date=chosen&&manual?(D.generatedAt||'').slice(0,10):g.asOf;
  const dirty=chosen&&manual?null:g.askDirty;
  const gross=giltValuation(g,clean,date,dirty),net=mtNetGiltYield(g,clean,rate,date,dirty);
  const row=document.createElement('tr');if(chosen)row.classList.add('selected');
  const columns=[g.shortTicker||g.name,g.maturity,fmt(clean,3),gross?fmt(gross.ytm,3)+'%':'—',net!=null?fmt(net,3)+'%':'—',gross?fmt(gross.duration,2):'—',g.asOf||'—'];
  for(let i=0;i<columns.length;i++){const cell=document.createElement('td');cell.className=i>=2&&i<=5?'n':'';cell.textContent=columns[i];if(i===0)cell.title=g.name;row.append(cell);}body.append(row);
 }
 document.getElementById('mt-gilt-tax-heading').textContent='AFTER-TAX GILT COMPARISON · '+rate+'% COUPON TAX';
 document.getElementById('mt-gilt-tax-summary').textContent='Nearest maturities to '+selected.maturity+' · quoted DMO offers '+sourceDate+'; a manually entered clean price applies only to the selected gilt.';
}
function mtRenderGiltSummary(host,statRows,b,v,clean,manual){
 const first=new Set(['Maturity','Coupon','Your clean purchase price','Model gross yield to maturity','Modified duration','Quoted bid / offer spread']);
 for(const [name,value,note] of statRows){if(first.has(name))host.append(researchTile(name,value,note));}
 const advanced=document.createElement('details');advanced.className='mt-advanced';const sum=document.createElement('summary');sum.textContent='Advanced valuation: dirty price, accrued interest, DV01, running yield and other calculations';advanced.append(sum);
 const grid=document.createElement('div');grid.className='research-stats';
 for(const [name,value,note] of statRows){if(!first.has(name))grid.append(researchTile(name,value,note));}
 advanced.append(grid);host.append(advanced);
 mtRenderGiltTax(b,clean,manual);
}
function mtGiltChartVisibility(count){
 const chartNode=document.getElementById('gilt-chart'),pills=document.getElementById('gilt-period');
 const heading=pills?.closest('.row');
 const visible=count>=2;
 if(chartNode)chartNode.hidden=!visible;
 if(pills)pills.hidden=!visible;
 if(heading){const h=heading.querySelector('h3');if(h)h.textContent=visible?'INDIVIDUAL GILT PRICE HISTORY':'INDIVIDUAL PRICE HISTORY — NOT YET AVAILABLE';}
 if(!visible&&chartNode){const note=chartNode.nextElementSibling;if(note&&note.classList.contains('note'))note.textContent='One valid dated DMO offer snapshot is saved. The price history is suppressed until at least two different dated prices are available. Collection of historical D10B data remains unverified.';}
}
function mtCompanyAmount(x,currency,kind,obj){
 const choice=document.getElementById('mt-peer-currency')?.value||'native';
 if(choice==='native')return companyAmount(x,currency);
 const date=(obj.f.asOf||obj.quote.financialAsOf||D.generatedAt||'').slice(0,10);
 const sign=x<0?-1:1;const effectiveCCY=(kind==='market'&&['GBp','GBX'].includes(currency))?'GBP':currency;
 const gbp=priceToGBP(Math.abs(x),effectiveCCY,date);
 if(gbp==null)return '—';
 if(choice==='gbp')return companyAmount(sign*gbp,'GBP');
 const rate=historicalFx('GBPUSD=X',date);
 return rate?companyAmount(sign*gbp*rate,'USD'):'—';
}
'''


def replace_exact(source: str, old: str, new: str, label: str) -> str:
    n = source.count(old)
    if n != 1:
        raise ValueError(f'{label}: expected exactly one anchor, found {n}. File changed; no output written.')
    return source.replace(old, new, 1)


def market_data_hash(source: str) -> str:
    a = source.index(MARKER) + len(MARKER)
    b = source.index(';</script>', a)
    return hashlib.sha256(source[a:b].encode('utf-8')).hexdigest()


def patch_html(source: str, css: str, js: str) -> str:
    before = market_data_hash(source)
    if f'id="{JS_ID}"' in source or f'id="{STYLE_ID}"' in source:
        raise ValueError('This snapshot already contains the research upgrade; refusing to inject twice')
    source = replace_exact(source, 'function renderGilts(){', INLINE_HELPERS+'\nfunction renderGilts(){', 'Gilt research insertion')
    source = replace_exact(source,
        'for(const [k,x,note] of st)host.append(researchTile(k,x,note));',
        'mtRenderGiltSummary(host,st,b,v,price,user!=null);',
        'Gilt concise + advanced summary')
    source = replace_exact(source,
        "else empty('gilt-chart',dates.length===1?'One DMO observation saved; the chart grows when later dated DMO files are collected.':'No historical DMO price snapshots yet.');",
        "else empty('gilt-chart',dates.length===1?'One dated price: historical chart unavailable.':'No historical DMO price snapshots yet.');\n  mtGiltChartVisibility(pts.length);",
        'Gilt history visibility')
    source = replace_exact(source,
        "value=kind==='ratio'?fmt(x,1)+'×':kind==='pct'?fmt(x,2)+'%':companyAmount(x,currency);covered++;",
        "value=kind==='ratio'?fmt(x,1)+'×':kind==='pct'?fmt(x,2)+'%':mtCompanyAmount(x,currency,kind,obj);if(value!=='—')covered++;",
        'Peer currency conversion')
    source = replace_exact(source,
        "for(const [label,key,kind] of metrics){const row=el('tr');row.append(el('td','',label));",
        "for(const [label,key,kind] of metrics){\n  if(label==='Market capitalisation'){const section=el('tr','mt-peer-group');const cell=el('td','', 'MONETARY FIGURES · verify reporting periods and FX conversion');cell.colSpan=data.length+1;section.append(cell);table.append(section);}\n  const row=el('tr');row.append(el('td','',label));",
        'Peer accounting/ratio grouping')
    source = replace_exact(source,
        '<p class="note" id="peer-coverage"></p>',
        '<div class="inputs" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0"><label class="mini" for="mt-peer-currency">FINANCIAL FIGURES</label><select class="field" id="mt-peer-currency"><option value="gbp">Convert monetary amounts to GBP</option><option value="usd">Convert monetary amounts to USD</option><option value="native">Original reported currency</option></select></div>\n<p class="note" id="peer-coverage"></p>',
        'Peer currency selector')
    source = replace_exact(source,
        '<p class="note" id="gilt-calc-note">',
        '''<section class="panel" id="mt-gilt-tax" aria-labelledby="mt-gilt-tax-heading">
  <div class="row"><div><h3 id="mt-gilt-tax-heading">AFTER-TAX GILT COMPARISON</h3><p id="mt-gilt-tax-summary" class="note">Conventional gilts of nearby maturity</p></div><label class="mini" for="mt-gilt-tax-rate">TAX ON COUPONS <select class="field" id="mt-gilt-tax-rate"><option value="0">0%</option><option value="20">20%</option><option value="40" selected>40%</option><option value="45">45%</option></select></label></div>
  <div class="small-scroll"><table class="watch"><thead><tr><th>Gilt</th><th>Maturity</th><th class="n">Clean offer</th><th class="n">Gross YTM*</th><th class="n">After-tax YTM*</th><th class="n">Duration</th><th>DMO date</th></tr></thead><tbody id="mt-gilt-tax-rows"></tbody></table></div>
  <p class="note">*Indicative model, not a published yield. Assumes holding to maturity, coupon tax at the selected marginal rate, and CGT exemption for conventional gilts. It does NOT model accrued income scheme relief, ex-dividend dates, exact settlement, personal savings allowance or trading costs. <a target="_blank" rel="noopener noreferrer" href="https://www.gov.uk/government/publications/accrued-income-scheme-hs343-self-assessment-helpsheet/hs343-accrued-income-scheme-2026">HMRC accrued interest rules</a>.</p>
</section>
<p class="note" id="gilt-calc-note">''',
        'Gilt after-tax comparator panel')
    source = replace_exact(source,
        "const chosen=all.filter(v=>state.newsCategory==='ALL'||v.category===state.newsCategory).slice(0,9);",
        "const chosen=all.filter(v=>state.newsCategory==='ALL'||v.category===state.newsCategory).slice(0,6);",
        'Overview headline limit')
    source = replace_exact(source, '</head>', f'<style id="{STYLE_ID}">\n{css}\n</style>\n</head>', 'Global style insertion')
    source = replace_exact(source, '</body>', f'<script id="{JS_ID}">\n{js}\n</script>\n</body>', 'Research application insertion')
    if market_data_hash(source) != before:
        raise AssertionError('Embedded market data changed; refusing to write')
    required = ['id="mt-gilt-tax"','id="mt-gilt-tax-rows"','id="mt-peer-currency"', f'id="{JS_ID}"',f'id="{STYLE_ID}"']
    for item in required:
        if item not in source:raise ValueError('Missing output component '+item)
    return source


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('html',type=pathlib.Path)
    p.add_argument('--check-only',action='store_true')
    a=p.parse_args()
    raw=a.html.read_text(encoding='utf-8')
    css=(ROOT/'terminal_research_upgrade.css').read_text(encoding='utf-8')
    js=(ROOT/'terminal_research_upgrade.js').read_text(encoding='utf-8')
    modified=patch_html(raw,css,js)
    if not a.check_only:a.html.write_text(modified,encoding='utf-8')
    print('Research layout upgraded: 6 core gilt fields, optional detail, indicative tax comparison, risk horizons, currency comparison, source exceptions; market data unchanged')

if __name__ == '__main__':main()
