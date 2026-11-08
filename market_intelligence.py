"""Optional news, release calendar, real US rates and European sovereign yields.

All sources are independently optional. This is a personal static snapshot; no article
is represented as live after generation. Data issues are reported and not fabricated.
"""
import datetime as dt
import email.utils
import json
import random
import re
import os
import pathlib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

FRED_REAL = {
    'DFII5': 'usReal5',
    'DFII10': 'usReal10',
    'T5YIE': 'usBreakeven5',
    'T10YIE': 'usBreakeven10',
}
EU_SOVEREIGNS = {'DE':'Germany', 'FR':'France', 'IT':'Italy', 'ES':'Spain'}
NEWS_QUERIES = {
    'GLOBAL': 'global financial markets stocks bonds central banks when:3d',
    'UK': 'UK FTSE gilts Bank of England inflation companies when:3d',
    'EUROPE': 'ECB euro zone European markets bonds stocks when:3d',
    'RATES': 'bond yields US treasury UK gilts ECB Fed rates when:3d',
    'COMPANIES': 'Shell BP AstraZeneca HSBC corporate earnings stocks when:3d',
}

def _parse_rss_date(s):
    try:
        d=email.utils.parsedate_to_datetime((s or '').strip())
        if d.tzinfo is None:d=d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except (ValueError, TypeError, IndexError):return None

def rss_articles(blob, category, generated=None, default_source="Google News", max_age_days=4):
    generated=generated or dt.datetime.now(dt.timezone.utc)
    root=ET.fromstring(blob)
    results=[]
    for item in root.findall('.//item'):
        title=(item.findtext('title') or '').strip()
        link=(item.findtext('link') or '').strip()
        when=_parse_rss_date(item.findtext('pubDate'))
        if not title or not link.startswith('https://') or not when:continue
        # Prevent outdated material and future-dated RSS corruption.
        age=(generated-when).total_seconds()
        if age < -300 or age>max_age_days*86400:continue
        source_node=item.find('source')
        source=source_node.text if source_node is not None and source_node.text else default_source
        results.append({'title':title[:220],'url':link,'source':source[:80],
                        'category':category,'published':when.strftime('%Y-%m-%d %H:%M UTC')})
    return results

# Reliable public feeds are attempted after news-search feed errors. These are
# editorial feeds rather than synthetic or algorithmically inferred headlines.
NEWS_FALLBACK_FEEDS = {
    'GLOBAL': [('BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml'),
               ('CNBC', 'https://www.cnbc.com/id/10001147/device/rss/rss.html')],
    'UK': [('BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml')],
    'EUROPE': [('BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml')],
    'RATES': [('CNBC', 'https://www.cnbc.com/id/10000664/device/rss/rss.html')],
    'COMPANIES': [('BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml')],
}


def bing_news_url(query):
    """Independent searchable RSS fallback. Availability is not guaranteed."""
    return 'https://www.bing.com/news/search?' + urllib.parse.urlencode(
        {'q':query.replace(' when:3d','').replace(' when:4d',''), 'format':'rss', 'setlang':'en-GB'})


def fetch_rss_once(url, timeout=7):
    """Bounded one-shot alternative RSS request; no long retry storms.

    Uses distinct host(s) from the failing Google feed. Some environments
    may block all of them; a failed feed must not block publishing.
    """
    req=urllib.request.Request(url, headers={
        'User-Agent':'Mozilla/5.0 (compatible; MarketTerminal/1.0)',
        'Accept':'application/rss+xml,application/xml,text/xml,*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        raw=response.read(750_001)
    if len(raw)>750_000:raise ValueError('RSS response exceeds safety bound')
    if len(raw)<10:raise ValueError('Empty RSS response')
    return raw


def _published_news_archive():
    """Recover dated headlines from the *last published* site after a feed outage.

    Never report these as fresh. Ignore out-of-window, future, invalid URL or
    synthetic entries. No account credentials or private data are involved.
    """
    repo=os.environ.get('GITHUB_REPOSITORY', 'rs88pvyhzz-code/market-terminal')
    if '/' not in repo:return []
    owner,project=repo.split('/',1)
    url=f'https://{owner}.github.io/{project}/news_cache.json'
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'MarketTerminal/1.0'})
        with urllib.request.urlopen(req,timeout=8) as response:raw=response.read(400_001)
        if len(raw)>400_000:raise ValueError('News archive too large')
        obj=json.loads(raw.decode('utf-8'))
        if not isinstance(obj,dict):return []
        now=dt.datetime.now(dt.timezone.utc)
        keep=[]
        for item in obj.get('articles',[]):
            if not isinstance(item,dict) or item.get('category') not in NEWS_QUERIES:continue
            if not str(item.get('url','')).startswith('https://') or not item.get('title'):continue
            try:when=dt.datetime.strptime(item['published'],'%Y-%m-%d %H:%M UTC').replace(tzinfo=dt.timezone.utc)
            except (KeyError,ValueError,TypeError):continue
            if -300 <= (now-when).total_seconds() <= 7*86400:
                keep.append({k:item[k] for k in ('title','url','source','category','published') if k in item})
        return keep[:100]
    except Exception:
        return []


def _editorial_topic_matches(category, article):
    """Avoid labelling a general business headline as UK/EU/rates news."""
    if category=='GLOBAL':return True
    text=(article.get('title') or '').lower()
    words={
      'UK':r'\b(uk|britain|british|england|scotland|london|ftse|gilts?|sterling|bank of england|pound)\b',
      'EUROPE':r'\b(europe|eurozone|euro area|eu|ecb|germany|france|italy|spain|dax|euro)\b',
      'RATES':r'\b(bonds?|yields?|treasur(?:y|ies)|interest rates?|central banks?|fed(?:eral reserve)?|ecb|gilts?)\b',
      'COMPANIES':r'\b(shares?|stocks?|corporat(?:e|ion)|companies|profits?|earnings|results|dividends|revenue|merger|takeover)\b',
    }
    return bool(re.search(words.get(category,r'$^'),text))


def collect_news(core,opts):
    reports=[];warnings=[];seen=set();cached=0
    def add(items, archived=False):
        for item in items:
            signature=(item['category'],re.sub(r'[^a-z\d]+','',item['title'].casefold())[:100])
            if signature in seen:continue
            seen.add(signature)
            if archived:item={**item,'restored':True}
            reports.append(item)
    for category,query in NEWS_QUERIES.items():
        url='https://news.google.com/rss/search?'+urllib.parse.urlencode(
            {'q':query,'hl':'en-GB','gl':'GB','ceid':'GB:en'})
        try:
            raw,used,msg=core.get_bytes(url,'news_'+category.lower(),opts.offline,opts.cache_hours)
            cached+=int(used)
            if 'stale cache' in msg:warnings.append('News '+category+': stale cached articles')
            add(rss_articles(raw,category))
        except Exception as exc:
            warnings.append('News '+category+': '+str(exc)[:120])
        # The Google News RSS feed has returned HTTP 503 in GitHub Actions.
        # Bing's RSS search is independently hosted, followed by editorial feeds.
        if any(r['category']==category for r in reports):continue
        if getattr(opts,'offline',False):continue
        try:
            raw=fetch_rss_once(bing_news_url(query))
            add(rss_articles(raw,category,default_source='Bing News'))
        except Exception as exc:
            warnings.append('News '+category+' Bing fallback: '+str(exc)[:90])
        if any(r['category']==category for r in reports):continue
        for name,feed in NEWS_FALLBACK_FEEDS[category]:
            try:
                raw=fetch_rss_once(feed)
                add([x for x in rss_articles(raw,category,default_source=name) if _editorial_topic_matches(category,x)])
            except Exception as exc:
                warnings.append('News '+category+' '+name+' fallback: '+str(exc)[:90])
            if any(r['category']==category for r in reports):break
    # Do not repeatedly publish an empty dashboard when feeds are temporarily down.
    # A prior headline stays eligible for no more than seven days after publication.
    missing=set(NEWS_QUERIES)-{r['category'] for r in reports}
    if missing and not getattr(opts,'offline',False):
        earlier=_published_news_archive()
        old=[x for x in earlier if x['category'] in missing]
        if old:
            add(old,archived=True)
            warnings.append('News: some feeds unavailable; recovered dated articles from the previous published snapshot (up to seven days old)')
    reports.sort(key=lambda a:a['published'],reverse=True)
    articles=reports[:80]
    # Created during the build; the existing GitHub Pages publish step already
    # uploads every file in public/, without requiring a workflow change.
    if not getattr(opts,'offline',False):
        try:
            file=pathlib.Path(__file__).resolve().parent/'public'/'news_cache.json'
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(json.dumps({'retrievedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
                                        'articles':articles},ensure_ascii=False),encoding='utf-8')
        except OSError as exc:
            warnings.append('News cache could not be saved: '+str(exc)[:100])
    return articles,warnings,cached

def _extract_release_date(item):
    # The ONS RSS feeds vary in structure. Only return dates explicitly supplied
    # in the item and parseable as calendar dates. Never infer a next release.
    candidates=[]
    for child in item.iter():
        if child.tag.lower().split('}')[-1] in ('releasedate','date','description','summary'):
            if child.text:candidates.append(child.text)
    import html
    text=html.unescape(' '.join(re.sub(r'<[^>]*>',' ',s) for s in candidates))
    patterns=[r'(?:Release date|Scheduled for|Release on|Published on)\s*:?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
              r'(?:Release date|Scheduled for|Release on)\s*:?\s*(\d{4}-\d{2}-\d{2})']
    for pattern in patterns:
        match=re.search(pattern,text,re.I)
        if not match:continue
        for fmt in ('%d %B %Y','%d %b %Y','%Y-%m-%d'):
            try:return dt.datetime.strptime(match.group(1),fmt).date().isoformat()
            except ValueError:pass
    return None

def parse_ons_upcoming(raw,today=None):
    today=today or dt.date.today()
    out=[]
    root=ET.fromstring(raw)
    for item in root.findall('.//item'):
        title=(item.findtext('title') or '').strip()
        link=(item.findtext('link') or '').strip()
        date=_extract_release_date(item)
        if not title or not link.startswith('https://') or not date:continue
        day=dt.date.fromisoformat(date)
        if day<today or (day-today).days>120:continue
        if not re.search(r'inflat|consumer price|employment|unemployment|gross domestic|GDP|retail sales|public sector financ|earnings|labour market|business investment|productivity|trade|production',title,re.I):continue
        out.append({'date':date,'region':'UK','title':title[:180],'url':link,'source':'ONS','time':'See official release'})
    return sorted(out,key=lambda x:x['date'])

def parse_bls_ics(raw,today=None):
    """Extract dated US macro events from BLS's official iCalendar feed."""
    import html
    today=today or dt.date.today()
    lines=[]
    text=raw.decode('utf-8-sig',errors='replace') if isinstance(raw,bytes) else raw
    for line in text.replace('\r\n','\n').split('\n'):
        if line.startswith((' ','\t')) and lines:lines[-1]+=line[1:]
        else:lines.append(line)
    events=[];event=None
    for line in lines:
        if line=='BEGIN:VEVENT':event={};continue
        if line=='END:VEVENT':
            if event:
                title=html.unescape(event.get('SUMMARY','')).replace('\\n',' ').strip()
                rawdate=event.get('DTSTART','')
                match=re.match(r'(\d{4})(\d\d)(\d\d)',rawdate)
                if match and re.search(r'Consumer Price Index|Employment Situation|Producer Price Index|Job Openings|Productivity and Costs|Employment Cost Index',title,re.I):
                    date=f'{match[1]}-{match[2]}-{match[3]}'
                    try:day=dt.date.fromisoformat(date)
                    except ValueError:day=today-dt.timedelta(days=1)
                    if today<=day<=today+dt.timedelta(days=120):
                        events.append({'date':date,'region':'US','title':title[:180],
                            'url':'https://www.bls.gov/schedule/',
                            'source':'BLS official calendar',
                            'time':rawdate[9:11]+':'+rawdate[11:13]+' ET' if len(rawdate)>=13 else 'Time on BLS website'})
            event=None;continue
        if event is None or ':' not in line:continue
        key,value=line.split(':',1)
        event[key.split(';')[0]]=value
    return sorted(events,key=lambda x:x['date'])


def parse_ecb_meetings(raw,today=None):
    """Extract dated ECB monetary-policy council meetings from official calendar text."""
    import html
    today=today or dt.date.today()
    plain=html.unescape(re.sub(r'<[^>]+>',' ',raw.decode('utf-8-sig',errors='replace') if isinstance(raw,bytes) else raw))
    plain=re.sub(r'\s+',' ',plain)
    results=[]
    # Limit each capture to the next explicit calendar date to avoid conflating
    # a non-policy meeting with a later monetary-policy meeting.
    pattern=r'(\d{2}/\d{2}/\d{4})\s+(.{0,180}?)(?=\d{2}/\d{2}/\d{4}|$)'
    for day,description in re.findall(pattern,plain):
        if 'non-monetary' in description.casefold() or not re.search(r'Governing Council.*monetary policy meeting',description,re.I):continue
        try:date=dt.datetime.strptime(day,'%d/%m/%Y').date()
        except ValueError:continue
        if not today<=date<=today+dt.timedelta(days=120):continue
        results.append({'date':date.isoformat(),'region':'EU',
            'title':'ECB '+('monetary policy decision and press conference' if 'press conference' in description.lower() else 'monetary policy meeting'),
            'url':'https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html',
            'source':'ECB meeting calendar','time':'Check ECB schedule'})
    return results


def parse_ons_api_releases(raw,today=None):
    """ONS's official upcoming-releases search API, not the published-only RSS feed.

    Source: https://developer.ons.gov.uk/search/search-releases/
    Only confirmed dates explicitly supplied by the ONS are included.
    """
    from zoneinfo import ZoneInfo
    today=today or dt.date.today()
    content=json.loads(raw)
    if not isinstance(content,dict) or not isinstance(content.get('releases'),list):
        raise ValueError('Unexpected ONS release API response')
    whitelist=re.compile(r'GDP|gross domestic|consumer price|inflation|retail sales|\bemployment\b|'
                         r'unemployment|labour market|average weekly earnings|public sector finances|'
                         r'UK trade|balance of payments|index of (production|services)|'
                         r'business investment|productivity|construction output',re.I)
    events=[];seen=set()
    for row in content['releases']:
        if not isinstance(row,dict):continue
        desc=row.get('description') or {}
        title=(desc.get('title') or row.get('title') or '').strip()
        if not title or not whitelist.search(title) or desc.get('cancelled') or desc.get('postponed'):continue
        if not desc.get('finalised',row.get('finalised',False)):continue
        stamp=desc.get('release_date') or row.get('release_date')
        if not stamp:continue
        try:
            when=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if when.tzinfo is None:when=when.replace(tzinfo=dt.timezone.utc)
            london=when.astimezone(ZoneInfo('Europe/London'))
        except (ValueError,TypeError):continue
        day=london.date()
        if not today<=day<=today+dt.timedelta(days=120):continue
        # Do not present a separate time-series release as another headline when
        # the substantive release is also published on the same day.
        if re.search(r'time series$',title,re.I):continue
        slug=(row.get('uri') or '').strip()
        url='https://www.ons.gov.uk'+slug if slug.startswith('/') else 'https://www.ons.gov.uk/releasecalendar'
        key=(day.isoformat(),title.casefold())
        if key in seen:continue
        seen.add(key)
        events.append({'date':day.isoformat(),'region':'UK','title':title[:180],
            'url':url,'source':'ONS official calendar','time':london.strftime('%H:%M')+' UK'})
    return sorted(events,key=lambda a:(a['date'],a['title']))


# Confirmed Bank of England MPC announcement dates, sourced from the BoE's
# published 2026 and 2027 calendar. Replace when the Bank revises its schedule.
# https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates
CONFIRMED_BOE_MPC_DATES=(
    '2026-12-17','2027-02-04','2027-03-18','2027-04-29',
    '2027-06-17','2027-07-29','2027-09-16','2027-11-04','2027-12-16')

def boe_mpc_upcoming(today=None):
    today=today or dt.date.today()
    return [{'date':iso,'region':'UK','title':'Bank of England MPC rate decision and minutes',
             'url':'https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates',
             'source':'Bank of England (confirmed schedule)','time':'12:00 UK'}
            for iso in CONFIRMED_BOE_MPC_DATES
            if today<=dt.date.fromisoformat(iso)<=today+dt.timedelta(days=120)]

def collect_calendar(core,opts):
    """Official ONS search API plus independent US and ECB calendars."""
    out=boe_mpc_upcoming();warnings=[];n_cached=0
    from_date=dt.date.today()
    params=urllib.parse.urlencode({
      'release-type':'type-upcoming','sort':'release_date_asc',
      'fromDate':from_date.isoformat(),
      'toDate':(from_date+dt.timedelta(days=120)).isoformat(),
      'limit':500, 'offset':0})
    api='https://api.beta.ons.gov.uk/v1/search/releases?'+params
    try:
        raw,c,msg=core.get_bytes(api,'ons_upcoming_api_v2',opts.offline,opts.cache_hours)
        rows=parse_ons_api_releases(raw)
        if not rows:raise ValueError('ONS returned no confirmed significant economic releases')
        out.extend(rows);n_cached+=int(c)
        if 'stale cache' in msg:warnings.append('ONS calendar: stale API cache')
    except Exception as e:
        warnings.append('ONS API unavailable: '+str(e)[:125])
        try:
            url='https://www.ons.gov.uk/releasecalendar?rss&release-type=type-upcoming&sort=date-newest&limit=100'
            raw,c,msg=core.get_bytes(url,'official_calendar_ons',opts.offline,opts.cache_hours)
            rows=parse_ons_upcoming(raw)
            out.extend(rows);n_cached+=int(c)
            if not rows:warnings.append('ONS RSS fallback also returned no confirmed upcoming releases')
        except Exception as e2:warnings.append('ONS RSS fallback: '+str(e2)[:125])
    feeds=[
      ('BLS','https://www.bls.gov/schedule/news_release/bls.ics',parse_bls_ics),
      ('ECB','https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html',parse_ecb_meetings),
    ]
    for name,url,parser in feeds:
        try:
            raw,c,msg=core.get_bytes(url,'official_calendar_'+name.lower(),opts.offline,opts.cache_hours)
            rows=parser(raw)
            out.extend(rows);n_cached+=int(c)
            if not rows:warnings.append(name+' calendar: no future dated releases verified')
            if 'stale cache' in msg:warnings.append(name+' calendar: stale cached schedule')
        except Exception as e:warnings.append(name+' calendar: '+str(e)[:120])
    unique={}
    for event in out:unique[(event['region'],event['date'],event['title'])]=event
    result=sorted(unique.values(),key=lambda e:(e['date'],e['region']))
    # Retain UK releases even when US and EU collectively exceed display limit.
    # The user switches between regional filters in the UI.
    uk=[x for x in result if x['region']=='UK'][:32]
    other=[x for x in result if x['region']!='UK'][:32]
    return sorted(uk+other,key=lambda e:(e['date'],e['region']))[:64],warnings,n_cached

def collect_us_real(core,opts):
    bydate={};warnings=[];cached=0
    for code,field in FRED_REAL.items():
        try:
            rows,c,msg=core.fetch_fred(code,opts)
            cached+=int(c)
            for r in rows:bydate.setdefault(r['date'],{'date':r['date']})[field]=r['value']
            if 'stale cache' in msg:warnings.append('US real yield '+code+': stale cache')
        except Exception as e:warnings.append('US real yield '+code+': '+str(e))
    return sorted(bydate.values(),key=lambda v:v['date']),warnings,cached

def collect_sovereign(core,opts):
    bydate={};warnings=[];cached=0
    for code,name in EU_SOVEREIGNS.items():
        url='https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_m?'+urllib.parse.urlencode({
            'geo':code,'sinceTimePeriod':str(dt.date.today().year-max(opts.years,3)-1)})
        try:
            raw,c,msg=core.get_bytes(url,'euro_10y_'+code,opts.offline,opts.cache_hours)
            pts=core.parse_jsonstat(json.loads(raw))
            for p in pts:bydate.setdefault(p['date'],{'date':p['date']})[code]=p['value']
            cached+=int(c)
            if 'stale cache' in msg:warnings.append('Eurostat 10Y '+code+': stale cache')
        except Exception as e:warnings.append('Eurostat 10Y '+code+': '+str(e))
    return sorted(bydate.values(),key=lambda x:x['date']),warnings,cached

def demo_extras(end,days=730):
    import math
    us_real=[];sovereign=[]
    for d in range(days,-1,-1):
        day=end-dt.timedelta(days=d)
        if day.weekday()>4:continue
        t=(days-d)/days
        us_real.append({'date':day.isoformat(),'usReal5':round(1.7+.3*math.sin(t*8),3),
                        'usReal10':round(1.9+.25*math.sin(t*8),3),
                        'usBreakeven5':round(2.3+.3*math.cos(t*9),3),
                        'usBreakeven10':round(2.1+.22*math.cos(t*9),3)})
        if day.day<=3:
            sovereign.append({'date':day.replace(day=1).isoformat(),
                       'DE':round(2.5+.35*math.sin(t*5),3),
                       'FR':round(3.2+.4*math.sin(t*5+.4),3),
                       'IT':round(3.5+.52*math.sin(t*5+.2),3),
                       'ES':round(3.1+.39*math.sin(t*5+.7),3)})
    # Clearly synthetic news and releases, not fictional claims about actual events.
    demo_news=[{'category':cat,'title':'DEMO ONLY — sample '+cat.lower()+' news headline; no report retrieved',
                'url':'https://news.google.com/','source':'SYNTHETIC DEMO',
                'published':'2026-11-05 12:00 UTC'} for cat in NEWS_QUERIES]
    demo_calendar=[{'date':(end+dt.timedelta(days=i)).isoformat(),'region':r,
                   'title':'DEMO ONLY — illustrative economic-release placeholder',
                   'url':u,'source':'SYNTHETIC DEMO','time':'Demonstration'} for i,r,u in [
            (6,'UK','https://www.ons.gov.uk/releasecalendar'),
            (9,'EU','https://ec.europa.eu/eurostat/web/main/news/release-calendar'),
            (11,'US','https://www.bls.gov/schedule/')]]
    return {'news':demo_news,'calendar':demo_calendar,'us_real':us_real,
            'sovereign_yields':sovereign}


# Company-specific headlines are separate from market headlines: they are evidence
# to inspect, not automatic claims about the cause of a share-price move.
def focus_movers(movers, limit=12):
    seen={}
    for market in movers:
        for row in market.get('gainers',[])+market.get('losers',[]):
            symbol=row.get('symbol')
            if symbol and row.get('date')==market.get('date'):
                score=abs(float(row.get('changePct') or 0))
                if symbol not in seen or seen[symbol]['score']<score:
                    seen[symbol]={'symbol':symbol,'name':row.get('name') or symbol,
                                  'score':score,'date':row.get('date')}
    return sorted(seen.values(),key=lambda r:(-r['score'],r['symbol']))[:max(0,limit)]


def collect_company_news(core, opts, movers, limit=12):
    out=[];warnings=[];cached=0
    now=dt.datetime.now(dt.timezone.utc)
    for company in focus_movers(movers,limit):
        symbol,name=company['symbol'],company['name']
        # Prefer specific company names to loose tickers like V or IT.
        name=re.sub(r'\s+',' ',name).strip()[:100]
        query='"'+name.replace('"','')+'" shares when:4d'
        url='https://news.google.com/rss/search?'+urllib.parse.urlencode(
            {'q':query,'hl':'en-GB','gl':'GB','ceid':'GB:en'})
        articles=[]
        if not getattr(opts,'offline',False):
            try:
                raw,used,msg=core.get_bytes(url,'company_news_'+re.sub(r'[^a-zA-Z0-9]','_',symbol),opts.offline,opts.cache_hours)
                articles=rss_articles(raw,'COMPANY',generated=now)[:5]
                cached+=int(used)
                if 'stale cache' in msg:warnings.append('Company news '+symbol+': stale cache')
            except Exception as exc:
                if len(warnings)<10:warnings.append('Company news '+symbol+': '+str(exc)[:120])
        if not articles and not getattr(opts,'offline',False):
            try:
                raw=fetch_rss_once(bing_news_url(query))
                articles=rss_articles(raw,'COMPANY',generated=now,default_source='Bing News')[:5]
            except Exception as exc:
                if len(warnings)<15:warnings.append('Company news '+symbol+' alternate RSS: '+str(exc)[:100])
        out.append({'symbol':symbol,'name':name,'articles':articles,
                    'retrievedAt':now.strftime('%Y-%m-%d %H:%M UTC'),
                    'source':'News RSS feeds (unofficial, selected by search)'})
    return out,warnings,cached
