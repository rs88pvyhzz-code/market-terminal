"""DMO D10B purchase/sale gilt prices for the static market terminal.

Uses the user's official 6 Nov 2026 DMO spreadsheet as an initial dated snapshot.
Attempts the DMO's Excel export endpoint at scheduled builds; this automated
endpoint is *not* guaranteed accessible. Also retains the latest published
valid DMO data across ephemeral GitHub Actions builds. Never invents prices.

The Purchase (DMO buys / investor sells) and Sale (DMO sells / investor buys)
columns are DMO retail-service reference prices, NOT executable broker quotes.
For index-linked gilts, DMO 'clean' is REAL, while dirty includes indexation.
"""
import datetime as dt
from fractions import Fraction
import io
import json
import math
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

DMO_PAGE = 'https://www.dmo.gov.uk/data/pdfdatareport?reportCode=D10B'
EXPORT = 'https://www.dmo.gov.uk/umbraco/surface/DataExport/GetDataExport'
PUBLIC_LATEST = 'https://rs88pvyhzz-code.github.io/market-terminal/dmo_latest.json'
PUBLIC_HISTORY = 'https://rs88pvyhzz-code.github.io/market-terminal/gilt_history_cache.json'
ROOT = pathlib.Path(__file__).resolve().parent
SEED = ROOT / 'dmo_gilt_prices.xlsx'
LATEST = ROOT / '.terminal_dmo_latest.json'
HISTORY = ROOT / '.terminal_gilt_history.json'
XML = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
COUPON_FRACTIONS={'¼':.25,'½':.5,'¾':.75,'⅛':.125,'⅜':.375,'⅝':.625,'⅞':.875,'⅓':1/3,'⅔':2/3}
ALIASES={'GB00BMBL1G81':'TN28','GB00BJMHB534':'TR29','GB00BVP99566':'T29K'}


def fnum(v):
    try:
        if v is None or str(v).strip() == '': return None
        n=float(str(v).replace(',','').replace('£','').strip())
        return n if math.isfinite(n) else None
    except (ValueError,TypeError,OverflowError): return None


def coupon_from_name(name):
    part=name.split('%',1)[0].strip()
    if not part: return None
    for frac,val in COUPON_FRACTIONS.items():
        if frac in part:
            base=part.replace(frac,'').strip()
            return float(base)+val if base else val
    pieces=part.split()
    try:
        return float(pieces[0])+(float(Fraction(pieces[1])) if len(pieces)>1 else 0)
    except (ValueError,ZeroDivisionError,IndexError): return None


def _read_xlsx(raw):
    """Read DMO's small Crystal Reports XLSX using stdlib, no pip packages."""
    if len(raw)>4_000_000 or not raw.startswith(b'PK'):raise ValueError('DMO export is not a small XLSX file')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        if 'xl/worksheets/sheet1.xml' not in names:raise ValueError('DMO spreadsheet sheet1 is missing')
        def safe_read(file,limit):
            info=z.getinfo(file)
            if info.file_size>limit: raise ValueError('Oversize spreadsheet XML')
            return z.read(file)
        shared=[]
        if 'xl/sharedStrings.xml' in names:
            node=ET.fromstring(safe_read('xl/sharedStrings.xml',1_500_000))
            for si in node.findall(f'{XML}si'):
                shared.append(''.join(t.text or '' for t in si.iter(f'{XML}t')))
        doc=ET.fromstring(safe_read('xl/worksheets/sheet1.xml',3_000_000))
        table=[]
        for r in doc.findall(f'.//{XML}sheetData/{XML}row'):
            cells=[None]*10
            for cell in r.findall(f'{XML}c'):
                match=re.match(r'([A-Z]+)',cell.attrib.get('r',''))
                if not match:continue
                col=0
                for ch in match.group(1):col=col*26+(ord(ch)-64)
                col-=1
                if col>=len(cells):continue
                kind=cell.attrib.get('t')
                if kind=='inlineStr':
                    rawval=''.join(x.text or '' for x in cell.iter(f'{XML}t'))
                else:
                    v=cell.find(f'{XML}v')
                    rawval=v.text if v is not None else None
                    if kind=='s' and rawval is not None:rawval=shared[int(rawval)]
                cells[col]=rawval
            table.append(cells)
        return table


def parse_dmo_xlsx(raw):
    """Parse only an authenticated D10B-shaped Excel export; return [rows],date."""
    table=_read_xlsx(raw)
    if not table or len(table)<15:raise ValueError('DMO report has too few rows')
    top=table[0]
    if 'PURCHASE AND SALE SERVICE PRICES' not in ' '.join(str(x or '') for x in top).upper():
        raise ValueError('Not the DMO purchase and sale prices report')
    date_s=next((re.search(r'(\d{2}-[A-Za-z]{3}-\d{4})',str(x)).group(1)
                 for x in top if x is not None and re.search(r'(\d{2}-[A-Za-z]{3}-\d{4})',str(x))),None)
    if date_s:
        date=dt.datetime.strptime(date_s,'%d-%b-%Y').date()
    else:
        raise ValueError('Source report has no verified data date')
    header=next((i for i,r in enumerate(table[:10]) if r[0]=='ISIN Code' and 'Gilt Name'==r[1]),None)
    if header is None:raise ValueError('Expected DMO ISIN and price headers missing')
    expected=('Purchase','Sale','Clean Price','Dirty Price')
    h=' '.join(str(x or '') for x in table[header][2:6])
    if any(x.lower() not in h.lower() for x in expected):raise ValueError('DMO price columns changed')
    out=[];seen=set()
    for row in table[header+1:]:
        isin=str(row[0] or '').strip().upper()
        if not re.fullmatch(r'GB[0-9A-Z]{10}',isin) or isin in seen:continue
        name=str(row[1] or '').strip()
        vals=[fnum(row[i]) for i in [2,3,4,5]]
        if not name or any(x is None or x<=0 or x>2000 for x in vals):continue
        # A correctly labelled DMO bid cannot be above its offer (allow rounding noise).
        if vals[0]>vals[2]+0.011 or vals[1]>vals[3]+0.011:continue
        rawdate=fnum(row[7])
        if rawdate is None:continue
        maturity=dt.date(1899,12,30)+dt.timedelta(days=round(rawdate))
        if maturity<date:continue
        coupon=coupon_from_name(name)
        if coupon is None or coupon<0 or coupon>20:continue
        index_linked='index-linked' in name.lower()
        ratio=fnum(row[6]); lag=str(row[9] or '').strip() or None
        if index_linked and ratio is not None and not(.2<=ratio<=15):continue
        buy,dirty_buy,sell,dirty_sell=map(lambda x:round(x,6),vals)
        out.append({'ticker':isin,'isin':isin,'shortTicker':ALIASES.get(isin,''),'name':name,
           'maturity':maturity.isoformat(),'coupon':round(coupon,6),
           'bidClean':buy,'bidDirty':dirty_buy,'askClean':sell,'askDirty':dirty_sell,
           'price':sell,'yieldSource':None,'asOf':date.isoformat(),'quoted':True,
           'indexLinked':index_linked,'indexRatio':ratio,'indexationLag':lag,
           'source':DMO_PAGE,'quoteType':'DMO retail purchase/sale service; dated historical indicative prices, not executable'} )
        seen.add(isin)
    if len(out)<30:raise ValueError('Only '+str(len(out))+' gilt rows; expected a full report')
    return sorted(out,key=lambda x:(x['maturity'],x['name'])), date


def _get_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'PersonalMarketResearch/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=9) as resp:
        raw=resp.read(1_900_000)
    return json.loads(raw)


def _accept_snapshot(obj):
    if not isinstance(obj,dict):return None
    date=obj.get('asOf'); rows=obj.get('bonds')
    if not isinstance(date,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):return None
    if not isinstance(rows,list) or not 30<=len(rows)<=150:return None
    if sum(bool(x.get('quoted') and x.get('asOf')==date and x.get('bidClean') and x.get('askClean')) for x in rows if isinstance(x,dict))<30:return None
    return obj


def _download_dmo_for(trade_date):
    # Direct Excel-export URL pattern documented by users of the DMO reporting tool.
    # D10B parameter names have not been confirmed; each response is parsed and
    # its embedded report date verified, so an error page can NEVER become prices.
    date=trade_date.strftime('%d/%m/%Y')
    for param in ('TradeDate','COBDate'):
        qs=urllib.parse.urlencode({'reportCode':'D10B','exportFormatValue':'xls',
                                   'parameters':'&'+param+'='+date})
        url=EXPORT+'?'+qs
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; PersonalMarketResearch/1.0)',
                                                    'Accept':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,*/*'})
            with urllib.request.urlopen(req,timeout=12) as response:
                blob=response.read(3_000_000)
            rows,report_date=parse_dmo_xlsx(blob)
            if report_date==trade_date:return {'asOf':report_date.isoformat(),'bonds':rows}
        except (OSError,urllib.error.URLError,ValueError,zipfile.BadZipFile,ET.ParseError,KeyError) as exc:
            pass
    return None


def _recent_business_days(today, count=2):
    result=[];cur=today
    while len(result)<count:
        if cur.weekday()<5:result.append(cur)
        cur-=dt.timedelta(days=1)
    return result


def collect(core,opts):
    warnings=[];candidates=[];downloaded=False
    if SEED.exists():
        try:
            seed_rows,day=parse_dmo_xlsx(SEED.read_bytes())
            candidates.append({'asOf':day.isoformat(),'bonds':seed_rows})
        except Exception as e:warnings.append('DMO spreadsheet could not be parsed: '+str(e)[:150])
    if LATEST.exists():
        try:
            p=_accept_snapshot(json.loads(LATEST.read_text('utf-8')))
            if p:candidates.append(p)
        except (ValueError,OSError):pass
    if not opts.offline:
        try:
            old=_accept_snapshot(_get_json(PUBLIC_LATEST))
            if old:candidates.append(old)
        except Exception:pass
        today=dt.datetime.now(dt.timezone.utc).date()
        for day in _recent_business_days(today):
            if candidates and max(x['asOf'] for x in candidates)>=day.isoformat():break
            new=_download_dmo_for(day)
            if new:
                candidates.append(new);downloaded=True;break
    if not candidates:
        warnings.append('No verified DMO Excel prices available; prices remain blank')
        return [],[],warnings,0
    latest=max(candidates,key=lambda p:p['asOf'])
    rows=[dict(g) for g in latest['bonds']]
    if not downloaded and not opts.offline:
        warnings.append('DMO automatic Excel export not verified; displaying latest dated DMO snapshot '+latest['asOf'])
    LATEST.write_text(json.dumps(latest,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
    prior={}
    if not opts.offline:
        try:
            obj=_get_json(PUBLIC_HISTORY)
            if isinstance(obj,dict):prior={k:v for k,v in obj.items() if isinstance(v,list) and re.fullmatch(r'GB[0-9A-Z]{10}',k)}
        except Exception:pass
    if HISTORY.exists():
        try:
            obj=json.loads(HISTORY.read_text('utf-8'))
            if isinstance(obj,dict):
                for k,v in obj.items():
                    if isinstance(v,list) and re.fullmatch(r'GB[0-9A-Z]{10}',k):
                        old={str(x[0]):float(x[1]) for x in prior.get(k,[]) if isinstance(x,list) and len(x)==2}
                        for item in v:
                            if isinstance(item,list) and len(item)==2:old[str(item[0])]=float(item[1])
                        prior[k]=[[day,price] for day,price in sorted(old.items())][-1500:]
        except Exception:pass
    for b in rows:
        if b['quoted']:
            key=b['isin']
            pts={str(x[0]):float(x[1]) for x in prior.get(key,[]) if isinstance(x,list) and len(x)==2}
            pts[b['asOf']]=float(b['askClean'])
            prior[key]=[[day,price] for day,price in sorted(pts.items())][-1500:]
    HISTORY.write_text(json.dumps(prior,separators=(',',':')),encoding='utf-8')
    history=[{'ticker':g['ticker'],'date':d,'close':v}
             for g in rows for d,v in prior.get(g['ticker'],[])][-15000:]
    return rows,history,warnings,int(downloaded)

if __name__=='__main__':
    import sys
    rows,date=parse_dmo_xlsx(pathlib.Path(sys.argv[1] if len(sys.argv)>1 else SEED).read_bytes())
    print('Verified',len(rows),'DMO gilts for',date,'; index linked',sum(r['indexLinked'] for r in rows))
    example=next(r for r in rows if r['isin']=='GB00BMBL1G81')
    print('TN28 DMO bid clean',example['bidClean'],'offer clean',example['askClean'])
