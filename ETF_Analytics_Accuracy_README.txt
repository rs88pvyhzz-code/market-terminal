MARKET TERMINAL — ETF SELECTION + DATA ACCURACY, 8 NOVEMBER 2026

Install in existing rs88pvyhzz-code/market-terminal repository:
1. Upload ONLY install_etf_trackers.py, replacing the file of that exact name.
2. Commit to main. The existing .github/workflows/publish.yml already runs this installer.
3. Check GitHub Actions > Refresh and publish Market Terminal for a successful run.
4. Refresh GitHub Pages. The ETF tab and Analytics audit are generated in the site.

What changes:
- ETF Trackers: same-index comparison (up to 5 of the lowest known TER), showing annualised fund returns, TER, indicative tracking difference and tracking error, dated fund assets where sourced, replication, income and quotation currency.
- ETF detail: annualised 1/3/5-year tracking difference in percentage points; TE remains separate. Difference is fund adjusted-close proxy CAGR minus exact-dated total-return index CAGR.
- Vanguard/iShares official TER retrieval remains first-priority; justETF third-party fallback; dated issuer snapshots when blocked. All marked by source.
- iShares official Net Assets of Fund when exact fund ISIN and fee/page identity checks pass. If a trustworthy dated figure cannot be extracted, AUM is unavailable.
- Analytics: ETF DATA ACCURACY & SOURCE COVERAGE — quote age, TER provenance and age, AUM completeness, 3Y benchmark coverage, ISIN gaps and ticker/index conflicts with links to product sources. No invented 'accuracy score'.
- Data Quality: compact ETF source coverage summary linking conceptually to the Analytics full audit.
- CSV export: added AUM and 1/3/5Y tracking difference.

Limits / methodology:
- Tracking difference is only computed when a matching total-return index is available (S&P 500, Russell 2000 or DAX), adjusted fund prices and same-date FX are available, and sufficient observations exist. An FX-hedged share class requires its own benchmark and does not use an unhedged reference.
- Tracking difference is an indicative MARKET-PRICE proxy, NOT an official NAV tracking difference. The same warning applies to indicative tracking error. Vanguard issuer-reported NAV tracking error is labelled separately.
- Bid-offer spread remains unavailable without verified executable bid/ask quotations.
- Fund size means assets of the whole fund as stated by issuer, not trading volume, liquidity or share-class AUM.
- This is an installer for a public research site, not a brokerage or trade execution system.

Local tests: tracking-difference math, data sufficiency, iShares ISIN-validated AUM parsing, installer markers, Python compilation, JavaScript syntax. The GitHub deployment has not been executed through this environment; connection refuses write operations.
