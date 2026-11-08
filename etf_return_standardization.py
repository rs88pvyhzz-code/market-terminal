#!/usr/bin/env python3
"""Standardise ETF returns in an already-built market-terminal HTML snapshot.

Run AFTER existing ETF installers, consolidation, and build_terminal.py; run
BEFORE verify_snapshot.py / GitHub Pages publishing. Does NOT change fund lists,
TER, replication, AUM, benchmarks, or other market dashboards.

Price: exchange-traded close, excluding cash distributions.
Adjusted: Yahoo's unofficial adjusted-close proxy (NOT certified fund NAV TR).
Local: actual exchange quote currency. GBP: historic same-day FX to GBP.
1Y/3Y/5Y values are annualised CAGRs, not cumulative 3Y/5Y gains.
Missing adjusted history or same-day FX remains unavailable; never assume it.
"""
import argparse
import datetime as dt
import json
import math
import pathlib
import re
import sys

MARKER='window.MT_DATA = '
PERIODS=(1,3,5)
BASIS={'adjusted_gbp':('adjustedGBP',2,True),
       'adjusted_local':('adjustedLocal',2,False),
       'price_gbp':('priceGBP',1,True),
       'price_local':('priceLocal',1,False)}


def load_snapshot(source):
    start=source.find(MARKER)
    if start<0 or source.count(MARKER)!=1:
        raise ValueError('Exactly one MT_DATA snapshot is required')
    a=start+len(MARKER)
    end=source.find('</script>',a)
    if end<0:raise ValueError('Unterminated MT_DATA block')
    inner=source[a:end]
    trimmed=inner.rstrip()
    if not trimmed.endswith(';'):
        raise ValueError('Unexpected JSON script termination')
    data=json.loads(trimmed[:-1])
    if not isinstance(data,dict) or not isinstance(data.get('etfTracker'),dict):
        raise ValueError('Expected ETF dataset; aborting without modifying HTML')
    return a,end,data


def rate_map(history):
    result={}
    symbols={'GBPUSD=X','USDGBP=X','GBPEUR=X','EURGBP=X'}
    for p in history:
        sym=p.get('symbol')
        if sym not in symbols:continue
        value=p.get('close')
        if isinstance(value,(int,float)) and math.isfinite(value) and value>0:
            result.setdefault(sym,{})[p['date']]=float(value)
    return result


def gbp_conversion(value,currency,date,fx):
    """Return GBP market-price equivalent on the SAME observation day."""
    if value is None or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
        return None
    ccy=(currency or '').strip()
    if ccy in ('GBp','GBX','GBp.'):
        return value/100
    if ccy=='GBP':return value
    if ccy=='USD':
        direct=fx.get('USDGBP=X',{}).get(date)
        if direct:return value*direct
        inv=fx.get('GBPUSD=X',{}).get(date)
        return value/inv if inv else None
    if ccy=='EUR':
        direct=fx.get('EURGBP=X',{}).get(date)
        if direct:return value*direct
        inv=fx.get('GBPEUR=X',{}).get(date)
        return value/inv if inv else None
    return None


def annualised(rows,years):
    """Use nearest observation BEFORE the exact anniversary, max 20 days old."""
    if len(rows)<2:return None
    by_date={r[0]:r[1] for r in rows if isinstance(r[1],(int,float)) and math.isfinite(r[1]) and r[1]>0}
    if len(by_date)<2:return None
    dates=sorted(by_date)
    end=dt.date.fromisoformat(dates[-1])
    cutoff=end-dt.timedelta(days=round(years*365.25))
    eligible=[d for d in dates if dt.date.fromisoformat(d)<=cutoff]
    if not eligible:return None
    begin=dt.date.fromisoformat(eligible[-1])
    if (cutoff-begin).days>20:return None
    span=(end-begin).days/365.25
    if span<years*.95 or span>years*1.07:return None
    start_val=by_date[eligible[-1]];end_val=by_date[dates[-1]]
    if start_val<=0 or end_val<=0:return None
    return round(100*((end_val/start_val)**(1/span)-1),2)


def evaluate(data):
    track=data['etfTracker']
    funds=track.get('funds') or []
    histories={r['symbol']:r.get('points') or [] for r in track.get('history') or []}
    fx=rate_map(data.get('history') or [])
    coverage={k:{str(n)+'Y':0 for n in PERIODS} for k in BASIS}
    missing=[]
    for fund in funds:
        sym=fund['symbol'];points=histories.get(sym,[])
        currency=(fund.get('quote') or {}).get('currency') or ''
        values={}
        for key,(keyname,idx,to_gbp) in BASIS.items():
            observations=[]
            for point in points:
                if len(point)<=idx:continue
                p=point[idx]
                if p is None or not isinstance(p,(int,float)) or not math.isfinite(p) or p<=0:continue
                current=gbp_conversion(p,currency,point[0],fx) if to_gbp else p
                if current is not None and current>0:observations.append((point[0],current))
            row={str(n)+'Y':annualised(observations,n) for n in PERIODS}
            values[keyname]=row
            for period,value in row.items():
                if value is not None:coverage[key][period]+=1
        fund['standardisedReturns']=values
        local=values['adjustedLocal'];sterling=values['adjustedGBP']
        fund['returnCurrencyEffect']={str(n)+'Y':round(sterling[str(n)+'Y']-local[str(n)+'Y'],2)
                                     if sterling[str(n)+'Y'] is not None and local[str(n)+'Y'] is not None else None
                                     for n in PERIODS}
        fund['returnStandardSource']='Yahoo adjusted close (unofficial proxy) / Yahoo close; dated FX from market snapshot'
        fund['returnQuoteCurrency']=currency or 'Unknown'
        fund['returnStandardNote']='GBP results use exact-date FX. No FX or adjustment substitution.'
        for n in PERIODS:
            fund['return'+str(n)+'Y']=values['adjustedGBP'][str(n)+'Y']
        fund['returnBasis']='Yahoo adjusted-close proxy, GBP (FX on same date); annualised, not issuer NAV total return'
        if values['adjustedGBP']['1Y'] is None:missing.append(sym)
    track['returnStandardCoverage']={'funds':len(funds),'periods':coverage,
                                     'gbpAdjusted1YMissing':missing,
                                     'basisDefault':'adjusted_gbp','asOf':data.get('generatedAt','')}
    track.setdefault('sources',[]).append('Standardised ETF returns: local price/adjusted proxy and GBP price/adjusted proxy; same-day FX only; 1Y/3Y/5Y annualised; unavailable does not mean zero.')
    return coverage


CONTROLS='''<div id="etf-return-standard-controls" class="etf-return-standard-controls">
  <label for="etf-return-standard-basis">RETURN BASIS
    <select class="field" id="etf-return-standard-basis" aria-label="Select the return basis for every ETF">
      <option value="adjusted_gbp" selected>Adjusted-price proxy · GBP</option>
      <option value="adjusted_local">Adjusted-price proxy · trading currency</option>
      <option value="price_gbp">Price only · GBP</option>
      <option value="price_local">Price only · trading currency</option>
    </select>
  </label>
  <span class="mini" id="etf-return-standard-note" aria-live="polite">1Y, 3Y and 5Y annualised · GBP · dividend-adjusted proxy · same-day FX only</span>
</div>
'''
CSS='''<style id="etf-return-standard-style">
.etf-return-standard-controls{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end;padding:10px 0}
.etf-return-standard-controls label{display:flex;gap:7px;align-items:center;font-size:11px;letter-spacing:.045em}
.etf-return-standard-controls .field{max-width:290px}
#etf-return-standard-note{line-height:1.4;max-width:780px}
</style>'''
JS=r'''// ETF RETURN STANDARDISATION — isolated, post-issuer enrichment.
// Preserve original fund selection, 6-way comparisons and research panels.
(function(){
 const basisNames={
   adjusted_gbp:['adjustedGBP','GBP','Yahoo adjusted-close proxy'],
   adjusted_local:['adjustedLocal','trading currency','Yahoo adjusted-close proxy'],
   price_gbp:['priceGBP','GBP','price only; distributions excluded'],
   price_local:['priceLocal','trading currency','price only; distributions excluded']
 };
 const selector=$('etf-return-standard-basis');
 if(!selector||typeof renderEtfTracker!=='function'||typeof ETF_FUNDS==='undefined')return;
 const original=renderEtfTracker;
 function apply(){
   const selected=basisNames[selector.value]||basisNames.adjusted_gbp;
   const key=selected[0];
   for(const f of ETF_FUNDS){
     const values=(f.standardisedReturns||{})[key]||{};
     for(const y of [1,3,5])f['return'+y+'Y']=values[y+'Y']??null;
     f.returnBasis=selected[2]+' · '+selected[1]+' · 1Y/3Y/5Y annualised; no missing data substituted';
   }
   etfState.basis=selector.value;
   const chartSelector=$('etf-basis');if(chartSelector)chartSelector.value=selector.value;
   const note=$('etf-return-standard-note');if(note)note.textContent=
     '1Y, 3Y and 5Y annualised · '+selected[1]+' · '+selected[2]+
     ' · no interpolation or missing FX substitution'+
     (selector.value.endsWith('_local')?' · different trading currencies are NOT comparable':'');
 }
 renderEtfTracker=function(){apply();return original.apply(this,arguments);};
 selector.addEventListener('change',()=>{apply();renderEtfTracker();});
 // Keep the detailed chart selector and compact-list returns consistent.
 const originalControl=$('etf-basis');
 if(originalControl)originalControl.addEventListener('change',()=>{
   if(basisNames[originalControl.value]){selector.value=originalControl.value;renderEtfTracker();}
 });
 apply();
})();
'''


def instrument_html(source):
    if 'id="etf-return-standard-basis"' in source:
        raise ValueError('Return standardisation already installed; refusing duplicate injection')
    if source.count('<div class="etf-table-scroll">')!=1:
        raise ValueError('ETF table anchor changed; do not publish altered page')
    if source.count('init();\n})();')!=1:
        raise ValueError('Dashboard script anchor changed; do not publish altered page')
    source=source.replace('<div class="etf-table-scroll">',CONTROLS+'<div class="etf-table-scroll">',1)
    source=source.replace('</head>',CSS+'\n</head>',1)
    source=source.replace('init();\n})();',JS+'\ninit();\n})();',1)
    # Remove misleading note written for the old fixed local-currency column.
    source=re.sub(r'<p class="note">\*Annualised historical performance in each fund\'s quoted currency,.*?</p>',
                  '<p class="note">*Annualised 1-, 3- and 5-year values use the selected return basis. Adjusted closes are unofficial dividend-adjusted proxies, not audited fund NAV total returns. GBP conversion uses FX observations on the exact ETF pricing dates; unavailable data remain blank.</p>',
                  source,count=1,flags=re.S)
    return source


def transform(text):
    a,end,data=load_snapshot(text)
    count=len(data['etfTracker'].get('funds') or [])
    before=[(f['symbol'],f.get('isin')) for f in data['etfTracker'].get('funds') or []]
    coverage=evaluate(data)
    after=[(f['symbol'],f.get('isin')) for f in data['etfTracker'].get('funds') or []]
    if before!=after or count!=len(after):raise ValueError('ETF catalogue changed unexpectedly')
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
    updated=text[:a]+payload+';'+text[end:]
    return instrument_html(updated),coverage,count


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html',type=pathlib.Path,default=pathlib.Path('terminal.html'))
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    p=args.html
    original=p.read_text(encoding='utf-8')
    updated,coverage,count=transform(original)
    if not args.dry_run:
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(mode='w',encoding='utf-8',dir=p.parent,delete=False,suffix='.tmp') as f:
            f.write(updated);temp=pathlib.Path(f.name)
        temp.replace(p)
    print('ETF standardized returns: %s original funds preserved; GBP adjusted 1Y %s/%s; local adjusted 1Y %s/%s%s' %
          (count,coverage['adjusted_gbp']['1Y'],count,coverage['adjusted_local']['1Y'],count,' (dry-run)' if args.dry_run else ''))
    return 0

if __name__=='__main__':sys.exit(main())
