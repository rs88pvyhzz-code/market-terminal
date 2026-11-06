"""Incremental ten-year equity price history for a static GitHub Pages terminal.

Yahoo historical daily closes are requested progressively (not one large burst),
then retained in one compressed site cache and refreshed periodically. At publication we export one small
JSON file per ticker. The browser downloads only the chart someone opens.

The cache belongs to the *website*, not an ephemeral GitHub Actions runner;
therefore repeated scheduled builds can gradually cover an index universe.
No prices are fabricated or extrapolated when a provider has no data.
"""
from __future__ import annotations
import concurrent.futures
import copy
import datetime as dt
import gzip
import json
import os
import pathlib
import re
import shutil
import urllib.request
from collections import defaultdict

CACHE_NAME = 'stock_history_cache.json.gz'
DEFAULT_DIR = pathlib.Path(__file__).resolve().parent / '.terminal_price_history'
SYMBOL_RE = re.compile(r'^[A-Za-z0-9^][A-Za-z0-9.^-]{0,24}$')


def _unpack(raw):
    obj = json.loads(gzip.decompress(raw).decode('utf-8'))
    if not isinstance(obj, dict) or not isinstance(obj.get('records'), dict):
        raise ValueError('Invalid historic price cache')
    return obj


def prior_cache(url=None, opener=None):
    """Retrieve prior published compressed cache, if available."""
    if not url:
        repo = os.environ.get('GITHUB_REPOSITORY', '')
        if '/' not in repo:
            return {}
        owner, project = repo.split('/', 1)
        url = f'https://{owner}.github.io/{project}/{CACHE_NAME}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'MarketTerminal/1.0'})
        if opener:
            return _unpack(opener(req))
        with urllib.request.urlopen(req, timeout=20) as response:
            # Upper bound prevents accidentally downloading an enormous error page.
            raw = response.read(80_000_001)
        if len(raw) > 80_000_000:
            raise ValueError('Historic price cache too large')
        return _unpack(raw)
    except Exception as exc:
        print(f'Price history: earlier cache not available ({str(exc)[:110]})', flush=True)
        return {}


def _date(value):
    try:
        return dt.date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _points(rows, years=10):
    clean = {}
    for r in rows:
        try:
            day = r['date'] if isinstance(r, dict) else r[0]
            price = r['close'] if isinstance(r, dict) else r[1]
            if _date(day) is None:
                continue
            price = round(float(price), 5)
            if price > 0 and price < 1e12:
                clean[day] = price
        except (ValueError, TypeError, IndexError, KeyError, OverflowError):
            continue
    points = sorted(clean.items())
    if not points:
        return []
    cutoff = (_date(points[-1][0]) - dt.timedelta(days=366*years)).isoformat()
    return [[date, price] for date, price in points if date >= cutoff]


def collect(core, opts, movers, company_history, cache_dir=DEFAULT_DIR, batch=60,
            provider=None, asof=None, seed=('NFLX', 'AXON', 'CCH.L', 'SHAW.L'),
            previous=None):
    """Return (available_symbols, coverage, warnings).

    provider(symbol, options) -> (quote, history, message, error) is injectable
    for deterministic tests and otherwise defaults to core.fetch_quote.
    """
    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / CACHE_NAME
    try:
        saved = _unpack(cache_file.read_bytes()) if cache_file.exists() else {}
    except Exception as exc:
        print('Price history: local cache unreadable:', str(exc)[:120], flush=True)
        saved = {}
    if not saved and not getattr(opts, 'offline', False):
        saved = previous if previous is not None else prior_cache()
    if not isinstance(saved, dict):
        saved = {}
    today = asof or dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    universe = {}
    for market in movers:
        for q in market.get('constituents', []):
            sym = q.get('symbol', '')
            if SYMBOL_RE.fullmatch(sym):
                universe.setdefault(sym, q.get('name', sym))
    # Also preserve user-preselected companies, even if not an index constituent.
    detail_symbols = {r.get('symbol') for r in company_history if isinstance(r, dict)}
    universe.update({s: s for s in detail_symbols if s and SYMBOL_RE.fullmatch(s)})
    records = {sym:rec for sym,rec in (saved.get('records') or {}).items()
               if sym in universe and isinstance(rec, dict) and len(rec.get('points') or []) > 1}
    attempts = {sym: when for sym,when in (saved.get('attempts') or {}).items() if sym in universe}

    # Reuse free data already fetched by the detailed-company and mover collectors.
    embedded = defaultdict(list)
    for row in company_history:
        sym = row.get('symbol')
        if sym in universe:
            embedded[sym].append(row)
    for sym,rows in embedded.items():
        points = _points(rows)
        if len(points) >= 2:
            records[sym] = {'symbol':sym, 'points':points, 'asOf':today,
                            'currency':records.get(sym,{}).get('currency','')}
            attempts[sym] = today

    def attempt_age(sym):
        when = attempts.get(sym)
        try:
            return (dt.datetime.fromisoformat(today.replace('Z','+00:00')) -
                    dt.datetime.fromisoformat(when.replace('Z','+00:00'))).total_seconds()/86400
        except (TypeError, ValueError, AttributeError):
            return 100000.0

    # Keep cached charts current between full Yahoo history refreshes using the
    # latest published constituent closing price, with a split/anomaly guard.
    # A price discontinuity must be refetched from Yahoo's split-adjusted series.
    force_refresh = set()
    for market in movers:
        for q in market.get('constituents',[]):
            sym = q.get('symbol')
            if sym not in records or not q.get('current'):
                continue
            price, day = q.get('price'), q.get('date')
            if not _date(day) or not records[sym].get('points'):
                continue
            try:
                val = float(price)
                last_day, last_price = records[sym]['points'][-1]
                if day > last_day and val > 0 and float(last_price) > 0:
                    if 0.65 < val/float(last_price) < 1.55:
                        records[sym]['points'].append([day,round(val,5)])
                    else:
                        force_refresh.add(sym)
            except (TypeError, ValueError, OverflowError):
                continue

    priorities = [sym for sym in seed if sym in universe]
    order = list(dict.fromkeys(priorities + list(universe)))
    # Missing series first; refresh cached series every ~45 days or immediately
    # when a suspected split would otherwise distort the historical chart.
    pending = [s for s in order if s not in records and attempt_age(s)>=2]
    refresh = [s for s in order if s in records and (s in force_refresh or attempt_age(s)>=45)]
    pending = list(dict.fromkeys(pending + refresh))[:max(0, int(batch))]
    warnings = []
    if pending and not getattr(opts, 'offline', False):
        hist_opts = copy.copy(opts)
        hist_opts.years = 10
        query = provider or (lambda sym, options: core.fetch_quote(
            ('Companies',sym,universe[sym],'equity'),options))
        def fetch(sym):
            try:
                quote, rows, _, err = query(sym, hist_opts)
                return sym, quote, _points(rows), err
            except Exception as exc:
                return sym, None, [], str(exc)[:130]
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(2,max(1,getattr(opts,'workers',2)))) as pool:
            for sym, quote, points, err in pool.map(fetch, pending):
                attempts[sym] = today
                if len(points) >= 2:
                    records[sym] = {'symbol':sym,'points':points,'asOf':today,
                                    'currency': (quote or {}).get('currency','')}
                elif len(warnings) < 8:
                    warnings.append(f'History {sym}: {err or "no usable daily closes"}')
    ordered = sorted(records)
    coverage = {'eligible':len(universe), 'available':len(records),
                'fetchedThisRun':len(pending) if not getattr(opts,'offline',False) else 0,
                'asOf':today, 'years':10}
    cache_file.write_bytes(gzip.compress(json.dumps(
        {'version':1,'records':records,'attempts':attempts},separators=(',',':'),ensure_ascii=False
    ).encode('utf-8'), compresslevel=6))
    print(f'Price history: {len(records)}/{len(universe)} tickers cached; '
          f'{coverage["fetchedThisRun"]} new requests', flush=True)
    return ordered, coverage, warnings


def publish_cache(public, cache_dir=DEFAULT_DIR):
    """Write a small file per ticker for lazy, on-demand browser chart loading.

    Also publish the compressed complete cache so the next fresh GitHub runner
    can rebuild the full history set without losing prior downloads.
    """
    public = pathlib.Path(public)
    cache_file = pathlib.Path(cache_dir) / CACHE_NAME
    if not cache_file.exists():
        raise FileNotFoundError('The history cache does not exist; run build_terminal.py first')
    source = _unpack(cache_file.read_bytes())
    path = public / 'stock_history'
    path.mkdir(parents=True, exist_ok=True)
    count = 0
    for symbol, item in sorted(source.get('records',{}).items()):
        if not SYMBOL_RE.fullmatch(symbol):
            continue
        if len(item.get('points',[])) < 2:
            continue
        dest = path / f'{symbol}.json'
        dest.write_text(json.dumps(item,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
        count += 1
    public.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cache_file,public/CACHE_NAME)
    print(f'Published {count} per-company history files and compressed cache',flush=True)
    return count


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--publish',required=True,help='Path to the static website output folder')
    args=parser.parse_args()
    publish_cache(args.publish)
