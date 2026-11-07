"""Snapshot-only personal security watchlist (no position size, cost basis or value).

Saved names are a provisional list, not an assertion of current holdings.
All quotes are from the existing unofficial Yahoo chart collector; company headlines
are sourced to Google News RSS when available. Missing facts remain missing.
"""
import concurrent.futures
import csv
import datetime as dt
import pathlib
import re
import urllib.parse

import company_data
import market_intelligence

KINDS={'stock':'equity','investment_trust':'equity','etf':'etf','fund':None}
# Official listing date for VALL; Yahoo chart also contains two USD launch/NAV
# reference points (~5.00) before GBP exchange trading (~3.67). Do not mix them.
# https://www.vanguard.co.uk/professional/product/etf/equity/E161/vanguard-ftse-global-all-cap-ucits-etf-usd-acc
FIRST_EXCHANGE_DATE={'VALL.L':'2026-08-20'}
BENCHMARKS={
    'AXON':'^GSPC', 'VAPX.L':'EFA', 'VUAG.L':'^GSPC', 'VUSA.L':'^GSPC',
    'VJPB.L':'^N225', 'XDEX.L':'EEM', 'XMJP.L':'^N225',
    'III.L':'^FTSE', 'VUKE.L':'^FTSE', 'VERX.L':'^STOXX',
    'CUKX.L':'^FTSE', 'CSPX.L':'^GSPC', 'RCP.L':'ACWI',
    'SMT.L':'ACWI', 'SHEL.L':'^FTSE', 'SIE.DE':'^GDAXI',
    'VV':'^GSPC', 'VBK':'^RUT', 'VHT':'^GSPC',
    'XDEW.L':'^GSPC', 'SKWD':'^GSPC', 'VALL.L':'ACWI'
}



def read_watchlist(path, limit=35):
    path=pathlib.Path(path)
    if not path.exists():return [],['Watchlist configuration file is missing']
    out=[];warnings=[];seen=set()
    with path.open('r',encoding='utf-8-sig',newline='') as handle:
        for i,row in enumerate(csv.DictReader(handle),2):
            raw=(row.get('symbol') or '').strip().upper()
            if not raw:continue
            symbol=company_data.valid_symbol(raw)
            kind=(row.get('asset_type') or 'stock').lower().strip().replace(' ','_')
            if not symbol or kind not in KINDS:
                warnings.append('Watchlist row '+str(i)+': invalid symbol or asset_type; skipped');continue
            if symbol in seen:continue
            if len(out)>=limit:
                warnings.append('Watchlist limited to '+str(limit)+' securities; extra rows skipped');break
            seen.add(symbol)
            # CSV is also committed publicly; never import private comments, cost or holdings.
            name=re.sub(r'[\x00-\x1f\x7f]', '',(row.get('name') or symbol).strip())[:96] or symbol
            bench=(row.get('benchmark') or BENCHMARKS.get(symbol) or '').strip().upper()
            bench=company_data.valid_symbol(bench) if bench else ''
            out.append({'symbol':symbol,'name':name,'assetType':kind,
                        'benchmark':bench or '',
                        'firstTradeDate':FIRST_EXCHANGE_DATE.get(symbol,'')})
    if not out:warnings.append('Personal watchlist contains no valid tickers')
    return out,warnings


def thin_history(rows, asof=None):
    """Keep a daily recent window; weekly and monthly older records for iPad speed.

    All points are observed source prices, never interpolated or invented.
    """
    if not rows:return []
    rows=sorted((r for r in rows if r.get('close') is not None),key=lambda r:r['date'])
    last=dt.date.fromisoformat(rows[-1]['date']);selected=[];old_bucket=None
    for row in rows:
        date=dt.date.fromisoformat(row['date']);age=(last-date).days
        if age<=380: selected.append(row);continue
        bucket=(date.isocalendar().year,date.isocalendar().week) if age<=365*10 else (date.year,date.month)
        if bucket!=old_bucket:selected.append(row)
        old_bucket=bucket
    if selected and selected[-1]['date']!=rows[-1]['date']:selected.append(rows[-1])
    return [[r['date'],r['close'],r.get('adjClose')] for r in selected]


def validate_quote_history(symbol, quote, history):
    """Exclude only known pre-listing, differently denominated reference points.

    All other large movements remain visible and should be investigated as
    potential corporate actions or data errors, never silently deleted.
    """
    history=sorted((x for x in history if x.get('date') and x.get('close') is not None),
                   key=lambda x:x['date'])
    start=FIRST_EXCHANGE_DATE.get(symbol)
    removed=0
    if start:
        removed=sum(x['date']<start for x in history)
        history=[x for x in history if x['date']>=start]
        if removed and quote:
            quote['historyWarning']=(f'Ignored {removed} pre-listing reference observations before '
                 +start+'; earlier source values were not London exchange quotes.')
    if quote and history:
        quote['historyStarts']=history[0]['date']
        quote['historyEnds']=history[-1]['date']
        # A security which began trading during the year has no genuine YTD
        # price return from the previous year's close.
        last=dt.date.fromisoformat(history[-1]['date'])
        first=dt.date.fromisoformat(history[0]['date'])
        if first >= dt.date(last.year,1,1):quote['ytdPct']=None
        if (last-first).days < 335:quote['yearPct']=None
        # Yahoo's 52-week range can include pre-listing seed values; for this
        # known issue calculate it from actual post-listing traded closes.
        if removed:
            recent=[x['close'] for x in history if x['date'] >= (last-dt.timedelta(days=365)).isoformat()]
            if recent:
                quote['high52']=max(recent);quote['low52']=min(recent)
        for a,b in zip(history,history[1:]):
            if a['close']>0 and b['date']<= (dt.date.fromisoformat(a['date'])+dt.timedelta(days=7)).isoformat():
                move=abs(b['close']/a['close']-1)
                if move>0.30:
                    quote['anomalyWarning']=(f'Large source price jump {move*100:.1f}% '
                         +a['date']+' to '+b['date']+'; check split, dividend and price units.')
                    break
    return quote,history


def collect_quotes(core,opts,watchlist):
    quotes=[];history=[];warnings=[];cached=0
    if not watchlist:return quotes,history,warnings,cached
    tradeable=[item for item in watchlist if KINDS[item['assetType']] is not None]
    if len(tradeable)!=len(watchlist):warnings.append('Unquoted fund platform codes are listed without market prices; do not substitute unrelated tickers')
    def one(item):
        return core.fetch_quote(('Personal Watchlist',item['symbol'],item['name'],KINDS[item['assetType']]),opts)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3,max(1,opts.workers))) as pool:
        futures={pool.submit(one,item):item for item in tradeable}
        done={}
        for future in concurrent.futures.as_completed(futures):
            item=futures[future]
            try:done[item['symbol']]=future.result()
            except Exception as exc:done[item['symbol']]=(None,[],None,item['symbol']+': '+str(exc))
    for item in tradeable:
        q,hh,msg,err=done[item['symbol']]
        if q:
            q,hh=validate_quote_history(item['symbol'],q,hh)
            quotes.append(q);cached+=int(bool(q.get('cached')))
            history.append({'symbol':item['symbol'],'points':thin_history(hh),'source':'Yahoo Finance daily chart (unofficial)'})
            if q.get('historyWarning'):warnings.append(item['symbol']+': '+q['historyWarning'])
            if q.get('anomalyWarning'):warnings.append(item['symbol']+': '+q['anomalyWarning'])
            if 'stale cache' in (q.get('cacheDetail') or ''):warnings.append('Watchlist '+item['symbol']+': stale cached price data')
        elif err:warnings.append('Watchlist quote '+str(err)[:180])
    return quotes,history,warnings,cached


def collect_news(core,opts,watchlist,limit=35):
    now=dt.datetime.now(dt.timezone.utc)
    def one(item):
        symbol=item['symbol'];name=item['name']
        # Google RSS names may not be unique. These are search matches, NOT certified issuer news.
        query='"'+name.replace('"','')[:88]+'" shares when:4d'
        url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query,'hl':'en-GB','gl':'GB','ceid':'GB:en'})
        try:
            raw,cached,msg=core.get_bytes(url,'personal_watch_news_'+re.sub(r'[^A-Za-z0-9]','_',symbol),opts.offline,opts.cache_hours)
            articles=market_intelligence.rss_articles(raw,'COMPANY',generated=now)[:4]
            warn='Watchlist '+symbol+': stale news cache' if 'stale cache' in msg else None
            return articles,int(cached),warn
        except Exception as exc:
            return [],0,'Watchlist news '+symbol+': '+str(exc)[:130]
    selected=[w for w in watchlist if w['assetType']!='fund'][:limit]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(one,item):item for item in selected}
        result={}
        for job in concurrent.futures.as_completed(jobs):result[jobs[job]['symbol']]=job.result()
    out=[];cached=0;warnings=[]
    for item in selected:
        articles,used,warning=result[item['symbol']]
        out.append({'symbol':item['symbol'],'name':item['name'],'retrievedAt':now.strftime('%Y-%m-%d %H:%M UTC'),
                    'articles':articles,'source':'Google News RSS search (unofficial)'})
        cached+=used
        if warning:warnings.append(warning)
    return out,warnings,cached


def coverage(records,quotes,news,history,companies):
    q={x['symbol']:x for x in quotes};n={x['symbol']:x for x in news};h={x['symbol']:x for x in history};c={x['symbol']:x for x in companies}
    # A usable twelve-month risk series requires more than a freshly listed ETF's few quotes.
    risk_count=0
    for item in records:
        pts=h.get(item['symbol'],{}).get('points',[])
        if len(pts)>=120 and pts[0][0] and pts[-1][0]:
            last=dt.date.fromisoformat(pts[-1][0]);cutoff=(last-dt.timedelta(days=365)).isoformat()
            recent=[row for row in pts if row[0]>=cutoff]
            if len(recent)>=120 and (last-dt.date.fromisoformat(recent[0][0])).days>=180:
                risk_count+=1
    return {'requested':len(records),'quoteEligible':sum(r['assetType']!='fund' for r in records),'quoted':len(quotes),
            'riskHistoryEligible':risk_count,
            'priceAnomalies':sum(bool(x.get('anomalyWarning')) for x in quotes),
            'preListingFixes':sum(bool(x.get('historyWarning')) for x in quotes),
            'historical':sum(len(h.get(r['symbol'],{}).get('points',[]))>=2 for r in records),
            'detailedFundamentals':sum(bool(c.get(r['symbol'],{}).get('trailingPE') or c.get(r['symbol'],{}).get('revenueTTM')) for r in records),
            'newsWithResults':sum(bool(n.get(r['symbol'],{}).get('articles')) for r in records)}
