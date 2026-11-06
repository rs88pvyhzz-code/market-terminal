"""Optional UK conventional-gilt quote collector for a non-commercial market snapshot.

Source: dividenddata.co.uk publicly displayed *indicative* clean quotes, not
FTSE-Tradeweb closing reference prices, executable bids or official prices.
No estimated bond prices are ever substituted for missing quotes.
Historical prices are accumulated from verified future snapshots, not backfilled.
"""
from html.parser import HTMLParser
import datetime as dt
import html
import json
import math
import pathlib
import re
import urllib.request

SOURCE = 'https://www.dividenddata.co.uk/uk-gilts-prices-yields.py'
DMO = 'https://www.dmo.gov.uk/data/gilt-market/historical-prices-and-yields/'
PUBLISHED_CACHE = 'https://rs88pvyhzz-code.github.io/market-terminal/gilt_history_cache.json'

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.cell=None; self.block=[]
    def handle_starttag(self,tag,attrs):
        if tag=='tr': self.row=[]
        elif tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.row is not None and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell=None
        elif tag=='tr' and self.row is not None:
            if self.row:self.rows.append(self.row)
            self.row=None;self.cell=None

PRICE_RE=re.compile(r'^(?:£\s*)?(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)$')
MATURITY_RE=re.compile(r'^\d{1,2}-[A-Za-z]{3}-\d{4}$')

def as_number(s):
    if not isinstance(s,str):return None
    m=PRICE_RE.match(s.replace(',','').strip())
    if not m:return None
    x=float(m.group(1))
    return x if math.isfinite(x) else None

def parse_listing(raw, now=None):
    """Parse public table and *source-declared* update date; reject stale prices."""
    now=now or dt.datetime.now(dt.timezone.utc).date()
    text=raw.decode('utf-8-sig',errors='replace') if isinstance(raw,bytes) else raw
    plain=html.unescape(re.sub(r'<[^>]+>',' ',text))
    m=re.search(r'Last\s+updated\s*:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})',plain,re.I)
    stamp=None
    if m:
        try:stamp=dt.datetime.strptime(m.group(1),'%d %b %Y').date()
        except ValueError:
            try:stamp=dt.datetime.strptime(m.group(1),'%d %B %Y').date()
            except ValueError:pass
    parser=TableParser();parser.feed(text)
    out=[];seen=set()
    for cells in parser.rows:
        if len(cells)<7:continue
        symbol=cells[0].upper().strip()
        if not re.fullmatch(r'[A-Z][A-Z0-9]{1,6}',symbol) or symbol in seen:continue
        date_index=next((i for i,x in enumerate(cells) if MATURITY_RE.fullmatch(x.strip())),None)
        if date_index is None or date_index<2 or date_index+4>=len(cells):continue
        try:maturity=dt.datetime.strptime(cells[date_index].strip(),'%d-%b-%Y').date()
        except ValueError:continue
        if maturity<=now:continue
        coupon=as_number(cells[date_index-1].replace('%','').strip())
        # Expected: ticker, name, coupon, maturity, residual life, clean price,
        # running yield, redemption yield. Detect price after residual life.
        price=as_number(cells[date_index+2].strip())
        ytm=as_number(cells[date_index+4].replace('%','').strip())
        if coupon is None or not 0<=coupon<=20:continue
        if price is not None and not 5<=price<=230:price=None
        if ytm is not None and not -5<=ytm<=25:ytm=None
        name=cells[date_index-2].strip()
        if not re.search(r'(?:Treasury|Green|Stock|Gilt)',name,re.I):continue
        # Important: NEVER label undated/old numbers as a current quote.
        price_current=stamp is not None and -1 <= (now-stamp).days <= 7
        out.append({'ticker':symbol,'name':name[:96],'coupon':coupon,
            'maturity':maturity.isoformat(), 'price':price if price_current else None,
            'yieldSource':ytm if price_current else None,
            'asOf':stamp.isoformat() if stamp else None,'quoted':bool(price_current and price is not None),
            'source':SOURCE,'quoteType':'Indicative public clean price (not executable)'})
        seen.add(symbol)
    return sorted(out,key=lambda r:r['maturity'])

def read_published_cache(url=PUBLISHED_CACHE):
    """Read only our own *public* previous snapshot; cap size and check dates."""
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'PersonalMarketResearch/1.0'})
        with urllib.request.urlopen(req,timeout=10) as r:data=r.read(1_500_000)
        payload=json.loads(data)
        if not isinstance(payload,dict):return {}
        return {str(k):[[str(p[0]),float(p[1])] for p in v[-1500:]
                 if isinstance(p,list) and len(p)==2 and re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(p[0]))
                 and isinstance(p[1],(int,float)) and 0< float(p[1])<400]
                for k,v in payload.items() if isinstance(v,list) and re.fullmatch(r'[A-Z0-9]{2,7}',k)}
    except Exception:return {}

def collect(core,opts):
    errors=[];out=[];used_cache=0
    try:
        blob,cached,msg=core.get_bytes(SOURCE,'public_gilt_listing',opts.offline,opts.cache_hours)
        out=parse_listing(blob)
        used_cache=int(cached)
        if not out:errors.append('Public gilt listing: no validated conventional gilts parsed')
        if cached and 'stale' in msg:errors.append('Public gilt listing: stale cached response')
    except Exception as e:errors.append('Public gilt listing unavailable: '+str(e)[:130])
    if not out:
        # Small, date-verified set of *identifiable* conventional gilts.
        # These are NOT price quotations. The calculator works with a user-entered clean price.
        known=[
          ('TN28','0 1/8% Treasury Gilt 2028',0.125,'2028-01-31'),
          ('TR29','0 7/8% Treasury Gilt 2029',0.875,'2029-10-22'),
          ('T29K','4% Treasury Gilt 2029',4.0,'2029-05-22'),
          ('TG30','0 3/8% Treasury Gilt 2030',0.375,'2030-10-22'),
          ('T31H','4 1/8% Treasury Gilt 2031',4.125,'2031-03-07'),
          ('TG31','0 1/4% Treasury Gilt 2031',0.25,'2031-07-31')]
        out=[{'ticker':ticker,'name':name,'coupon':coupon,'maturity':maturity,
              'price':None,'yieldSource':None,'asOf':None,'quoted':False,
              'source':'https://www.dmo.gov.uk/data/gilt-market/gilts-in-issue/',
              'quoteType':'No verified quote; enter price for calculation'}
             for ticker,name,coupon,maturity in known]
        errors.append('No current gilt quotes retrieved; showing six verified bond descriptions without prices')
    prior=read_published_cache() if not opts.offline else {}
    local=pathlib.Path(core.ROOT)/'.terminal_gilt_history.json'
    if local.exists():
        try:
            saved=json.loads(local.read_text('utf-8'))
            for sym,points in saved.items():prior.setdefault(sym,points)
        except Exception:pass
    for bond in out:
        if bond['quoted']:
            pts=dict((d,float(v)) for d,v in prior.get(bond['ticker'],[])
                     if isinstance(d,str) and isinstance(v,(int,float)))
            pts[bond['asOf']]=bond['price']
            prior[bond['ticker']]=[[k,round(v,5)] for k,v in sorted(pts.items())][-900:]
    local.write_text(json.dumps(prior,separators=(',',':')),'utf-8')
    series=[{'ticker':b['ticker'],'date':day,'close':price}
            for b in out for day,price in prior.get(b['ticker'],[])][-8000:]
    return out,series,errors,used_cache

if __name__=='__main__':
    from pathlib import Path
    html_text=Path(__file__).parent.joinpath('sample_gilts.html').read_text() if Path(__file__).parent.joinpath('sample_gilts.html').exists() else ''
    print(len(parse_listing(html_text,dt.date(2026,11,6))))
