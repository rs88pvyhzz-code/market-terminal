"""Fixed-income credit spreads, transparent index valuation proxies, and issuer events.

- Credit: FRED/ICE daily OAS (% converted to basis points), never executable quotes.
- Valuations: computed ONLY from covered positive-earnings constituents; not
  official whole-index P/E; coverage and dates are always visible.
- Events: Yahoo via yfinance calendar (indicative) and optional curated
  issuer-confirmed CSV; never infer a future earnings date from periodicity.
No paid API or on-page network calls are required.
"""
from __future__ import annotations
import concurrent.futures
import csv
import datetime as dt
import math
import pathlib
from urllib.parse import quote

CREDIT_SERIES = (
    ('US_IG','US investment grade','US','BAMLC0A0CM'),
    ('US_BBB','US BBB','US','BAMLC0A4CBBB'),
    ('US_HY','US high yield','US','BAMLH0A0HYM2'),
    ('US_BB','US BB','US','BAMLH0A1HYBB'),
    ('US_CCC','US CCC & below','US','BAMLH0A3HYC'),
    ('EU_HY','Euro high yield','Euro area','BAMLHE00EHYIOAS'),
)
MARKET_INDICES=(
    ('SP500','S&P 500','US'),
    ('NASDAQ100','Nasdaq 100','US'),
    ('FTSE100','FTSE 100','UK'),
    ('FTSE250','FTSE 250','UK'),
)


def finite(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError, OverflowError):
        return None


def prior_value(history, cutoff):
    found=None
    for point in history:
        if point['date']<=cutoff: found=point['bp']
        else: break
    return found


def collect_credit(builder, opts, asof=None):
    """No-key FRED graph CSV, using the terminal's existing cache/error handling."""
    warnings=[]; results=[]; cache_count=0
    def fetch(spec):
        key,name,region,code=spec
        rows,cached,msg=builder.fetch_fred(code,opts)
        history=[{'date':r['date'],'bp':round(100*r['value'],2)} for r in rows
                 if finite(r.get('value')) is not None and 0<=r['value']<100]
        if not history: raise ValueError('No valid OAS observations')
        history=history[-820:]  # FRED/ICE release now limits public history to ~3 years
        last=history[-1]; current_date=dt.date.fromisoformat(last['date'])
        prev_month=prior_value(history,(current_date-dt.timedelta(days=30)).isoformat())
        prev_year=prior_value(history,(current_date-dt.timedelta(days=365)).isoformat())
        return {'key':key,'name':name,'region':region,'fredCode':code,
                'sourceUrl':'https://fred.stlouisfed.org/series/'+code,
                'date':last['date'],'latestBp':last['bp'],
                'change30Bp':round(last['bp']-prev_month,2) if prev_month is not None else None,
                'change365Bp':round(last['bp']-prev_year,2) if prev_year is not None else None,
                'history':history,'cached':cached,'source':'FRED / ICE BofA (third-party index, OAS)'} ,int(cached),msg
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3,max(1,opts.workers))) as pool:
        tasks={pool.submit(fetch,s):s for s in CREDIT_SERIES}
        for fut in concurrent.futures.as_completed(tasks):
            spec=tasks[fut]
            try:
                row,cc,msg=fut.result(); results.append(row);cache_count+=cc
                if 'stale cache' in msg: warnings.append('Credit '+spec[3]+': stale cached response')
            except Exception as exc: warnings.append('Credit '+spec[3]+': '+str(exc)[:150])
    ordered={s[0]:i for i,s in enumerate(CREDIT_SERIES)}
    return sorted(results,key=lambda r:ordered[r['key']]),warnings,cache_count


def market_valuation(movers, fundamentals, companies, us_rates, uk_rates, asof=None):
    """Compute P/E proxy on covered profitable securities only. Not index P/E."""
    by_sym={f.get('symbol'):f for f in fundamentals if isinstance(f,dict)}
    for c in companies:
        sym=c.get('symbol')
        if sym and sym not in by_sym:by_sym[sym]=c
    markets={m.get('id'):m for m in movers}
    output=[]
    def latest_rate(rows,field):
        valid=[r for r in rows if finite(r.get(field)) is not None]
        if not valid:return (None,None)
        last=valid[-1]
        if asof:
            try:
                d0=dt.date.fromisoformat(str(asof)[:10]);d1=dt.date.fromisoformat(last['date'])
                if (d0-d1).days>21:return (None,None)
            except ValueError:pass
        return finite(last[field]),last['date']
    for mid,name,region in MARKET_INDICES:
        market=markets.get(mid) or {}
        constituents=market.get('constituents') or []
        # Never count dual-index members twice within one index.
        unique={q.get('symbol'):q for q in constituents if q.get('symbol')}
        all_cap=0;caps=0;pe_n=0;fwd_n=0;div_n=0
        sum_pe_cap=0;sum_pe_income=0
        sum_fwd_cap=0;sum_fwd_income=0
        sum_div_cap=0;sum_div=0
        last_financial_date=None
        for sym,q in unique.items():
            f=by_sym.get(sym) or {}
            cap=finite(f.get('marketCap'))
            if cap is None or cap<=0:continue
            all_cap+=cap;caps+=1
            stamp=str(f.get('asOf') or f.get('financialAsOf') or '')[:10]
            if stamp and (last_financial_date is None or stamp>last_financial_date):last_financial_date=stamp
            pe=finite(f.get('trailingPE'))
            if pe is not None and 0<pe<10000:
                sum_pe_cap+=cap;sum_pe_income+=cap/pe;pe_n+=1
            fp=finite(f.get('forwardPE'))
            if fp is not None and 0<fp<10000:
                sum_fwd_cap+=cap;sum_fwd_income+=cap/fp;fwd_n+=1
            dy=finite(f.get('dividendYieldPct'))
            if dy is not None and 0<=dy<=30:
                sum_div+=cap*dy;sum_div_cap+=cap;div_n+=1
        trailing=sum_pe_cap/sum_pe_income if sum_pe_income>0 else None
        forward=sum_fwd_cap/sum_fwd_income if sum_fwd_income>0 else None
        ey=100/trailing if trailing and trailing>0 else None
        risk_date=None
        if region=='US':nominal,risk_date=latest_rate(us_rates,'DGS10')
        else:nominal,risk_date=latest_rate(uk_rates,'gilt10y')
        coverage=round(100*pe_n/len(unique),1) if unique else 0
        output.append({'id':mid,'name':name,'region':region,'members':len(unique),
            'withMarketCap':caps,'positivePERows':pe_n,'forwardPERows':fwd_n,
            'dividendRows':div_n,'peCoveragePct':coverage,
            'capPositivePEPct':round(100*sum_pe_cap/all_cap,1) if all_cap else None,
            'trailingPEProxy':round(trailing,2) if trailing is not None else None,
            'forwardPEProxy':round(forward,2) if forward is not None else None,
            'earningsYieldPct':round(ey,2) if ey is not None else None,
            'dividendYieldProxyPct':round(sum_div/sum_div_cap,2) if sum_div_cap else None,
            'benchmark10yPct':round(nominal,2) if nominal is not None else None,
            'benchmarkDate':risk_date,
            'earningsMinus10yPct':round(ey-nominal,2) if ey is not None and nominal is not None else None,
            'financialRetrievedAsOf':last_financial_date,
            'method':'Harmonic market-cap-weighted PE of positive-earnings constituents with both market cap and P/E. This is NOT the official full-index P/E.'})
    return output


def collect_market_earnings(movers, companies, offline=False, today=None, provider=None):
    """Optional short-window bulk Yahoo earnings diary for tracked market constituents.

    The source is not an issuer confirmation. One request only; skips cleanly if
    yfinance bulk calendar is unavailable. Future date labels only, no fake times.
    """
    if offline:return [],[]
    today=today or dt.datetime.now(dt.timezone.utc).date()
    tracked={str(c.get('symbol','')).upper():c.get('name') or c.get('symbol') for c in companies if c.get('symbol')}
    for market in movers:
        for row in market.get('constituents') or []:
            if row.get('symbol'):tracked.setdefault(str(row['symbol']).upper(),row.get('name') or row['symbol'])
    if not tracked:return [],[]
    try:
        if provider is None:
            import yfinance as yf
            cal=yf.Calendars(start=today.isoformat(),end=(today+dt.timedelta(days=20)).isoformat())
            df=cal.get_earnings_calendar(limit=100,filter_most_active=False)
        else:df=provider()
        if df is None or getattr(df,'empty',True):return [],[]
    except Exception as exc:
        return [],['Optional bulk earnings calendar: '+str(exc)[:150]]
    seen=set();out=[]
    for idx,row in df.iterrows():
        sym=str(idx or row.get('Symbol') or '').upper().strip()
        if not sym or sym not in tracked:continue
        stamp=row.get('Event Start Date')
        if stamp is None or str(stamp) in ('NaT','nan','None'):continue
        try:
            # Preserve the provider's listed session date; do not shift to UTC.
            d=stamp.date() if hasattr(stamp,'date') else dt.date.fromisoformat(str(stamp)[:10])
        except (TypeError,ValueError):continue
        if not today<=d<=today+dt.timedelta(days=20):continue
        key=(sym,d.isoformat())
        if key in seen:continue
        seen.add(key)
        out.append({'symbol':sym,'company':tracked[sym],
                    'date':d.isoformat(),'endDate':None,'type':'earnings',
                    'title':'Earnings report (market calendar estimate)',
                    'time':None,'status':'Indicative — market calendar',
                    'source':'Yahoo Finance / yfinance calendar (unverified)',
                    'sourceUrl':'https://finance.yahoo.com/quote/'+quote(sym,safe='.')+'/'})
    return out,[]


EVENT_COLS=['symbol','event_date','event_type','title','source_url','announced_at_utc','event_time_utc']

def issuer_events(companies, csv_file, today=None, bulk_events=None):
    """Combine indicative yfinance calendars with verified manually sourced issuer events."""
    today=today or dt.datetime.now(dt.timezone.utc).date()
    lo=today-dt.timedelta(days=7);hi=today+dt.timedelta(days=180)
    out=[];warnings=[]
    names={str(c.get('symbol','')).upper():c.get('name') for c in companies}
    def include(raw):
        day=raw.get('date')
        try: date=dt.date.fromisoformat(str(day))
        except (ValueError,TypeError):return
        if not lo<=date<=hi:return
        raw['date']=date.isoformat();out.append(raw)
    for c in companies:
        sym=str(c.get('symbol') or '').upper()
        if not sym:continue
        for e in c.get('events') or []:
            if not isinstance(e,dict):continue
            typ=str(e.get('type') or '')
            if typ not in ('earnings','ex-dividend','dividend-payment'):continue
            include({'symbol':sym,'company':c.get('name') or sym,'date':e.get('date'),
                 'endDate':e.get('endDate'),'type':typ,'title':e.get('title') or typ,
                 'time':None,'status':'Indicative — verify issuer',
                 'source':'Yahoo Finance / yfinance calendar (unverified)',
                 'sourceUrl':'https://finance.yahoo.com/quote/'+quote(sym,safe='.')+'/'})
    for e in bulk_events or []:
        if not isinstance(e,dict) or e.get('type')!='earnings':continue
        if any(x.get('symbol')==e.get('symbol') and x.get('type')=='earnings' and x.get('date')==e.get('date') for x in out):continue
        include(dict(e))
    path=pathlib.Path(csv_file)
    if path.exists():
        try:
            with path.open(encoding='utf-8-sig',newline='') as handle:
                reader=csv.DictReader(handle)
                if not set(EVENT_COLS).issubset(reader.fieldnames or []):
                    warnings.append('Company event CSV missing required columns')
                else:
                    for index,row in enumerate(reader,2):
                        sym=(row.get('symbol') or '').strip().upper()
                        url=(row.get('source_url') or '').strip()
                        announced=(row.get('announced_at_utc') or '').strip()
                        if not sym or not url.startswith('https://') or not announced:
                            if any(row.values()):warnings.append('Company events row '+str(index)+': source/symbol missing')
                            continue
                        try:
                            publication=dt.datetime.fromisoformat(announced.replace('Z','+00:00'))
                            event_date=dt.date.fromisoformat(row['event_date'].strip())
                            if publication.tzinfo is None or publication.date()>event_date:
                                raise ValueError('Missing timezone or publication later than event')
                        except (ValueError,TypeError,KeyError):
                            warnings.append('Company events row '+str(index)+': invalid date or publication');continue
                        include({'symbol':sym,'company':names.get(sym,sym),
                            'date':event_date.isoformat(),'endDate':None,
                            'type':(row.get('event_type') or 'issuer-announcement').strip(),
                            'title':(row.get('title') or 'Company announcement').strip()[:160],
                            'time':(row.get('event_time_utc') or '').strip() or None,
                            'status':'Issuer-sourced','source':'Issuer announcement',
                            'sourceUrl':url,'announcedAt':announced})
        except OSError as exc:warnings.append('Company events CSV: '+str(exc)[:150])
    # A confirmed issuer date supersedes an indicative Yahoo event for same symbol, date and category.
    confirmed={(e['symbol'],e['date'],e['type']) for e in out if e['status']=='Issuer-sourced'}
    out=[e for e in out if e['status']=='Issuer-sourced' or (e['symbol'],e['date'],e['type']) not in confirmed]
    out.sort(key=lambda e:(e['date'], e['symbol'], e['type'],e['status']))
    return out,warnings,{'detailedProfiles':len(companies),'datedEvents':len(out),
        'issuerSourced':sum(e['status']=='Issuer-sourced' for e in out)}
