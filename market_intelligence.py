"""Optional news, release calendar, real US rates and European sovereign yields.

All sources are independently optional. This is a personal static snapshot; no article
is represented as live after generation. Data issues are reported and not fabricated.
"""
import datetime as dt
import email.utils
import json
import random
import re
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

def rss_articles(blob, category, generated=None):
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
        if age < -300 or age>4*86400:continue
        source_node=item.find('source')
        source=source_node.text if source_node is not None and source_node.text else 'Google News'
        results.append({'title':title[:220],'url':link,'source':source[:80],
                        'category':category,'published':when.strftime('%Y-%m-%d %H:%M UTC')})
    return results

def collect_news(core,opts):
    reports=[];warnings=[];seen=set();cached=0
    for category,query in NEWS_QUERIES.items():
        url='https://news.google.com/rss/search?'+urllib.parse.urlencode(
            {'q':query,'hl':'en-GB','gl':'GB','ceid':'GB:en'})
        try:
            raw,is_cached,msg=core.get_bytes(url,'news_'+category.lower(),opts.offline,opts.cache_hours)
            cached+=int(is_cached)
            if 'stale cache' in msg:warnings.append('News '+category+': stale cached articles')
            items=rss_articles(raw,category)
            for item in items:
                signature=re.sub(r'[^a-z\d]+','',item['title'].casefold())[:100]
                if signature not in seen:
                    seen.add(signature);reports.append(item)
        except Exception as e:warnings.append('News '+category+': '+str(e))
    reports.sort(key=lambda a:a['published'],reverse=True)
    return reports[:80],warnings,cached

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


def collect_calendar(core,opts):
    """Retrieve multiple official calendar sources; failure of one is isolated."""
    feeds=[
        ('ONS','https://www.ons.gov.uk/releasecalendar?rss&release-type=type-upcoming&sort=date-newest&limit=100',
          parse_ons_upcoming),
        ('BLS','https://www.bls.gov/schedule/news_release/bls.ics',parse_bls_ics),
        ('ECB','https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html',parse_ecb_meetings),
    ]
    out=[];warnings=[];n_cached=0
    for name,url,parser in feeds:
        try:
            raw,is_cached,msg=core.get_bytes(url,'official_calendar_'+name.lower(),opts.offline,opts.cache_hours)
            rows=parser(raw)
            out+=rows;n_cached+=int(is_cached)
            if not rows:warnings.append(name+' calendar: no future dated releases could be verified from source')
            if 'stale cache' in msg:warnings.append(name+' calendar: stale cached release schedule')
        except Exception as e:warnings.append(name+' calendar: '+str(e))
    # Deduplicate identical title/date combinations; sort chronologically.
    unique={}
    for event in out:unique[(event['region'],event['date'],event['title'])]=event
    return sorted(unique.values(),key=lambda e:(e['date'],e['region']))[:40],warnings,n_cached

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
