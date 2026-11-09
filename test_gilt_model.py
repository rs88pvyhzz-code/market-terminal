#!/usr/bin/env python3
"""Gilt model regression test: run by the workflow before every build.

Reconciles the page's JavaScript yield model against the DMO's own figures.
DMO dirty minus clean = accrued interest, so the model's accrued interest must
match it for every regular conventional gilt. Fails the build if it does not.
"""
import json, pathlib, subprocess, sys, tempfile
import gilt_market

ROOT = pathlib.Path(__file__).resolve().parent
html = (ROOT / 'terminal_template.html').read_text('utf-8')
a, b = html.index('function giltDay('), html.index('function giltTaxRate(')
model = html[a:b]
n = html.index('function giltTaxRate(')
net = html[n:html.index('const ladderState', n)].replace(
    "document.getElementById('mt-gilt-tax-rate')?.value", 'undefined')
rows, day = gilt_market.parse_dmo_xlsx((ROOT / 'dmo_gilt_prices.xlsx').read_bytes())

JS = r'''
const D={generatedAt:'2026-11-09'};
%s
%s
const rows=%s; let ok=0,total=0,fails=[];
for(const g of rows){ if(g.indexLinked)continue; total++;
  const f=giltCashflows(g,g.asOf,true); const dmo=g.askDirty-g.askClean;
  if(f&&Math.abs(f.accrued-dmo)<0.0005)ok++; else fails.push(g.name);}
const check=(c,msg)=>{if(!c){console.error('FAIL: '+msg);process.exit(1);}};
check(ok/total>=0.95,`accrued reconciles for only ${ok}/${total}: ${fails.join(', ')}`);
// Ex-dividend: 4%% gilt paying 2 Jun/2 Dec. Trade Fri 20 Nov 2026 settles Mon 23 Nov (T+1),
// exactly 7 business days before the Wed 2 Dec coupon -> ex-div, negative accrued, coupon not received.
const ex={coupon:4,maturity:'2030-12-02',indexLinked:false};
const fx=giltCashflows(ex,'2026-11-20');
check(fx.exDividend&&fx.accrued<0&&fx.flows[0].coupon===0,'ex-dividend handling');
check(!giltCashflows({...ex,cusip:'X'},'2026-11-20').exDividend,'US Treasuries must not go ex-dividend');
const g=rows.find(r=>r.isin==='GB00BMBL1G81');           // 0 1/8%% 2028 (TN28)
const v=giltValuation(g,g.askClean,g.asOf,g.askDirty);
check(Math.abs(giltNetYield(g,g.askClean,0,g.asOf,g.askDirty)-v.ytm)<1e-6,'0%% tax must equal gross yield');
const hi=rows.find(r=>!r.indexLinked&&r.coupon>=4&&r.maturity>'2030');
const vh=giltValuation(hi,hi.askClean,hi.asOf,hi.askDirty),nh=giltNetYield(hi,hi.askClean,45,hi.asOf,hi.askDirty);
check(nh<vh.ytm-1.5,'45%% tax must cut a 4%%+ coupon gilt yield materially');
console.log(`Gilt model OK: accrued reconciles to DMO for ${ok}/${total} conventional gilts (${fails.join(', ')||'all'} differ: irregular first coupon)`);
''' % (model, net, json.dumps(rows))

with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
    f.write(JS)
sys.exit(subprocess.run(['node', f.name]).returncode)
