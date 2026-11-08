#!/usr/bin/env python3
"""Validate the market snapshot and polish its layout for publication.

Called by the existing GitHub Actions `Check market data` step:
    python verify_snapshot.py terminal.html

- Removes the redundant large securities-lending / counterparty-risk card.
- Fixes Company Research peer table header/data column alignment.
- Makes ETF columns readable without page-level sideways scrolling on iPad.
- Consistent spacing, tabular number alignment, responsive grids and long labels.

Safe to run more than once: the injected stylesheet is replaced, not duplicated.
"""
from __future__ import annotations
import argparse
import hashlib
import pathlib
import re
import sys

CSS = r"""
/* ===== Terminal layout polish: generated view only, no data changes ===== */
:root{--mt-cell-line:#2a2a30;--mt-row-hover:#231f1a}
html,body{max-width:100%}
.workspace-stage,.workspace-view,.panel{min-width:0;max-width:100%}
.panel{box-sizing:border-box}
.panel>.row,.panel .row{min-width:0;column-gap:12px;row-gap:8px}
.panel h2,.panel h3{line-height:1.3}
.panel .field,.panel select,.panel input{max-width:100%}
.chart, .chart svg, .chart canvas{max-width:100%}
/* Every financial table uses the same numeric alignment and row rhythm. */
table.watch,table.small-table{border-collapse:collapse;font-variant-numeric:tabular-nums lining-nums}
.watch th,.watch td,.small-table th,.small-table td{box-sizing:border-box;vertical-align:middle}
.watch th.n,.watch td.n,.small-table th.n,.small-table td.n{text-align:right}
.watch th{padding:10px 11px;line-height:1.35}
.watch td{padding:8px 11px;line-height:1.35}
.watch tbody tr:hover td{background:var(--mt-row-hover)}
.small-scroll,.constituents-scroll,.watchlist-table-scroll{max-width:100%;min-width:0;overflow-x:auto;overscroll-behavior-inline:contain}

/* COMPANY RESEARCH — identical column widths for headings, metrics and values.
   The old auto-layout gave long company names oversized columns; the headings
   were also left-aligned whereas their corresponding numbers were right-aligned. */
#peer-panel,#peer-table{min-width:0}
#peer-table{max-width:100%;overflow-x:auto;overscroll-behavior-inline:contain}
#peer-table .watch{table-layout:fixed;width:100%;min-width:770px}
#peer-table .watch th:first-child{width:23%;text-align:left}
#peer-table .watch th:not(:first-child){text-align:right;white-space:normal;overflow-wrap:anywhere;line-height:1.35;font-weight:600}
#peer-table .watch td:first-child{font-weight:500;color:#dddde2;white-space:normal}
#peer-table .watch td:not(:first-child){text-align:right;white-space:nowrap}
#peer-table .watch tr:last-child td:not(:first-child){text-align:right}
#peer-table .watch tr:nth-child(even) td{background:rgba(255,255,255,.018)}
#peer-table .watch tbody tr:hover td{background:var(--mt-row-hover)}
#peer-panel .compare-pickers{min-width:0}
#peer-panel .compare-pickers select{display:block;width:100%;min-width:0;text-overflow:ellipsis}

/* ETF TRACKERS — compact eight-column screen, no 1440px forced minimum.
   The table scrolls inside its own panel only on narrow screens. */
#etf-tracker-panel .etf-table-scroll{max-width:100%;min-width:0;overflow:auto;overscroll-behavior-inline:contain}
#etf-tracker-panel .etf-table{table-layout:fixed;width:100%;min-width:900px}
#etf-tracker-panel .etf-table th:first-child{width:32%;text-align:left}
#etf-tracker-panel .etf-table th:nth-child(2){width:9%}
#etf-tracker-panel .etf-table th:nth-child(3){width:7%}
#etf-tracker-panel .etf-table th:nth-child(4){width:14%}
#etf-tracker-panel .etf-table th:nth-child(5),#etf-tracker-panel .etf-table th:nth-child(6),#etf-tracker-panel .etf-table th:nth-child(7){width:10%}
#etf-tracker-panel .etf-table th:nth-child(8){width:8%}
#etf-tracker-panel .etf-table th:not(:first-child):not(:nth-child(3)):not(:last-child),
#etf-tracker-panel .etf-table td:not(:first-child):not(:nth-child(3)):not(:last-child){text-align:right}
#etf-tracker-panel .etf-table th:nth-child(3),#etf-tracker-panel .etf-table td:nth-child(3),
#etf-tracker-panel .etf-table th:last-child,#etf-tracker-panel .etf-table td:last-child{text-align:center}
#etf-tracker-panel .etf-table td:first-child{white-space:normal;overflow-wrap:anywhere}
#etf-tracker-panel .etf-table td:not(:first-child){white-space:nowrap}
#etf-tracker-panel .etf-table thead th{white-space:normal;overflow-wrap:normal;line-height:1.3}
#etf-tracker-panel .etf-table tr.etf-geo-group th{width:auto;text-align:left!important;white-space:normal}
#etf-tracker-panel .etf-table tbody tr:not(.etf-geo-group):nth-child(even) td{background:rgba(255,255,255,.018)}
#etf-tracker-panel .etf-table tbody tr.etf-active td{background:#332717}
#etf-tracker-panel .etf-table tbody tr:hover td{background:#2e251b}
#etf-tracker-panel .etf-table input[type=checkbox]{vertical-align:middle;max-width:100%}
#etf-tracker-panel .etf-stat-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}
#etf-tracker-panel .etf-stat{min-width:0;padding:11px 12px}
#etf-tracker-panel .etf-stat .v{overflow-wrap:anywhere}
#etf-tracker-panel .etf-controls,#etf-tracker-panel .etf-plot-controls{max-width:100%}
#etf-tracker-panel .etf-detail{min-width:0}
#etf-tracker-panel .etf-compare-grid{max-width:100%}

/* Broad screen checks: cards, charts and controls must not overflow the page. */
.research-stats,.g2,.g3,.macro,.row,.inputs{min-width:0}
.research-stats>* ,.g2>*,.g3>*,.macro>*{min-width:0}
@media(min-width:1024px){
  #peer-table .watch{min-width:0}
  #etf-tracker-panel .etf-table{min-width:0}
}
@media(max-width:1100px){
  #etf-tracker-panel .etf-stat-grid{grid-template-columns:repeat(3,minmax(0,1fr))}
}
@media(max-width:800px){
  #peer-panel .compare-pickers{grid-template-columns:repeat(2,minmax(0,1fr))}
  #etf-tracker-panel .etf-stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .watch th,.watch td{padding:7px 8px}
}
@media(max-width:520px){
  #etf-tracker-panel .etf-stat-grid{grid-template-columns:1fr}
  #peer-table .watch{min-width:680px}
  #etf-tracker-panel .etf-table{min-width:800px}
}
"""
STYLE_OPEN = '<style id="mt-layout-polish-2026">'
STYLE_CLOSE = '</style>'
SECTION = re.compile(r'\s*<section\s+id="etf-structure-section"[^>]*>.*?</section>', re.S)
STYLESHEET = re.compile(re.escape(STYLE_OPEN) + r'.*?' + re.escape(STYLE_CLOSE), re.S)
DATA_MARKER = 'window.MT_DATA = '


def snapshot_data_hash(html: str) -> str:
    if html.count(DATA_MARKER) != 1:
        raise ValueError('Expected one embedded market-data marker')
    raw = html.split(DATA_MARKER,1)[1].split(';</script>',1)[0]
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def polish(html: str) -> tuple[str,bool,bool]:
    baseline = snapshot_data_hash(html)
    # The generator still creates this legacy panel. Removing it from the
    # built HTML leaves the source data and smaller replication facts intact.
    html, removed = SECTION.subn('', html, count=1)
    if removed > 1:
        raise AssertionError('Multiple ETF sections removed')
    if 'id="etf-structure-section"' in html:
        raise ValueError('Unexpected nested ETF structure section')
    block = STYLE_OPEN + '\n' + CSS + '\n' + STYLE_CLOSE
    if STYLE_OPEN in html:
        if html.count(STYLE_OPEN) != 1:
            raise ValueError('Duplicate layout stylesheets')
        html, count = STYLESHEET.subn(lambda match:block, html, count=1)
        if count != 1: raise ValueError('Unable to replace layout stylesheet')
    else:
        if html.count('</head>') != 1:
            raise ValueError('No unique HTML head')
        html=html.replace('</head>',block+'\n</head>',1)
    if snapshot_data_hash(html) != baseline:
        raise ValueError('The embedded market data was altered; refusing to save')
    if 'id="peer-table"' not in html or 'id="etf-tracker-panel"' not in html:
        raise ValueError('This does not look like the current market terminal')
    return html, bool(removed), True




def validate_snapshot(html: str) -> tuple[int,int,int]:
    """Preserve the original market-data publication guard verbatim in effect."""
    import datetime as dt
    import json
    marker = 'window.MT_DATA = '
    if marker not in html:
        raise ValueError('Missing embedded market data')
    try:
        raw = html.split(marker, 1)[1].split(';</script>', 1)[0]
        data = json.loads(raw)
    except Exception as exc:
        raise ValueError(f'Cannot decode embedded data: {exc}') from exc
    if data.get('demo') is not False:
        raise ValueError('Demo or unverified data; refusing to publish')
    q = data.get('quotes') or []
    obs = len(data.get('history') or [])
    if len(q) < 12 or obs < 150:
        raise ValueError('Too few actual market data observations; refusing to publish')
    now = dt.datetime.now(dt.timezone.utc)
    stamps = []
    for item in q:
        try:
            stamp = dt.datetime.strptime(item['asOf'], '%Y-%m-%d %H:%M UTC').replace(tzinfo=dt.timezone.utc)
            stamps.append(stamp)
        except (KeyError, ValueError, TypeError):
            pass
    if not stamps or max(stamps) < now - dt.timedelta(days=7):
        raise ValueError('Prices older than 7 days; refusing to publish')
    print(f"Snapshot verified: {len(q)} instruments, {obs} observations; "
          f"latest quote {max(stamps).isoformat()}, {len(data.get('warnings') or [])} warnings")
    return len(q),obs,len(data.get('warnings') or [])


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('html',type=pathlib.Path,help='Published terminal.html generated by build_terminal.py')
    args=p.parse_args()
    src = args.html.read_text(encoding='utf-8')
    modified,removed,styled = polish(src)
    # Do not change terminal.html if market data fail the original publication checks.
    validate_snapshot(modified)
    if modified != src:
        args.html.write_text(modified,encoding='utf-8')
    print(f"Layout checked: ETF lending panel removed={removed}; "
          f"table layouts aligned={styled}; market data unchanged")
    return 0

if __name__ == '__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('ERROR: '+str(exc),file=sys.stderr)
        sys.exit(1)
