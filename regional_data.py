"""UK ONS, euro-area Eurostat and ECB official data collectors.

Every series is optional: on failure the dashboard records a warning rather
than silently fabricating a value or replacing it with another measure.
"""
import csv
import datetime as dt
import io
import json
import re
import urllib.parse

ONS_SERIES = [
    ('D7G7', 'mm23', 'uk_cpi', 'UK CPI inflation (12m)', 'monthly', 'UK'),
    ('MGSX', 'lms', 'uk_unemployment', 'UK unemployment (16+, LFS)', 'monthly', 'UK'),
    ('IHYQ', 'ukea', 'uk_gdp_qoq', 'UK real GDP (q/q)', 'quarterly', 'UK'),
    ('IHYR', 'ukea', 'uk_gdp_yoy', 'UK real GDP (y/y)', 'quarterly', 'UK'),
]
# Eurostat's aggregate for 2026 is EA21. Do not silently switch between
# aggregate compositions: maintain comparable statistical series.
EUROSTAT_SERIES = [
    ('prc_hicp_manr', {'geo':'EA21', 'coicop':'CP00'}, 'eu_inflation', 'Euro-area HICP inflation (12m)', 'monthly'),
    ('une_rt_m', {'geo':'EA21', 'sex':'T','age':'Y15-74','s_adj':'SA','unit':'PC_ACT'}, 'eu_unemployment', 'Euro-area unemployment (15–74)', 'monthly'),
    ('namq_10_gdp', {'geo':'EA21','na_item':'B1GQ','s_adj':'SCA','unit':'CLV_PCH_PRE'}, 'eu_gdp_qoq', 'Euro-area real GDP (q/q)', 'quarterly'),
]
for _region, _label in [('DE','Germany'),('FR','France'),('IT','Italy'),('ES','Spain')]:
    EUROSTAT_SERIES.extend([
        ('prc_hicp_manr', {'geo':_region,'coicop':'CP00'}, _region.lower()+'_inflation', _label+' HICP inflation (12m)', 'monthly'),
        ('une_rt_m', {'geo':_region,'sex':'T','age':'Y15-74','s_adj':'SA','unit':'PC_ACT'}, _region.lower()+'_unemployment', _label+' unemployment (15–74)', 'monthly'),
        ('namq_10_gdp', {'geo':_region,'na_item':'B1GQ','s_adj':'SCA','unit':'CLV_PCH_PRE'}, _region.lower()+'_gdp_qoq', _label+' real GDP (q/q)', 'quarterly'),
    ])
# ECB nominal zero-coupon government spot curve, all credit ratings, *not* Bunds.
ECB_MATURITIES = [2,5,10,20,30]
ECB_CURVE_PREFIX = 'B.U2.EUR.4F.G_N_C.SV_C_YM.'
ECB_POLICY_KEY = 'D.U2.EUR.4F.KR.DFR.LEV'


def parse_ons_csv(raw, frequency):
    text = raw.decode('utf-8-sig',errors='replace') if isinstance(raw,bytes) else raw
    months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    data=[]
    for row in csv.reader(io.StringIO(text)):
        if len(row)<2:continue
        period=row[0].strip().upper()
        m=re.fullmatch(r'(\d{4}) (JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|Q[1-4])',period)
        if not m:continue
        is_quarter=m[2].startswith('Q')
        if (frequency=='quarterly')!=is_quarter:continue
        try: value=float(row[1].strip())
        except (ValueError,TypeError):continue
        y=int(m[1]); month=(int(m[2][1])-1)*3+1 if is_quarter else months[m[2]]
        data.append({'date':f'{y:04d}-{month:02d}-01','value':value,'period':period})
    data.sort(key=lambda p:p['date'])
    if not data:raise ValueError('No monthly/quarterly values in ONS CSV')
    return data


def parse_jsonstat(payload):
    """Decode JSON-stat 2.0: select index zero on all dims except time."""
    ids=payload.get('id',[]);sizes=payload.get('size',[])
    if not ids or not sizes or 'time' not in ids or len(ids)!=len(sizes):
        raise ValueError('Eurostat JSON-stat dimensions not understood')
    tdim=ids.index('time');dim=payload['dimension']['time']['category']['index']
    index=dict(dim) if isinstance(dim,dict) else {x:i for i,x in enumerate(dim)}
    vals=payload.get('value',{})
    mult=1
    for size in sizes[tdim+1:]:mult*=size
    out=[]
    for period,pos in index.items():
        offset=pos*mult
        value=vals.get(str(offset)) if isinstance(vals,dict) else vals[offset] if offset<len(vals) else None
        try:v=float(value)
        except (ValueError,TypeError):continue
        m=re.fullmatch(r'(\d{4})-Q([1-4])',period)
        day=f'{m[1]}-{(int(m[2])-1)*3+1:02d}-01' if m else (period+'-01' if re.fullmatch(r'\d{4}-\d{2}',period) else None)
        if day:out.append({'date':day,'value':v,'period':period})
    out.sort(key=lambda p:p['date'])
    if not out:raise ValueError('No values in Eurostat series for selected aggregate')
    return out


def parse_ecb_csv(raw):
    text=raw.decode('utf-8-sig',errors='replace') if isinstance(raw,bytes) else raw
    data=[]
    for r in csv.DictReader(io.StringIO(text)):
        day=r.get('TIME_PERIOD') or r.get('TIME_PERIOD ')
        v=r.get('OBS_VALUE')
        try: value=float(v)
        except (ValueError,TypeError):continue
        if day and re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):data.append({'date':day,'value':value})
    data.sort(key=lambda x:x['date'])
    if not data:raise ValueError('ECB data file returned no dated observations')
    return data


def economic_series(key,name,rows,source,region,frequency,cached,source_url=''):
    return {'key':key,'name':name,'unit':'%', 'history':rows,
            'value':round(rows[-1]['value'],3),'date':rows[-1]['date'],
            'period':rows[-1].get('period',rows[-1]['date']),
            'region':region,'frequency':frequency,'cached':cached,
            'source':source,'sourceUrl':source_url}


def get_regional_data(core,opts):
    """Return (macro series, ECB daily yield rows, warnings, cached count)."""
    warnings=[];macros=[];euro_days={};n_cached=0
    for code,dataset,key,name,freq,region in ONS_SERIES:
        # ONS published CSV endpoint; failure is clearly marked and isolated.
        path=f'/{"economy/inflationandpriceindices" if code=="D7G7" else "employmentandlabourmarket/peoplenotinwork/unemployment" if code=="MGSX" else "economy/grossdomesticproductgdp"}/timeseries/{code.lower()}/{dataset}'
        url='https://www.ons.gov.uk/generator?'+urllib.parse.urlencode({'format':'csv','uri':path})
        try:
            raw,cached,msg=core.get_bytes(url,f'ons_{code.lower()}',opts.offline,opts.cache_hours)
            pts=parse_ons_csv(raw,freq)
            macros.append(economic_series(key,name,pts,'ONS',region,freq,cached,url));n_cached+=int(cached)
            if 'stale cache' in msg:warnings.append(f'ONS {code}: stale cache')
        except Exception as e:warnings.append(f'ONS {code}: {e}')
    for table,filters,key,name,freq in EUROSTAT_SERIES:
        query=dict(filters)
        query['sinceTimePeriod']=str(dt.date.today().year-max(opts.years,3)-1)
        url='https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/'+table+'?'+urllib.parse.urlencode(query)
        try:
            raw,cached,msg=core.get_bytes(url,'eurostat_'+key,opts.offline,opts.cache_hours)
            pts=parse_jsonstat(json.loads(raw))
            macros.append(economic_series(key,name,pts,'Eurostat',filters['geo'] if filters['geo']!='EA21' else 'EU',freq,cached,url));n_cached+=int(cached)
            if 'stale cache' in msg:warnings.append(f'Eurostat {key}: stale cache')
        except Exception as e:warnings.append(f'Eurostat {key}: {e}')
    start=dt.date.today()-dt.timedelta(days=int(opts.years*365.25)+16)
    q={'startPeriod':start.isoformat(),'format':'csvdata'}
    keys=[(f'SR_{n}Y',f'eur{n}y') for n in ECB_MATURITIES]+[('DFR','depositRate')]
    for label,field in keys:
        is_policy=label=='DFR'
        series=ECB_POLICY_KEY if is_policy else ECB_CURVE_PREFIX+label
        dataset='FM' if is_policy else 'YC'
        url='https://data-api.ecb.europa.eu/service/data/'+dataset+'/'+series+'?'+urllib.parse.urlencode(q)
        try:
            raw,cached,msg=core.get_bytes(url,'ecb_'+field+'_y'+str(opts.years),opts.offline,opts.cache_hours)
            pts=parse_ecb_csv(raw)
            for p in pts:euro_days.setdefault(p['date'],{'date':p['date']})[field]=round(p['value'],5)
            n_cached+=int(cached)
            if 'stale cache' in msg:warnings.append('ECB '+field+': stale cache')
        except Exception as e:warnings.append(f'ECB {field}: {e}')
    eu_rates=sorted(euro_days.values(),key=lambda x:x['date'])
    policy=[{'date':r['date'],'value':r['depositRate']} for r in eu_rates if r.get('depositRate') is not None]
    if policy:macros.append(economic_series('eu_policy','ECB deposit facility rate',policy,'ECB','EU','policy',False,'https://data.ecb.europa.eu/data/datasets/FM/FM.'+ECB_POLICY_KEY))
    return macros,eu_rates,warnings,n_cached


def demo_regional(end,days=730):
    """Synthetic demo only. No values are represented as historical facts."""
    import math
    uk=[];ea=[];policy=[]
    for d in range(days,-1,-1):
        day=end-dt.timedelta(days=d)
        if day.weekday()>4:continue
        x=(days-d)/days
        ea.append({'date':day.isoformat(),**{f'eur{n}y':round(2.2+n*.047+.18*math.sin(x*9),3) for n in ECB_MATURITIES},
                   'depositRate':round(2+.5*(1-x),3)})
    macros=[]
    definitions=[('UK','uk_cpi','UK CPI inflation (12m)','monthly',3.1),('UK','uk_unemployment','UK unemployment (16+, LFS)','monthly',4.4),
       ('UK','uk_gdp_qoq','UK real GDP (q/q)','quarterly',.5),('UK','uk_gdp_yoy','UK real GDP (y/y)','quarterly',1.4),
       ('EU','eu_inflation','Euro-area HICP inflation (12m)','monthly',2.4),('EU','eu_unemployment','Euro-area unemployment (15–74)','monthly',6.2),
       ('EU','eu_gdp_qoq','Euro-area real GDP (q/q)','quarterly',.3),('EU','eu_policy','ECB deposit facility rate','policy',2.4)]
    for j,(region,key,name,freq,v) in enumerate(definitions):
        hh=[]
        if freq=='quarterly':
            for k in range(20):
                year=2022+k//4;quarter=1+k%4
                if dt.date(year,month,1)>end:break
                hh.append({'date':f'{year}-{(quarter-1)*3+1:02d}-01','value':round(v+.14*math.sin(k/3+j),3),'period':f'{year} Q{quarter}'})
        else:
            for k in range(48):
                year=2023+k//12;month=1+k%12
                if dt.date(year,month,1)>end:break
                hh.append({'date':f'{year}-{month:02d}-01','value':round(v+.18*math.sin(k/5+j),3),'period':f'{year}-{month:02d}'})
        macros.append(economic_series(key,name,hh,'SYNTHETIC DEMO',region,freq,False))
    for region,name in [('DE','Germany'),('FR','France'),('IT','Italy'),('ES','Spain')]:
        for metric,name_suffix,freq,v in [('inflation','HICP inflation (12m)','monthly',2.5),('unemployment','unemployment (15–74)','monthly',6.0),('gdp_qoq','real GDP (q/q)','quarterly',.4)]:
            data=[]
            for k in range(34 if freq=='monthly' else 19):
                year=2024+k//(12 if freq=='monthly' else 4)
                m=1+(k%12 if freq=='monthly' else (k%4)*3)
                if dt.date(year,m,1)>end:continue
                data.append({'date':f'{year}-{m:02d}-01','value':round(v+.12*math.sin(k/4+len(name)),3),'period':f'{year}-{m:02d}' if freq=='monthly' else f'{year} Q{(m-1)//3+1}'})
            macros.append(economic_series(region.lower()+'_'+metric,name+' '+name_suffix,data,'SYNTHETIC DEMO',region,freq,False))
    return macros,ea
