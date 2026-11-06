"""Selected-company research for the static terminal.

Prices use the existing Yahoo chart collector; optional fundamentals come from
`yfinance` (pip install yfinance). Never invent missing P/E or income figures.
The static terminal embeds only companies listed here or requested via CLI.
"""
import datetime as dt
import math
import random
import re

DEFAULT_COMPANIES = [
    ('SHEL.L', 'Shell plc'), ('AZN.L', 'AstraZeneca plc'), ('HSBA.L', 'HSBC Holdings'),
    ('BP.L','BP plc'), ('ULVR.L','Unilever plc'), ('GSK.L','GSK plc'),
    ('RIO.L','Rio Tinto plc'), ('LLOY.L','Lloyds Banking Group'),
    ('BARC.L','Barclays plc'), ('REL.L','RELX plc'), ('DGE.L','Diageo plc'),
    ('NG.L','National Grid plc'), ('BATS.L','British American Tobacco'),
    ('MSFT','Microsoft'), ('AAPL','Apple'), ('NVDA','NVIDIA'),
    ('GOOGL','Alphabet'), ('AMZN','Amazon'), ('META','Meta Platforms'),
    ('JPM','JPMorgan Chase'), ('BRK-B','Berkshire Hathaway'), ('TSLA','Tesla'),
    ('XOM','Exxon Mobil'), ('WMT','Walmart'), ('V','Visa')
]


def valid_symbol(s):
    s=s.strip().upper()
    return s if re.fullmatch(r'[A-Z0-9^][A-Z0-9.\-^]{0,17}',s) else None


def company_universe(custom):
    records={sym:name for sym,name in DEFAULT_COMPANIES}
    for raw in custom:
        symbol=valid_symbol(raw)
        if not symbol: raise ValueError('Invalid company ticker: '+raw)
        records.setdefault(symbol,symbol)
    return list(records.items())


def _num(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError,OverflowError): return None


def _text(v):
    return str(v).strip() if v is not None and str(v).strip() else None


def annual_income_rows(ticker):
    try:
        frame=ticker.income_stmt
        if frame is None or frame.empty: return []
        cols=sorted(frame.columns, reverse=True)[:5]
        def take(col, names):
            for k in names:
                if k in frame.index:
                    x=_num(frame.loc[k,col]);
                    if x is not None: return x
            return None
        rows=[]
        for col in cols:
            date=col.date().isoformat() if hasattr(col,'date') else str(col)[:10]
            rows.append({'fiscalYear':date[:4],'fiscalEnd':date,
                'revenue':take(col,['Total Revenue','Operating Revenue']),
                'operatingProfit':take(col,['Operating Income']),
                'netProfit':take(col,['Net Income','Net Income Common Stockholders','Net Income From Continuing And Discontinued Operation']),
                'pretaxProfit':take(col,['Pretax Income']),
                'dilutedEps':take(col,['Diluted EPS'])})
        return rows
    except Exception: return []


def financials_for(symbol, offline=False):
    if offline:
        return {},[], 'No fundamentals fetched (offline mode)'
    try:
        import yfinance as yf
    except ImportError:
        return {},[], 'Fundamental data unavailable: install the optional yfinance package'
    try:
        t=yf.Ticker(symbol)
        info=t.get_info() or {}
        if not isinstance(info,dict):info={}
        rows=annual_income_rows(t)
        status='Yahoo Finance via yfinance (unofficial; figures unverified)'
        return info,rows,status
    except Exception as e:
        return {},[],f'Fundamentals fetch failed: {str(e)[:180]}'


def fetch_company(symbol,name,builder,opts):
    """Return a summary and annual income rows, plus separate daily price history."""
    q,history,_,error=builder.fetch_quote(('Companies',symbol,name,'equity'),opts)
    info,annual,status=financials_for(symbol, opts.offline)
    # Yahoo share price may be in GBp, while reported financials are USD/GBP.
    # Do not infer market capitalization currency from the reporting currency.
    quote_currency=(q or {}).get('currency') or info.get('currency') or ''
    marketcap_currency=('GBP' if quote_currency in ('GBp','GBX') else quote_currency)
    financial_currency=info.get('financialCurrency') or ''
    trailing=_num(info.get('trailingPE'))
    forward=_num(info.get('forwardPE'))
    div_yield=_num(info.get('dividendYield'))
    latest=annual[0] if annual else {}
    # If a statement is missing, do not silently swap in TTM without relabelling.
    company={
        'symbol':symbol,'name':_text(info.get('longName')) or _text(info.get('shortName')) or name,
        'sector':_text(info.get('sector')),'industry':_text(info.get('industry')),
        'exchange':_text(info.get('exchange')),
        'price':q['price'] if q else None,
        'changePct':q['changePct'] if q else None,
        'priceCurrency':quote_currency,'priceAsOf':q['asOf'] if q else None,
        'marketCap':_num(info.get('marketCap')),'marketCapCurrency':marketcap_currency,
        'trailingPE':trailing if trailing and trailing>0 else None,
        'forwardPE':forward if forward and forward>0 else None,
        'epsTTM':_num(info.get('trailingEps')),
        'dividendYieldPct':div_yield,'priceToBook':_num(info.get('priceToBook')),
        'revenueTTM':_num(info.get('totalRevenue')),
        'netIncomeTTM':_num(info.get('netIncomeToCommon')),
        'profitMarginPct':_num(info.get('profitMargins'))*100 if _num(info.get('profitMargins')) is not None else None,
        'ebitda':_num(info.get('ebitda')),'enterpriseToEbitda':_num(info.get('enterpriseToEbitda')),
        'freeCashflow':_num(info.get('freeCashflow')),'totalDebt':_num(info.get('totalDebt')),
        'roePct':_num(info.get('returnOnEquity'))*100 if _num(info.get('returnOnEquity')) is not None else None,
        'revenue':latest.get('revenue'),'operatingProfit':latest.get('operatingProfit'),
        'netProfit':latest.get('netProfit'),'fiscalEnd':latest.get('fiscalEnd'),
        'financialCurrency':financial_currency,'annual':annual,
        'fundamentalSource':status,'priceSource':q['source'] if q else None,
        'warning':error or None,
    }
    return company,history,error


def demo_companies():
    """All demonstration financial figures intentionally synthetic and marked."""
    rng=random.Random(4472)
    companies=[];prices=[]
    for i,(sym,name) in enumerate(DEFAULT_COMPANIES):
        reporting='USD' if sym in ('SHEL.L','BP.L','RIO.L') or '.L' not in sym else 'GBP'
        quote='GBp' if sym.endswith('.L') else 'USD'
        annual=[]
        for year in (2025,2024,2023,2022):
            base=(28+i*5)*1e9 * (1-(2025-year)*.035)
            revenue=round(base*(1+rng.uniform(-.06,.06)))
            net=round(revenue*rng.uniform(.06,.18))
            annual.append({'fiscalYear':str(year),'fiscalEnd':f'{year}-12-31',
                'revenue':revenue,'operatingProfit':round(net*1.34),'netProfit':net,
                'pretaxProfit':round(net*1.18),'dilutedEps':None})
        val=1600+i*135 if quote=='GBp' else 90+i*12
        end=dt.date(2026,11,5)
        # Eleven years of WEEKLY synthetic observations so the demo can genuinely
        # illustrate its 1/5/10-year selectors without implying daily quote accuracy.
        for age in range(365*11 + (-365*11) % 7, -1, -7):
            day=end-dt.timedelta(days=age)
            if day.weekday()>4:continue
            progress=(365*11-age)/(365*11)
            v=val*(.56+.44*progress)*(1+.04*math.sin((365*11-age)/130+i))
            prices.append({'symbol':sym,'date':day.isoformat(),'close':round(v,4)})
        current=next(p['close'] for p in reversed(prices) if p['symbol']==sym)
        companies.append({'symbol':sym,'name':name,'sector':'SYNTHETIC / TEST','industry':'Test only',
            'exchange':'Synthetic demonstration','price':current,'changePct':rng.uniform(-2.5,2.5),
            'priceCurrency':quote,'priceAsOf':'2026-11-05 16:30 UTC',
            'marketCap':round(80e9+i*14e9),'marketCapCurrency':'GBP' if quote=='GBp' else 'USD',
            'trailingPE':round(rng.uniform(9,35),2),'forwardPE':round(rng.uniform(8,30),2),
            'epsTTM':round(rng.uniform(1,19),2),'dividendYieldPct':round(rng.uniform(.2,4.8),2),
            'priceToBook':round(rng.uniform(1,8),2),'revenueTTM':annual[0]['revenue'],
            'netIncomeTTM':annual[0]['netProfit'],'profitMarginPct':round(100*annual[0]['netProfit']/annual[0]['revenue'],2),
            'revenue':annual[0]['revenue'],'operatingProfit':annual[0]['operatingProfit'],
            'netProfit':annual[0]['netProfit'],'fiscalEnd':'2025-12-31',
            'financialCurrency':reporting,'annual':annual,'fundamentalSource':'SYNTHETIC DEMO — NOT REAL FINANCIALS',
            'priceSource':'SYNTHETIC DEMO','warning':None})
    return companies,prices
