#!/usr/bin/env python3
"""Install ETF Trackers including refreshed TER and indicative tracking-error research.

Replace the existing install_etf_trackers.py in GitHub. The existing Actions
workflow already calls this installer before generating the market dashboard.
No additional uploaded modules or workflow edits are required.

Run: python install_etf_trackers.py --repo . [--dry-run]
"""
import argparse
import datetime as dt
import pathlib
import py_compile
import shutil
import sys

PACKAGE=pathlib.Path(__file__).resolve().parent

# CODE BLOCKS injected by packaging script.
METRICS_SOURCE='"""ETF costs and indicative benchmark tracking error for the Market Terminal.\n\nTER: public justETF ISIN profile (third-party, not issuer confirmation).\nIf the page is unavailable or ambiguous, preserve the catalogue figure and mark\nits provenance. Never invent missing charges or an observation date.\n\nTracking error: annualised weekly standard deviation of total-return proxy ETF\nquotation differences versus the fund\'s *matching* benchmark total-return index.\nThis is indicative market-price tracking dispersion, NOT audited NAV tracking\nerror. Daily cross-market closes are often asynchronous, hence weekly use.\nNo tracking error against price-only indices or broad ETF proxy benchmarks.\n"""\nimport concurrent.futures\nimport datetime as dt\nimport html\nfrom html.parser import HTMLParser\nimport math\nimport re\nimport urllib.parse\nimport urllib.request\n\nUSER_AGENT = {\'User-Agent\':\'Mozilla/5.0 (compatible; UKETFResearch/1.0)\',\n              \'Accept-Language\':\'en-GB,en;q=0.9\',\'Accept\':\'text/html,*/*\'}\n# Only explicitly verified total-return-index Yahoo symbols. The index currency\n# matters; the fund\'s actual benchmark variant (gross/net) must be checked.\nTR_BENCHMARKS = {\n    \'S&P 500\': (\'^SP500TR\',\'S&P 500 Total Return\',\'USD\'),\n    \'Russell 2000\': (\'^RUTTR\',\'Russell 2000 Total Return\',\'USD\'),\n    \'DAX\': (\'^GDAXI\',\'DAX Performance Index\',\'EUR\'),\n}\n\nclass _VisibleText(HTMLParser):\n    def __init__(self):\n        super().__init__(); self.parts=[];self.skip=0\n    def handle_starttag(self,tag,attrs):\n        if tag in (\'script\',\'style\',\'noscript\',\'svg\'):self.skip+=1\n    def handle_endtag(self,tag):\n        if tag in (\'script\',\'style\',\'noscript\',\'svg\') and self.skip:self.skip-=1\n    def handle_data(self,data):\n        if not self.skip and data.strip():self.parts.append(data.strip())\n\n\ndef parse_ter_page(document, isin):\n    """Return TER in percent only after matching the page\'s actual ISIN."""\n    parser=_VisibleText();parser.feed(document)\n    visible=\'\\n\'.join(parser.parts)\n    start=visible[:max(3500,min(len(visible),18000))]\n    if not re.search(r\'\\bISIN\\s*\'+re.escape(isin)+r\'\\b\',start,re.I):\n        return None\n    # Prefer the page\'s primary TER summary, not the comparables fee table.\n    patterns=(r\'\\bTER\\s*\\n\\s*([0-9]+(?:\\.[0-9]+)?)\\s*%\\s*p\\.a\\.\',\n              r"ETF.s TER\\s*\\(total expense ratio\\)\\s*amounts to\\s*([0-9]+(?:\\.[0-9]+)?)\\s*%",\n              r\'\\bTotal expense ratio\\s*\\n\\s*([0-9]+(?:\\.[0-9]+)?)\\s*%\')\n    for pattern in patterns:\n        match=re.search(pattern,visible[:12000],re.I)\n        if match:\n            value=float(match.group(1))\n            return value if 0<=value<=5 else None\n    return None\n\n\ndef fetch_ter(fund,timeout=6):\n    isin=fund.get(\'isin\',\'\')\n    if not re.fullmatch(r\'[A-Z]{2}[A-Z0-9]{10}\',isin):return None,\'ISIN unavailable\'\n    url=\'https://www.justetf.com/uk/etf-profile.html?isin=\'+urllib.parse.quote(isin)\n    try:\n        request=urllib.request.Request(url,headers=USER_AGENT)\n        with urllib.request.urlopen(request,timeout=timeout) as response:\n            if \'text/html\' not in response.headers.get(\'Content-Type\',\'\').lower():\n                return None,\'Unexpected response type\'\n            page=response.read(900000).decode(\'utf-8\',\'replace\')\n        fee=parse_ter_page(page,isin)\n        return (fee,\'justETF profile\' if fee is not None else \'TER not found or ISIN did not match\')\n    except Exception as exc:\n        return None,\'Fee source unavailable: \'+type(exc).__name__\n\n\ndef update_fees(funds,offline=False,max_fetch=80):\n    today=dt.datetime.now(dt.timezone.utc).date().isoformat()\n    for f in funds:\n        f[\'terSource\']=\'Editorial CSV (not live verified)\' if f.get(\'terPct\') is not None else \'Not available\'\n        f[\'terCheckedAt\']=None\n        f[\'terStatus\']=\'Catalogue value\' if f.get(\'terPct\') is not None else \'Missing\'\n    if offline:\n        return {\'checked\':0,\'updated\':0,\'failed\':0,\'skipped\':len(funds)},[]\n    eligible=[f for f in funds if re.fullmatch(r\'[A-Z]{2}[A-Z0-9]{10}\',f.get(\'isin\',\'\'))]\n    eligible=eligible[:max(0,min(80,int(max_fetch)))]\n    outcomes={}\n    # Website may rate limit or block automated fetches; keep the catalogue values.\n    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:\n        futures={pool.submit(fetch_ter,f):f[\'symbol\'] for f in eligible}\n        for future in concurrent.futures.as_completed(futures):\n            try:outcomes[futures[future]]=future.result()\n            except Exception:outcomes[futures[future]]=(None,\'Request failed\')\n    updated=0;errors=0\n    for f in eligible:\n        fee,status=outcomes.get(f[\'symbol\'],(None,\'Unavailable\'))\n        if fee is None:\n            errors+=1\n            f[\'terStatus\']=(\'Catalogue fallback\' if f.get(\'terPct\') is not None else \'Missing\')\n            f[\'terCheckError\']=status\n        else:\n            f[\'terPct\']=round(fee,3)\n            f[\'terSource\']=\'justETF public profile (third-party; verify issuer factsheet)\'\n            f[\'terCheckedAt\']=today\n            f[\'terStatus\']=\'Refreshed\'\n            updated+=1\n    return {\'checked\':len(eligible),\'updated\':updated,\'failed\':errors,\n            \'skipped\':len(funds)-len(eligible)},[]\n\n\ndef _convert_to_usd(price,currency,date,gbpusd):\n    if price is None or price<=0:return None\n    if currency in (\'GBp\',\'GBX\'):\n        rate=gbpusd.get(date)\n        return price*rate/100 if rate and rate>0 else None\n    if currency==\'GBP\':\n        rate=gbpusd.get(date)\n        return price*rate if rate and rate>0 else None\n    if currency==\'USD\':return price\n    return None  # No inference from unknown or EUR currencies.\n\n\ndef _convert_to_benchmark(price,currency,date,gbpusd,gbpeur,index_ccy):\n    if index_ccy==\'USD\':return _convert_to_usd(price,currency,date,gbpusd)\n    if index_ccy!=\'EUR\' or price is None or price<=0:return None\n    if currency==\'EUR\':return price\n    eur=gbpeur.get(date)\n    if currency==\'GBP\':return price*eur if eur and eur>0 else None\n    if currency in (\'GBp\',\'GBX\'):return price*eur/100 if eur and eur>0 else None\n    if currency==\'USD\':\n        usd=gbpusd.get(date)\n        return price*eur/usd if eur and usd and eur>0 and usd>0 else None\n    return None\n\n\ndef _weekly_common(fund_points,index_points,currency,fx,years,index_ccy=\'USD\',fx_eur=None):\n    """Use the latest SAME-DATE traded observation in each ISO week."""\n    fund_map={p[0]:_convert_to_benchmark(p[2],currency,p[0],fx,fx_eur or {},index_ccy)\n              for p in fund_points if len(p)>2 and p[2] is not None}\n    index_map={r[\'date\']:r[\'close\'] for r in index_points\n               if r.get(\'date\') and isinstance(r.get(\'close\'),(int,float)) and r[\'close\']>0}\n    common=sorted(d for d in fund_map if d in index_map and fund_map[d] and fund_map[d]>0)\n    if not common:return []\n    end=dt.date.fromisoformat(common[-1])\n    start=end-dt.timedelta(days=round(years*365.25)+10)\n    weekly={}\n    for date in common:\n        d=dt.date.fromisoformat(date)\n        if d<start:continue\n        weekly[d.isocalendar()[:2]]=(date,fund_map[date],index_map[date])\n    return sorted(weekly.values())\n\n\ndef _tracking_error(weekly,years):\n    if not weekly:return None,0\n    end=dt.date.fromisoformat(weekly[-1][0]);start=end-dt.timedelta(days=round(years*365.25))\n    rows=[r for r in weekly if dt.date.fromisoformat(r[0])>=start]\n    if len(rows)< max(30,int(52*years*.65)):return None,max(0,len(rows)-1)\n    span=(dt.date.fromisoformat(rows[-1][0])-dt.date.fromisoformat(rows[0][0])).days/365.25\n    if span < years*.80:return None,max(0,len(rows)-1)\n    active=[]\n    for prev,cur in zip(rows,rows[1:]):\n        gap=(dt.date.fromisoformat(cur[0])-dt.date.fromisoformat(prev[0])).days\n        if gap<4 or gap>12:continue\n        active.append(cur[1]/prev[1]-cur[2]/prev[2])\n    if len(active)<max(26,int(years*52*.60)):return None,len(active)\n    mean=sum(active)/len(active)\n    sd=math.sqrt(sum((x-mean)**2 for x in active)/(len(active)-1))\n    return round(100*sd*math.sqrt(52),2),len(active)\n\n\ndef update_tracking_error(data,core,opts,main_history):\n    funds=data.get(\'funds\',[])\n    series={r[\'symbol\']:r.get(\'points\',[]) for r in data.get(\'history\',[])}\n    fx={r[\'date\']:r[\'close\'] for r in main_history\n        if r.get(\'symbol\')==\'GBPUSD=X\' and isinstance(r.get(\'close\'),(int,float)) and r[\'close\']>0}\n    fx_eur={r[\'date\']:r[\'close\'] for r in main_history\n        if r.get(\'symbol\')==\'GBPEUR=X\' and isinstance(r.get(\'close\'),(int,float)) and r[\'close\']>0}\n    results={}\n    used={f.get(\'benchmark\') for f in funds}\n    for index,(ticker,name,ccy) in TR_BENCHMARKS.items():\n        if index not in used:continue\n        try:\n            # Cache and retry handled by existing market-terminal Yahoo chart reader.\n            opt=__import__(\'copy\').copy(opts)\n            opt.years=min(6,opts.years)\n            quote,history,_,error=core.fetch_quote((\'ETF benchmark\',ticker,name,\'index\'),opt)\n            if error or not history:continue\n            results[index]=(ticker,name,ccy,history)\n        except Exception:continue\n    calculated=0\n    for f in funds:\n        for years in (1,3,5):f[\'trackingError\'+str(years)+\'Y\']=None\n        f[\'trackingErrorBasis\']=\'Unavailable: exact fund total-return benchmark not sourced\'\n        f[\'trackingErrorBenchmark\']=\'\'\n        f[\'trackingErrorObs\']=None\n        ref=results.get(f.get(\'benchmark\'))\n        if ref is None:continue\n        ticker,name,currency,ref_history=ref\n        q=f.get(\'quote\') or {}\n        points=series.get(f[\'symbol\'],[])\n        if not points or not q.get(\'currency\'):\n            f[\'trackingErrorBasis\']=\'Unavailable: ETF adjusted-close prices or currency missing\'\n            continue\n        if q.get(\'currency\',\'\').upper() not in (\'USD\',\'GBP\',\'GBX\',\'EUR\'):\n            f[\'trackingErrorBasis\']=\'Unavailable: cannot convert ETF to benchmark currency\'\n            continue\n        periods=[]\n        for years in (1,3,5):\n            rows=_weekly_common(points,ref_history,q[\'currency\'],fx,years,currency,fx_eur)\n            val,obs=_tracking_error(rows,years)\n            f[\'trackingError\'+str(years)+\'Y\']=val\n            periods.append((years,obs,val))\n            if val is not None:calculated+=1\n        f[\'trackingErrorBenchmark\']=name+\' [\'+ticker+\']\'\n        f[\'trackingErrorObs\']=periods[0][1]\n        f[\'trackingErrorBasis\']=\'Indicative annualised WEEKLY closing-price dispersion; adjusted ETF quotes vs \'+name+\'. Not audited fund NAV tracking error; London and US close times differ.\'\n    return {\'eligible\':sum(f.get(\'benchmark\') in TR_BENCHMARKS for f in funds),\n            \'benchmarksAvailable\':len(results),\n            \'calculatedPeriods\':calculated},[]\n\n\n\ndef update_peer_dispersion(data,main_history):\n    """Research-only peer dispersion; NEVER substitute for index tracking error.\n\n    Same named benchmark and same quote currency; adjusted close of both funds.\n    Even two funds tracking one index can differ in securities lending, price\n    timing, distributions and NAV. Treat as a relative peer comparison only.\n    """\n    groups={}\n    for f in data.get(\'funds\',[]):\n        if f.get(\'benchmark\'):groups.setdefault(f[\'benchmark\'],[]).append(f)\n    histories={r[\'symbol\']:r[\'points\'] for r in data.get(\'history\',[])}\n    measured=0\n    for f in data.get(\'funds\',[]):\n        f[\'peerDispersion1Y\']=None\n        f[\'peerDispersion3Y\']=None\n        f[\'peerSymbol\']=\'\'\n        own=histories.get(f[\'symbol\'],[])\n        cur=(f.get(\'quote\') or {}).get(\'currency\')\n        if not cur or not own:continue\n        peers=[p for p in groups.get(f.get(\'benchmark\'),[]) if p[\'symbol\']!=f[\'symbol\']\n               and (p.get(\'quote\') or {}).get(\'currency\')==cur and histories.get(p[\'symbol\'])]\n        if not peers:continue\n        peers.sort(key=lambda p:(p.get(\'terPct\') is None,p.get(\'terPct\') or 999,p[\'symbol\']))\n        peer=peers[0]\n        pmap={r[0]:r[2] for r in histories[peer[\'symbol\']] if len(r)>2 and r[2] and r[2]>0}\n        ownmap={r[0]:r[2] for r in own if len(r)>2 and r[2] and r[2]>0}\n        common=sorted(set(ownmap)&set(pmap))\n        if not common:continue\n        weekly={}\n        for date in common:\n            iso=dt.date.fromisoformat(date).isocalendar()\n            weekly[(iso.year,iso.week)]=(date,ownmap[date],pmap[date])\n        samples=sorted(weekly.values())\n        f[\'peerSymbol\']=peer[\'symbol\']\n        for years in (1,3):\n            value,n=_tracking_error(samples,years)\n            f[\'peerDispersion\'+str(years)+\'Y\']=value\n            if value is not None:measured+=1\n    return measured\n\ndef enrich(data,core,opts,main_history):\n    """Add fee + TE research to existing ETF snapshot, with failures non-fatal."""\n    funds=data.get(\'funds\',[])\n    if not funds:return data,[],0\n    import os\n    max_fetch=int(os.environ.get(\'ETF_METADATA_MAX_FETCH\',\'80\'))\n    fees,warnings=update_fees(funds,offline=opts.offline,max_fetch=max_fetch)\n    tracking,warns=update_tracking_error(data,core,opts,main_history)\n    peers=update_peer_dispersion(data,main_history)\n    data[\'metricsCoverage\']={\'ter\':fees,\'trackingError\':tracking,\'peerDispersionPeriods\':peers}\n    data.setdefault(\'sources\',[]).extend([\n        \'TER: justETF public ISIN profile when retrieved; otherwise dated editorial catalogue, not issuer-verified.\',\n        \'Indicative tracking error: weekly ETF adjusted-close proxy vs matching total-return index, sample standard deviation × sqrt(52). Not official NAV tracking error.\',\n        \'Peer dispersion: weekly adjusted close relative to same named benchmark ETF in same trading currency; NOT index tracking error.\'\n    ])\n    return data,warnings+warns,0\n'
EXTRA_JS='// ETF CHARGES + INDICATIVE TRACKING ERROR (after base ETF frontend, before init()).\n// Values are calculated in Python; this view never guesses missing values.\nconst _renderEtfTrackerBase=renderEtfTracker;\nrenderEtfTracker=function(){\n  _renderEtfTrackerBase();\n  const tbody=$(\'etf-rows\');if(!tbody)return;\n  const table=tbody.closest(\'table\'),head=table?.querySelector(\'thead tr\');\n  if(head&&!head.querySelector(\'.etf-te-heading\')){\n    const title=el(\'th\',\'etf-te-heading\',\'1Y indicative TE†\');\n    title.title=\'Annualised weekly ETF adjusted-close versus exact total-return benchmark. Indicative; not fund NAV tracking error.\';\n    const cells=[...head.children],feeCol=cells.find(c=>/Annual OCF|TER/i.test(c.textContent));\n    head.insertBefore(title,feeCol?.nextSibling||cells[5]||null);\n  }\n  for(const tr of tbody.querySelectorAll(\'tr\')){\n    if(tr.querySelector(\'.etf-te-value\'))continue;\n    const ticker=tr.cells?.[1]?.textContent?.trim(),fund=ETF_BY_SYMBOL.get(ticker);\n    if(!fund)continue;\n    const td=el(\'td\',\'n etf-te-value\',etfPct(fund.trackingError1Y));\n    td.title=fund.trackingErrorBasis||\'No matched total-return index data\';\n    const feeCol=tr.cells[3];tr.insertBefore(td,feeCol?.nextSibling||null);\n  }\n  const count=ETF_DATA.metricsCoverage||{};\n  const stamp=$(\'etf-coverage\');\n  if(stamp){\n    const fees=count.ter?.updated??0,te=count.trackingError?.calculatedPeriods??0;\n    stamp.textContent+=\' · \'+fees+\' costs refreshed · \'+te+\' TE periods\';\n  }\n};\nconst _etfDetailsBase=etfDetails;\netfDetails=function(){\n  _etfDetailsBase();\n  const f=ETF_BY_SYMBOL.get(etfState.selected);if(!f)return;\n  const charges=$(\'etf-detail-stats\');\n  const cost=charges?.querySelector(\'.etf-stat\');\n  if(cost){const sub=cost.querySelector(\'.d\');if(sub)sub.textContent=(f.terSource||\'Unverified\')+(f.terCheckedAt?\' · \'+f.terCheckedAt:\'\');}\n  const host=$(\'etf-risk-stats\');\n  if(!host)return;\n  for(const years of [1,3,5]){\n    const amount=f[\'trackingError\'+years+\'Y\'];\n    etfStatistic(host,years+\'Y tracking error*\',etfPct(amount),\n      amount==null?\'Benchmark total-return data unavailable\':(f.trackingErrorBenchmark||\'\')+\' · weekly price proxy\');\n  }\n  const note=$(\'etf-warning\');\n  if(note)note.textContent+=\' · *Tracking error is INDICATIVE weekly ETF market-price versus matching total-return index, not issuer-reported NAV tracking error. London/US closing times can inflate this figure. Never compare against a price-only benchmark.\';\n};\n\n// Include all new source/metric fields in exported research data.\netfExport=function(){\n  const columns=[\'market\',\'category\',\'symbol\',\'name\',\'benchmark\',\'terPct\',\'terSource\',\'terCheckedAt\',\n    \'replication\',\'distribution\',\'domicile\',\'isin\',\'hedged\',\'trackingError1Y\',\n    \'trackingError3Y\',\'trackingError5Y\',\'trackingErrorBenchmark\',\n    \'trackingErrorBasis\',\'return1Y\',\'return3Y\',\'return5Y\',\'quoteStatus\',\'note\'];\n  const encode=x=>\'"\'+String(x==null?\'\':x).replace(/"/g,\'""\')+\'"\';\n  const csv=[columns.map(encode).join(\',\'),...etfFiltered().map(f=>columns.map(k=>encode(f[k])).join(\',\'))].join(\'\\r\\n\');\n  const blob=new Blob([csv],{type:\'text/csv;charset=utf-8\'}),url=URL.createObjectURL(blob),a=el(\'a\');\n  a.href=url;a.download=\'etf-trackers-with-ter-and-tracking-error-\'+(D.generatedAt||\'snapshot\').slice(0,10)+\'.csv\';\n  document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),250);\n};\nconst _etfDetailsWithTracking=etfDetails;\netfDetails=function(){\n  _etfDetailsWithTracking();\n  const f=ETF_BY_SYMBOL.get(etfState.selected),host=$(\'etf-risk-stats\');\n  if(!f||!host)return;\n  etfStatistic(host,\'1Y ETF-peer dispersion\',etfPct(f.peerDispersion1Y),\n    f.peerSymbol?\'Versus \'+f.peerSymbol+\' · same named index and quote currency\':\'No eligible same-index peer\');\n  etfStatistic(host,\'3Y ETF-peer dispersion\',etfPct(f.peerDispersion3Y),\'ETF-to-ETF comparison, NOT benchmark tracking error\');\n};\n'


def replace_exact(source,old,new,label):
    n=source.count(old)
    if n!=1:raise RuntimeError(f'{label}: wanted 1 insertion point, found {n}. Nothing written.')
    return source.replace(old,new,1)


def build_updates(repo):
    script=(repo/'build_terminal.py').read_text('utf-8')
    template=(repo/'terminal_template.html').read_text('utf-8')
    if 'import etf_tracker\n' in script or 'id="etf-tracker-panel"' in template:
        raise RuntimeError('ETF tab appears installed already. Patch is intended for original repository source.')

    script=replace_exact(script,'import personal_watchlist\n',
                         'import personal_watchlist\nimport etf_tracker\nimport etf_metrics\n','ETF Python imports')
    script=replace_exact(script,
        '        return demo\n    # Persist the visible watchlist',
        "        demo['etfTracker']=etf_tracker.demo(ROOT/'etf_catalog.csv')\n"
        '        return demo\n    # Persist the visible watchlist','ETF demo payload')
    script=replace_exact(script,
        '    quality=build_quality(quotes,hist,movers,fundamentals,fcoverage,calendar,gilts,us_bonds,macro,warnings)',
        "    etf_data,etf_warnings,etf_cached=etf_tracker.collect(sys.modules[__name__],opts,ROOT/'etf_catalog.csv',quotes,hist,watch_quotes,watch_history)\n"
        "    warnings.extend(etf_warnings);cached_count+=etf_cached\n"
        "    etf_data,metric_warnings,metric_cached=etf_metrics.enrich(etf_data,sys.modules[__name__],opts,hist)\n"
        "    warnings.extend(metric_warnings);cached_count+=metric_cached\n"
        '    quality=build_quality(quotes,hist,movers,fundamentals,fcoverage,calendar,gilts,us_bonds,macro,warnings)',
        'ETF quotes + live cost + tracking error')
    script=replace_exact(script,
        "    return {'personalWatchlist':watchlist,'watchlist_quotes':watch_quotes,",
        "    return {'etfTracker':etf_data,'personalWatchlist':watchlist,'watchlist_quotes':watch_quotes,",
        'ETF snapshot payload')

    css=(PACKAGE/'etf_styles.css').read_text('utf-8')
    section=(PACKAGE/'etf_panel.html').read_text('utf-8')
    section=section.replace('TER/replication details are editorial snapshots, not live issuer facts.',
        'TER is checked against public ISIN profiles when accessible; otherwise catalogue values are labelled as fallback. Indicative tracking error uses ETF closing prices and a total-return index, not official NAVs.')
    javascript=(PACKAGE/'etf_frontend.js').read_text('utf-8')+'\n'+EXTRA_JS
    template=replace_exact(template,'</style>\n</head>',css+'\n</style>\n</head>','ETF styles')
    nav='    <button type="button" role="tab" id="tab-economics"'
    template=replace_exact(template,nav,
        '    <button type="button" role="tab" id="tab-etfs" aria-controls="view-etfs" data-workspace="etfs" aria-selected="false">ETF TRACKERS</button>\n'+nav,
        'ETF navigation tab')
    template=replace_exact(template,'<section class="panel" id="quality-panel">',
        section+'\n<section class="panel" id="quality-panel">','ETF panel')
    template=replace_exact(template,"    ['economics','ECONOMIC DATA'",
        "    ['etfs','ETF RESEARCH','TER · tracking error · country funds · equities · bonds',['etf-tracker-panel']],\n"
        "    ['economics','ECONOMIC DATA'", 'ETF workspace panel group')
    template=replace_exact(template,
        "const WORKSPACES=['overview','fx','equities','companies','bonds','analytics','economics','watchlist','quality'];",
        "const WORKSPACES=['overview','fx','equities','companies','bonds','analytics','etfs','economics','watchlist','quality'];",
        'Workspace registry')
    template=replace_exact(template,'const workspaceForSection={',
        "const workspaceForSection={'etf-tracker-panel':'etfs',", 'ETF deep link')
    template=replace_exact(template,
        "    case 'economics': renderMacro(); renderEconomicPrints(); renderCalendar(); break;",
        "    case 'etfs': renderEtfTracker(); break;\n"
        "    case 'economics': renderMacro(); renderEconomicPrints(); renderCalendar(); break;",'ETF renderer')
    template=replace_exact(template,
        "  for(const q of D.quotes||[])all.push({kind:'instrument'",
        "  for(const fund of D.etfTracker?.funds||[])all.push({kind:'etfTracker',label:fund.name,code:fund.symbol,detail:fund.market+' · ETF research'});\n"
        "  for(const q of D.quotes||[])all.push({kind:'instrument'",'Search ETF catalogue')
    template=replace_exact(template,
        "  else if(item.kind==='company'){openConstituent(item.code);}",
        "   else if(item.kind==='company'){openConstituent(item.code);}\n"
        "  else if(item.kind==='etfTracker'){etfState.selected=item.code;activateWorkspace('etfs',{scroll:false});renderEtfTracker();}",
        'Search ETF navigation')
    template=replace_exact(template,
        '// UK GILT SECURITY MONITOR — conventional UK gilts, quoted clean price when sourced.',
        javascript+'\n// UK GILT SECURITY MONITOR — conventional UK gilts, quoted clean price when sourced.',
        'ETF JavaScript')
    template=replace_exact(template,
        'initWatchlist();renderWatchlist();renderDataQuality();',
        'initWatchlist();renderWatchlist();initEtfTracker();renderEtfTracker();renderDataQuality();',
        'ETF initialization')
    if template.count('/*__DATA__*/null') != 1:
        raise RuntimeError('Snapshot marker lost')
    if template.count('id="etf-tracker-panel"')!=1 or template.count("case 'etfs':")!=1:
        raise RuntimeError('ETF tab injection inconsistent')
    return {'build_terminal.py':script,'terminal_template.html':template,
            'etf_metrics.py':METRICS_SOURCE}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=pathlib.Path,default=pathlib.Path.cwd())
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    repo=args.repo.resolve()
    if not (repo/'build_terminal.py').is_file() or not (repo/'terminal_template.html').is_file():
        parser.error('Not the market-terminal source directory')
    updates=build_updates(repo)
    for name,body in updates.items():
        compile(body, str(repo/name),'exec') if name.endswith('.py') else None
    print('ETF integration verified:',', '.join(updates))
    if args.dry_run:return 0
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    for name in ('build_terminal.py','terminal_template.html'):
        backup=repo/(name+'.before-etf-'+stamp+'.bak')
        shutil.copy2(repo/name,backup)
        print('Backup',backup.name)
    for name,text in updates.items():
        (repo/name).write_text(text,'utf-8')
    print('ETF Trackers with TER and indicative tracking error installed.')
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as err:
        print('ERROR:',err,file=sys.stderr)
        sys.exit(1)
