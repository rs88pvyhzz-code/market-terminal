"""Constituent-wide daily index risers/fallers for the personal market terminal.

Collect an index's complete membership (Wikipedia tables or optional local CSV),
then look up SAME-DAY price changes for every constituent. This deliberately
never labels a ranking of a partial watchlist as a market-wide top ten.

Sources: Wikipedia constituent pages (unofficial membership snapshot) and Yahoo
Finance's unofficial spark/chart endpoints. Both may change or deny automation.
"""
import concurrent.futures
import csv
import datetime as dt
import html.parser
import io
import json
import pathlib
import re
import time
import urllib.parse
from collections import Counter

MARKET_CONFIG = {
    'FTSE100': {'name':'FTSE 100','page':'FTSE_100_Index','suffix':'.L','expected_min':80,'expected_max':115},
    'FTSE250': {'name':'FTSE 250','page':'FTSE_250_Index','suffix':'.L','expected_min':195,'expected_max':275},
    'SP500': {'name':'S&P 500','page':'List_of_S%26P_500_companies','suffix':'','expected_min':450,'expected_max':530},
    'NASDAQ100': {'name':'Nasdaq 100','page':'List_of_NASDAQ-100_companies','suffix':'','expected_min':85,'expected_max':115},
}
DEFAULT_MARKETS = ('FTSE100','FTSE250','SP500','NASDAQ100')


class Tables(html.parser.HTMLParser):
    """Collect text from simple Wikimedia wikitables; no third-party packages."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables=[];self.depth=0;self.rows=[];self.cells=[]
        self.active=False;self.cell=None;self.ignore=0

    def handle_starttag(self, tag, attrs):
        if tag=='table':
            if self.depth==0:
                self.rows=[];self.active='wikitable' in dict(attrs).get('class','').lower()
            self.depth+=1
        if not self.depth or not self.active or self.depth!=1:return
        if tag=='tr':self.cells=[]
        elif tag in ('th','td'):
            self.cell={'tag':tag,'text':[]}
        elif tag in ('sup','script','style') and self.cell:self.ignore+=1
        elif tag=='br' and self.cell and not self.ignore:self.cell['text'].append(' ')

    def handle_data(self,data):
        if self.depth==1 and self.active and self.cell and not self.ignore:
            self.cell['text'].append(data)

    def handle_endtag(self,tag):
        if self.depth==1 and self.active:
            if tag in ('sup','script','style') and self.ignore:self.ignore-=1
            if tag in ('th','td') and self.cell:
                value=' '.join(''.join(self.cell['text']).split())
                self.cells.append((self.cell['tag'], value));self.cell=None
            elif tag=='tr' and self.cells:self.rows.append(self.cells);self.cells=[]
        if tag=='table' and self.depth:
            self.depth-=1
            if self.depth==0 and self.active:self.tables.append(self.rows);self.active=False


def clean_symbol(value, suffix):
    s=re.sub(r'\[[^\]]*\]','',value).strip().split()[0] if value.strip() else ''
    s=s.upper().strip().replace('\u200b','').replace('–','-')
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,12}',s):return None
    if suffix:
        s=s.rstrip('.')+suffix
    else:
        s=s.replace('.','-')
    return s


def parse_constituents(html, market_id):
    cfg=MARKET_CONFIG[market_id]
    parser=Tables();parser.feed(html)
    candidates=[]
    for table in parser.tables:
        for hi,head in enumerate(table[:3]):
            headers=[text.lower().strip().replace('\n',' ') for _,text in head]
            def col(names):
                return next((i for i,x in enumerate(headers) if x in names),None)
            symbol_col=col({'ticker','symbol','epic','ticker symbol'})
            name_col=col({'company','security','name','company name'})
            if symbol_col is None or name_col is None:continue
            found=[];seen=set()
            for row in table[hi+1:]:
                if len(row)<=max(name_col,symbol_col):continue
                s=clean_symbol(row[symbol_col][1],cfg['suffix'])
                n=row[name_col][1]
                if s and s not in seen and n:
                    found.append({'symbol':s,'name':n});seen.add(s)
            candidates.append(found)
    return max(candidates,key=len,default=[])


def load_constituents(market_id, main_module, opts):
    cfg=MARKET_CONFIG[market_id]
    local=main_module.ROOT/'constituents'/f'{market_id}.csv'
    if local.exists():
        with local.open(encoding='utf-8-sig',newline='') as f:
            rows=[];seen=set()
            for r in csv.DictReader(f):
                raw=r.get('symbol') or r.get('Symbol') or r.get('Ticker') or ''
                s=raw.strip().upper() if cfg['suffix'] and raw.upper().endswith(cfg['suffix'].upper()) else clean_symbol(raw,cfg['suffix'])
                if s and not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,17}',s):s=None
                name=r.get('name') or r.get('Name') or r.get('Company') or s
                if s and s not in seen: rows.append({'symbol':s,'name':name});seen.add(s)
        source='Local constituent CSV'
        cached=False
    else:
        url='https://en.wikipedia.org/wiki/'+cfg['page']
        raw,cached,_=main_module.get_bytes(url,'members_'+market_id,opts.offline,max(opts.cache_hours,24))
        rows=parse_constituents(raw.decode('utf-8',errors='replace'),market_id)
        source='Wikipedia (constituents)'
    if not cfg['expected_min']<=len(rows)<=cfg['expected_max']:
        raise RuntimeError(f'Constituent list not credible: {len(rows)} parsed (expected {cfg["expected_min"]}–{cfg["expected_max"]}); no partial ranking issued')
    return rows,source,cached


def parse_chart_result(result, symbol, name, main_module):
    meta=result.get('meta',{})
    stamps=result.get('timestamp') or []
    qs=result.get('indicators',{}).get('quote') or [{}]
    closes=qs[0].get('close') or []
    tz=meta.get('exchangeTimezoneName','UTC')
    history=sorted({main_module.iso_date(t,tz):main_module.safe_float(v) for t,v in zip(stamps,closes)
       if main_module.safe_float(v) is not None and main_module.safe_float(v)>0}.items())
    if len(history)<2:return None
    timestamp=meta.get('regularMarketTime') or stamps[-1]
    day=main_module.iso_date(timestamp,tz)
    last=main_module.safe_float(meta.get('regularMarketPrice')) or history[-1][1]
    prev=main_module.prior_close(history,day,meta)
    if not prev or prev<=0 or not last:return None
    return {'symbol':symbol,'name':name,'price':round(last,4),
            'change':round(last-prev,4),'changePct':round((last/prev-1)*100,2),
            'currency':meta.get('currency',''),'date':day,
            'asOf':dt.datetime.fromtimestamp(timestamp,dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}


def fetch_spark_batch(pairs,main_module,opts):
    syms=','.join(p['symbol'] for p in pairs)
    query=urllib.parse.urlencode({'symbols':syms,'range':'5d','interval':'1d'})
    key='movers_spark_'+str(abs_hash(syms))
    raw,cached,msg=main_module.get_bytes('https://query1.finance.yahoo.com/v7/finance/spark?'+query,key,opts.offline,opts.cache_hours)
    payload=json.loads(raw.decode('utf-8'))
    res=payload['spark']['result']
    names={p['symbol']:p['name'] for p in pairs}
    out={}
    for item in res:
        sym=item['symbol']
        if sym not in names:continue
        r=item.get('response') or []
        if r:
            rec=parse_chart_result(r[0],sym,names[sym],main_module)
            if rec:out[sym]=rec
    return out


def abs_hash(s):
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()[:18]


def fetch_chart_mover(pair,main_module,opts):
    sym=pair['symbol']
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+urllib.parse.quote(sym,safe='')+'?range=1mo&interval=1d'
    key='movers_chart_'+urllib.parse.quote(sym,safe='').replace('%','_')
    raw,cached,msg=main_module.get_bytes(url,key,opts.offline,opts.cache_hours)
    data=json.loads(raw.decode('utf-8'))['chart']['result'][0]
    return parse_chart_result(data,sym,pair['name'],main_module)


def build_market_movers(main_module, opts):
    market_ids=[s.strip().upper() for s in opts.movers_markets.split(',') if s.strip()]
    wrong=[x for x in market_ids if x not in MARKET_CONFIG]
    if wrong:raise ValueError('Unknown --movers-markets: '+', '.join(wrong))
    universes={}; warnings=[]
    for mid in market_ids:
        try:
            members,source,cached=load_constituents(mid,main_module,opts)
            universes[mid]=(members,source)
            print(f'Movers: {mid} {len(members)} constituents ({source})',flush=True)
        except Exception as e:
            warnings.append(f'Movers {mid}: {e}')
    unique={p['symbol']:p for members,src in universes.values() for p in members}
    quotes={}
    pairs=list(unique.values())
    batches=[pairs[i:i+20] for i in range(0,len(pairs),20)]
    failed=[]
    if batches:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(3,opts.workers)) as ex:
            futures={ex.submit(fetch_spark_batch,b,main_module,opts):b for b in batches}
            for fut in concurrent.futures.as_completed(futures):
                batch=futures[fut]
                try:
                    got=fut.result();quotes.update(got)
                    failed.extend(p for p in batch if p['symbol'] not in got)
                except Exception:
                    failed.extend(batch)
    if failed:
        print(f'Movers: batch feed missing {len(failed)} names, trying chart quotes...',flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(3,opts.workers)) as ex:
            futures={ex.submit(fetch_chart_mover,p,main_module,opts):p for p in failed}
            for i,fut in enumerate(concurrent.futures.as_completed(futures),1):
                try:
                    q=fut.result()
                    if q:quotes[q['symbol']]=q
                except Exception:pass
                if i%100==0: print(f'  {i}/{len(failed)} fallback quotes checked',flush=True)
    final=[]
    for mid in market_ids:
        if mid not in universes:continue
        members,src=universes[mid]
        matches=[quotes[p['symbol']].copy() for p in members if p['symbol'] in quotes]
        days=Counter(q['date'] for q in matches)
        same_day=days.most_common(1)[0][0] if days else None
        current=[q for q in matches if q['date']==same_day]
        gainers=sorted((q for q in current if q['changePct']>0),key=lambda q:(-q['changePct'],q['symbol']))[:10]
        losers=sorted((q for q in current if q['changePct']<0),key=lambda q:(q['changePct'],q['symbol']))[:10]
        coverage=len(current)/len(members)
        complete=len(current)==len(members) and len(gainers)==10 and len(losers)==10
        if not complete:warnings.append(f'Movers {mid}: partial sample {len(current)}/{len(members)} ({coverage:.0%}) for {same_day or "unknown day"}; rankings NOT guaranteed to be full-market top ten')
        # Include the entire index membership in the HTML snapshot, not just movers.
        # Missing/stale quotes stay visible, with explicit availability flags.
        constituents=[]
        for member in members:
            q=quotes.get(member['symbol'])
            constituents.append({
                'symbol':member['symbol'],'name':member['name'],
                'price':q['price'] if q else None,
                'changePct':q['changePct'] if q and q['date']==same_day else None,
                'currency':q.get('currency','') if q else '',
                'date':q.get('date') if q else None,
                'asOf':q.get('asOf') if q else None,
                'current':bool(q and q['date']==same_day),
            })
        constituents.sort(key=lambda r:(r['name'].casefold(),r['symbol']))
        final.append({'id':mid,'name':MARKET_CONFIG[mid]['name'],'date':same_day,
            'members':len(members),'quoted':len(matches),'sameDay':len(current),'coveragePct':round(coverage*100,1),
            'complete':complete,'source':src+' + Yahoo Finance (unofficial)',
            'gainers':gainers,'losers':losers,'constituents':constituents})
    return final,warnings


def demo_movers():
    import random
    rng=random.Random(251)
    out=[]
    for market_id in MARKET_CONFIG:
        count={'FTSE100':100,'FTSE250':250,'SP500':503,'NASDAQ100':101}[market_id]
        rows=[]
        for i in range(count):
            ch=round(rng.uniform(-8.5,8.5),2)
            price=round(rng.uniform(120,3500),2)
            rows.append({'symbol':f'TEST{i+1:03d}','name':f'Synthetic company {i+1:03d}',
                'price':price,'change':round(price*ch/100,2),'changePct':ch,
                'currency':'GBp' if market_id.startswith('FTSE') else 'USD',
                'date':'2026-11-05','asOf':'2026-11-05 16:30 UTC'})
        out.append({'id':market_id,'name':MARKET_CONFIG[market_id]['name'],'date':'2026-11-05',
              'members':count,'quoted':count,'sameDay':count,'coveragePct':100,'complete':True,
              'source':'SYNTHETIC DEMO — NOT REAL MARKET DATA',
               'constituents':sorted([{**r,'current':True} for r in rows],key=lambda r:r['name']),
              'gainers':sorted((r for r in rows if r['changePct']>0),key=lambda r:-r['changePct'])[:10],
              'losers':sorted((r for r in rows if r['changePct']<0),key=lambda r:r['changePct'])[:10]})
    return out
