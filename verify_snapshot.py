"""Guard against publishing demo output or an empty/stale snapshot."""
import datetime as dt
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
html = path.read_text(encoding='utf-8')
marker = 'window.MT_DATA = '
if marker not in html:
    sys.exit('ERROR: Missing embedded market data')
try:
    raw = html.split(marker, 1)[1].split(';</script>', 1)[0]
    data = json.loads(raw)
except Exception as exc:
    sys.exit(f'ERROR: Cannot decode embedded data: {exc}')
if data.get('demo') is not False:
    sys.exit('ERROR: Demo or unverified data; refusing to publish')
q = data.get('quotes') or []
if len(q) < 12 or len(data.get('history') or []) < 150:
    sys.exit('ERROR: Too few actual market data observations; refusing to publish')
now = dt.datetime.now(dt.timezone.utc)
stamps = []
for item in q:
    try:
        stamp = dt.datetime.strptime(item['asOf'], '%Y-%m-%d %H:%M UTC').replace(tzinfo=dt.timezone.utc)
        stamps.append(stamp)
    except (KeyError, ValueError, TypeError):
        pass
if not stamps or max(stamps) < now - dt.timedelta(days=7):
    sys.exit('ERROR: Prices older than 7 days; refusing to publish')
print(f"Snapshot verified: {len(q)} instruments, {len(data['history'])} observations; "
      f"latest quote {max(stamps).isoformat()}, {len(data.get('warnings') or [])} warnings")
