"""Historical equity market breadth and sector price performance, with explicit coverage.

Uses only the existing dated Yahoo-adjusted-for-splits *price* history cache,
constituent lists and fetched sector summaries. No missing prices are estimated.
Historical universe/sector labels are CURRENT and therefore introduce survivorship
bias; these are not point-in-time index reconstructions or total-return indices.
"""
from __future__ import annotations
import bisect
import datetime as dt
import gzip
import json
import math
import pathlib
from collections import defaultdict

REFERENCE = {'FTSE100': '^FTSE', 'FTSE250': '^FTMC', 'SP500': '^GSPC', 'NASDAQ100': 'QQQ'}
LOOKBACKS = {'1M': 30, '3M': 90, '6M': 182, '1Y': 365}
MIN_POINTS = {'1M': 10, '3M': 35, '6M': 70, '1Y': 140}
SECTOR_NAMES = {
    'Technology': 'Information Technology',
    'Financial Services': 'Financials',
    'Consumer Cyclical': 'Consumer Discretionary',
    'Consumer Defensive': 'Consumer Staples',
    'Basic Materials': 'Materials',
    'Real Estate': 'Real Estate',
    'Healthcare': 'Health Care',
    'Communication Services': 'Communication Services',
    'Industrials': 'Industrials', 'Energy': 'Energy', 'Utilities': 'Utilities',
}


def safe_date(value):
    try: return dt.date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError): return None


def parse_prices(rows):
    """Sorted, de-duplicated, valid dated closes. Reject tiny/negative/NaN."""
    cleaned={}
    for row in rows or []:
        try:
            day=row.get('date') if isinstance(row,dict) else row[0]
            price=(row.get('close') if 'close' in row else row.get('v')) if isinstance(row,dict) else row[1]
            value=float(price)
            if safe_date(day) and math.isfinite(value) and 0<value<1e12:
                cleaned[str(day)[:10]]=value
        except (TypeError, ValueError, KeyError, IndexError, OverflowError): pass
    return sorted(cleaned.items())


def load_history(cache_file):
    try:
        raw=gzip.decompress(pathlib.Path(cache_file).read_bytes())
        data=json.loads(raw)
        return {symbol:parse_prices(record.get('points'))
                for symbol,record in data.get('records',{}).items()
                if isinstance(record,dict)}
    except (OSError, EOFError, ValueError, TypeError, KeyError, gzip.BadGzipFile):
        return {}


def valid_near(points, asof, max_lag=5):
    """Closest observation on or before the market's effective quote date."""
    idx=bisect.bisect_right(points,(asof, float('inf')))-1
    if idx<0:return -1
    if (safe_date(asof)-safe_date(points[idx][0])).days>max_lag:return -1
    return idx


def suspicious_gap(points):
    # Split-adjusted share closes should not generally move >55% in a day.
    # Exclude entire affected return window; flag in source notes, never rewrite prices.
    return any(a[1]>0 and abs(b[1]/a[1]-1)>0.55 for a,b in zip(points,points[1:]))


def price_return(points, asof, days, minimum=10):
    if len(points)<minimum:return None
    last_idx=valid_near(points,asof)
    if last_idx<0:return None
    target=safe_date(asof)-dt.timedelta(days=days)
    # Allow a normal weekend/holiday lag, but not arbitrary earlier observations.
    base_idx=bisect.bisect_right(points,(target.isoformat(),float('inf')))-1
    if base_idx<0 or (target-safe_date(points[base_idx][0])).days>9:return None
    window=points[base_idx:last_idx+1]
    if len(window)<minimum or suspicious_gap(window):return None
    if window[0][1]<=0:return None
    return 100*(window[-1][1]/window[0][1]-1)


def _ma_eligible(points,n,day):
    idx=valid_near(points,day)
    if idx+1<n:return None
    subset=points[idx-n+1:idx+1]
    # Require reasonable calendar span for a true daily MA, not weekly closes.
    span=(safe_date(subset[-1][0])-safe_date(subset[0][0])).days
    if span < 0.92*(n-1) or span > (n-1)*2.1+20 or suspicious_gap(subset):return None
    return subset[-1][1],sum(x[1] for x in subset)/n


def build(movers, fundamentals, history_rows, cache_file, today=None):
    history=load_history(cache_file)
    sectors={str(r.get('symbol')):SECTOR_NAMES.get((r.get('sector') or '').strip(),(r.get('sector') or '').strip())
             for r in fundamentals or [] if r.get('symbol') and r.get('sector')}
    # Historical market index price series already stored by the main collector.
    benchmarks=defaultdict(list)
    for row in history_rows or []:
        if row.get('symbol') in set(REFERENCE.values()) and row.get('close') is not None:
            benchmarks[row['symbol']].append(row)
    benchmarks={k:parse_prices(v) for k,v in benchmarks.items()}
    output_breadth=[];output_sectors=[]
    for market in movers or []:
        mid=market.get('id')
        if mid not in REFERENCE:continue
        members=market.get('constituents') or []
        date=str(market.get('date') or today or '')[:10]
        if not safe_date(date):continue
        above={50:0,200:0};eligible={50:0,200:0}
        n_hi=n_lo=eligible_52=0
        advances=declines=unchanged=0
        returned=[]
        sectormembers=defaultdict(int)
        sectorsymbols=defaultdict(list)
        for q in members:
            sym=q.get('symbol');s=sectors.get(sym)
            if s:
                sectormembers[s]+=1
                sectorsymbols[s].append(sym)
            if q.get('current') and q.get('date')==date and q.get('changePct') is not None:
                change=float(q['changePct'])
                if change>0:advances+=1
                elif change<0:declines+=1
                else:unchanged+=1
            points=history.get(sym,[])
            idx=valid_near(points,date)
            if idx<0:continue
            for n in (50,200):
                result=_ma_eligible(points,n,date)
                if result:
                    value,ma=result
                    eligible[n]+=1
                    if value>ma:above[n]+=1
            if idx+1>=200:
                sample=points[max(0,idx-251):idx+1]
                if (safe_date(sample[-1][0])-safe_date(sample[0][0])).days>=300 and not suspicious_gap(sample):
                    eligible_52+=1
                    last=sample[-1][1]
                    # Closing-price highs/lows, not intraday ticks.
                    if last>=max(v for _,v in sample)-1e-9:n_hi+=1
                    if last<=min(v for _,v in sample)+1e-9:n_lo+=1
        total=int(market.get('members') or len(members))
        output_breadth.append({
            'id':mid,'name':market.get('name',mid),'date':date,'members':total,
            'quoted':int(market.get('sameDay') or advances+declines+unchanged),
            'advancers':advances,'decliners':declines,'unchanged':unchanged,
            'above50':above[50],'eligible50':eligible[50],
            'above200':above[200],'eligible200':eligible[200],
            'high52':n_hi,'low52':n_lo,'eligible52':eligible_52,
            'dataSource':'Current index constituents + Yahoo Finance dated closing prices',
            'method':'Sample breadth using current index membership; no historical index reconstruction.',
        })
        benchmark=REFERENCE[mid]
        bp=benchmarks.get(benchmark,[])
        reference={period:price_return(bp,date,days,minimum=MIN_POINTS[period])
                   for period,days in LOOKBACKS.items()}
        sector_records=[]
        for sector,syms in sorted(sectorsymbols.items()):
            perf={};coverage={}
            for period,days in LOOKBACKS.items():
                vals=[]
                for sym in syms:
                    r=price_return(history.get(sym,[]),date,days,MIN_POINTS[period])
                    if r is not None:vals.append(r)
                coverage[period]=len(vals)
                sr=sum(vals)/len(vals) if vals else None
                idx_return=reference[period]
                perf[period]={
                    'sectorReturnPct':round(sr,3) if sr is not None else None,
                    'indexReturnPct':round(idx_return,3) if idx_return is not None else None,
                    # Difference in percentage points, NOT a relative total return.
                    'relativePp':round(sr-idx_return,3) if sr is not None and idx_return is not None else None,
                    'covered':len(vals)
                }
            sector_records.append({'sector':sector,'sectorMembers':len(syms),'periods':perf})
        output_sectors.append({'id':mid,'name':market.get('name',mid),'date':date,'members':total,
          'sectorIdentified':sum(sectormembers.values()),
          'benchmark':benchmark,'referencePeriods':{k:None if v is None else round(v,3) for k,v in reference.items()},
          'sectors':sector_records,
          'method':'Equal-weight mean of covered constituent PRICE changes versus the selected broad-market price benchmark (Nasdaq 100 uses QQQ ETF as a proxy); local quote currency, excludes dividends; current sector classification (survivorship bias).',
          'source':'Current constituents, Yahoo sector labels, stored Yahoo historical closing prices'})
    return {'breadth':output_breadth,'sectorPerformance':output_sectors,
            'historyCount':len(history),'generatedDate':today or (dt.datetime.now(dt.timezone.utc).date().isoformat())}
