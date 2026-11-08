"""Broad ETF research catalogue and Yahoo snapshot collection.

No holdings, quantities, purchase prices or portfolio values are stored.
Metadata in etf_catalog.csv is editorial and must be checked against issuer factsheets.
Yahoo adjusted closes are unofficial total-return proxies, not certified NAV returns.
"""
import concurrent.futures
import copy
import csv
import datetime as dt
import pathlib
import re

FIELDS = ('category', 'market', 'symbol', 'name', 'benchmark', 'terPct',
          'replication', 'distribution', 'domicile', 'isin', 'hedged',
          'reference', 'note')
SYMBOL_RE = re.compile(r'^[A-Z0-9.^=_-]{1,32}$')
CATEGORIES = {'Equity', 'Bonds', 'Thematic', 'Commodity ETC'}


def read_catalog(path):
    funds, warnings, seen = [], [], set()
    source = pathlib.Path(path)
    if not source.is_file():
        return funds, ['ETF catalog missing: ' + source.name]
    with source.open(encoding='utf-8-sig', newline='') as handle:
        for line, row in enumerate(csv.DictReader(handle), 2):
            symbol = (row.get('symbol') or '').strip().upper()
            if not SYMBOL_RE.fullmatch(symbol) or symbol in seen:
                warnings.append('ETF row ' + str(line) + ': duplicate or invalid symbol')
                continue
            seen.add(symbol)
            entry = {k: (row.get(k) or '').strip() for k in FIELDS}
            if entry['category'] not in CATEGORIES:
                warnings.append(symbol + ': unknown category')
                continue
            fee = entry['terPct']
            try:
                fee = float(fee) if fee else None
                if fee is not None and not 0 <= fee <= 5:
                    raise ValueError('outside accepted range')
            except ValueError:
                warnings.append(symbol + ': fee rejected')
                fee = None
            entry['terPct'] = fee
            if entry['replication'] not in ('Physical full', 'Physical sampling',
                                            'Synthetic swap', ''):
                entry['replication'] = ''
                warnings.append(symbol + ': replication unknown')
            isin = entry['isin']
            entry['issuerFactsUrl'] = ('https://www.justetf.com/uk/etf-profile.html?isin=' + isin
                                       if re.fullmatch(r'[A-Z]{2}[A-Z0-9]{10}', isin) else '')
            # Editorial snapshot date, not live issuer validation.
            entry['factsAsOf'] = '2026-11-08' if fee is not None or entry['replication'] else ''
            entry.update(quote=None, return1Y=None, return3Y=None, return5Y=None,
                         returnBasis='', quoteStatus='Not downloaded')
            funds.append(entry)
    return funds, warnings


def compact_history(history):
    """Daily last five years; weekly earlier. No invented or interpolated prices."""
    raw = sorted((r for r in history if r.get('date') and r.get('close') and r['close'] > 0),
                 key=lambda r: r['date'])
    if not raw:
        return []
    end = dt.date.fromisoformat(raw[-1]['date'])
    out, bucket = [], None
    for r in raw:
        d = dt.date.fromisoformat(r['date'])
        if (end - d).days <= 365 * 5:
            out.append([r['date'], r['close'], r.get('adjClose')])
        else:
            week = d.isocalendar()[:2]
            if week != bucket:
                out.append([r['date'], r['close'], r.get('adjClose')])
            bucket = week
    return out


def annualised_performance(points, years):
    """Trailing annualised growth from documented daily prices or adjusted-close proxy."""
    if len(points) < 2:
        return None, ''
    end = dt.date.fromisoformat(points[-1][0])
    cutoff = (end - dt.timedelta(days=round(years * 365.25))).isoformat()
    initial = next((p for p in reversed(points) if p[0] <= cutoff), points[0])
    span = (end - dt.date.fromisoformat(initial[0])).days / 365.25
    if span < years * 0.95:
        return None, ''
    adjusted = initial[2] is not None and points[-1][2] is not None
    idx = 2 if adjusted else 1
    first, last = initial[idx], points[-1][idx]
    if not first or not last or first <= 0 or last <= 0:
        return None, ''
    return round(100 * ((last / first)**(1 / span) - 1), 2), ('Adjusted close proxy' if adjusted else 'Price only')


def attach(fund, quote, points):
    if not quote:
        fund['quoteStatus'] = 'Unavailable'
        return
    fund['quote'] = {k: quote.get(k) for k in (
        'symbol', 'currency', 'price', 'changePct', 'asOf', 'source', 'cached',
        'adjustedAvailable')}
    fund['quoteStatus'] = 'Quoted' if quote.get('price') is not None else 'Unavailable'
    bases = []
    for years in (1, 3, 5):
        result, basis = annualised_performance(points, years)
        fund['return' + str(years) + 'Y'] = result
        if basis:
            bases.append(basis)
    fund['returnBasis'] = ', '.join(dict.fromkeys(bases))


def demo(path):
    funds, warnings = read_catalog(path)
    return {'funds': funds, 'history': [],
            'coverage': {'catalogued': len(funds), 'quoted': 0, 'withHistory': 0,
                         'unavailable': len(funds), 'failedDownloads': 0, 'demo': True},
            'warnings': warnings, 'sources': ['Editorial research catalogue; demo has no ETF quotations']}


def collect(core, opts, path, main_quotes, main_history, watch_quotes, watch_history):
    funds, warnings = read_catalog(path)
    existing = {q['symbol']: q for q in main_quotes}
    for q in watch_quotes:
        existing.setdefault(q['symbol'], q)
    known_history = {}
    for row in main_history:
        known_history.setdefault(row['symbol'], []).append(row)
    for item in watch_history:
        sym = item.get('symbol')
        if sym and sym not in known_history:
            known_history[sym] = [
                {'date': p[0], 'close': p[1], 'adjClose': p[2] if len(p) > 2 else None}
                for p in item.get('points', [])]
    todo = [f for f in funds if f['symbol'] not in existing]
    options = copy.copy(opts)
    options.years = min(10, max(1, opts.years))
    results = {}

    def one(fund):
        return core.fetch_quote(('ETF research', fund['symbol'], fund['name'], 'etf'), options)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, max(1, opts.workers))) as pool:
        tasks = {pool.submit(one, f): f['symbol'] for f in todo}
        for task in concurrent.futures.as_completed(tasks):
            sym = tasks[task]
            try:
                results[sym] = task.result()
            except Exception as exc:
                results[sym] = (None, [], None, str(exc))

    history, cached, failed = [], 0, 0
    for fund in funds:
        sym = fund['symbol']
        if sym in existing:
            quote, raw = existing[sym], known_history.get(sym, [])
        else:
            quote, raw, detail, error = results.get(sym, (None, [], None, 'Not fetched'))
            if error:
                failed += 1
                if failed <= 8:
                    warnings.append('ETF ' + sym + ': ' + str(error)[:115])
            if quote:
                cached += int(bool(quote.get('cached')))
        points = compact_history(raw)
        attach(fund, quote, points)
        if points:
            history.append({'symbol': sym, 'points': points})
    quoted = sum(f['quoteStatus'] == 'Quoted' for f in funds)
    return ({'funds': funds, 'history': history,
             'coverage': {'catalogued': len(funds), 'quoted': quoted,
                          'withHistory': len(history), 'unavailable': len(funds) - quoted,
                          'failedDownloads': failed, 'demo': False},
             'warnings': warnings,
             'sources': ['ETF metadata: editorial catalogue dated 2026-11-08; issuer factsheets for verification',
                         'Prices: Yahoo Finance unofficial historical chart download; not NAV']},
            warnings, cached)
