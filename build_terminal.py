#!/usr/bin/env python3
"""Build a self-contained, Bloomberg-inspired global market research dashboard.

Usage:
    python build_terminal.py                     # market data -> terminal.html
    python build_terminal.py --years 20           # up to 20-year history where available
    python build_terminal.py --demo               # SYNTHETIC demonstration, no network
    python build_terminal.py --offline            # read prior successful download cache

Python 3.9+ standard library only. Data: Yahoo Finance (unofficial), Bank of
England IADB and FRED graph CSV (an undocumented no-key download route).
This is an end-of-run SNAPSHOT, not a live trading service. See README.
"""
import argparse
import concurrent.futures
import csv
import datetime as dt
import io
import json
import math
import pathlib
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from bisect import bisect_right
from zoneinfo import ZoneInfo
import market_movers
import company_data
import regional_data
import market_intelligence
import market_fundamentals
import market_price_history
import gilt_market
import us_treasury_market
import economic_forecasts
import market_additions
import personal_watchlist

ROOT = pathlib.Path(__file__).resolve().parent
CACHE = ROOT / '.terminal_cache'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; PersonalMarketResearch/1.0)', 'Accept': 'application/json,text/csv,text/plain,*/*'}
# Group, ticker, label, kind: yield = an interest-rate quote in percent,
# volatility = an index level, otherwise a price level (NOT necessarily a total return).
INSTRUMENTS = [
 ('Equities','^FTSE','FTSE 100','index'),('Equities','^FTMC','FTSE 250','index'),
 ('Equities','^GSPC','S&P 500','index'),('Equities','^IXIC','Nasdaq Composite','index'),
 ('Equities','^DJI','Dow Jones Industrial','index'),('Equities','^RUT','Russell 2000','index'),
 ('Equities','^STOXX50E','Euro Stoxx 50','index'),('Equities','^STOXX','STOXX Europe 600','index'),
 ('Equities','^GDAXI','DAX','index'),('Equities','^FCHI','CAC 40','index'),
 ('Equities','FTSEMIB.MI','FTSE MIB','index'),('Equities','^IBEX','IBEX 35','index'),
 ('Equities','^SSMI','Swiss Market Index','index'),('Equities','^N225','Nikkei 225','index'),
 ('Equities','^TOPX','TOPIX','index'),('Equities','^HSI','Hang Seng','index'),
 ('Equities','000300.SS','CSI 300','index'),('Equities','^KS11','KOSPI','index'),
 ('Equities','^AXJO','ASX 200','index'),('Equities','^NSEI','Nifty 50','index'),
 ('Equities','^BVSP','Brazil Bovespa','index'),('Equities','^MXX','Mexico IPC','index'),
 ('Equities','^GSPTSE','S&P/TSX Composite','index'),('Equities','^TWII','Taiwan Weighted','index'),
 ('Equities','^JKSE','Jakarta Composite','index'),('Equities','^STI','Singapore STI','index'),
 ('Equities','^VIX','VIX volatility','volatility'),
 ('ETFs','ACWI','iShares MSCI ACWI ETF','etf'),('ETFs','URTH','iShares MSCI World ETF','etf'),
 ('ETFs','EEM','iShares MSCI EM ETF','etf'),('ETFs','EFA','iShares MSCI EAFE ETF','etf'),
 ('ETFs','SPY','S&P 500 ETF (SPY)','etf'),('ETFs','QQQ','Nasdaq 100 ETF (QQQ)','etf'),
 ('ETFs','IEUR','European equities ETF','etf'),('ETFs','EWJ','Japan equities ETF','etf'),
 ('ETFs','EWU','UK equities ETF','etf'),('ETFs','INDA','India equities ETF','etf'),
 ('ETFs','EWZ','Brazil equities ETF','etf'),('ETFs','EWT','Taiwan equities ETF','etf'),
 ('ETFs','XLK','US Technology ETF','etf'),('ETFs','XLF','US Financials ETF','etf'),
 ('ETFs','XLE','US Energy ETF','etf'),('ETFs','XLV','US Healthcare ETF','etf'),
 ('ETFs','XLI','US Industrials ETF','etf'),('ETFs','XLP','US Staples ETF','etf'),
 ('ETFs','XLY','US Discretionary ETF','etf'),('ETFs','XLU','US Utilities ETF','etf'),
 ('ETFs','VNQ','US REIT ETF','etf'),('ETFs','TLT','20Y+ Treasury ETF','etf'),
 ('ETFs','IEF','7–10Y Treasury ETF','etf'),('ETFs','SHY','1–3Y Treasury ETF','etf'),
 ('ETFs','LQD','IG corporate bond ETF','etf'),('ETFs','HYG','High-yield bond ETF','etf'),
 ('ETFs','TIP','Inflation-linked bond ETF','etf'),
 ('FX','GBPUSD=X','GBP/USD','fx'),('FX','GBPEUR=X','GBP/EUR','fx'),
 ('FX','EURUSD=X','EUR/USD','fx'),('FX','USDJPY=X','USD/JPY','fx'),
 ('FX','USDCHF=X','USD/CHF','fx'),('FX','AUDUSD=X','AUD/USD','fx'),
 ('FX','USDCNY=X','USD/CNY','fx'),('FX','EURGBP=X','EUR/GBP','fx'),
 ('Rates','^IRX','US 13-week bill yield¹','yield'),('Rates','^FVX','US 5Y yield¹','yield'),
 ('Rates','^TNX','US 10Y yield¹','yield'),('Rates','^TYX','US 30Y yield¹','yield'),
 ('Commodities','BZ=F','Brent crude futures','future'),('Commodities','CL=F','WTI crude futures','future'),
 ('Commodities','GC=F','Gold futures','future'),('Commodities','SI=F','Silver futures','future'),
 ('Commodities','HG=F','Copper futures','future'),('Commodities','NG=F','US natural gas futures','future'),
 ('Commodities','ZC=F','Corn futures','future'),('Commodities','ZW=F','Wheat futures','future'),
 ('Crypto','BTC-USD','Bitcoin/USD','crypto'),('Crypto','ETH-USD','Ethereum/USD','crypto'),
]
# Each official / public series has its own frequency. No attempt to call these 'live'.
FRED_MACRO = [
 ('UNRATE','us_unemployment','US unemployment','%', 'level'),
 ('CPIAUCSL','us_cpi','US CPI, 12m change','%', 'yoy12'),
 ('FEDFUNDS','fed_funds','US effective Fed funds','%', 'level'),
 ('GDPC1','us_real_gdp','US real GDP, 4q change','%', 'yoy4'),
 ('M2SL','us_m2','US M2 money supply, 12m change','%', 'yoy12'),
]
FRED_US_YIELDS = ['DGS1','DGS2','DGS3','DGS5','DGS7','DGS10','DGS20','DGS30']
BOE_CODES = {'gilt5y':'IUDSNZC','gilt10y':'IUDMNZC','gilt20y':'IUDLNZC','bankRate':'IUDBEDR',
             'gilt5yReal':'IUDSRZC','gilt10yReal':'IUDMRZC','gilt20yReal':'IUDLRZC',
             'gilt5yInflation':'IUDSIZC','gilt10yInflation':'IUDMIZC','gilt20yInflation':'IUDLIZC'}


def today_utc(): return dt.datetime.now(dt.timezone.utc)
def iso_date(unix, tz='UTC'):
    try: zone=ZoneInfo(tz)
    except (KeyError, ValueError): zone=dt.timezone.utc
    return dt.datetime.fromtimestamp(unix, zone).date().isoformat()
def safe_float(v):
    try:
        f=float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError, OverflowError): return None

def rounded(v, d=5): return None if v is None else round(v, d)

def get_bytes(url, key, offline=False, max_age_hours=4):
    CACHE.mkdir(exist_ok=True)
    file=CACHE / (key + '.bin')
    if file.exists() and (offline or time.time()-file.stat().st_mtime < max_age_hours*3600):
        return file.read_bytes(), True, 'cached'
    if offline:
        if file.exists(): return file.read_bytes(), True, 'cached (offline)'
        raise RuntimeError('Not present in offline cache')
    last_error=None
    for n in range(3):
        try:
            req=urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r: b=r.read()
            if len(b)<10: raise RuntimeError('Suspiciously short response')
            file.write_bytes(b)
            return b, False, 'downloaded'
        except Exception as exc:
            last_error=exc
            if n<2: time.sleep(0.6*(2**n))
    if file.exists(): return file.read_bytes(), True, 'stale cache after fetch failed: '+str(last_error)
    raise RuntimeError(str(last_error))

def prior_close(pts, last_day, meta):
    # The chart's 'chartPreviousClose' is the start-of-chart comparison and is
    # NOT the prior trading close. Prefer previousClose when provided.
    p=safe_float(meta.get('previousClose'))
    if p and p>0: return p
    past=[v for d,v in pts if d < last_day]
    return past[-1] if past else (pts[-2][1] if len(pts)>1 else None)

def prior_on_or_before(pts, cutoff):
    keys=[date for date,_ in pts]
    i=bisect_right(keys, cutoff)-1
    return pts[i][1] if i>=0 else None

def fetch_quote(info, opts):
    group, symbol, name, kind=info
    start=dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=int(opts.years*365.25)+16)
    end=today_utc()+dt.timedelta(days=2)
    query=urllib.parse.urlencode({'period1':int(start.timestamp()),'period2':int(end.timestamp()),'interval':'1d','events':'div,splits','includeAdjustedClose':'true'})
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+urllib.parse.quote(symbol,safe='')+'?'+query
    try:
        if not opts.offline: time.sleep(0.12)  # avoid bursty parallel requests
        b,cached,info_msg=get_bytes(url, 'yf_'+urllib.parse.quote(symbol,safe='').replace('%','_')+'_y'+str(opts.years),opts.offline,opts.cache_hours)
        res=json.loads(b.decode('utf-8'))['chart']['result'][0]
        m=res['meta']; tz=m.get('exchangeTimezoneName','UTC')
        closes=res['indicators']['quote'][0].get('close',[])
        adj_block=res.get('indicators',{}).get('adjclose') or []
        adjusted=adj_block[0].get('adjclose',[]) if adj_block else []
        adj_by_day={}
        if kind in ('etf','equity'):
            for t,value in zip(res.get('timestamp',[]),adjusted):
                v=safe_float(value)
                if v is not None and v>0:adj_by_day[iso_date(t,tz)]=v
        pts_by_day={}
        for t,v in zip(res.get('timestamp',[]),closes):
            vf=safe_float(v)
            if vf is not None and vf>0: pts_by_day[iso_date(t,tz)]=vf
        pts=sorted(pts_by_day.items())
        if len(pts)<2: raise RuntimeError('Under two historical closes')
        quote_time=m.get('regularMarketTime') or res['timestamp'][-1]
        last_day=iso_date(quote_time,tz)
        raw=safe_float(m.get('regularMarketPrice'))
        price=raw if raw and raw>0 else pts[-1][1]
        prev=prior_close(pts,last_day,m)
        if not prev or prev<=0: raise RuntimeError('Invalid previous close')
        y0=last_day[:4]+'-01-01'
        # On 1 Jan, use the last observation from the prior calendar year.
        ref_ytd=prior_on_or_before(pts, (dt.date.fromisoformat(y0)-dt.timedelta(days=1)).isoformat())
        cutoff=(dt.date.fromisoformat(last_day)-dt.timedelta(days=365)).isoformat()
        ref_year=prior_on_or_before(pts,cutoff)
        # Require at least ~330 days of history to call it a 1Y price move.
        earliest=dt.date.fromisoformat(pts[0][0]); last=dt.date.fromisoformat(last_day)
        if (last-earliest).days<330: ref_year=None
        pc=lambda p: rounded(100*(price/p-1),2) if p and p>0 else None
        bp=lambda p: rounded(100*(price-p),1) if p is not None else None
        yield_quote=kind=='yield'
        q={
          'group':group,'symbol':symbol,'name':name,'kind':kind,
          'currency':m.get('currency') or ('%' if yield_quote else ''),
          'price':rounded(price,5), 'changePct':None if yield_quote else pc(prev),
          'changeBp':bp(prev) if yield_quote else None,
          'ytdPct':None if yield_quote or kind=='volatility' else pc(ref_ytd),
          'yearPct':None if yield_quote or kind=='volatility' else pc(ref_year),
          'ytdBp':bp(ref_ytd) if yield_quote else None,
          'yearBp':bp(ref_year) if yield_quote else None,
          'high52':rounded(safe_float(m.get('fiftyTwoWeekHigh')),4),
          'low52':rounded(safe_float(m.get('fiftyTwoWeekLow')),4),
          'asOf':dt.datetime.fromtimestamp(quote_time,dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
          'delayedMin':m.get('exchangeDataDelayedBy'),
          'cached':cached,'cacheDetail':info_msg,'source':'Yahoo Finance',
          'adjustedAvailable':len(adj_by_day)>=2
        }
        hh=[{'date':date,'symbol':symbol,'close':rounded(val,5),
             **({'adjClose':rounded(adj_by_day[date],5)} if date in adj_by_day else {})} for date,val in pts]
        return q,hh,info_msg,None
    except Exception as exc: return None,[],None,(symbol+': '+str(exc))

def parse_boe(opts):
    start=(dt.date.today()-dt.timedelta(days=int(opts.years*365.25)+16)).strftime('%d/%b/%Y')
    url=('https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes'
        +'&'+urllib.parse.urlencode({'Datefrom':start,'Dateto':'now','SeriesCodes':','.join(BOE_CODES.values()),'CSVF':'TN','UsingCodes':'Y','VPD':'Y','VFD':'N'}))
    raw,cached,msg=get_bytes(url,'boe_rates_y'+str(opts.years),opts.offline,opts.cache_hours)
    text=raw.decode('utf-8-sig',errors='replace')
    rows=[]
    for r in csv.DictReader(io.StringIO(text)):
        day=r.get('DATE') or r.get('Date') or r.get('date')
        if not day: continue
        try: date=dt.datetime.strptime(day.strip(),'%d %b %Y').date().isoformat()
        except ValueError: continue
        x={'date':date}
        for label,code in BOE_CODES.items(): x[label]=safe_float((r.get(code) or '').strip())
        if any(x[k] is not None for k in BOE_CODES): rows.append(x)
    if not rows: raise RuntimeError('No valid BoE rows; data format or access changed')
    rows.sort(key=lambda r:r['date'])
    return rows,cached,msg

def fetch_fred(code,opts):
    # FRED public graph CSV is NOT the official API; this can change.
    start=(dt.date.today()-dt.timedelta(days=int(opts.years*365.25)+410)).isoformat()
    url='https://fred.stlouisfed.org/graph/fredgraph.csv?'+urllib.parse.urlencode({'id':code,'cosd':start})
    raw,cached,msg=get_bytes(url,'fred_'+code+'_y'+str(opts.years),opts.offline,opts.cache_hours)
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig',errors='replace')))
    out=[]
    for r in reader:
        date=r.get('observation_date') or r.get('DATE') or r.get('date')
        v=safe_float(r.get(code))
        if date and v is not None:
            try: dt.date.fromisoformat(date)
            except ValueError: continue
            out.append({'date':date,'value':v})
    if len(out)<2: raise RuntimeError('No data from FRED '+code)
    out.sort(key=lambda r:r['date'])
    return out,cached,msg

def derived_yoy(rows,offset):
    # Calendar series: monthly offset 12 and quarterly offset 4.
    out=[]
    for i in range(offset,len(rows)):
        cur,prev=rows[i],rows[i-offset]
        # Avoid comparing months separated by nonstandard gaps.
        a,b=dt.date.fromisoformat(cur['date']),dt.date.fromisoformat(prev['date'])
        expected=365 if offset==12 else 365
        if abs((a-b).days-expected)>50 or prev['value']==0: continue
        out.append({'date':cur['date'],'value':round(100*(cur['value']/prev['value']-1),3)})
    return out

def macro_series(key,name,unit,method,rows,cached):
    history=derived_yoy(rows,12 if method=='yoy12' else 4) if method!='level' else rows
    return {'key':key,'name':name,'unit':unit,'history':history,
            'value':rounded(history[-1]['value'],3) if history else None,
            'date':history[-1]['date'] if history else None,'cached':cached,'source':'FRED','region':'US','frequency':'monthly' if method in ('level','yoy12') else 'quarterly'}

def parse_us_rates(opts):
    # Pull maturities as independent series because FRED CSV can differ by frequency/date.
    datasets={}; warnings=[];cached_n=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4,opts.workers)) as ex:
        futures={ex.submit(fetch_fred,code,opts):code for code in FRED_US_YIELDS}
        for fut in concurrent.futures.as_completed(futures):
            code=futures[fut]
            try:
                rows,cached,_=fut.result()
                datasets[code]=rows;cached_n+=int(cached)
            except Exception as e: warnings.append(code+': '+str(e))
    # Daily rates can include holidays; use exact dates for coherent comparisons.
    days={}
    for code,rows in datasets.items():
        for r in rows: days.setdefault(r['date'],{'date':r['date']})[code]=r['value']
    return sorted(days.values(),key=lambda r:r['date']),warnings,cached_n

def demo_data():
    """Synthetic offline TEST fixture. Clearly labelled; never present as market data."""
    rng=random.Random(17)
    end=dt.date(2026,11,5)
    quotes=[];hist=[]
    for j,(g,s,n,k) in enumerate(INSTRUMENTS):
        initial=2500 if k=='index' else 150 if k=='etf' else 1.22 if k=='fx' else 4.1 if k=='yield' else 95
        v=initial*(1+(j%7)*0.11)
        observations=[]
        for d in range(730, -1, -1):
            day=end-dt.timedelta(days=d)
            if day.weekday()>4: continue
            v*=1+rng.gauss(.00022, .01 if k!='yield' else .003)
            observations.append((day.isoformat(),v))
        prev=observations[-2][1];start_year=next((val for date,val in reversed(observations) if date<'2026-01-01'),None)
        last=observations[-1][1]
        quotes.append({'group':g,'symbol':s,'name':n,'kind':k,'currency':'GBP' if s=='^FTSE' else 'USD',
            'price':round(last,4),'changePct':round((last/prev-1)*100,2) if k!='yield' else None,
            'changeBp':round(100*(last-prev),2) if k=='yield' else None,
            'ytdPct':round((last/start_year-1)*100,2) if start_year and k not in ['yield','volatility'] else None,
            'yearPct':round((last/observations[-252][1]-1)*100,2) if k not in ['yield','volatility'] else None,
            'ytdBp':round(100*(last-start_year),2) if k=='yield' else None,
            'yearBp':round(100*(last-observations[-252][1]),2) if k=='yield' else None,
            'low52':None,'high52':None,'asOf':'2026-11-05 16:30 UTC','delayedMin':None,'cached':False,'cacheDetail':'demo','source':'SYNTHETIC DEMO'})
        hist += [{'symbol':s,'date':date,'close':round(x,5)} for date,x in observations]
    uk=[];us=[]
    for d in range(730,-1,-1):
        day=end-dt.timedelta(days=d)
        if day.weekday()>4:continue
        k=(730-d)/730
        uk.append({'date':day.isoformat(),'gilt5y':round(4+.35*k+.09*math.sin(k*12),3),
          'gilt10y':round(4.5+.35*k+.1*math.sin(k*11),3),'gilt20y':round(5.1+.25*k+.1*math.sin(k*10),3),'bankRate':4.25 if k<.5 else 4.0,
          'gilt5yReal':round(1.3+.24*k+.1*math.sin(k*11),3),'gilt10yReal':round(1.4+.25*k+.09*math.sin(k*10),3),'gilt20yReal':round(1.65+.2*k+.07*math.sin(k*11),3),
          'gilt5yInflation':round(2.7+.11*k+.08*math.sin(k*9),3),'gilt10yInflation':round(3.1+.1*k+.07*math.sin(k*12),3),'gilt20yInflation':round(3.45+.1*k+.08*math.sin(k*9),3)})
        us.append({'date':day.isoformat(),**{'DGS'+str(y):round(3.5+.025*y+.15*math.sin(k*8),3) for y in [1,2,3,5,7,10,20,30]}})
    macro=[]
    for j,(_,key,name,unit,method) in enumerate(FRED_MACRO):
        hh=[]
        for m in range(42):
            year=2023+(m//12);month=m%12+1
            if year>2026:break
            hh.append({'date':f'{year}-{month:02d}-01','value':round(2.1+j*.45+.2*math.sin(m/4+j),2)})
        macro.append({'key':key,'name':name,'unit':unit,'value':hh[-1]['value'],'date':hh[-1]['date'],'history':hh,'cached':False,'source':'SYNTHETIC DEMO','region':'US','frequency':'monthly' if method in ('level','yoy12') else 'quarterly'})
    regional,eu=regional_data.demo_regional(end)
    macro.extend(regional)
    macro.append(regional_data.economic_series('uk_policy','Bank of England Bank Rate',
        [{'date':r['date'],'value':r['bankRate']} for r in uk if r['bankRate'] is not None],
        'SYNTHETIC DEMO','UK','policy',False))
    companies, company_history = company_data.demo_companies()
    extras=market_intelligence.demo_extras(end)
    demo_f=[{'symbol':c['symbol'],'trailingPE':c.get('trailingPE'),'forwardPE':c.get('forwardPE'),
              'marketCap':c.get('marketCap'),'dividendYieldPct':c.get('dividendYieldPct'),
              'revenueTTM':c.get('revenueTTM'),'netIncomeTTM':c.get('netIncomeTTM'),
              'financialCurrency':c.get('financialCurrency'),'asOf':'SYNTHETIC DEMO'} for c in companies]
    demo_news=[{'symbol':'SHEL.L','name':'Shell plc','articles':[],
                'retrievedAt':'SYNTHETIC DEMO','source':'SYNTHETIC DEMO'}]
    demo_prints,_,demo_forecasts=economic_forecasts.collect(macro,ROOT/'__none_demo_forecasts.csv')
    return {**extras,'economicPrints':demo_prints,'forecastCoverage':{'sourced':demo_forecasts,'series':len(demo_prints)},'company_news':demo_news,'fundamentals':demo_f,'fundamentalsCoverage':{'eligible':0,'available':0,'summaries':len(demo_f),'fetchedThisRun':0},'quotes':quotes,'history':hist,'uk_rates':uk,'us_rates':us,'eu_rates':eu,'macro':macro,
            'companies':companies,'company_history':company_history,
            'movers':market_movers.demo_movers(),'generatedAt':today_utc().strftime('%Y-%m-%d %H:%M UTC'),
            'demo':True,'warnings':['DEMONSTRATION ONLY: all values and historical series are synthetic.'],
            'sources':['SYNTHETIC DEMO'],'yearsRequested':2}

def build_quality(quotes,hist,movers,fundamentals,coverage,calendar,gilts,us_bonds,macro,warnings):
    """Transparent coverage and freshness counts, not an arbitrary accuracy score."""
    today=today_utc().date()
    def age(iso):
        try:return (today-dt.date.fromisoformat(str(iso)[:10])).days
        except (ValueError,TypeError):return None
    stale=[q['symbol'] for q in quotes if (age(q.get('asOf')) or 0)>4]
    suspicious=[q['symbol'] for q in quotes if q.get('changePct') is not None
        and abs(q['changePct'])>(15 if q.get('kind')=='index' else 35)]
    coverage_by_index=[]
    fund={f['symbol'] for f in fundamentals if f.get('trailingPE') is not None}
    for m in movers:
        members=m.get('constituents',[])
        coverage_by_index.append({'name':m.get('name',m.get('id','')),
            'members':m.get('members') or len(members),'quoted':sum(bool(q.get('current')) for q in members),
            'peAvailable':sum(q.get('symbol') in fund for q in members)})
    return {'requested':len(INSTRUMENTS),'quoted':len(quotes),'staleQuotes':stale,
      'unusualPriceMoves':suspicious[:20], 'adjustedSeries':len({r['symbol'] for r in hist if r.get('adjClose') is not None}),
      'fundamentalsCovered':coverage.get('summaries',len(fundamentals)),
      'fundamentalsEligible':coverage.get('eligible',0),
      'indexCoverage':coverage_by_index,'futureCalendar':len(calendar),
      'macroeconomicSeries':len(macro),'pricedGilts':sum(bool(x.get('quoted')) for x in gilts),
      'pricedUSTreasuries':sum(bool(x.get('quoted')) for x in us_bonds),
      'retrievalWarnings':len(warnings),'generatedAt':today_utc().isoformat()}

def build(opts):
    watchlist,watch_errors=personal_watchlist.read_watchlist(ROOT/'personal_watchlist.csv')
    if opts.demo:
        demo=demo_data()
        demo['credit_spreads']=[]
        demo['market_valuations']=market_additions.market_valuation(demo['movers'],demo.get('fundamentals',[]),demo['companies'],demo['us_rates'],demo['uk_rates'])
        # Demonstration uses only synthetic company data; never show invented facts as live.
        demo_profiles={c['symbol']:c for c in demo['companies']}
        demo_hist={}
        for r in demo.get('company_history',[]):demo_hist.setdefault(r['symbol'],[]).append(r)
        demo['personalWatchlist']=watchlist
        demo['watchlist_quotes']=[{'symbol':w['symbol'],'name':w['name'],'kind':'equity','price':demo_profiles[w['symbol']]['price'],
            'currency':demo_profiles[w['symbol']]['priceCurrency'],'changePct':demo_profiles[w['symbol']]['changePct'],
            'asOf':'2026-11-05 16:30 UTC','source':'SYNTHETIC DEMO'} for w in watchlist if w['symbol'] in demo_profiles]
        demo['watchlist_history']=[{'symbol':w['symbol'],'points':personal_watchlist.thin_history(demo_hist.get(w['symbol'],[]))} for w in watchlist if w['symbol'] in demo_hist]
        demo['watchlist_news']=[]
        demo['watchlistCoverage']=personal_watchlist.coverage(watchlist,demo['watchlist_quotes'],[],demo['watchlist_history'],demo['companies'])
        demo['company_events']=[]
        demo['companyEventCoverage']={'detailedProfiles':len(demo['companies']),'datedEvents':0,'issuerSourced':0}
        return demo
    # Persist the visible watchlist in source control; it contains symbols only.
    # The site's public repository must not receive personal position values.
    existing={s.upper() for s in opts.companies}
    for item in watchlist:
        if item['assetType'] in ('stock','investment_trust') and item['symbol'].upper() not in existing:
            opts.companies.append(item['symbol'])
            existing.add(item['symbol'].upper())
    quotes=[];hist=[];warnings=list(watch_errors);cached_count=0
    print(f'Downloading {len(INSTRUMENTS)} market series ({opts.years} years requested) ...',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=opts.workers) as ex:
        futures={ex.submit(fetch_quote,rec,opts):rec[1] for rec in INSTRUMENTS}
        for i,fut in enumerate(concurrent.futures.as_completed(futures),1):
            q,hh,msg,err=fut.result()
            if err: warnings.append('Yahoo '+err)
            else:
                quotes.append(q);hist.extend(hh);cached_count+=int(q['cached'])
                if 'stale cache' in (q.get('cacheDetail') or ''): warnings.append('Yahoo '+q['symbol']+': stale cached response')
            if i%10==0 or i==len(INSTRUMENTS): print(f'  {i}/{len(INSTRUMENTS)} checked; {len(quotes)} successful',flush=True)
    order={rec[1]:i for i,rec in enumerate(INSTRUMENTS)}
    quotes.sort(key=lambda x:order[x['symbol']]);hist.sort(key=lambda x:(order[x['symbol']],x['date']))
    try:
        uk,b_c,boe_msg=parse_boe(opts);cached_count+=int(b_c)
        if 'stale cache' in boe_msg: warnings.append('BoE: stale cached response')
        print(f'BoE: {len(uk)} daily observations',flush=True)
    except Exception as e: uk=[];warnings.append('BoE: '+str(e))
    macro=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4,opts.workers)) as ex:
        future={ex.submit(fetch_fred,code,opts):(key,name,unit,method,code) for code,key,name,unit,method in FRED_MACRO}
        for fut in concurrent.futures.as_completed(future):
            key,name,unit,method,code=future[fut]
            try:
                series,cached,msg=fut.result(); macro.append(macro_series(key,name,unit,method,series,cached));cached_count+=int(cached)
                if 'stale cache' in msg: warnings.append('FRED '+code+': stale cached response')
            except Exception as e: warnings.append('FRED '+code+': '+str(e))
    regional,eu,regional_warnings,n_region_cached=regional_data.get_regional_data(sys.modules[__name__],opts)
    macro.extend(regional);cached_count+=n_region_cached
    if uk:
        uk_policy=[{'date':r['date'],'value':r['bankRate']} for r in uk if r.get('bankRate') is not None]
        if uk_policy:
            macro.append(regional_data.economic_series('uk_policy','Bank of England Bank Rate',uk_policy,
              'Bank of England','UK','policy',False,'https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp'))
    warnings.extend(regional_warnings)
    order_macro={x[1]:i for i,x in enumerate(FRED_MACRO)}
    macro.sort(key=lambda x:order_macro.get(x['key'],len(order_macro)))
    economic_prints,forecast_warn,forecast_count=economic_forecasts.collect(macro,ROOT/'consensus_forecasts.csv')
    warnings.extend(forecast_warn)
    us,uswarn,n_us_cached=parse_us_rates(opts);cached_count+=n_us_cached
    warnings.extend('FRED '+w for w in uswarn)
    us_real,realwarn,n_real_cached=market_intelligence.collect_us_real(sys.modules[__name__],opts)
    warnings.extend(realwarn);cached_count+=n_real_cached
    # Use one common fetch/cache layer and the validated Eurostat JSON-stat parser.
    class SovereignAdapter:
        get_bytes=staticmethod(get_bytes)
        parse_jsonstat=staticmethod(regional_data.parse_jsonstat)
    sovereign,sovwarn,n_sov_cached=market_intelligence.collect_sovereign(SovereignAdapter,opts)
    warnings.extend(sovwarn);cached_count+=n_sov_cached
    news,newwarn,n_news_cached=market_intelligence.collect_news(sys.modules[__name__],opts)
    warnings.extend(newwarn);cached_count+=n_news_cached
    calendar,calwarn,n_cal_cached=market_intelligence.collect_calendar(sys.modules[__name__],opts)
    warnings.extend(calwarn);cached_count+=n_cal_cached
    movers=[]
    if not opts.no_movers:
        movers,mwarn=market_movers.build_market_movers(sys.modules[__name__],opts)
        warnings.extend(mwarn)
    companies=[]; company_history=[]
    if not opts.no_companies:
        selections=company_data.company_universe(opts.companies)
        print(f'Companies: retrieving selected-company data for {len(selections)} tickers ...',flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(2, opts.workers)) as ex:
            fs={ex.submit(company_data.fetch_company,sym,name,sys.modules[__name__],opts):sym for sym,name in selections}
            for f in concurrent.futures.as_completed(fs):
                sym=fs[f]
                try:
                    company, hh, err=f.result()
                    companies.append(company)
                    company_history.extend(hh)
                    if err: warnings.append('Company '+err)
                except Exception as exc: warnings.append(f'Company {sym}: {exc}')
        company_order={sym:i for i,(sym,_) in enumerate(selections)}
        companies.sort(key=lambda r:company_order.get(r['symbol'],9999))
    # Save historical prices for the most unusual movers, without needing a paid
    # API or downloading financial statements for every index constituent.
    focus=market_intelligence.focus_movers(movers,limit=opts.mover_history_limit)
    detailed_syms={c['symbol'] for c in companies}
    price_targets=[c for c in focus if c['symbol'] not in detailed_syms]
    if price_targets and not opts.offline:
        import copy
        hist_opts=copy.copy(opts);hist_opts.years=min(opts.years,10)
        print(f'Mover price history: retrieving {len(price_targets)} ticker histories ...',flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(2,opts.workers)) as pool:
            tasks={pool.submit(fetch_quote,('Companies',x['symbol'],x['name'],'equity'),hist_opts):x for x in price_targets}
            for fut in concurrent.futures.as_completed(tasks):
                x=tasks[fut]
                try:
                    q,hh,msg,err=fut.result()
                    if hh: company_history.extend(hh)
                    if err and len(warnings)<35:warnings.append('Mover history '+x['symbol']+': '+str(err)[:130])
                except Exception as e:
                    if len(warnings)<35:warnings.append('Mover history '+x['symbol']+': '+str(e)[:130])
    watch_quotes,watch_history,wqw,watch_cached=personal_watchlist.collect_quotes(sys.modules[__name__],opts,watchlist)
    warnings.extend(wqw);cached_count+=watch_cached
    watch_news,wnw,wn_cached=personal_watchlist.collect_news(sys.modules[__name__],opts,watchlist)
    warnings.extend(wnw);cached_count+=wn_cached
    watch_coverage=personal_watchlist.coverage(watchlist,watch_quotes,watch_news,watch_history,companies)
    print(f'Personal watchlist: {watch_coverage["quoted"]}/{len(watchlist)} quotes, {watch_coverage["historical"]} charts, {watch_coverage["newsWithResults"]} news matches',flush=True)
    company_news,nwarn,nnews_cached=market_intelligence.collect_company_news(
        sys.modules[__name__],opts,movers,limit=opts.company_news_limit)
    warnings.extend(nwarn);cached_count+=nnews_cached
    fundamentals, fcoverage, fwarnings=market_fundamentals.collect(
        movers,companies, ROOT/'.terminal_fundamentals', batch_size=opts.fundamentals_batch,
        offline=opts.offline or opts.no_fundamentals)
    warnings.extend(fwarnings)
    print(f'Fundamentals: {fcoverage["summaries"]} of {fcoverage["eligible"]} unique constituents have summaries; {fcoverage["available"]} have P/E',flush=True)
    history_symbols, history_coverage, history_warnings=market_price_history.collect(
        sys.modules[__name__], opts, movers, company_history,
        cache_dir=ROOT/'.terminal_price_history', batch=opts.price_history_batch)
    warnings.extend(history_warnings)
    # Official FedInvest U.S. Treasury security quotations; dated, not live.
    us_bonds,us_treasury_history,ust_warnings,ust_cached=us_treasury_market.collect(sys.modules[__name__],opts)
    warnings.extend(ust_warnings);cached_count+=ust_cached
    print(f'US Treasuries: {len(us_bonds)} listed with dated quotations, {len(us_treasury_history)} prices',flush=True)
    # Optional individual UK government-bond indicative clean-price snapshot.
    # Never invent missing quotes; source and date are retained for every bond.
    gilts,gilt_history,gilt_warnings,gilt_cached=gilt_market.collect(sys.modules[__name__],opts)
    warnings.extend(gilt_warnings)
    cached_count+=gilt_cached
    print(f'Gilts: {len(gilts)} DMO bonds ({sum(x.get("indexLinked",False) for x in gilts)} index-linked), {sum(x["quoted"] for x in gilts)} dated price quotes; {len(gilt_history)} saved observations',flush=True)
    # Corporate spreads are sourced ICE/FRED OAS index levels, not single-bond yields.
    credit_spreads,credit_warnings,credit_cached=market_additions.collect_credit(sys.modules[__name__],opts)
    warnings.extend(credit_warnings);cached_count+=credit_cached
    market_valuations=market_additions.market_valuation(movers,fundamentals,companies,us,uk,asof=today_utc().date().isoformat())
    bulk_events,bulk_warnings=market_additions.collect_market_earnings(movers,companies,offline=opts.offline or opts.no_companies)
    warnings.extend(bulk_warnings)
    company_events,event_warnings,event_coverage=market_additions.issuer_events(companies,ROOT/'company_events.csv',bulk_events=bulk_events)
    warnings.extend(event_warnings)
    print(f'Credit: {len(credit_spreads)} / {len(market_additions.CREDIT_SERIES)} FRED series; market valuation: {len(market_valuations)} indices; issuer events: {len(company_events)}',flush=True)
    quality=build_quality(quotes,hist,movers,fundamentals,fcoverage,calendar,gilts,us_bonds,macro,warnings)
    quality['personalWatchlist']=watch_coverage
    return {'personalWatchlist':watchlist,'watchlist_quotes':watch_quotes,'watchlist_history':watch_history,
            'watchlist_news':watch_news,'watchlistCoverage':watch_coverage,
            'credit_spreads':credit_spreads,'market_valuations':market_valuations,'company_events':company_events,'companyEventCoverage':event_coverage,
            'quality':quality,'economicPrints':economic_prints,'forecastCoverage':{'sourced':forecast_count,'series':len(economic_prints)},
            'us_treasuries':us_bonds,'us_treasury_history':us_treasury_history,'gilts':gilts,'gilt_history':gilt_history,
'fundamentals':fundamentals,'fundamentalsCoverage':fcoverage,
            'priceHistorySymbols':history_symbols,'priceHistoryCoverage':history_coverage,
            'company_news':company_news,
            'news':news,'calendar':calendar,'us_real':us_real,'sovereign_yields':sovereign,
        'companies':companies,'company_history':company_history,
       'movers':movers,'quotes':quotes,'history':hist,'uk_rates':uk,'us_rates':us,'eu_rates':eu,'macro':macro,
       'generatedAt':today_utc().strftime('%Y-%m-%d %H:%M UTC'),'demo':False,
       'warnings':warnings,'sources':['Yahoo Finance (unofficial)','Bank of England','FRED graph CSV (unofficial download)','Office for National Statistics','Eurostat','European Central Bank','UK Debt Management Office D10B purchase/sale service prices (dated)','US Treasury FedInvest rates/prices (dated)','FRED / ICE BofA corporate OAS (third-party licensed)', 'Yahoo Finance / yfinance calendar (indicative issuer dates)','Personal watchlist: source tickers only; no holdings or valuations'],
       'yearsRequested':opts.years,'cachedSeries':cached_count}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--years',type=int,default=20,help='historical years requested (1–25, default 20)')
    p.add_argument('--workers',type=int,default=3,help='concurrent network requests (1–6, default 3)')
    p.add_argument('--cache-hours',type=float,default=4,help='re-use recent downloads (default 4h)')
    p.add_argument('--offline',action='store_true',help='build using only previously cached responses')
    p.add_argument('--demo',action='store_true',help='generate an explicitly SYNTHETIC, offline interactive demo')
    p.add_argument('--output',default=None,help='output HTML filename')
    p.add_argument('--movers-markets',default=','.join(market_movers.DEFAULT_MARKETS),
        help='index constituent markets for top 10 movers: FTSE100,FTSE250,SP500,NASDAQ100 (default all four)')
    p.add_argument('--no-movers',action='store_true',help='skip constituent-level mover downloads')
    p.add_argument('--companies',default='',help='extra company tickers separated by commas (e.g. SHEL.L,MSFT)')
    p.add_argument('--no-companies',action='store_true',help='skip detailed company collection')
    p.add_argument('--fundamentals-batch',type=int,default=40,help='maximum new constituent financial summaries per build (default 40)')
    p.add_argument('--mover-history-limit',type=int,default=12,help='up to 12 daily movers receive ten-year price history')
    p.add_argument('--price-history-batch',type=int,default=60,help='number of additional ten-year charts downloaded per update')
    p.add_argument('--company-news-limit',type=int,default=12,help='fetch related headlines for up to 12 large daily movers')
    p.add_argument('--no-fundamentals',action='store_true',help='read existing financial cache only')
    a=p.parse_args()
    if not 1<=a.years<=25: p.error('--years must be 1–25')
    if not 1<=a.workers<=6: p.error('--workers must be 1–6')
    if not 0<=a.fundamentals_batch<=150:p.error('--fundamentals-batch must be 0–150')
    if not 0<=a.mover_history_limit<=30:p.error('--mover-history-limit must be 0–30')
    if not 0<=a.price_history_batch<=125:p.error('--price-history-batch must be 0–125')
    if not 0<=a.company_news_limit<=30:p.error('--company-news-limit must be 0–30')
    if not a.no_movers:
        unknown=set(a.movers_markets.upper().split(','))-set(market_movers.MARKET_CONFIG)
        if unknown: p.error('unknown movers market(s): '+', '.join(sorted(unknown)))
    a.companies=[x.strip() for x in a.companies.split(',') if x.strip()]
    payload=build(a)
    if not payload['quotes'] and not payload['uk_rates'] and not payload['macro'] and not payload['us_rates']:
        raise SystemExit('No data was retrieved. Check internet access; use --demo to preview the interface.')
    template=(ROOT/'terminal_template.html').read_text('utf-8')
    marker='/*__DATA__*/null'
    if template.count(marker)!=1: raise SystemExit('Missing template data placeholder')
    js=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    dest=ROOT/(a.output or ('terminal_demo.html' if a.demo else 'terminal.html'))
    dest.write_text(template.replace(marker,js),'utf-8')
    print(f'Wrote {dest.name}: {len(payload["quotes"])} instruments, {len(payload["history"])} closes, '
          f'{len(payload["uk_rates"])} UK rates, {len(payload["us_rates"])} US rates, {len(payload["eu_rates"])} euro rates, '
          f'{len(payload["macro"])} economic series, {len(payload["sovereign_yields"])} sovereign-yield observations, {len(payload["news"])} news headlines, {len(payload["calendar"])} scheduled releases, {len(payload["movers"])} mover markets, '+
          f'{len(payload["companies"])} company profiles; {len(payload["warnings"])} warnings')
    if payload['warnings']:
        for w in payload['warnings'][:12]: print('WARNING:',w)
    return 0

if __name__=='__main__': sys.exit(main())
