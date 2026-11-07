"""Incremental, cached financial summaries for entire stock-index universes.

Static site: no server-side lookup after publication.  A small, bounded number of
financial summaries is fetched per build; cache must be persisted between builds
(the previously published GitHub Pages snapshot). Missing fields are never guessed.
"""
from __future__ import annotations
import concurrent.futures
import datetime as dt
import json
import math
import pathlib
import os
import urllib.request

CACHE_NAME = 'fundamental_summaries.json'
MARKETS = ('SP500', 'FTSE100', 'FTSE250', 'NASDAQ100')


def finite(value):
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError,OverflowError):
        return None


def convert(symbol, info, collected):
    if not isinstance(info,dict) or not info:
        return None
    tr=finite(info.get('trailingPE'))
    fwd=finite(info.get('forwardPE'))
    pbr=finite(info.get('priceToBook'))
    yield_pct=finite(info.get('dividendYield'))
    # This yfinance release's dividendYield is already a percentage, e.g. 3.06.
    # Deliberately never multiply by 100 (Shell 306% bug).
    if yield_pct is not None and not 0<=yield_pct<=30:yield_pct=None
    margin=finite(info.get('profitMargins'))
    currency=info.get('financialCurrency') or None
    values={
        'symbol':symbol,
        'schemaVersion':2,
        'asOf':collected,
        'source':'Yahoo Finance / yfinance (unofficial, unverified)',
        'trailingPE':tr if tr is not None and tr>0 else None,
        'forwardPE':fwd if fwd is not None and fwd>0 else None,
        'marketCap':finite(info.get('marketCap')),
        'priceToBook':pbr if pbr is not None and pbr>0 else None,
        'dividendYieldPct':yield_pct,
        'revenueTTM':finite(info.get('totalRevenue')),
        'netIncomeTTM':finite(info.get('netIncomeToCommon')),
        'profitMarginPct':100*margin if margin is not None else None,
        'financialCurrency':currency,
        'sector':info.get('sector') or None,
        'industry':info.get('industry') or None,
        'epsTTM':finite(info.get('trailingEps')),
        'ebitda':finite(info.get('ebitda')),
        'enterpriseToEbitda':finite(info.get('enterpriseToEbitda')),
        'freeCashflow':finite(info.get('freeCashflow')),
        'totalDebt':finite(info.get('totalDebt')),
        'roePct':(100*finite(info.get('returnOnEquity')) if finite(info.get('returnOnEquity')) is not None else None),
        'earningsGrowthPct': (100*finite(info.get('earningsGrowth')) if finite(info.get('earningsGrowth')) is not None else None),
        'revenueGrowthPct': (100*finite(info.get('revenueGrowth')) if finite(info.get('revenueGrowth')) is not None else None),
        'earningsReportedDate':None,
    }
    # Only retain non-empty summaries; a symbol that returned blanks is not 'covered'.
    if not any(values.get(x) is not None for x in ('trailingPE','forwardPE','marketCap','revenueTTM','netIncomeTTM')):
        return None
    return values


def previous_site_snapshot():
    """Load saved financial summaries from the previous GitHub Pages build.

    Runners have ephemeral disks. Download a small standalone JSON file, not the
    20-year terminal.html, which can exceed the old 24 MB read limit.  The
    smaller file also records unsuccessful lookups so each subsequent run can
    progress through the index constituents instead of retrying the same names.
    """
    repo=os.environ.get('GITHUB_REPOSITORY','')
    if '/' not in repo:return {}
    owner,name=repo.split('/',1)
    base=f'https://{owner}.github.io/{name}/'
    url=base+'fundamentals_cache.json'
    try:
        request=urllib.request.Request(url,headers={
            'User-Agent':'PersonalMarketResearch/1.1',
            'Cache-Control':'no-cache',
            'Accept':'application/json'})
        with urllib.request.urlopen(request,timeout=18) as response:
            payload=json.loads(response.read(15_000_000).decode('utf-8'))
        if isinstance(payload,dict) and isinstance(payload.get('records'),dict) and isinstance(payload.get('attempts'),dict):
            return payload
    except Exception as exc:
        # Initial migration: existing page won't have a separate cache file.
        print('Fundamental cache: standalone file unavailable; checking previous site snapshot ('+str(exc)[:90]+')',flush=True)

    # One-time fallback for previously published builds. The large HTML may be
    # truncated by size or a CDN during the transition; failures must be clear.
    try:
        request=urllib.request.Request(base,headers={
            'User-Agent':'PersonalMarketResearch/1.1','Cache-Control':'no-cache'})
        with urllib.request.urlopen(request,timeout=25) as response:
            html=response.read(65_000_000).decode('utf-8')
        json_source=html.split('window.MT_DATA = ',1)[1].split(';</script>',1)[0]
        page=json.loads(json_source)
        if page.get('demo') is not False:return {}
        data={x['symbol']:x for x in page.get('fundamentals',[]) if isinstance(x,dict) and x.get('symbol')}
        coverage=page.get('fundamentalsCoverage') or {}
        prior_attempts=coverage.get('attempts') if isinstance(coverage,dict) else {}
        if not isinstance(prior_attempts,dict):prior_attempts={}
        print(f'Fundamental cache: recovered {len(data)} summaries from prior HTML',flush=True)
        return {'records':data,'attempts':{**{s:r.get('asOf','') for s,r in data.items()},**prior_attempts}}
    except Exception as exc:
        print('Fundamental cache: previous publication could not be recovered; starting new cache ('+str(exc)[:120]+')',flush=True)
        return {}


def collect(movers, detailed_companies, directory, batch_size=40, offline=False, provider=None, asof=None):
    """Return (summaries, coverage, warnings), updating the persisted JSON cache.

    `provider(symbol)` may be injected by tests; the production provider is
    yfinance.Ticker(symbol).get_info.  Successful summaries are cached for thirty
    days. Scheduled builds recover previous data from the published website.
    """
    directory=pathlib.Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/CACHE_NAME
    try:
        previous=json.loads(path.read_text('utf-8')) if path.exists() else {}
        if not isinstance(previous,dict):previous={}
    except Exception:
        previous={}
    if not previous and not offline:
        previous=previous_site_snapshot()
    stamp=asof or dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    now=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
    seen={}
    for mid in MARKETS:
        for market in movers:
            if market.get('id')==mid:
                for q in market.get('constituents',[]):
                    seen.setdefault(q['symbol'],q.get('name',q['symbol']))
    universe=list(seen)
    # Get financial summaries for the most important daily market movers FIRST.
    # The full indexed universe is still retained, but requests are bounded per run.
    hot=[]
    for market in movers:
        for row in (market.get('gainers',[])+market.get('losers',[])):
            if row.get('symbol') in seen and row.get('date')==market.get('date'):
                hot.append((abs(finite(row.get('changePct')) or 0),row['symbol']))
    priority=[s for _,s in sorted(hot,reverse=True)]
    lookup_order=list(dict.fromkeys(priority+universe))
    records={k:v for k,v in previous.get('records',{}).items() if k in seen and isinstance(v,dict)}
    for old in records.values():
        dy=finite(old.get('dividendYieldPct'))
        if dy is not None and not 0<=dy<=30:old['dividendYieldPct']=None
    attempts={k:v for k,v in previous.get('attempts',{}).items() if k in seen}
    resumed_summaries=len(records)
    # Detailed profiles (e.g. Shell) have priority over summary-only snapshots.
    for c in detailed_companies:
        sym=c.get('symbol')
        if sym not in seen:continue
        vals={k:c.get(k) for k in ('trailingPE','forwardPE','marketCap','priceToBook',
             'dividendYieldPct','revenueTTM','netIncomeTTM','profitMarginPct','financialCurrency','sector',
             'industry','epsTTM','ebitda','enterpriseToEbitda','freeCashflow','totalDebt','roePct',
             'earningsGrowthPct','revenueGrowthPct')}
        if not any(vals.get(k) is not None for k in ('trailingPE','forwardPE','marketCap','revenueTTM','netIncomeTTM')):continue
        records[sym]={'symbol':sym,'schemaVersion':2,'asOf':stamp,'source':'Detailed company profile (Yahoo Finance via yfinance)',**vals}
        attempts[sym]=stamp
    def age_days(s):
        try:return (now-dt.datetime.fromisoformat(s.replace('Z','+00:00'))).total_seconds()/86400
        except Exception:return 100000
    def needs_update(sym):
        last=attempts.get(sym,'')
        if sym in records:
            # One-off progressive migration adds earnings/revenue growth to old
            # financial summaries; avoid a 30-day wait for the new screener.
            if records[sym].get('schemaVersion')!=2:return age_days(last)>=2
            return age_days(records[sym].get('asOf',''))>=30 and age_days(last)>=2
        return age_days(last)>=2
    pending=[s for s in lookup_order if needs_update(s)][:max(0,batch_size)]
    warnings=[]
    new_successes=0
    if pending and not offline:
        if provider is None:
            try:
                import yfinance as yf
                provider=lambda symbol: yf.Ticker(symbol).get_info() or {}
            except ImportError:
                warnings.append('Fundamentals unavailable: install yfinance')
                pending=[]
        def retrieve(symbol):
            try:return symbol,convert(symbol,provider(symbol),stamp),None
            except Exception as exc:return symbol,None,str(exc)[:110]
        # Low concurrency to reduce Yahoo throttling and GitHub action runtime.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for sym,obj,err in pool.map(retrieve,pending):
                attempts[sym]=stamp
                if obj:
                    records[sym]=obj
                    new_successes+=1
                elif err and len(warnings)<8:warnings.append('Fundamentals '+sym+': '+err)
    output=[records[s] for s in universe if s in records]
    coverage={'eligible':len(universe),'available':sum(1 for obj in output if obj.get('trailingPE') is not None),
              'summaries':len(output),'fetchedThisRun':len(pending) if not offline else 0,
              'successfulNewThisRun':new_successes,'resumedFromCache':resumed_summaries,
              'updatedAt':stamp,'attempts':attempts}
    path.write_text(json.dumps({'records':records,'attempts':attempts},separators=(',',':')),encoding='utf-8')
    return output,coverage,warnings
