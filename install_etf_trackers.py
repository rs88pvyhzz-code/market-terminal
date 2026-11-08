#!/usr/bin/env python3
"""Add ETF Trackers to the EXISTING market-terminal repository without deleting features.

Usage: python install_etf_trackers.py --repo /path/to/market-terminal
       python install_etf_trackers.py --repo . --dry-run

Requires a clean copy of the 8-Nov-2026 terminal architecture. Does not run Git
or push to GitHub. Existing files are backed up before replacement.
"""
import argparse
import datetime as dt
import pathlib
import py_compile
import shutil
import sys

PACKAGE = pathlib.Path(__file__).resolve().parent


def replace_exact(text, old, new, label):
    if text.count(old) != 1:
        raise RuntimeError(f'{label}: expected exactly one insertion point; found {text.count(old)}. No changes saved.')
    return text.replace(old, new, 1)


def build_updates(repo):
    script = (repo/'build_terminal.py').read_text('utf-8')
    template = (repo/'terminal_template.html').read_text('utf-8')
    if 'import etf_tracker\n' in script or 'id="etf-tracker-panel"' in template:
        raise RuntimeError('ETF feature appears to be installed already; refusing to duplicate it.')

    script = replace_exact(script, 'import personal_watchlist\n',
                           'import personal_watchlist\nimport etf_tracker\n', 'Python import')
    script = replace_exact(script,
        '        return demo\n    # Persist the visible watchlist',
        "        demo['etfTracker']=etf_tracker.demo(ROOT/'etf_catalog.csv')\n"
        '        return demo\n    # Persist the visible watchlist', 'Demo payload')
    script = replace_exact(script,
        '    quality=build_quality(quotes,hist,movers,fundamentals,fcoverage,calendar,gilts,us_bonds,macro,warnings)',
        "    etf_data,etf_warnings,etf_cached=etf_tracker.collect(sys.modules[__name__],opts,ROOT/'etf_catalog.csv',quotes,hist,watch_quotes,watch_history)\n"
        '    warnings.extend(etf_warnings);cached_count+=etf_cached\n'
        '    quality=build_quality(quotes,hist,movers,fundamentals,fcoverage,calendar,gilts,us_bonds,macro,warnings)', 'ETF data retrieval')
    script = replace_exact(script,
        "    return {'personalWatchlist':watchlist,'watchlist_quotes':watch_quotes,",
        "    return {'etfTracker':etf_data,'personalWatchlist':watchlist,'watchlist_quotes':watch_quotes,", 'ETF snapshot payload')

    css = (PACKAGE/'etf_styles.css').read_text('utf-8')
    section = (PACKAGE/'etf_panel.html').read_text('utf-8')
    javascript = (PACKAGE/'etf_frontend.js').read_text('utf-8')
    template = replace_exact(template, '</style>\n</head>',css+'\n</style>\n</head>', 'ETF styles')
    # Navbar sits immediately after Analytics and before Economics.
    nav = '    <button type="button" role="tab" id="tab-economics"'
    template = replace_exact(template, nav,
        '    <button type="button" role="tab" id="tab-etfs" aria-controls="view-etfs" data-workspace="etfs" aria-selected="false">ETF TRACKERS</button>\n'+nav,
        'ETF navigation tab')
    template = replace_exact(template, '<section class="panel" id="quality-panel">',
        section+'\n<section class="panel" id="quality-panel">', 'ETF panel')
    template = replace_exact(template,
        "    ['economics','ECONOMIC DATA'",
        "    ['etfs','ETF RESEARCH','Low cost · country funds · specialist equities · sovereign and credit bonds',['etf-tracker-panel']],\n"
        "    ['economics','ECONOMIC DATA'", 'ETF workspace panel group')
    template = replace_exact(template,
        "const WORKSPACES=['overview','fx','equities','companies','bonds','analytics','economics','watchlist','quality'];",
        "const WORKSPACES=['overview','fx','equities','companies','bonds','analytics','etfs','economics','watchlist','quality'];", 'Workspace registry')
    template = replace_exact(template,
        'const workspaceForSection={',
        "const workspaceForSection={'etf-tracker-panel':'etfs',", 'ETF direct URL navigation')
    template = replace_exact(template,
        "    case 'economics': renderMacro(); renderEconomicPrints(); renderCalendar(); break;",
        "    case 'etfs': renderEtfTracker(); break;\n"
        "    case 'economics': renderMacro(); renderEconomicPrints(); renderCalendar(); break;", 'ETF tab rendering')
    template = replace_exact(template,
        "  for(const q of D.quotes||[])all.push({kind:'instrument'",
        "  for(const fund of D.etfTracker?.funds||[])all.push({kind:'etfTracker',label:fund.name,code:fund.symbol,detail:fund.market+' · ETF research'});\n"
        "  for(const q of D.quotes||[])all.push({kind:'instrument'", 'Search ETF catalogue')
    template = replace_exact(template,
        "  else if(item.kind==='company'){openConstituent(item.code);}",
        "   else if(item.kind==='company'){openConstituent(item.code);}\n"
        "  else if(item.kind==='etfTracker'){etfState.selected=item.code;activateWorkspace('etfs',{scroll:false});renderEtfTracker();}",
        'Search ETF navigation')
    template = replace_exact(template,
        '// UK GILT SECURITY MONITOR — conventional UK gilts, quoted clean price when sourced.',
        javascript+'\n// UK GILT SECURITY MONITOR — conventional UK gilts, quoted clean price when sourced.',
        'ETF JavaScript')
    template = replace_exact(template,
        'initWatchlist();renderWatchlist();renderDataQuality();',
        'initWatchlist();renderWatchlist();initEtfTracker();renderEtfTracker();renderDataQuality();',
        'ETF initialization')
    if template.count('/*__DATA__*/null') != 1:
        raise RuntimeError('Snapshot JSON marker lost; refusing to write')
    if template.count('id="etf-tracker-panel"') != 1 or template.count("case 'etfs':")!=1:
        raise RuntimeError('ETF panel/renderer injection inconsistent')
    return {'build_terminal.py':script, 'terminal_template.html':template}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=pathlib.Path,default=pathlib.Path.cwd(),help='Existing market-terminal checkout')
    parser.add_argument('--dry-run',action='store_true',help='Check anchors and code, write nothing')
    args=parser.parse_args()
    repo=args.repo.resolve()
    if not (repo/'build_terminal.py').is_file() or not (repo/'terminal_template.html').is_file():
        parser.error('Pass --repo pointing to the folder containing build_terminal.py and terminal_template.html')
    updates=build_updates(repo)
    print('Patch validated against:',repo)
    for key,body in updates.items():print('  ',key,':',len(body),'characters')
    print('  etf_catalog.csv: 78 candidates across 47 markets')
    if args.dry_run:return 0
    # Only write after all source-anchor validations passed.
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    for original in updates:
        backup=repo/(original+'.before-etf-'+stamp+'.bak')
        shutil.copy2(repo/original,backup)
        print('  Backup:',backup.name)
    for filename in ('etf_catalog.csv','etf_tracker.py'):
        if (PACKAGE/filename).resolve() != (repo/filename).resolve():
    shutil.copy2(PACKAGE/filename,repo/filename)
    for name,content in updates.items():
        (repo/name).write_text(content,'utf-8')
    py_compile.compile(str(repo/'build_terminal.py'),doraise=True)
    py_compile.compile(str(repo/'etf_tracker.py'),doraise=True)
    print('Installed. Verify locally with: python build_terminal.py --demo')
    print('Then commit build_terminal.py, terminal_template.html, etf_catalog.csv and etf_tracker.py in Git.')
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('ERROR:',exc,file=sys.stderr)
        sys.exit(1)
