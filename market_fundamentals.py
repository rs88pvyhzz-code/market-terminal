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
        'earningsReportedDate':None,
    }
    # Only retain non-empty summaries; a symbol that returned blanks is not 'covered'.
    if not any(values.get(x) is not None for x in ('trailingPE','forwardPE','marketCap','revenueTTM','netIncomeTTM')):
        return None
    return values


def previous_site_snapshot():
    """Recover financial summaries from the site's LAST publication on GitHub Pages.

    A GitHub Actions runner is ephemeral. Reuse the last published static JSON,
    rather than asking the user to configure an additional workflow cache.
    Publication can be delayed; a failed build retains the previous site.
    """
    repo=os.environ.get('GITHUB_REPOSITORY','')
    if '/' not in repo:return {}
    owner,name=repo.split('/',1)
    url=f'https://{owner}.github.io/{name}/'
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'PersonalMarketResearch/1.0'})
        with urllib.request.urlopen(request,timeout=18) as response:
            html=response.read(24_000_000).decode('utf-8')
        json_source=html.split('window.MT_DATA = ',1)[1].split(';</script>',1)[0]
        page=json.loads(json_source)
        if page.get('demo') is not False:return {}
        data={x['symbol']:x for x in page.get('fundamentals',[]) if isinstance(x,dict) and x.get('symbol')}
        return {'records':data,'attempts':{s:r.get('asOf','') for s,r in data.items()}}
    except Exception:
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
    records={k:v for k,v in previous.get('records',{}).items() if k in seen and isinstance(v,dict)}
    attempts={k:v for k,v in previous.get('attempts',{}).items() if k in seen}
    # Detailed profiles (e.g. Shell) have priority over summary-only snapshots.
    for c in detailed_companies:
        sym=c.get('symbol')
        if sym not in seen:continue
        vals={k:c.get(k) for k in ('trailingPE','forwardPE','marketCap','priceToBook',
             'dividendYieldPct','revenueTTM','netIncomeTTM','profitMarginPct','financialCurrency','sector')}
        if not any(vals.get(k) is not None for k in ('trailingPE','forwardPE','marketCap','revenueTTM','netIncomeTTM')):continue
        records[sym]={'symbol':sym,'asOf':stamp,'source':'Detailed company profile (Yahoo Finance via yfinance)',**vals}
        attempts[sym]=stamp
    def age_days(s):
        try:return (now-dt.datetime.fromisoformat(s.replace('Z','+00:00'))).total_seconds()/86400
        except Exception:return 100000
    def needs_update(sym):
        last=attempts.get(sym,'')
        if sym in records:return age_days(records[sym].get('asOf',''))>=30 and age_days(last)>=2
        return age_days(last)>=2
    pending=[s for s in universe if needs_update(s)][:max(0,batch_size)]
    warnings=[]
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
                if obj:records[sym]=obj
                elif err and len(warnings)<8:warnings.append('Fundamentals '+sym+': '+err)
    output=[records[s] for s in universe if s in records]
    coverage={'eligible':len(universe),'available':sum(1 for obj in output if obj.get('trailingPE') is not None),
              'summaries':len(output),'fetchedThisRun':len(pending) if not offline else 0,'updatedAt':stamp}
    path.write_text(json.dumps({'records':records,'attempts':attempts},separators=(',',':')),encoding='utf-8')
    return output,coverage,warnings
