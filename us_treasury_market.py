"""Official U.S. Treasury FedInvest end-of-day security quotations.

Fetches FiscalData FedInvest FIP rates/prices first; fallback to TreasuryDirect's
public 'Today's Prices' table, then a prior independently dated site snapshot.
Quoted prices are *not* live/executable broker bids/asks. No synthetic prices.
"""
from html.parser import HTMLParser
from pathlib import Path
import datetime as dt
import json
import math
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
LATEST = ROOT / '.terminal_us_treasury_latest.json'
HISTORY = ROOT / '.terminal_us_treasury_history.json'
import os as _os
# Published-site cache location follows whichever repository runs the build.
_REPO=_os.environ.get('GITHUB_REPOSITORY','rs88pvyhzz-code/market-terminal').split('/',1)
_PAGES=f'https://{_REPO[0]}.github.io/{_REPO[1]}/'
PUBLIC_LATEST = _PAGES+'us_treasury_latest.json'
PUBLIC_HISTORY = _PAGES+'us_treasury_history_cache.json'
BASE = 'https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/fip_rates_prices'
BACKUP_API = 'https://api.transparency.treasury.gov/services/api/fiscal_service/v1/accounting/od/fip_rates_prices'
TODAY_PAGE = 'https://www.treasurydirect.gov/GA-FI/FedInvest/todaySecurityPriceDetail'
FIELDS = 'data_date,cusip,security_type,rate_amt,maturity_dt,buy_amt,sell_amt,end_of_day_amt'


def finite(v):
    try:
        if v in (None,'','N/A','NULL'): return None
        x=float(str(v).replace(',','').replace('%','').strip())
        return x if math.isfinite(x) else None
    except (TypeError,ValueError,OverflowError): return None


def kind(s):
    s=str(s or '').upper()
    if 'TIPS' in s or 'INFLATION' in s: return 'TIPS'
    if 'FRN' in s or 'FLOAT' in s: return 'FRN'
    if 'BILL' in s: return 'Bill'
    if 'NOTE' in s: return 'Note'
    if 'BOND' in s: return 'Bond'
    return None


def price(v):
    v=finite(v)
    return round(v,6) if v is not None and 25<v<200 else None


def parse_date(value):
    if not value: return None
    s=str(value).strip()
    for fmt in ('%Y-%m-%d','%m/%d/%Y','%b %d, %Y','%B %d, %Y'):
        try: return dt.datetime.strptime(s,fmt).date()
        except ValueError: pass
    return None


def normalize(raw,when):
    cusip=str(raw.get('cusip') or raw.get('CUSIP') or '').strip().upper()
    if not re.fullmatch(r'[0-9A-Z]{9}',cusip):return None
    category=kind(raw.get('security_type') or raw.get('SECURITY TYPE'))
    if category is None:return None
    maturity=parse_date(raw.get('maturity_dt') or raw.get('MATURITY DATE'))
    if not maturity or maturity<=when:return None
    coupon=finite(raw.get('rate_amt') if 'rate_amt' in raw else raw.get('RATE'))
    if coupon is None or not 0<=coupon<=20: return None
    b=price(raw.get('sell_amt') if 'sell_amt' in raw else raw.get('SELL'))
    a=price(raw.get('buy_amt') if 'buy_amt' in raw else raw.get('BUY'))
    e=price(raw.get('end_of_day_amt') if 'end_of_day_amt' in raw else raw.get('END OF DAY'))
    if b is not None and a is not None and b > a+0.125: return None
    # FedInvest BUY = investor pays (offer); SELL = investor receives (bid).
    return {'ticker':cusip,'cusip':cusip,'name':f'US Treasury {category} {coupon:g}% {maturity:%d %b %Y}',
            'type':category,'maturity':maturity.isoformat(),'coupon':round(coupon,5),
            'bid':b,'ask':a,'endOfDay':e,'price':e if e is not None else ((a+b)/2 if a is not None and b is not None else a if a is not None else b),
            'asOf':when.isoformat(),'quoted':any(v is not None for v in (a,b,e)),
            'indexLinked':category=='TIPS','floating':category=='FRN',
            'source':BASE,'quoteType':'FedInvest dated US Treasury reference quote; not executable'}


def accept_rows(rows,today=None,at_least=50):
    today=today or dt.datetime.now(dt.timezone.utc).date()
    candidates={}
    for item in rows:
        if not isinstance(item,dict):continue
        day=parse_date(item.get('data_date') or item.get('DATE') or item.get('asOf'))
        if day is None or day>today+dt.timedelta(days=1) or (today-day).days>21:continue
        rec=normalize(item,day)
        if rec and rec['quoted']:
            candidates.setdefault(day,{})[rec['cusip']]=rec
    if not candidates: raise ValueError('No recent valid Treasury security quotations')
    dates=sorted(candidates,reverse=True)
    for day in dates:
        subset=list(candidates[day].values())
        if len(subset)>=at_least:
            subset.sort(key=lambda r:(r['type'],r['maturity'],r['cusip']))
            return subset,day
    raise ValueError('No sufficiently complete dated Treasury quotation set')


class Parser(HTMLParser):
    def __init__(self): super().__init__();self.rows=[];self.row=None;self.cell=None;self.in_cell=False
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        elif tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_data(self,s):
        if self.cell is not None:self.cell.append(s)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.row is not None and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        elif tag=='tr' and self.row is not None:
            if self.row:self.rows.append(self.row)
            self.row=None


def parse_html(content,asof=None):
    txt=content.decode('utf-8','replace') if isinstance(content,bytes) else content
    m=re.search(r'Prices\s+For\s*:\s*([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})',re.sub(r'<[^>]*>',' ',txt),re.I)
    day=parse_date(m.group(1)) if m else None
    if not day: raise ValueError('Today prices HTML has no published quote date')
    tab=Parser();tab.feed(txt)
    headers=['CUSIP','SECURITY TYPE','RATE','MATURITY DATE','CALL DATE','BUY','SELL','END OF DAY']
    out=[]
    for row in tab.rows:
        if len(row)>=8 and re.fullmatch(r'[0-9A-Z]{9}',row[0].strip(),re.I):
            r=dict(zip(headers,row[:8]));r['DATE']=day.isoformat();out.append(r)
    return accept_rows(out,asof)


def parse_json(blob,asof=None):
    obj=json.loads(blob)
    rows=obj.get('data') if isinstance(obj,dict) else obj
    if not isinstance(rows,list):raise ValueError('Unexpected FiscalData response shape')
    return accept_rows(rows,asof)


def public_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'PersonalMarketResearch/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as r:raw=r.read(10_000_000)
    return json.loads(raw)


# The original site keeps its saved snapshot; a new repository falls back to it
# until it has published its own.
LEGACY_PAGES='https://rs88pvyhzz-code.github.io/market-terminal/'

def prior_file(path,url):
    if path.exists():
        try:return json.loads(path.read_text('utf-8'))
        except (OSError,ValueError):pass
    for candidate in (url,url.replace(_PAGES,LEGACY_PAGES)):
        try:return public_json(candidate)
        except Exception:continue
    return None


def collect(core,opts):
    warnings=[];used_cache=0;today=dt.datetime.now(dt.timezone.utc).date();result=None
    if not opts.offline:
        for i,base in enumerate((BASE,BACKUP_API)):
            query=urllib.parse.urlencode({'sort':'-data_date','page[size]':'1500','fields':FIELDS})
            url=base+'?'+query
            try:
                raw,cached,msg=core.get_bytes(url,'us_fedinvest_api_'+str(i),False,opts.cache_hours)
                result=parse_json(raw,today);used_cache+=int(cached);break
            except Exception as e:warnings.append('US Treasury FiscalData '+str(i+1)+': '+str(e)[:105])
        if result is None:
            try:
                raw,cached,msg=core.get_bytes(TODAY_PAGE,'us_fedinvest_today_html',False,opts.cache_hours)
                result=parse_html(raw,today);used_cache+=int(cached)
                for r in result[0]:r['source']=TODAY_PAGE
            except Exception as e:warnings.append('US Treasury current-price HTML: '+str(e)[:120])
    # Previous published quotations retain their original date; NEVER re-label as current.
    if result is None:
        saved=prior_file(LATEST,PUBLIC_LATEST)
        try:
            if saved and isinstance(saved,dict) and isinstance(saved.get('bonds'),list):
                result=accept_rows([dict(r,data_date=r['asOf'],cusip=r.get('cusip'),security_type=r.get('type'),
                              rate_amt=r.get('coupon'),maturity_dt=r.get('maturity'),
                              buy_amt=r.get('ask'),sell_amt=r.get('bid'),end_of_day_amt=r.get('endOfDay'))
                            for r in saved['bonds']],today)
                warnings.append('US Treasury: showing LAST SAVED, NOT CURRENT FedInvest quotes')
        except Exception:pass
    if result is None:
        warnings.append('US Treasury security prices unavailable; official benchmark yield charts remain available')
        return [],[],warnings,used_cache
    bonds,day=result
    LATEST.write_text(json.dumps({'asOf':day.isoformat(),'bonds':bonds},separators=(',',':')),'utf-8')
    saved=prior_file(HISTORY,PUBLIC_HISTORY)
    prev=saved if isinstance(saved,dict) else {}
    history={}
    for bond in bonds:
        cusip=bond['cusip'];old=prev.get(cusip,[])
        if not isinstance(old,list):old=[]
        pts={str(r[0]):round(float(r[1]),6) for r in old[-600:]
             if isinstance(r,list) and len(r)==2 and isinstance(r[0],str) and
                re.fullmatch(r'\d{4}-\d{2}-\d{2}',r[0]) and
                isinstance(r[1],(int,float)) and 25<float(r[1])<200}
        v=bond['price']
        if v and 25<v<200:pts[day.isoformat()]=round(v,6)
        if pts:history[cusip]=[[d,p] for d,p in sorted(pts.items())][-500:]
    # retain histories of matured or temporarily unlisted bonds
    for cusip,points in prev.items():
        if re.fullmatch(r'[0-9A-Z]{9}',cusip) and cusip not in history and isinstance(points,list):history[cusip]=points[-500:]
    HISTORY.write_text(json.dumps(history,separators=(',',':')),'utf-8')
    # Small inline first observation; full price-history cache published separately.
    inline=[{'cusip':b['cusip'],'date':day.isoformat(),'close':round(b['price'],6)}
            for b in bonds if b['price'] is not None]
    return bonds,inline,warnings,used_cache
