"""Full company profiles (accounts, valuation, calendar) for a wider universe.

Universe: every FTSE 100 constituent plus the 100 largest US companies by market
capitalisation among S&P 500 / Nasdaq 100 constituents (ranked from the
financial-summary cache, so the US list fills in as summaries are collected).

Yahoo throttles bulk requests, so profiles are refreshed in rotation: a bounded
batch per build, each profile kept for seven days. The cache is published with
the site (company_profiles_cache.json) and restored by the next build, because
GitHub runners start with an empty disk. Prices are NOT stored here; the page
uses the constituent quotes collected on every build. Missing values stay None.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import urllib.request

import company_data

CACHE_NAME = 'company_profiles_cache.json'
REFRESH_DAYS = 7
RETRY_DAYS = 2
US_TOP_N = 100


def _restore_published():
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    if '/' not in repo:
        return {}
    owner, name = repo.split('/', 1)
    url = f'https://{owner}.github.io/{name}/{CACHE_NAME}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'PersonalMarketResearch/1.1',
                                                   'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=18) as r:
            data = json.loads(r.read(20_000_000).decode('utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print('Company profiles: no published cache yet (' + str(exc)[:80] + ')', flush=True)
        return {}


def universe(movers, fundamentals, top_us=US_TOP_N):
    """Return [(symbol, name)] for FTSE 100 + largest US constituents."""
    names, ftse, us = {}, [], set()
    for market in movers or []:
        for row in market.get('constituents') or []:
            sym = str(row.get('symbol') or '').upper()
            if not sym:
                continue
            names.setdefault(sym, row.get('name') or sym)
            if market.get('id') == 'FTSE100':
                ftse.append(sym)
            elif market.get('id') in ('SP500', 'NASDAQ100'):
                us.add(sym)
    caps = {str(f.get('symbol')).upper(): f.get('marketCap') for f in fundamentals or []
            if isinstance(f.get('marketCap'), (int, float)) and f.get('marketCap') > 0}
    largest = sorted((s for s in us if s in caps), key=lambda s: -caps[s])[:top_us]
    out = list(dict.fromkeys(ftse + largest))
    return [(s, names.get(s, s)) for s in out]


def _profile(symbol, name, info, annual, status, events, stamp):
    num = company_data._num
    text = company_data._text
    div = num(info.get('dividendYield'))
    if div is not None and not 0 <= div <= 30:
        div = None
    tr, fw = num(info.get('trailingPE')), num(info.get('forwardPE'))
    pct = lambda k: num(info.get(k)) * 100 if num(info.get(k)) is not None else None
    latest = annual[0] if annual else {}
    quote_ccy = info.get('currency') or ''
    return {
        'symbol': symbol, 'name': text(info.get('longName')) or text(info.get('shortName')) or name,
        'sector': text(info.get('sector')), 'industry': text(info.get('industry')),
        'exchange': text(info.get('exchange')),
        'marketCap': num(info.get('marketCap')),
        'marketCapCurrency': 'GBP' if quote_ccy in ('GBp', 'GBX') else quote_ccy,
        'trailingPE': tr if tr and tr > 0 else None, 'forwardPE': fw if fw and fw > 0 else None,
        'epsTTM': num(info.get('trailingEps')), 'dividendYieldPct': div,
        'priceToBook': num(info.get('priceToBook')),
        'revenueTTM': num(info.get('totalRevenue')), 'netIncomeTTM': num(info.get('netIncomeToCommon')),
        'profitMarginPct': pct('profitMargins'), 'ebitda': num(info.get('ebitda')),
        'enterpriseToEbitda': num(info.get('enterpriseToEbitda')),
        'freeCashflow': num(info.get('freeCashflow')), 'totalDebt': num(info.get('totalDebt')),
        'roePct': pct('returnOnEquity'), 'earningsGrowthPct': pct('earningsGrowth'),
        'revenueGrowthPct': pct('revenueGrowth'),
        'revenue': latest.get('revenue'), 'operatingProfit': latest.get('operatingProfit'),
        'netProfit': latest.get('netProfit'), 'fiscalEnd': latest.get('fiscalEnd'),
        'financialCurrency': info.get('financialCurrency') or '', 'annual': annual, 'events': events,
        'fundamentalSource': status, 'financialAsOf': stamp[:10], 'asOf': stamp,
    }


def collect(movers, fundamentals, detailed, directory, batch=35, offline=False, fetch=None, asof=None):
    """Return (profiles, coverage, warnings). `fetch(symbol)` is injectable for tests."""
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CACHE_NAME
    try:
        cache = json.loads(path.read_text('utf-8')) if path.exists() else {}
    except Exception:
        cache = {}
    if not cache and not offline:
        cache = _restore_published()
    records = cache.get('records') if isinstance(cache.get('records'), dict) else {}
    attempts = cache.get('attempts') if isinstance(cache.get('attempts'), dict) else {}
    stamp = asof or dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    now = dt.datetime.fromisoformat(stamp.replace('Z', '+00:00'))

    def age(iso):
        try:
            return (now - dt.datetime.fromisoformat(str(iso).replace('Z', '+00:00'))).total_seconds() / 86400
        except Exception:
            return 1e9

    detailed_syms = {str(c.get('symbol')).upper() for c in detailed or []}
    wanted = [(s, n) for s, n in universe(movers, fundamentals) if s not in detailed_syms]
    wanted_syms = {s for s, _ in wanted}
    records = {k: v for k, v in records.items() if k in wanted_syms}

    def stale(sym):
        if sym in records:
            return age(records[sym].get('asOf')) >= REFRESH_DAYS and age(attempts.get(sym)) >= RETRY_DAYS
        return age(attempts.get(sym)) >= RETRY_DAYS
    # Never-fetched first, then oldest.
    pending = sorted((x for x in wanted if stale(x[0])),
                     key=lambda x: (x[0] in records, records.get(x[0], {}).get('asOf', '')))[:max(0, batch)]
    warnings, fetched = [], 0
    if pending and not offline:
        fetch = fetch or (lambda s: company_data.financials_for(s, False))
        for sym, name in pending:
            attempts[sym] = stamp
            try:
                info, annual, status, events = fetch(sym)
            except Exception as exc:
                if len(warnings) < 8:
                    warnings.append('Company profile ' + sym + ': ' + str(exc)[:100])
                continue
            if not info and not annual:
                continue
            records[sym] = _profile(sym, name, info or {}, annual or [], status, events or [], stamp)
            fetched += 1
    path.write_text(json.dumps({'records': records, 'attempts': attempts}, separators=(',', ':')), 'utf-8')
    coverage = {'universe': len(wanted), 'profiles': len(records), 'fetchedThisRun': fetched,
                'refreshDays': REFRESH_DAYS}
    return list(records.values()), coverage, warnings


def publish(directory, public):
    """Copy the cache into the website folder so the next build can restore it."""
    src = pathlib.Path(directory) / CACHE_NAME
    if src.exists():
        dest = pathlib.Path(public)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / CACHE_NAME).write_text(src.read_text('utf-8'), 'utf-8')
