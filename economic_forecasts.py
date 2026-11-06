"""Optional, sourced forecasts and latest official macro actual-vs-previous table.

No consensus is inferred from official releases, and forecasts are never fabricated.
Forecasts require an externally supplied, pre-release source and exact series/period/unit.
"""
from __future__ import annotations
import csv
import datetime as dt
import math
import pathlib

HEADERS=['series_key','period','forecast','unit','source','source_url','recorded_at_utc','release_at_utc']


def _utc(x):
    try:
        obj=dt.datetime.fromisoformat(x.strip().replace('Z','+00:00'))
        return obj.astimezone(dt.timezone.utc) if obj.tzinfo else None
    except (ValueError,TypeError,AttributeError):return None


def _valid_number(raw):
    try:
        x=float(raw)
        return x if math.isfinite(x) and abs(x)<1e9 else None
    except (ValueError,TypeError):return None


def collect(macros, csv_file):
    """Return (rows, errors, forecast_count). Latest 'actual' is a DATA PERIOD,
    not necessarily a release day or real-time economic-news print.
    """
    forecasts={}; warnings=[]
    path=pathlib.Path(csv_file)
    if path.exists():
        with path.open(encoding='utf-8-sig',newline='') as file:
            reader=csv.DictReader(file)
            if not set(HEADERS).issubset(reader.fieldnames or []):
                warnings.append('Forecast file: missing required columns; forecasts omitted')
            else:
                for i,row in enumerate(reader,2):
                    if not any(row.values()):continue
                    key=(row.get('series_key') or '').strip()
                    period=(row.get('period') or '').strip()
                    v=_valid_number(row.get('forecast'))
                    unit=(row.get('unit') or '').strip()
                    source=(row.get('source') or '').strip()
                    url=(row.get('source_url') or '').strip()
                    rec=_utc(row.get('recorded_at_utc') or '')
                    rel=_utc(row.get('release_at_utc') or '')
                    if not key or not period or v is None or not unit or not source or not url.startswith('https://') or rec is None or rel is None or rec>=rel:
                        if len(warnings)<12:warnings.append(f'Forecast row {i}: invalid/incomplete, or not recorded before release')
                        continue
                    forecasts[(key,period)]={'forecast':v,'unit':unit,'source':source[:100],
                       'sourceUrl':url,'recordedAt':rec.isoformat(),'releaseAt':rel.isoformat()}
    output=[];count=0
    for m in macros:
        hh=[]
        for p in m.get('history',[]):
            v=_valid_number(p.get('value'))
            if v is not None and p.get('date'):hh.append({'date':str(p['date']),'value':v,'period':p.get('period')})
        hh.sort(key=lambda p:p['date'])
        if not hh:continue
        latest=hh[-1]; earlier=hh[-2] if len(hh)>1 else None
        period=str(m.get('period') or latest.get('period') or latest['date'])
        entry={'key':m.get('key'),'region':m.get('region','US'),
          'name':m.get('name'),'period':period,'observationDate':latest['date'],
          'value':latest['value'],'previous':earlier['value'] if earlier else None,
          'previousPeriod':(earlier.get('period') or earlier['date']) if earlier else None,
          'unit':m.get('unit',''),'frequency':m.get('frequency',''),
          'actualSource':m.get('source','')}
        f=forecasts.get((entry['key'],period))
        if f:
            if f['unit']==entry['unit']:
                entry.update(f)
                entry['surprise']=round(entry['value']-f['forecast'],5)
                count+=1
            elif len(warnings)<12:warnings.append('Forecast '+str(entry['key'])+' unit mismatch; ignored')
        output.append(entry)
    return output,warnings,count
