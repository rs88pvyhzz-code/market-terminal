#!/usr/bin/env python3
"""2026-11-08 issuer-verified ETF consolidation for market-terminal.

Apply this AFTER `install_etf_trackers.py` and BEFORE `build_terminal.py`.
Original market, economics, analytics, watchlist and company panels are preserved.

Facts originate in dated issuer screenshots. Never pass US domiciled fees to UCITS.
ISIN is the authoritative identity; a same-name ticker is insufficient.
Fund AUM is not share-class size, market turnover or tradable liquidity.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import re
import shutil
import sys

ISSUER_CSV = 'symbol,isin,issuer,name,category,market,benchmark,reference,terPct,aum,aumCurrency,aumAsOf,issuerDate,replication,replicationDetail,distribution,domicile,riskIndicator,issuerTe3,lendingReturnPct,note,sourceUrl\nINRG.L,IE00B1XNHC34,iShares,,,,,"Fund AUM $2,975.29m; distinct from share class $2,600.26m.",0.65,2975290000,USD,2026-10-31,2026-11-04,,"Physical, replication detail not specified",,Ireland,7,,,,https://www.ishares.com/uk/individual/en/products/251911/\nITKY.L,IE00B1FZS574,iShares,,,,,,0.74,101850000,USD,2026-10-31,2026-11-04,,"Physical, replication detail not specified",,Ireland,7,,,,https://www.ishares.com/uk/individual/en/products/251879/\nSPOL.L,IE00B4M7GH52,iShares,,,,,,0.74,1120830000,USD,2026-10-31,2026-11-04,,"Physical, replication detail not specified",,Ireland,7,,,,https://www.ishares.com/uk/individual/en/products/251875/\nCMX1.L,IE00B5WHFQ43,iShares,,,,,,0.65,116480000,USD,2026-10-31,2026-11-04,,"Physical, replication detail not specified",,Ireland,6,,,,https://www.ishares.com/uk/individual/en/products/253734/\nLTAM.L,IE00B27YCK28,iShares,,,,,,0.2,1921140000,USD,2026-10-31,2026-11-04,Physical sampling,Physical optimised; matches sampling classification,Dist,Ireland,,,,,https://www.ishares.com/uk/individual/en/products/251856/\nFWRG.L,IE000716YHJ7,Invesco,Invesco FTSE All-World UCITS ETF Acc,,,FTSE All-World,,0.15,5184690000,USD,2026-09-30,2026-09-30,,"Physical, replication detail not specified",Acc,Ireland,,,,,https://www.invesco.com/content/dam/invesco/emea/en/product-documents/etf/share-class/factsheet/IE000716YHJ7_factsheet_en.pdf\nEQQQ.L,IE0032077012,Invesco,,,,,,0.3,21610380000,USD,2026-09-30,2026-09-30,,"Physical, replication detail not specified",,,,,,,https://www.invesco.com/content/dam/invesco/emea/en/product-documents/etf/share-class/factsheet/IE0032077012_factsheet_en.pdf\nHMCX.L,IE00B64PTF05,HSBC,,,,FTSE 250 Gross,"Issuer\'s reported 3Y NAV tracking error, not indicative price-based TE.",0.09,60311075,GBP,2026-09-30,2026-09-30,Physical full,Physical full; 3-year tracking error is 0.07%,Dist,Ireland,,0.07,,,\nISPY.L,IE00BYPLS672,L&G,,,,,,0.69,3924100000,USD,2026-11-05,2026-11-05,Physical full,Physical full,,,,,,,\nSMH.L,IE00BMC38736,VanEck,VanEck Semiconductor UCITS ETF,Thematic,Semiconductors,MarketVector US Listed Semiconductor 10% Capped Screened,USD LSE listing SMH; GBP LSE listing SMGB. Old SEMI.L line was not evidenced.,0.35,8324900000,USD,2026-10-31,2026-10-31,Physical full,Physical full,Acc,Ireland,,,,,https://www.vaneck.com/uk/en/library/fact-sheets/smh-fact-sheet.pdf\nFRIN.L,IE00BHZRQZ17,Franklin Templeton,,,,,FRIN is the GBP LSE ticker; USD LSE listing is FLXI.,0.19,2400000000,USD,2026-11-06,2026-11-06,Physical full,Physical full,,,,,,,https://www.franklintempleton.co.uk/our-funds/etf/price-and-performance/products/27853/SINGLCLASS/IE00BHZRQZ17\nFRXT.L,IE000CM02H85,Franklin Templeton,,,,,FRXT is the GBP LSE ticker; USD LSE listing is FLXT.,0.19,1120000000,USD,2026-11-06,2026-11-06,Physical full,Physical full,,,,,,,https://www.franklintempleton.co.uk/our-funds/etf/price-and-performance/products/32637/SINGLCLASS/IE000CM02H85\nFVUB.L,IE00BHZRQY00,Franklin Templeton,,,,,FVUB is the GBP LSE ticker; USD LSE listing is FLXB.,0.19,229440000,USD,2026-11-06,2026-11-06,Physical full,Physical full,,,,,,,https://www.franklintempleton.co.uk/our-funds/etf/price-and-performance/products/27851/SINGLCLASS/IE00BHZRQY00\nFLXK.L,IE00BHZRR030,Franklin Templeton,Franklin FTSE Korea UCITS ETF,Equity,South Korea,FTSE Korea 30/18 Capped,^KS11,0.09,4030000000,USD,2026-11-06,2026-11-06,Physical full,Physical full,Acc,Ireland,,,,,https://www.franklintempleton.co.uk/our-funds/etf/price-and-performance/products/27854/SINGLCLASS/IE00BHZRR030\nKSA.L,IE000C7DDDX4,Franklin Templeton,Franklin FTSE Saudi Arabia UCITS ETF,Equity,Saudi Arabia,FTSE Saudi Arabia 30/18 Capped,"KSA is the LSE USD ticker, FLXS is the Xetra ticker; very small fund.",0.39,5780000,USD,2026-11-06,2026-11-06,Physical full,Physical full,Acc,Ireland,,,,,https://www.franklintempleton.co.uk/our-funds/etf/price-and-performance/products/41675/SINGLCLASS/IE000C7DDDX4\nCG1.L,FR0010655712,Amundi,Amundi DAX UCITS ETF,Equity,Germany DAX,DAX,"Amount €1,446.41m captured 8 November; exact NAV date not visible. Different ISIN from C001.DE.",.10,1446410000,EUR,,2026-11-08,,Direct physical; full vs sampled unspecified,Mixed,,,,,,https://www.amundietf.co.uk/en/individual/products/equity/amundi-dax-ucits-etf/fr0010655712\nCACX.L,FR0007052782,Amundi,Amundi CAC 40 UCITS ETF Dist,Equity,France,CAC 40,^FCHI,.25,4233280000,EUR,,2026-11-08,,Direct physical; full vs sampled unspecified,Dist,France,,,,,https://www.amundietf.co.uk/en/professional/products/equity/amundi-cac-40-ucits-etf-dist/fr0007052782\nRBOT.L,IE00BYZK4552,iShares,iShares Automation & Robotics UCITS ETF Acc,Thematic,Robotics,STOXX Global Automation & Robotics Net USD,,0.4,5525810000,USD,2026-10-31,2026-11-08,Physical sampling,,Acc,Ireland,6,,,"Physical optimised. Fund AUM differs from USD share-class assets $5,187.98m.",\nXMJP.L,LU0274209740,Xtrackers,Xtrackers MSCI Japan UCITS ETF 1C,Equity,Japan,MSCI Japan,^N225,0.12,6470000000,GBP,2026-11-05,2026-11-05,Physical full,Physical full,Acc,Luxembourg,,,0.0634,"Fund AUM as of 5 Nov, distinct from fund base JPY.",\nXDWD.L,IE00BJ0KDQ92,Xtrackers,Xtrackers MSCI World UCITS ETF 1C,Equity,Developed world,MSCI World,URTH,0.12,22510000000,GBP,,2026-11-08,Physical full,Physical full,Acc,Ireland,,,,Issuer page/secondary listing verified USD LSE line XDWD; same ISIN GBX XWLD.,\nXDEW.L,IE00BLNMYC90,Xtrackers,Xtrackers S&P 500 Equal Weight UCITS ETF 1C,Equity,US equal weight,S&P 500 Equal Weight,^GSPC,0.15,11900000000,GBP,,2026-11-08,Physical full,Physical full,Acc,Ireland,,,,Issuer LSE USD line XDEW; GBX line XDWE. SP500 price index is not fund benchmark.,https://etf.dws.com/en-gb/IE00BLNMYC90-s-p-500-equal-weight-ucits-etf-1c/\nXMTD.L,LU0292109187,Xtrackers,Xtrackers MSCI Taiwan UCITS ETF 1C,Equity,Taiwan,MSCI Taiwan 20-35 Custom,^TWII,0.65,711890000,USD,2026-09-30,2026-09-30,Physical full,Physical full,Acc,Luxembourg,,,,Different share class/ISIN from XTMT.L; GBX line XMTW.,https://etf.dws.com/en-gb/LU0292109187-msci-taiwan-ucits-etf-1c/\nXMBR.L,LU0292109344,Xtrackers,Xtrackers MSCI Brazil UCITS ETF 1C,Equity,Brazil,MSCI Brazil TRN,^BVSP,0.25,283540000,USD,2026-09-30,2026-09-30,,Physical; subtype unverified,Acc,Luxembourg,,,,Issuer factsheet 30 Sept 2026,\nXMEX.L,LU0476289466,Xtrackers,Xtrackers MSCI Mexico UCITS ETF 1C,Equity,Mexico,MSCI Mexico TRN,^MXX,0.65,306900000,USD,2026-09-30,2026-09-30,,Physical; subtype unverified,Acc,Luxembourg,,,,Issuer factsheet 30 Sept 2026,\nXMLA.L,LU0292108619,Xtrackers,Xtrackers MSCI EM Latin America Swap UCITS ETF 1C,Equity,Latin America,MSCI EM Latin America TRN,,0.4,130930000,USD,2026-09-30,2026-09-30,Synthetic swap,Synthetic swap,Acc,Luxembourg,,,,Benchmark switched 1 June 2026; earlier index not directly comparable; benchmarkChangeDate=2026-06-01,\nXMAF.L,LU0592217524,Xtrackers,Xtrackers MSCI Africa Top 50 Swap UCITS ETF 1C,Equity,Africa,MSCI EFM Africa Top 50 Capped TRN,,0.65,85700000,USD,2026-09-30,2026-09-30,Synthetic swap,Synthetic swap,Acc,Luxembourg,,,,Emerging and frontier exposure,\nXDEX.L,IE00BM67HJ62,Xtrackers,Xtrackers MSCI EM ex China UCITS ETF 1C,Equity,EM ex China,MSCI EM ex China,EEM,0.16,131500000,GBP,2026-09-30,2026-09-30,,Physical; subtype unverified,Acc,Ireland,,,,Benchmark changed July 2024; EEM proxy includes China; benchmarkChangeDate=2024-07-31,https://etf.dws.com/en-gb/IE00BM67HJ62-msci-emerging-markets-ex-china-ucits-etf-1c/\nXDAX.L,LU0274211480,Xtrackers,Xtrackers DAX UCITS ETF 1C,Equity,Germany DAX,DAX,^GDAXI,0.09,6090000000,GBP,,2026-11-08,,Physical; subtype unverified,Acc,Luxembourg,,,0.0008,Issuer current listing screenshot AUM £6.09bn,\nLSPX.L,LU0496786657,Amundi,Amundi Core S&P 500 Swap UCITS ETF USD Dist,Equity,United States,S&P 500,,.05,32749140000,USD,,2026-11-08,Synthetic swap,Synthetic swap disclosed in product name; exposure amounts/counterparties unavailable.,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nSP5G.L,LU1950341179,Amundi,Amundi Core S&P 500 Swap UCITS ETF GBP Hedged Dist,Equity,United States,S&P 500,,.05,24301510000,GBP,,2026-11-08,Synthetic swap,Synthetic swap disclosed in product name; exposure amounts/counterparties unavailable.,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nMEUD.L,LU0908500753,Amundi,Amundi Core STOXX Europe 600 UCITS ETF Acc,Equity,Europe,STOXX Europe 600,,.07,22784870000,EUR,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nLCJP.L,LU1781541252,Amundi,Amundi Core MSCI Japan UCITS ETF Acc,Equity,Japan,MSCI Japan,,.12,1080070450000,JPY,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nLCJG.L,LU1781541682,Amundi,Amundi Core MSCI Japan UCITS ETF GBP Hedged Acc,Equity,Japan,MSCI Japan GBP Hedged,,.20,5076750000,GBP,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nBNKE.L,LU1829219390,Amundi,Amundi Euro Stoxx Banks UCITS ETF Acc,Equity,Eurozone,EURO STOXX Banks,,.30,6009750000,EUR,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nMSED.L,LU1681047236,Amundi,Amundi Core EURO STOXX 50 UCITS ETF EUR Acc,Equity,Eurozone,EURO STOXX 50,,.09,5162590000,EUR,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nMSEX.L,FR0012399772,Amundi,Amundi EURO STOXX 50 II UCITS ETF GBP Hedged Acc,Equity,Eurozone,EURO STOXX 50 GBP Hedged,,.20,4057940000,GBP,,2026-11-08,,,Acc,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nEMXN.L,LU2009202107,Amundi,Amundi MSCI Emerging ex China Swap UCITS ETF Acc,Equity,EM ex China,MSCI EM ex China,,.15,4268790000,USD,,2026-11-08,Synthetic swap,Synthetic swap disclosed in product name; exposure amounts/counterparties unavailable.,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nTNOG.L,LU0533033741,Amundi,Amundi MSCI World Information Technology UCITS ETF USD Acc,Thematic,Technology,MSCI World Information Technology,,.30,3207220000,USD,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nGILS.L,LU1407892592,Amundi,Amundi Core UK Government Bond UCITS ETF Dist,Bonds,UK gilts,UK Government Bonds,,.05,2019950000,GBP,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Yield to maturity and effective duration NOT obtained.",\nU71G.L,LU1407888053,Amundi,Amundi US Treasury Bond 7-10Y UCITS ETF Dist,Bonds,US Treasury 7-10y,US Treasury 7-10Y,,.06,2306940000,USD,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Yield to maturity and effective duration NOT obtained.",\nLCUK.L,LU1781541096,Amundi,Amundi UK Equity All Cap UCITS ETF Dist,Equity,UK FTSE All Share,UK All Cap,,.04,1697040000,GBP,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nCOMG.L,LU1829218749,Amundi,Amundi Bloomberg Equal-weight Commodity ex-Agriculture UCITS ETF Acc,Commodity ETC,Broad commodities,Bloomberg Equal-weight Commodity ex Agriculture,,.30,1846480000,EUR,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Classified as commodity ETF; derivative replication not confirmed.",\nWATL.L,FR0010527275,Amundi,Amundi MSCI Water UCITS ETF Dist,Thematic,Water,MSCI Water,,.60,1610060000,EUR,,2026-11-08,,,Dist,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nMFEX.L,LU1646360971,Amundi,Amundi Core MSCI EMU UCITS ETF Dist,Equity,Eurozone,MSCI EMU,,.12,1406830000,EUR,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nTIPH.L,LU1452600601,Amundi,Amundi US TIPS UCITS ETF GBP Hedged Dist,Bonds,US inflation linked,US TIPS GBP Hedged,,.12,1170470000,GBP,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Yield to maturity and effective duration NOT obtained.",\nTIPG.L,LU1452600270,Amundi,Amundi US TIPS UCITS ETF Dist,Bonds,US inflation linked,US TIPS,,.09,1577340000,USD,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Yield to maturity and effective duration NOT obtained.",\nMFDD.L,LU0908501132,Amundi,Amundi MSCI EMU ESG Broad Transition UCITS ETF Dist,Equity,Eurozone,MSCI EMU ESG Broad Transition,,.12,1399380000,EUR,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nDAXX.L,LU0252633754,Amundi,Amundi DAX II UCITS ETF Acc,Equity,Germany DAX,DAX,,.15,1398370000,EUR,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nESGL.L,LU1940199711,Amundi,Amundi MSCI Europe ESG Selection UCITS ETF Acc,Equity,Europe,MSCI Europe ESG Selection,,.20,1273930000,EUR,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nCRPX.L,LU1829219127,Amundi,Amundi EUR Corporate Bond Climate Paris Aligned UCITS ETF Acc,Bonds,EUR investment grade,EUR Corporate Climate Paris Aligned,,.14,1144940000,EUR,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nCM9.PA,FR0010756114,Amundi,Amundi MSCI World Ex EMU UCITS ETF Acc,Equity,Developed world,MSCI World ex EMU,,.35,992120000,EUR,,2026-11-08,,,Acc,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nC3M.PA,FR0010754200,Amundi,Amundi Euro Government Bond 0-6 M UCITS ETF Acc,Bonds,EUR government 0-6m,EUR Sovereign 0-6M,,.14,970890000,EUR,,2026-11-08,,,Acc,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nINRL.L,FR0010375766,Amundi,Amundi MSCI India Swap UCITS ETF USD Acc,Equity,India,MSCI India,,.85,1032670000,USD,,2026-11-08,Synthetic swap,Synthetic swap disclosed in product name; exposure amounts/counterparties unavailable.,Acc,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nL100.L,LU1650492173,Amundi,Amundi Core FTSE 100 Swap UCITS ETF Acc,Equity,UK FTSE 100,FTSE 100,,.14,718000000,GBP,,2026-11-08,Synthetic swap,Synthetic swap disclosed in product name; exposure amounts/counterparties unavailable.,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nU13G.L,LU1407887162,Amundi,Amundi US Treasury Bond 1-3Y UCITS ETF Dist,Bonds,US Treasury 1-3y,US Treasury 1-3Y,,.06,914910000,USD,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Yield to maturity and effective duration NOT obtained.",\nGIL5.L,LU1439943090,Amundi,Amundi UK Government Bond 0-5Y UCITS ETF Dist,Bonds,UK short gilts,UK Gilts 0-5Y,,.05,665400000,GBP,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Yield to maturity and effective duration NOT obtained.",\nJPNL.L,FR0010245514,Amundi,Amundi Japan TOPIX II UCITS ETF EUR Dist,Equity,Japan,TOPIX,,.45,633360000,EUR,,2026-11-08,,,Dist,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nMEUG.L,FR0010261198,Amundi,Amundi MSCI Europe UCITS ETF Acc,Equity,Europe,MSCI Europe,,.25,627140000,EUR,,2026-11-08,,,Acc,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nLGWU.DE,LU1598689153,Amundi,Amundi MSCI EMU Small Cap ESG Broad Transition UCITS ETF Dist,Equity,Eurozone,MSCI EMU Small Cap,,.40,563380000,EUR,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nU10G.L,LU1407890620,Amundi,Amundi US Treasury Bond Long Dated UCITS ETF Dist,Bonds,US Treasury long dated,US Treasury Long-Dated,,.06,596420000,USD,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Yield to maturity and effective duration NOT obtained.",\nJPXX.L,LU1646359619,Amundi,Amundi MSCI Japan SRI Climate Paris Aligned UCITS ETF GBP Hedged Acc,Equity,Japan,MSCI Japan SRI GBP Hedged,,.20,428430000,GBP,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nC5E.PA,FR0010790980,Amundi,Amundi Stoxx Europe 50 UCITS ETF Acc,Equity,Europe,STOXX Europe 50,,.15,510230000,EUR,,2026-11-08,,,Acc,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nASIL.L,LU1900068914,Amundi,Amundi MSCI China ESG Selection Extra UCITS ETF Acc,Equity,China,MSCI China ESG Selection,,.65,478480000,EUR,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nCLIM.L,LU1563454310,Amundi,Amundi Global Aggregate Green Bond UCITS ETF Acc,Bonds,Global green bonds,Global Aggregate Green Bond,,.25,402860000,EUR,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nKLMG.L,LU1563455630,Amundi,Amundi Global Aggregate Green Bond UCITS ETF GBP Hedged Dist,Bonds,Global green bonds GBP hedged,Global Aggregate Green Bond GBP Hedged,,.30,335620000,GBP,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nCD8.PA,FR0010717090,Amundi,Amundi MSCI EMU High Dividend UCITS ETF Acc,Equity,Eurozone,MSCI EMU High Dividend,,.30,401320000,EUR,,2026-11-08,,,Acc,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nDTEC.L,LU2023678282,Amundi,Amundi Global Memory Chips UCITS ETF Acc,Thematic,Semiconductors,Global Memory Chips,,.45,445110000,USD,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nU37G.L,LU1407888996,Amundi,Amundi US Treasury Bond 3-7Y UCITS ETF Dist,Bonds,US Treasury 3-7y,US Treasury 3-7Y,,.06,425560000,USD,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Yield to maturity and effective duration NOT obtained.",\nGILI.L,LU1407893301,Amundi,Amundi UK Government Inflation-Linked Bond UCITS ETF Dist,Bonds,UK index linked,UK Government Inflation Linked,,.07,229850000,GBP,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Yield to maturity and effective duration NOT obtained.",\nANRJ.L,FR0010930644,Amundi,Amundi Global Hydrogen UCITS ETF Acc,Thematic,Hydrogen,Global Hydrogen,,.45,198890000,EUR,,2026-11-08,,,Acc,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nGIST.L,LU1910939849,Amundi,Amundi Global Government Inflation-Linked Bond 1-10Y UCITS ETF Dist,Bonds,Global inflation-linked,Global Government Inflation Linked 1-10Y,,.09,165960000,USD,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible. Yield to maturity and effective duration NOT obtained.",\nELCR.L,LU2023679090,Amundi,Amundi MSCI Smart Mobility UCITS ETF Acc,Thematic,Smart mobility,MSCI Smart Mobility,,.45,158470000,USD,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nUSIX.L,LU1285959703,Amundi,Amundi USD Corporate Bond Climate Paris Aligned UCITS ETF Dist,Bonds,USD investment grade,USD Corporate Climate Paris Aligned,,.14,128520000,USD,,2026-11-08,,,Dist,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nGHYU.L,LU2099295466,Amundi,Amundi Global High Yield Corporate Bond ESG UCITS ETF USD Acc,Bonds,USD high yield,Global High Yield ESG,,.25,110130000,USD,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nEBUY.L,LU2023678878,Amundi,Amundi MSCI Digital Economy UCITS ETF Acc,Thematic,Digital economy,MSCI Digital Economy,,.45,105030000,USD,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nCNAL.L,FR0011720911,Amundi,Amundi MSCI China A UCITS ETF Acc,Equity,China,MSCI China A,,.35,95010000,USD,,2026-11-08,,,Acc,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nMILL.L,LU2023678449,Amundi,Amundi Global Sport and eSport UCITS ETF Acc,Thematic,Sport & eSport,Global Sport & eSport,,.45,18970000,USD,,2026-11-08,,,Acc,Luxembourg,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\nCFR.L,FR0010655704,Amundi,Amundi CAC Transition Climate UCITS ETF,Equity,France,CAC Climate Transition,,.25,11500000,EUR,,2026-11-08,,,Acc,France,,,,"Issuer product finder screenshot, captured 8 Nov 2026; the AUM reporting date was not visible.",\n'
US_BONDS_JSON = [{'symbol': 'AGG', 'name': 'iShares Core U.S. Aggregate Bond ETF', 'netExpensePct': 0.03, 'assetsUsd': 139076000000, 'trailing12mYieldPct': 4.12, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'SGOV', 'name': 'iShares 0-3 Month Treasury Bond ETF', 'netExpensePct': 0.09, 'assetsUsd': 116516000000, 'trailing12mYieldPct': 3.63, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'MUB', 'name': 'iShares National Muni Bond ETF', 'netExpensePct': 0.05, 'assetsUsd': 55049000000, 'trailing12mYieldPct': 3.28, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'IUSB', 'name': 'iShares Core Universal USD Bond ETF', 'netExpensePct': 0.06, 'assetsUsd': 50428000000, 'trailing12mYieldPct': 4.34, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'TLT', 'name': 'iShares 20+ Year Treasury Bond ETF', 'netExpensePct': 0.15, 'assetsUsd': 48863000000, 'trailing12mYieldPct': 4.77, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'IEF', 'name': 'iShares 7-10 Year Treasury Bond ETF', 'netExpensePct': 0.15, 'assetsUsd': 44637000000, 'trailing12mYieldPct': 4.05, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'GOVT', 'name': 'iShares U.S. Treasury Bond ETF', 'netExpensePct': 0.05, 'assetsUsd': 43253000000, 'trailing12mYieldPct': 3.77, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'MBB', 'name': 'iShares MBS ETF', 'netExpensePct': 0.04, 'assetsUsd': 35962000000, 'trailing12mYieldPct': 4.42, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'LQD', 'name': 'iShares iBoxx $ Investment Grade Corporate Bond ETF', 'netExpensePct': 0.14, 'assetsUsd': 32950000000, 'trailing12mYieldPct': 4.83, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'SHY', 'name': 'iShares 1-3 Year Treasury Bond ETF', 'netExpensePct': 0.15, 'assetsUsd': 27537000000, 'trailing12mYieldPct': 3.6, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'USHY', 'name': 'iShares Broad USD High Yield Corporate Bond ETF', 'netExpensePct': 0.08, 'assetsUsd': 27505000000, 'trailing12mYieldPct': 7.14, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'IGSB', 'name': 'iShares 1-5 Year Investment Grade Corporate Bond ETF', 'netExpensePct': 0.04, 'assetsUsd': 23751000000, 'trailing12mYieldPct': 4.67, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'IGIB', 'name': 'iShares 5-10 Year Investment Grade Corporate Bond ETF', 'netExpensePct': 0.04, 'assetsUsd': 19618000000, 'trailing12mYieldPct': 5.07, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'USIG', 'name': 'iShares Broad USD Investment Grade Corporate Bond ETF', 'netExpensePct': 0.04, 'assetsUsd': 18048000000, 'trailing12mYieldPct': 4.93, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'HYG', 'name': 'iShares iBoxx $ High Yield Corporate Bond ETF', 'netExpensePct': 0.49, 'assetsUsd': 18024000000, 'trailing12mYieldPct': 6.09, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'BINC', 'name': 'iShares Flexible Income Active ETF', 'netExpensePct': 0.4, 'assetsUsd': 17051000000, 'trailing12mYieldPct': 5.75, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'IEI', 'name': 'iShares 3-7 Year Treasury Bond ETF', 'netExpensePct': 0.15, 'assetsUsd': 17047000000, 'trailing12mYieldPct': 3.79, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'STIP', 'name': 'iShares 0-5 Year TIPS Bond ETF', 'netExpensePct': 0.03, 'assetsUsd': 16866000000, 'trailing12mYieldPct': 4.61, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'TIP', 'name': 'iShares TIPS Bond ETF', 'netExpensePct': 0.18, 'assetsUsd': 14578000000, 'trailing12mYieldPct': 4.24, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'EMB', 'name': 'iShares J.P. Morgan USD Emerging Markets Bond ETF', 'netExpensePct': 0.39, 'assetsUsd': 13842000000, 'trailing12mYieldPct': 5.35, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'SUB', 'name': 'iShares Short-Term National Muni Bond ETF', 'netExpensePct': 0.07, 'assetsUsd': 13382000000, 'trailing12mYieldPct': 2.58, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'IAGG', 'name': 'iShares Core International Aggregate Bond ETF', 'netExpensePct': 0.07, 'assetsUsd': 13133000000, 'trailing12mYieldPct': 5.15, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'TLH', 'name': 'iShares 10-20 Year Treasury Bond ETF', 'netExpensePct': 0.15, 'assetsUsd': 12348000000, 'trailing12mYieldPct': 4.64, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'FLOT', 'name': 'iShares Floating Rate Bond ETF', 'netExpensePct': 0.15, 'assetsUsd': 11658000000, 'trailing12mYieldPct': 4.25, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'ICSH', 'name': 'iShares Ultra Short Duration Bond Active ETF', 'netExpensePct': 0.08, 'assetsUsd': 8902000000, 'trailing12mYieldPct': 4.12, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'SHYG', 'name': 'iShares 0-5 Year High Yield Corporate Bond ETF', 'netExpensePct': 0.3, 'assetsUsd': 7772000000, 'trailing12mYieldPct': 7.18, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'TFLO', 'name': 'iShares Treasury Floating Rate Bond ETF', 'netExpensePct': 0.15, 'assetsUsd': 7410000000, 'trailing12mYieldPct': 3.74, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'ICVT', 'name': 'iShares Convertible Bond ETF', 'netExpensePct': 0.2, 'assetsUsd': 6918000000, 'trailing12mYieldPct': 1.62, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}, {'symbol': 'CMF', 'name': 'iShares California Muni Bond ETF', 'netExpensePct': 0.08, 'assetsUsd': 5466000000, 'trailing12mYieldPct': 3.03, 'asOf': '2026-11-05', 'issuer': 'iShares US', 'domicile': 'US', 'ukRetailAccessible': 'Not established'}]

# Supplemental 8 Nov 2026 audit, and Vanguard audited FY2026 fund-level disclosure.
# Audit turnover is on-exchange proxy, not all market trading or bid/ask spread.
AUDIT_EVIDENCE = [{'symbol': 'VWRP.L', 'isin': 'IE00BK5BQT80', 'medianTurnoverGbpM': 54.01, 'zeroVolumeDays3m': 0, 'flags': 'Catalogue CSV TER 0.19 superseded by issuer snapshot 0.14 | TD/TE: Vanguard factsheet & UK site, 30-Sep-26, USD NAV vs FTSE All-World', 'lendingPolicy': 'Yes. Fund kept 92.3% of lending revenue, agent 7.7% (Vanguard Funds plc AR June 2025, via LedgerTouch)', 'lendingLevel': 'Vanguard: typically low single-digit % of NAV (group-wide, not fund-specific)', 'collateral': 'Sovereign debt only (Vanguard AR)', 'counterparty': 'n/a (physical)', 'auditAum': 88.84, 'auditAumUnit': 'USD bn', 'auditAumSource': 'GitHub site (issuer-sourced)', 'auditReplication': 'Physical - sampling (representative sample)', 'auditReplicationConfirmed': True, 'auditTd1y': 0.05, 'auditTd3y': 0, 'auditTd5y': -0.01}, {'symbol': 'VWRL.L', 'isin': 'IE00B3RBWM25', 'medianTurnoverGbpM': 11.81, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': 'Yes. Fund kept 92.3% of lending revenue, agent 7.7% (Vanguard Funds plc AR June 2025, via LedgerTouch)', 'lendingLevel': 'Vanguard: typically low single-digit % of NAV (group-wide, not fund-specific)', 'collateral': 'Sovereign debt only (Vanguard AR)', 'counterparty': '', 'auditAum': 88.84, 'auditAumUnit': 'USD bn', 'auditAumSource': 'GitHub site (issuer-sourced)', 'auditReplication': 'Physical - sampling (same fund as VWRP)', 'auditReplicationConfirmed': True, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'FWRG.L', 'isin': 'IE000716YHJ7', 'medianTurnoverGbpM': 7.04, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 5.22, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Invesco UK site + factsheet 30-Sep-26 (FWRA Acc line)', 'auditReplication': 'Physical (type not stated)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'SWDA.L', 'isin': 'IE00B4L5Y983', 'medianTurnoverGbpM': 5.42, 'zeroVolumeDays3m': 0, 'flags': 'TD: BlackRock NAV vs MSCI World Net, 30-Jun-26 (latest found). Lending return 0.02%', 'lendingPolicy': 'Yes - BlackRock programme', 'lendingLevel': 'Avg 8.08%, max 11.16% (12m to 30-Jun-26)', 'collateral': '108.1% of loan', 'counterparty': 'Borrower list not disclosed', 'auditAum': 153.26, 'auditAumUnit': 'USD bn', 'auditAumSource': 'BlackRock product page 25-Sep-26', 'auditReplication': 'Physical - optimised (sampling)', 'auditReplicationConfirmed': True, 'auditTd1y': 0.01, 'auditTd3y': 0.04, 'auditTd5y': 0.06}, {'symbol': 'SWRD.L', 'isin': '', 'medianTurnoverGbpM': 3.65, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 21.99, 'auditAumUnit': 'USD bn', 'auditAumSource': 'GitHub site (issuer-sourced)', 'auditReplication': 'Physical sampling', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'CSPX.L', 'isin': 'IE00B5BMR087', 'medianTurnoverGbpM': 75.23, 'zeroVolumeDays3m': 0, 'flags': 'TD: BlackRock NAV vs S&P 500 (net), 30-Sep-26. Lending return 0.00%', 'lendingPolicy': 'Yes - BlackRock programme; fund keeps 62.5% of income', 'lendingLevel': 'Avg 2.59%, max 4.26% (12m to 30-Jun-26)', 'collateral': '109.5% of loan; equities, govt bonds, cash; 102.5-112% range', 'counterparty': 'Borrower list not disclosed; indemnified programme', 'auditAum': 153.02, 'auditAumUnit': 'USD bn', 'auditAumSource': 'iShares/BlackRock product page 02-Nov-26', 'auditReplication': 'Physical - full replication', 'auditReplicationConfirmed': True, 'auditTd1y': 0.13, 'auditTd3y': 0.16, 'auditTd5y': 0.18}, {'symbol': 'VUAG.L', 'isin': 'IE00BFMXXD54', 'medianTurnoverGbpM': 29.51, 'zeroVolumeDays3m': 0, 'flags': 'TD/TE: Vanguard factsheet & UK site, 30-Sep-26, vs S&P 500 Net TR (30% WHT)', 'lendingPolicy': 'Yes. Fund kept 92.3% of lending revenue, agent 7.7% (Vanguard Funds plc AR June 2025, via LedgerTouch)', 'lendingLevel': '0.016% of NAV: USD 11.1m on loan vs USD 71.3bn (30-Jun-25)', 'collateral': '106.6% of loan; sovereign debt only (30-Jun-25)', 'counterparty': 'n/a (physical)', 'auditAum': 89.4, 'auditAumUnit': 'USD bn', 'auditAumSource': 'GitHub site (issuer-sourced)', 'auditReplication': 'Physical - full (sampling only where impractical)', 'auditReplicationConfirmed': True, 'auditTd1y': 0.12, 'auditTd3y': 0.16, 'auditTd5y': 0.18}, {'symbol': 'IUSA.L', 'isin': 'IE0031442068', 'medianTurnoverGbpM': 5.63, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'CNDX.L', 'isin': 'IE00B53SZB19', 'medianTurnoverGbpM': 28.57, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'EQQQ.L', 'isin': '', 'medianTurnoverGbpM': 12.9, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 21.61, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Invesco factsheet 30-Sep-26', 'auditReplication': 'Physical (type not stated)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'R2US.L', 'isin': '', 'medianTurnoverGbpM': 3.09, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 4.75, 'auditAumUnit': 'USD bn', 'auditAumSource': 'GitHub site (issuer-sourced)', 'auditReplication': 'Physical sampling', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'VUKE.L', 'isin': 'IE00B810Q511', 'medianTurnoverGbpM': 15.4, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': 'Yes. Fund kept 92.3% of lending revenue, agent 7.7% (Vanguard Funds plc AR June 2025, via LedgerTouch)', 'lendingLevel': '0.28% of NAV, 1.83% of lendable assets: GBP 12.8m (31-Dec-22 - stale)', 'collateral': 'Sovereign debt only (Vanguard AR)', 'counterparty': '', 'auditAum': 6.58, 'auditAumUnit': 'GBP bn', 'auditAumSource': 'GitHub site (issuer-sourced)', 'auditReplication': 'Physical', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'ISF.L', 'isin': 'IE0005042456', 'medianTurnoverGbpM': 41.9, 'zeroVolumeDays3m': 0, 'flags': 'TD: iShares NAV vs FTSE 100 net, 30-Sep-26. Lags index by more than its 0.07% TER', 'lendingPolicy': 'Yes - BlackRock programme', 'lendingLevel': 'Avg 4.82% (12m to 31-Mar-26); max 8.14% latest period', 'collateral': '109.8% of loan', 'counterparty': 'Borrower list not disclosed', 'auditAum': 16.6, 'auditAumUnit': 'GBP bn', 'auditAumSource': 'iShares product page 20-Oct-26', 'auditReplication': 'Physical - replicated (full)', 'auditReplicationConfirmed': True, 'auditTd1y': -0.1, 'auditTd3y': -0.11, 'auditTd5y': -0.09}, {'symbol': 'HMCX.L', 'isin': 'IE00B64PTF05', 'medianTurnoverGbpM': 0.1, 'zeroVolumeDays3m': 0, 'flags': 'GBP60m fund vs GBP2.15bn Vanguard on same index - closure risk', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 0.0603, 'auditAumUnit': 'GBP bn', 'auditAumSource': 'HSBC monthly report 30-Sep-26', 'auditReplication': 'Physical - full', 'auditReplicationConfirmed': True, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'VMIG.L', 'isin': 'IE00BFMXVQ44', 'medianTurnoverGbpM': 1.37, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': 'Yes. Fund kept 92.3% of lending revenue, agent 7.7% (Vanguard Funds plc AR June 2025, via LedgerTouch)', 'lendingLevel': 'Vanguard: typically low single-digit % of NAV (group-wide, not fund-specific)', 'collateral': 'Sovereign debt only (Vanguard AR)', 'counterparty': '', 'auditAum': 2.15, 'auditAumUnit': 'GBP bn', 'auditAumSource': 'GitHub site (issuer-sourced)', 'auditReplication': 'Physical', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'VMID.L', 'isin': 'IE00BKX55Q28', 'medianTurnoverGbpM': 2.14, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': 'Yes. Fund kept 92.3% of lending revenue, agent 7.7% (Vanguard Funds plc AR June 2025, via LedgerTouch)', 'lendingLevel': 'Vanguard: typically low single-digit % of NAV (group-wide, not fund-specific)', 'collateral': 'Sovereign debt only (Vanguard AR)', 'counterparty': '', 'auditAum': 2.15, 'auditAumUnit': 'GBP bn', 'auditAumSource': 'GitHub site (issuer-sourced)', 'auditReplication': 'Physical', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'MIDD.L', 'isin': 'IE00B00FV128', 'medianTurnoverGbpM': 13.06, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Physical sampling', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'VERX.L', 'isin': '', 'medianTurnoverGbpM': 4.15, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': 'Yes. Fund kept 92.3% of lending revenue, agent 7.7% (Vanguard Funds plc AR June 2025, via LedgerTouch)', 'lendingLevel': 'Vanguard: typically low single-digit % of NAV (group-wide, not fund-specific)', 'collateral': 'Sovereign debt only (Vanguard AR)', 'counterparty': '', 'auditAum': 5.35, 'auditAumUnit': 'EUR bn', 'auditAumSource': 'GitHub site (issuer-sourced)', 'auditReplication': 'Physical', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IMEU.L', 'isin': 'IE00B1YZSC51', 'medianTurnoverGbpM': 3.63, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'EUE.L', 'isin': 'IE0008471009', 'medianTurnoverGbpM': 2.13, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'XDAX.L', 'isin': 'LU0274211480', 'medianTurnoverGbpM': 0.44, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 6.09, 'auditAumUnit': 'GBP bn', 'auditAumSource': 'Xtrackers product finder (1C/1D)', 'auditReplication': 'Physical full', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'EXS1.DE', 'isin': 'DE0005933931', 'medianTurnoverGbpM': 8.69, 'zeroVolumeDays3m': 0, 'flags': 'Code flags ticker/exchange mismatch (iShares lists DAXEX on Xetra)', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Physical full', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'C001.DE', 'isin': 'LU2611732046', 'medianTurnoverGbpM': 0.9, 'zeroVolumeDays3m': 2, 'flags': 'Catalogue ISIN LU2611732046; Amundi DAX screenshot (FR0010655712, 0.10%, EUR1.45bn) is a DIFFERENT fund - do not merge', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Physical full', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'CAC.PA', 'isin': 'FR0007052782', 'medianTurnoverGbpM': 1.59, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 4.23, 'auditAumUnit': 'EUR bn', 'auditAumSource': 'Amundi UK site', 'auditReplication': 'Physical - direct (type not stated)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'SJPA.L', 'isin': 'IE00B4L5YX21', 'medianTurnoverGbpM': 0.86, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'XMJP.L', 'isin': 'LU0274209740', 'medianTurnoverGbpM': 0.2, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 6.47, 'auditAumUnit': 'GBP bn', 'auditAumSource': 'Xtrackers product page 05-Nov-26', 'auditReplication': 'Physical - direct (type not stated)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'VAPX.L', 'isin': '', 'medianTurnoverGbpM': 1.27, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': 'Yes. Fund kept 92.3% of lending revenue, agent 7.7% (Vanguard Funds plc AR June 2025, via LedgerTouch)', 'lendingLevel': 'Vanguard: typically low single-digit % of NAV (group-wide, not fund-specific)', 'collateral': 'Sovereign debt only (Vanguard AR)', 'counterparty': '', 'auditAum': 2.91, 'auditAumUnit': 'USD bn', 'auditAumSource': 'GitHub site (issuer-sourced)', 'auditReplication': 'Physical', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'AEJL.L', 'isin': 'LU1900068328', 'medianTurnoverGbpM': 0.01, 'zeroVolumeDays3m': 3, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': 'Swap structure confirmed; counterparty not found - issuer page needed. UCITS cap 10% NAV', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Synthetic swap', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'EIMI.L', 'isin': 'IE00BKM4GZ66', 'medianTurnoverGbpM': 13.5, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'LEMA.L', 'isin': 'LU2573967036', 'medianTurnoverGbpM': 1.77, 'zeroVolumeDays3m': 0, 'flags': 'Amundi Core MSCI EM Swap', 'lendingPolicy': 'No lending of substitute basket (Amundi policy per Morningstar - dated)', 'lendingLevel': '', 'collateral': '', 'counterparty': 'Fund-level counterparty not found; Amundi OTC panel of ~18 banks (30-Sep-25); UCITS cap 10% NAV', 'auditAum': 10.4, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Amundi factsheet 28-Feb-26', 'auditReplication': 'Synthetic - unfunded swap (substitute basket)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'AEME.L', 'isin': 'LU1437017350', 'medianTurnoverGbpM': 0.22, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Physical full', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'XDEX.L', 'isin': 'IE00BM67HJ62', 'medianTurnoverGbpM': 0.05, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 0.1315, 'auditAumUnit': 'GBP bn', 'auditAumSource': 'Xtrackers factsheet 30-Sep-26', 'auditReplication': 'Physical - direct (type not stated)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'EMXN.L', 'isin': 'LU2009202107', 'medianTurnoverGbpM': 1.08, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': 'Swap structure confirmed; counterparty not found - issuer page needed. UCITS cap 10% NAV', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Synthetic swap', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'FRIN.L', 'isin': 'IE00BHZRQZ17', 'medianTurnoverGbpM': 0.41, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 2.4, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Franklin UK site 06-Nov-26', 'auditReplication': 'Physical - full', 'auditReplicationConfirmed': True, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'XCX5.L', 'isin': 'LU0514695187', 'medianTurnoverGbpM': 0.15, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': 'Counterparty not found in public snippets; check Xtrackers product page; UCITS cap 10% NAV', 'auditAum': 0.52, 'auditAumUnit': 'USD bn', 'auditAumSource': 'finanzen.net (third party) 2026', 'auditReplication': 'Synthetic - unfunded swap (substitute basket + swap)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'INDA.L', 'isin': 'IE000N70F6V6', 'medianTurnoverGbpM': 0.02, 'zeroVolumeDays3m': 49, 'flags': 'Traded on only 17 of 66 days - effectively illiquid on LSE', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': 'Swap structure confirmed; counterparty not found - issuer page needed. UCITS cap 10% NAV', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Synthetic swap', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'ICGA.L', 'isin': 'IE00BJ5JPG56', 'medianTurnoverGbpM': None, 'zeroVolumeDays3m': None, 'flags': 'Code flags: iShares identifies ICGA as MSCI China not China A, Xetra line; no Yahoo data', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Physical full', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'LCCG.L', 'isin': 'LU1841731745', 'medianTurnoverGbpM': 0.01, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': 'Swap structure confirmed; counterparty not found - issuer page needed. UCITS cap 10% NAV', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Synthetic swap', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'FRXT.L', 'isin': 'IE000CM02H85', 'medianTurnoverGbpM': 0.17, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 1.12, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Franklin UK site 06-Nov-26', 'auditReplication': 'Physical - full', 'auditReplicationConfirmed': True, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'XTMT.L', 'isin': 'LU2928641757', 'medianTurnoverGbpM': 0.08, 'zeroVolumeDays3m': 21, 'flags': 'Catalogue ISIN LU2928641757 is not the 1C class in the screenshot; Acc/Dist unresolved', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 0.712, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Xtrackers factsheet 30-Sep-26 - NB screenshot is 1C LU0292109187, catalogue ISIN differs', 'auditReplication': 'Physical - direct (type not stated)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'LTAM.L', 'isin': 'IE00B27YCK28', 'medianTurnoverGbpM': 1.58, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 1.921, 'auditAumUnit': 'USD bn', 'auditAumSource': 'iShares factsheet Oct-26', 'auditReplication': 'Physical (type not stated)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'XMLA.L', 'isin': 'LU0292108619', 'medianTurnoverGbpM': 0.09, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': 'Swap structure confirmed; counterparty not found - issuer page needed. UCITS cap 10% NAV', 'auditAum': 0.1309, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Xtrackers factsheet 30-Sep-26', 'auditReplication': 'Synthetic - swap', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'ALAU.PA', 'isin': 'LU1681045297', 'medianTurnoverGbpM': 0.11, 'zeroVolumeDays3m': 2, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': 'Swap structure confirmed; counterparty not found - issuer page needed. UCITS cap 10% NAV', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Synthetic swap', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'FVUB.L', 'isin': 'IE00BHZRQY00', 'medianTurnoverGbpM': 0.16, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 0.2294, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Franklin UK site 06-Nov-26', 'auditReplication': 'Physical - full', 'auditReplicationConfirmed': True, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'XMBR.L', 'isin': 'LU0292109344', 'medianTurnoverGbpM': 0.24, 'zeroVolumeDays3m': 1, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 0.2835, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Xtrackers factsheet 30-Sep-26', 'auditReplication': 'Physical - direct (type not stated)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'CMX1.L', 'isin': 'IE00B5WHFQ43', 'medianTurnoverGbpM': 0.03, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 0.1165, 'auditAumUnit': 'USD bn (share class)', 'auditAumSource': 'iShares factsheet Oct-26', 'auditReplication': 'Physical - replicated', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'XMEX.L', 'isin': 'LU0476289466', 'medianTurnoverGbpM': 0.06, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 0.3069, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Xtrackers factsheet 30-Sep-26', 'auditReplication': 'Physical - direct (type not stated)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'SPOL.L', 'isin': 'IE00B4M7GH52', 'medianTurnoverGbpM': 0.57, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 1.121, 'auditAumUnit': 'USD bn (share class)', 'auditAumSource': 'iShares factsheet Oct-26', 'auditReplication': 'Physical - replicated', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'CECL.L', 'isin': 'LU1900066462', 'medianTurnoverGbpM': None, 'zeroVolumeDays3m': None, 'flags': 'No price data - possibly delisted or wrong ticker | DELISTED from LSE (Amundi notice, LU1900066462) - remove from catalogue', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Synthetic swap', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'TURL.L', 'isin': 'LU1900067601', 'medianTurnoverGbpM': None, 'zeroVolumeDays3m': None, 'flags': 'No price data - possibly delisted or wrong ticker | DELISTED from LSE (Amundi notice, LU1900067601) - remove from catalogue', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Synthetic swap', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'ITKY.L', 'isin': 'IE00B1FZS574', 'medianTurnoverGbpM': 0.04, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 0.1019, 'auditAumUnit': 'USD bn (share class)', 'auditAumSource': 'iShares factsheet Oct-26', 'auditReplication': 'Physical - replicated', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'XMAF.L', 'isin': 'LU0592217524', 'medianTurnoverGbpM': 0.02, 'zeroVolumeDays3m': 7, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': 'Swap structure confirmed; counterparty not found - issuer page needed. UCITS cap 10% NAV', 'auditAum': 0.0857, 'auditAumUnit': 'USD bn', 'auditAumSource': 'Xtrackers factsheet 30-Sep-26', 'auditReplication': 'Synthetic - swap', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'LGQM.L', 'isin': 'LU1287022708', 'medianTurnoverGbpM': None, 'zeroVolumeDays3m': None, 'flags': 'No price data - possibly delisted or wrong ticker | Fund alive but LGQM is a Xetra/Stuttgart ticker - .L is wrong. Historic TD about -1.1% to -1.4% a year vs index (2017-2020, Lyxor factsheet)', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 0.095, 'auditAumUnit': 'EUR bn', 'auditAumSource': 'Third-party (TradingView/Eulerpool) 2026', 'auditReplication': 'Synthetic swap', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'SEMI.L', 'isin': '', 'medianTurnoverGbpM': 8.62, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 8.325, 'auditAumUnit': 'USD bn', 'auditAumSource': 'VanEck factsheet 31-Oct-26', 'auditReplication': 'Physical - full', 'auditReplicationConfirmed': True, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'RBOT.L', 'isin': 'IE00BYZK4552', 'medianTurnoverGbpM': 1.95, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 5.526, 'auditAumUnit': 'USD bn', 'auditAumSource': 'iShares factsheet Oct-26', 'auditReplication': 'Physical (type not stated)', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'INRG.L', 'isin': 'IE00B1XNHC34', 'medianTurnoverGbpM': 1.24, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 2.975, 'auditAumUnit': 'USD bn', 'auditAumSource': 'iShares factsheet Oct-26', 'auditReplication': 'Physical - replicated', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'ISPY.L', 'isin': 'IE00BYPLS672', 'medianTurnoverGbpM': 1.13, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': 3.924, 'auditAumUnit': 'USD bn', 'auditAumSource': 'L&G UK site 05-Nov-26', 'auditReplication': 'Physical - full', 'auditReplicationConfirmed': True, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'VGOV.L', 'isin': '', 'medianTurnoverGbpM': 1, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': 'Yes. Fund kept 92.3% of lending revenue, agent 7.7% (Vanguard Funds plc AR June 2025, via LedgerTouch)', 'lendingLevel': 'Vanguard: typically low single-digit % of NAV (group-wide, not fund-specific)', 'collateral': 'Sovereign debt only (Vanguard AR)', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Physical sampling', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IGLT.L', 'isin': 'IE00B1FZSB30', 'medianTurnoverGbpM': 4.12, 'zeroVolumeDays3m': 0, 'flags': 'TD: iShares NAV vs FTSE Actuaries Conventional Gilts All Stocks, 30-Sep-26. Lending return only 0.06% for ~65% of fund on loan', 'lendingPolicy': 'Yes - BlackRock programme', 'lendingLevel': 'Avg 64.75%, max 84.22% (12m to 30-Jun-26)', 'collateral': '107.9% of loan', 'counterparty': 'Borrower list not disclosed', 'auditAum': 4.11, 'auditAumUnit': 'GBP bn', 'auditAumSource': 'iShares factsheet (fund-level)', 'auditReplication': 'Physical - sampled', 'auditReplicationConfirmed': True, 'auditTd1y': 0.01, 'auditTd3y': 0, 'auditTd5y': -0.01}, {'symbol': 'INXG.L', 'isin': 'IE00B1FZSD53', 'medianTurnoverGbpM': 0.6, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Physical sampling', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IGLS.L', 'isin': 'IE00B4WXJK79', 'medianTurnoverGbpM': 4.03, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'VAGP.L', 'isin': 'IE00BG47KG48', 'medianTurnoverGbpM': 0.45, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': 'Yes. Fund kept 92.3% of lending revenue, agent 7.7% (Vanguard Funds plc AR June 2025, via LedgerTouch)', 'lendingLevel': 'Vanguard: typically low single-digit % of NAV (group-wide, not fund-specific)', 'collateral': 'Sovereign debt only (Vanguard AR)', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Physical sampling', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'AGBP.L', 'isin': 'IE00BF540Y54', 'medianTurnoverGbpM': 0.9, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IB01.L', 'isin': 'IE00BGSF1X88', 'medianTurnoverGbpM': 35.74, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Physical sampling', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IBTS.L', 'isin': 'IE00B14X4S71', 'medianTurnoverGbpM': 0.63, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IBTM.L', 'isin': 'IE00B1FZS798', 'medianTurnoverGbpM': 1.3, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IDTL.L', 'isin': 'IE00BSKRJZ44', 'medianTurnoverGbpM': 1.46, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'ITPS.L', 'isin': 'IE00B1FZSC47', 'medianTurnoverGbpM': 0.64, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'TIP5.L', 'isin': 'IE00BDQYWQ65', 'medianTurnoverGbpM': 0.79, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'SLXX.L', 'isin': 'IE00B00FV011', 'medianTurnoverGbpM': 1.27, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Physical sampling', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'LQDE.L', 'isin': 'IE0032895942', 'medianTurnoverGbpM': 1.7, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IEAC.L', 'isin': 'IE00B3F81R35', 'medianTurnoverGbpM': 12.74, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IHYG.L', 'isin': 'IE00B66F4759', 'medianTurnoverGbpM': 7.74, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'SHYU.L', 'isin': 'IE00B4PY7Y77', 'medianTurnoverGbpM': 0.06, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IEMB.L', 'isin': 'IE00B2NPKV68', 'medianTurnoverGbpM': 5.19, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'EMLC.L', 'isin': '', 'medianTurnoverGbpM': 0.1, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'IGLO.L', 'isin': 'IE00B3F81K65', 'medianTurnoverGbpM': 0.31, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}, {'symbol': 'FLOT.L', 'isin': 'IE00BZ048462', 'medianTurnoverGbpM': 0.51, 'zeroVolumeDays3m': 0, 'flags': '', 'lendingPolicy': '', 'lendingLevel': '', 'collateral': '', 'counterparty': '', 'auditAum': None, 'auditAumUnit': '', 'auditAumSource': 'MISSING', 'auditReplication': 'Unverified', 'auditReplicationConfirmed': False, 'auditTd1y': None, 'auditTd3y': None, 'auditTd5y': None}]
VANGUARD_FY26 = [{'symbol': 'VWRP.L', 'isin': 'IE00BK5BQT80', 'terPct': 0.14, 'terEvidenceDate': '2026-07-28', 'replication': 'Physical sampling', 'fy26FundReturnPct': 23.58, 'fy26IndexReturnPct': 23.59, 'fy26TrackingDifferencePP': -0.01, 'te3GrossPct': 0.068, 'teExpectedPct': 0.3, 'netAssetsJun26': 75962322212, 'baseCurrency': 'USD', 'loanPctNav': None, 'reportedLendingRevenueNet': 8972533, 'reportPages': '188-227', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'auditDerivedLoanPctNav': 1.44897, 'auditDerivedLoanAsOf': '2026-06-30', 'auditDerivedLoanQualification': 'Derived in supplied Vanguard workbook, not separately verified against lending schedules.'}, {'symbol': 'VWRL.L', 'isin': 'IE00B3RBWM25', 'terPct': 0.14, 'terEvidenceDate': '2026-07-28', 'replication': 'Physical sampling', 'fy26FundReturnPct': 23.58, 'fy26IndexReturnPct': 23.59, 'fy26TrackingDifferencePP': -0.01, 'te3GrossPct': 0.068, 'teExpectedPct': 0.3, 'netAssetsJun26': 75962322212, 'baseCurrency': 'USD', 'loanPctNav': None, 'reportedLendingRevenueNet': 8972533, 'reportPages': '188-227', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'auditDerivedLoanPctNav': 1.44897, 'auditDerivedLoanAsOf': '2026-06-30', 'auditDerivedLoanQualification': 'Derived in supplied Vanguard workbook, not separately verified against lending schedules.'}, {'symbol': 'VUAG.L', 'isin': 'IE00BFMXXD54', 'terPct': 0.07, 'terEvidenceDate': '2026-06-30', 'replication': 'Physical full', 'fy26FundReturnPct': 22.03, 'fy26IndexReturnPct': 21.88, 'fy26TrackingDifferencePP': 0.15, 'te3GrossPct': 0.018, 'teExpectedPct': 0.2, 'netAssetsJun26': 85401032046, 'baseCurrency': 'USD', 'loanPctNav': None, 'reportedLendingRevenueNet': 112003, 'reportPages': '365-372', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'auditDerivedLoanPctNav': 0.02921, 'auditDerivedLoanAsOf': '2026-06-30', 'auditDerivedLoanQualification': 'Derived in supplied Vanguard workbook, not separately verified against lending schedules.'}, {'symbol': 'VUKE.L', 'isin': 'IE00B810Q511', 'terPct': 0.09, 'terEvidenceDate': '2026-06-30', 'replication': 'Physical full', 'fy26FundReturnPct': 23.5, 'fy26IndexReturnPct': 23.6, 'fy26TrackingDifferencePP': -0.1, 'te3GrossPct': 0.023, 'teExpectedPct': 0.2, 'netAssetsJun26': 6432514042, 'baseCurrency': 'GBP', 'loanPctNav': None, 'reportedLendingRevenueNet': 112163, 'reportPages': '177-181', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'auditDerivedLoanPctNav': 0.19987, 'auditDerivedLoanAsOf': '2026-06-30', 'auditDerivedLoanQualification': 'Derived in supplied Vanguard workbook, not separately verified against lending schedules.'}, {'symbol': 'VMIG.L', 'isin': 'IE00BFMXVQ44', 'terPct': 0.1, 'terEvidenceDate': '2026-06-30', 'replication': 'Physical full', 'fy26FundReturnPct': 10.04, 'fy26IndexReturnPct': 10.13, 'fy26TrackingDifferencePP': -0.09, 'te3GrossPct': 0.044, 'teExpectedPct': 0.2, 'netAssetsJun26': 1999556185, 'baseCurrency': 'GBP', 'loanPctNav': None, 'reportedLendingRevenueNet': 1464961, 'reportPages': '182-187', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'auditDerivedLoanPctNav': 4.89014, 'auditDerivedLoanAsOf': '2026-06-30', 'auditDerivedLoanQualification': 'Derived in supplied Vanguard workbook, not separately verified against lending schedules.'}, {'symbol': 'VMID.L', 'isin': 'IE00BKX55Q28', 'terPct': 0.1, 'terEvidenceDate': '2026-06-30', 'replication': 'Physical full', 'fy26FundReturnPct': 10.04, 'fy26IndexReturnPct': 10.13, 'fy26TrackingDifferencePP': -0.09, 'te3GrossPct': 0.044, 'teExpectedPct': 0.2, 'netAssetsJun26': 1999556185, 'baseCurrency': 'GBP', 'loanPctNav': None, 'reportedLendingRevenueNet': 1464961, 'reportPages': '182-187', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'auditDerivedLoanPctNav': 4.89014, 'auditDerivedLoanAsOf': '2026-06-30', 'auditDerivedLoanQualification': 'Derived in supplied Vanguard workbook, not separately verified against lending schedules.'}, {'symbol': 'VERX.L', 'isin': 'IE00BKX55S42', 'terPct': 0.1, 'terEvidenceDate': '2026-06-30', 'replication': 'Physical full', 'fy26FundReturnPct': 22.03, 'fy26IndexReturnPct': 21.56, 'fy26TrackingDifferencePP': 0.47, 'te3GrossPct': 0.181, 'teExpectedPct': 0.3, 'netAssetsJun26': 4735053992, 'baseCurrency': 'EUR', 'loanPctNav': None, 'reportedLendingRevenueNet': 544610, 'reportPages': '270-276', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'auditDerivedLoanPctNav': 1.75029, 'auditDerivedLoanAsOf': '2026-06-30', 'auditDerivedLoanQualification': 'Derived in supplied Vanguard workbook, not separately verified against lending schedules.'}, {'symbol': 'VAPX.L', 'isin': 'IE00B9F5YL18', 'terPct': 0.15, 'terEvidenceDate': '2026-06-30', 'replication': 'Physical full', 'fy26FundReturnPct': 72.75, 'fy26IndexReturnPct': 72.96, 'fy26TrackingDifferencePP': -0.21, 'te3GrossPct': 0.098, 'teExpectedPct': 0.3, 'netAssetsJun26': 3298366685, 'baseCurrency': 'USD', 'loanPctNav': None, 'reportedLendingRevenueNet': 1201787, 'reportPages': '255-261', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'auditDerivedLoanPctNav': 2.42705, 'auditDerivedLoanAsOf': '2026-06-30', 'auditDerivedLoanQualification': 'Derived in supplied Vanguard workbook, not separately verified against lending schedules.'}, {'symbol': 'VGOV.L', 'isin': 'IE00B42WWV65', 'terPct': 0.05, 'terEvidenceDate': '2026-06-30', 'replication': 'Physical sampling', 'fy26FundReturnPct': 2.49, 'fy26IndexReturnPct': 2.52, 'fy26TrackingDifferencePP': -0.03, 'te3GrossPct': 0.02, 'teExpectedPct': 0.4, 'netAssetsJun26': 610254387, 'baseCurrency': 'GBP', 'loanPctNav': None, 'reportedLendingRevenueNet': 0, 'reportPages': '763-767', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'auditDerivedLoanPctNav': 0, 'auditDerivedLoanAsOf': '2026-06-30', 'auditDerivedLoanQualification': 'Derived in supplied Vanguard workbook, not separately verified against lending schedules.'}, {'symbol': 'VAGP.L', 'isin': 'IE00BG47KG48', 'terPct': 0.08, 'terEvidenceDate': '2026-06-30', 'replication': 'Physical sampling', 'fy26FundReturnPct': 3.12, 'fy26IndexReturnPct': 3.21, 'fy26TrackingDifferencePP': -0.09, 'te3GrossPct': 0.086, 'teExpectedPct': 0.3, 'netAssetsJun26': 6207094236, 'baseCurrency': 'USD', 'loanPctNav': None, 'reportedLendingRevenueNet': 0, 'reportPages': '566-742', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'distribution': 'Dist', 'auditDerivedLoanPctNav': 0, 'auditDerivedLoanAsOf': '2026-06-30', 'auditDerivedLoanQualification': 'Derived in supplied Vanguard workbook, not separately verified against lending schedules.'}, {'symbol': 'VAGS.L', 'isin': 'IE00BG47K971', 'terPct': 0.08, 'terEvidenceDate': '2026-06-30', 'replication': 'Physical sampling', 'fy26FundReturnPct': 3.12, 'fy26IndexReturnPct': 3.21, 'fy26TrackingDifferencePP': -0.09, 'te3GrossPct': 0.086, 'teExpectedPct': 0.3, 'netAssetsJun26': 6207094236, 'baseCurrency': 'USD', 'loanPctNav': None, 'reportedLendingRevenueNet': 0, 'reportPages': '566-742', 'footnote': 'Fund-level audited; not share-class-specific. 3-year realised TE is gross.', 'distribution': 'Acc'}]
VANGUARD_BY_SYMBOL = {r['symbol']:r for r in VANGUARD_FY26}
AUDIT_BY_SYMBOL = {r['symbol']:r for r in AUDIT_EVIDENCE}
EXCLUDED_LONDON_LINES = {
 'CECL.L':'LSE listing delisted July 2023; underlying fund may continue elsewhere',
 'TURL.L':'LSE listing delisted July 2023; underlying fund may continue elsewhere',
}


# Issuer NAV-to-benchmark figures, all percentage points. These issuer series
# are not market-price-based tracking error. 3/5Y Invesco cumulatives
# are first annualised; VanEck already publishes annualised periods.
PERFORMANCE = {
 'SMH.L': {'asOf':'2026-10-31','method':'Issuer fund/index annualised total returns in USD',
     'values':{1:(55.57,56.04),3:(54.66,55.08),5:(29.83,30.15)}},
 'EQQQ.L': {'asOf':'2026-09-30','method':'Issuer fund/index total returns in USD; 3Y and 5Y annualised from cumulative',
     'values':{1:(23.49,23.76),3:(108.69,109.83),5:(110.91,112.65)}},
 'FWRG.L': {'asOf':'2026-09-30','method':'Issuer fund/index total returns in USD; 3Y annualised from cumulative',
     'values':{1:(16.67,16.66),3:(80.46,80.05)}}
}

def facts():
    return list(csv.DictReader(io.StringIO(ISSUER_CSV)))

def is_isin_valid(s):
    s=(s or '').upper()
    if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]',s): return False
    digits=''.join(str(int(ch,36)) for ch in s)
    total=0
    for i,ch in enumerate(digits[::-1]):
        n=int(ch)
        if i%2==1:
            n=n*2
            n=n//10+n%10 if n>9 else n
        total+=n
    return total%10==0

def validate():
    rows=facts()
    assert len(rows)==78, ('Issuer row count altered',len(rows))
    assert len({r['symbol'] for r in rows})==len(rows), 'Duplicate symbol in issuer CSV'
    assert len({r['isin'] for r in rows})==len(rows), 'Duplicate share class ISIN in issuer CSV'
    for r in rows:
        assert is_isin_valid(r['isin']), ('Bad ISIN',r['symbol'],r['isin'])
        assert 0 <= float(r['terPct']) <= 5, ('Fee out of range',r['symbol'])
        assert float(r['aum'])>0, ('Bad AUM',r['symbol'])
        assert r['aumCurrency'] in ('USD','EUR','GBP','JPY')
    for r in US_BONDS_JSON:
        assert re.fullmatch(r'[A-Z]{2,5}',r['symbol'])
    return rows

# Market category identifiers already used by the original ETF tab.
NEW_MARKET_REF={
 'Developed world':'URTH','United States':'^GSPC','UK FTSE 100':'^FTSE',
 'UK FTSE All Share':'^FTSE','UK short gilts':'','UK gilts':'',
 'Japan':'^N225','Germany DAX':'^GDAXI','France':'^FCHI',
 'Europe':'^STOXX','Eurozone':'^STOXX50E',
 'India':'^NSEI','Taiwan':'^TWII','Brazil':'^BVSP',
 'Mexico':'^MXX','South Korea':'^KS11',
 'US equal weight':'^GSPC',
}
# These broad-price proxies are NOT equivalent to the tracked total-return benchmark.
MARKETS_WITH_NONMATCHING_PROXY={'UK FTSE All Share','Japan','India','Taiwan','Brazil',
 'Mexico','South Korea','US equal weight','Developed world'}

# Preserve LSE verified prices, but never treat an unverified Paris symbol as an alias.
SYMBOL_MIGRATIONS={
 'SEMI.L':('SMH.L','VanEck Semiconductor'),
 'CAC.PA':('CACX.L','Amundi CAC 40'),
}

def install_catalogue(catalog:pathlib.Path,dry_run=False):
    if not catalog.is_file(): raise RuntimeError('Missing etf_catalog.csv')
    source=catalog.read_text(encoding='utf-8-sig')
    dr=csv.DictReader(io.StringIO(source));cols=dr.fieldnames
    mandatory={'category','market','symbol','name','benchmark','terPct','replication',
               'distribution','domicile','isin','hedged','reference','note'}
    if not cols or not mandatory.issubset(cols):
        raise RuntimeError('Unexpected catalogue columns: will not overwrite')
    entries=list(dr)
    for prior,(new,name_start) in SYMBOL_MIGRATIONS.items():
        candidates=[x for x in entries if x['symbol']==prior and x['name'].startswith(name_start)]
        if len(candidates)==1:
            if any(x['symbol']==new for x in entries):
                raise RuntimeError('Migration would create duplicate '+new)
            candidates[0]['symbol']=new
            candidates[0]['note']=('Verified London exchange line, former placeholder '+prior+'. '+candidates[0].get('note','')).strip()
    indexed={x['symbol']:x for x in entries}
    counts=dict(original=len(entries),matched=0,added=0,conflicts=0,final=0)
    for r in facts():
        symbol=r['symbol']; entry=indexed.get(symbol)
        if not entry:
            if not r['name'] or not r['category'] or not r['market']:
                # Name absent: this record may only enrich an existing entry.
                continue
            entry={k:'' for k in cols}
            for k in ('category','market','symbol','name','benchmark','distribution','domicile','reference'):
                entry[k]=r[k]
            if not entry['reference']:entry['reference']=NEW_MARKET_REF.get(r['market'],'')
            if r['market'] in MARKETS_WITH_NONMATCHING_PROXY:
                entry['note']='Indicative price reference only; benchmark is not identical.'
            entries.append(entry);indexed[symbol]=entry;counts['added']+=1
        else:counts['matched']+=1
        old_isin=(entry.get('isin') or '').strip().upper()
        if old_isin and old_isin!=r['isin']:
            counts['conflicts']+=1
            entry['note']=('VERIFY: source ISIN '+r['isin']+' conflicts with catalogue '+old_isin+'. '+
                           (entry.get('note') or '')).strip()
            continue
        entry['isin']=r['isin']
        entry['terPct']=('%g' % float(r['terPct']))
        if r['replication'] in ('Physical full','Physical sampling','Synthetic swap'):
            entry['replication']=r['replication']
        # Physical confirmed without a full/sampling label should not overwrite an
        # existing editor's classification nor count as full issuer verification.
        if r['distribution'] and r['distribution']!='Mixed':entry['distribution']=r['distribution']
        if r['domicile']:entry['domicile']=r['domicile']
        if r['benchmark'] and not entry.get('benchmark'):entry['benchmark']=r['benchmark']
        info='Issuer snapshot '+r['issuer']+' '+r['issuerDate']+'; AUM date '+(r['aumAsOf'] or 'not published')
        if info not in (entry.get('note') or ''):
            entry['note']=((entry.get('note') or '')+' | '+info).strip(' |')
        if r['note'] and r['note'] not in entry['note']:
            entry['note']+=' | '+r['note']
    if len({r['symbol'] for r in entries})!=len(entries):
        raise RuntimeError('Duplicate symbol after catalogue patch')
    counts['final']=len(entries)
    buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer,fieldnames=cols,lineterminator='\n')
    writer.writeheader();writer.writerows(entries)
    output=buffer.getvalue()
    if output.replace('\r\n','\n')!=source.replace('\r\n','\n') and not dry_run:
        backup=catalog.with_suffix('.before-consolidation.bak')
        if not backup.exists():shutil.copy2(catalog,backup)
        catalog.write_text(output,encoding='utf-8')
    return counts


# Apply the issuer-backed 2026 share-class corrections AFTER original consolidation.
_BASE_INSTALL_CATALOGUE = install_catalogue

def install_catalogue(catalog:pathlib.Path,dry_run=False):
    counts=_BASE_INSTALL_CATALOGUE(catalog,dry_run)
    # install() calls this on its isolated staging copy, so the changes below
    # do not touch the original until all build and HTML checks succeed.
    if dry_run: return counts
    original=catalog.read_text(encoding='utf-8-sig')
    reader=csv.DictReader(io.StringIO(original));headers=reader.fieldnames
    items=list(reader)
    items=[r for r in items if r['symbol'] not in EXCLUDED_LONDON_LINES]
    indexed={r['symbol']:r for r in items}
    if 'VAGP.L' in indexed:
        r=indexed['VAGP.L']
        existing=(r.get('isin') or '').upper()
        if existing not in ('','IE00BG47KG48'):
            raise RuntimeError('VAGP ISIN conflict: not safe to reassign income status')
        r['isin']='IE00BG47KG48';r['distribution']='Dist';r['terPct']='0.08'
        r['replication']='Physical sampling';r['domicile']='Ireland'
        note='Vanguard UK 2026: VAGP is distributing (IE00BG47KG48).'
        if note not in (r.get('note') or ''):
            r['note']=((r.get('note') or '')+' | '+note).strip(' |')
    else:
        raise RuntimeError('VAGP.L absent; review ETF catalogue before correction')
    if 'VAGS.L' not in indexed:
        row={k:'' for k in headers}
        row.update(category='Bonds',market='Global aggregate bond',symbol='VAGS.L',
                   name='Vanguard Global Aggregate Bond GBP Hedged Acc',
                   benchmark='Bloomberg Global Aggregate Float Adjusted and Scaled GBP Hedged',
                   terPct='0.08',replication='Physical sampling',distribution='Acc',
                   domicile='Ireland',isin='IE00BG47K971',hedged='GBP',
                   note='Fund-level AUM shared with VAGP; do not add across share classes. Vanguard UK 2026.')
        items.append(row)
    else:
        if indexed['VAGS.L']['isin'] not in ('','IE00BG47K971'):
            raise RuntimeError('VAGS ISIN conflict')
        indexed['VAGS.L'].update(isin='IE00BG47K971',distribution='Acc',terPct='0.08',
                                  replication='Physical sampling',domicile='Ireland')
    # Fill Vanguard ISINs absent from the original catalogue (VERX, VAPX,
    # VGOV), without overwriting any conflicting identifier.
    backfilled=[]
    seen={}
    for row in items:
        sym=row['symbol'];isin=(row.get('isin') or '').strip().upper()
        if sym in seen:raise RuntimeError('Duplicate ETF line '+sym)
        seen[sym]=1
        v=VANGUARD_BY_SYMBOL.get(sym)
        if v:
            if isin and isin!=v['isin']:
                raise RuntimeError('Vanguard ISIN mismatch for '+sym)
            if not isin:
                row['isin']=v['isin']
                backfilled.append(sym)
            if not row.get('replication'):row['replication']=v['replication']
            if not row.get('terPct'):row['terPct']='%g'%v['terPct']
            if not row.get('domicile'):row['domicile']='Ireland'
    buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=headers,lineterminator='\n')
    writer.writeheader();writer.writerows(items)
    if buffer.getvalue()!=original.replace('\r\n','\n'):
        catalog.write_text(buffer.getvalue(),encoding='utf-8')
    counts['final']=len(items)
    counts['netChange']=len(items)-counts['original']
    counts['vanguardIsinBackfills']=backfilled
    counts['vanguardClassCorrection']='VAGP distributes; VAGS accumulates'
    counts['excludedLondonListings']=list(EXCLUDED_LONDON_LINES)
    return counts


# Compact ETF v5 catalogue adjustments. Keep three markets geographically correct.
_BASE_INSTALL_CATALOGUE_V4=install_catalogue

def install_catalogue(catalog:pathlib.Path,dry_run=False):
    counts=_BASE_INSTALL_CATALOGUE_V4(catalog,dry_run)
    if dry_run:return counts
    content=catalog.read_text('utf-8-sig')
    reader=csv.DictReader(io.StringIO(content)); fields=reader.fieldnames
    rows=[r for r in reader if r['symbol']!='GEND.L']
    index={r['symbol']:r for r in rows}
    for sym,market in [('XDEW.L','US equal weight'),('LCUK.L','UK FTSE All Share'),('KSA.L','Saudi Arabia')]:
        if sym in index:index[sym]['market']=market
    if 'MIDD.L' in index:
        entry=index['MIDD.L']
        if entry.get('isin') not in ('','IE00B00FV128'):
            raise RuntimeError('MIDD ISIN conflict; refusing fee override')
        entry.update(isin='IE00B00FV128',terPct='0.4',replication='Physical sampling',distribution='Dist')
        note='Official iShares: 0.40% TER, physical optimised, ISIN IE00B00FV128.'
        if note not in entry.get('note',''):entry['note']=((entry.get('note') or '')+' | '+note).strip(' |')
    if 'XDEW.L' in index:
        entry=index['XDEW.L']
        if entry.get('isin') not in ('','IE00BLNMYC90'):
            raise RuntimeError('XDEW ISIN conflict')
        entry.update(isin='IE00BLNMYC90',terPct='0.15',replication='Physical full',
            benchmark='S&P 500 Equal Weight',distribution='Acc')
    if 'LCUK.L' in index:
        entry=index['LCUK.L']
        if entry.get('isin') not in ('','LU1781541096'):
            raise RuntimeError('LCUK ISIN conflict')
        # Amundi confirms direct physical; justETF describes full replication.
        entry.update(isin='LU1781541096',terPct='0.04',replication='Physical full',distribution='Dist',
            benchmark='Morningstar UK NR')
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n')
    writer.writeheader();writer.writerows(rows)
    if out.getvalue()!=content.replace('\r\n','\n'):catalog.write_text(out.getvalue(),encoding='utf-8')
    counts['final']=len(rows);counts['netChange']=len(rows)-counts['original']
    counts['removedFunds']=['GEND.L']
    return counts

def inject_build(path:pathlib.Path,dry_run=False):
    content=path.read_text(encoding='utf-8')
    if 'import etf_consolidation\n' in content:return False
    old='import etf_issuer_db\n'
    anchor='    warnings.extend(issuer_warnings);cached_count+=issuer_cached\n'
    if content.count(old)!=1 or content.count(anchor)!=1:
        raise RuntimeError('ETF installer has not run, or script changed; refusing unsafe patch')
    revised=content.replace(old,old+'import etf_consolidation\n',1)
    revised=revised.replace(anchor,anchor+'    etf_data=etf_consolidation.enrich(etf_data)\n',1)
    compile(revised,str(path),'exec')
    if not dry_run:path.write_text(revised,encoding='utf-8')
    return True

def annualize(percent,years):
    return ((1+float(percent)/100)**(1/years)-1)*100

def apply_issuer_performance(f):
    src=PERFORMANCE.get(f['symbol'])
    if not src:return
    f['issuerTrackingAsOf']=src['asOf']
    f['issuerTrackingBasis']=src['method']
    for years,(ret,index) in src['values'].items():
        if years>1 and 'annualised from cumulative' in src['method']:
            ret,index=annualize(ret,years),annualize(index,years)
        f['issuerReturn'+str(years)+'Y']=round(ret,4)
        f['issuerBenchmarkReturn'+str(years)+'Y']=round(index,4)
        f['issuerTrackingDifference'+str(years)+'Y']=round(ret-index,4)

def enrich(data):
    """Attach snapshot data only to exact ISINs. Live issuer records take priority."""
    source={r['symbol']:r for r in facts()}
    counts=dict(matched=0,unmatched=0,isinConflicts=0,feeFallback=0,
                aumFallback=0,replicationFallback=0,officialTe3=0,
                issuerTrackingComparison=0)
    for f in data.get('funds',[]):
        r=source.get(f.get('symbol'))
        if not r:continue
        if (f.get('isin') or '').upper()!=r['isin']:
            counts['isinConflicts']+=1
            f['identifierWarning']='Snapshot ISIN differs from this trading line; no metadata applied'
            continue
        counts['matched']+=1
        verified_date=r['issuerDate']
        fund_source=r['issuer']+' screenshot / issuer factsheet ('+verified_date+')'
        f['snapshotIsin']=r['isin']
        f['snapshotIssuer']=r['issuer']
        f['snapshotAsOf']=r['aumAsOf']
        f['snapshotCapturedAt']=verified_date
        if f.get('terStatus')!='Issuer confirmed':
            f.update(terPct=float(r['terPct']),terAsOf=verified_date,
                     terCheckedAt=verified_date,terStatus='Issuer snapshot (not refreshed)',
                     terSource=fund_source,terProvider=r['issuer'])
            if r.get('sourceUrl'):f['terUrl']=r['sourceUrl']
            counts['feeFallback']+=1
        if f.get('fundSize') is None or f.get('fundSize')==0 or not f.get('fundSizeSource'):
            f.update(fundSize=float(r['aum']),fundSizeCurrency=r['aumCurrency'],
                fundSizeAsOf=r['aumAsOf'],fundSizeCheckedAt=verified_date,
                fundSizeSource=fund_source,
                fundSizeStatus=('Dated issuer factsheet' if r['aumAsOf'] else
                                'Dated screenshot; precise AUM as-of date not shown'),
                issuerProvider=r['issuer'])
            if r['sourceUrl']:f['issuerVerifiedUrl']=r['sourceUrl']
            counts['aumFallback']+=1
        if r['replication'] in ('Physical full','Physical sampling','Synthetic swap'):
            if f.get('replicationStatus')!='Fund-specific issuer verified':
                f['replication']=r['replication']
                f['replicationType']=('Synthetic' if r['replication']=='Synthetic swap' else 'Physical')
                f['replicationStatus']='Fund-specific issuer verified'
                f['issuerReplicationDetail']=r['replicationDetail'] or r['replication']
                f['replicationCheckedAt']=verified_date
                f['structureSource']=r['sourceUrl']
                counts['replicationFallback']+=1
        elif r.get('replicationDetail') and f.get('replicationStatus')!='Fund-specific issuer verified':
            f['replicationType']='Physical' if 'Physical' in r['replicationDetail'] else f.get('replicationType','Unknown')
            f['issuerReplicationDetail']=r['replicationDetail']
            f['replicationStatus']='Issuer verified physical; full/sampling not established'
        if r['riskIndicator']:
            f['issuerRiskIndicator7']=int(r['riskIndicator'])
            f['issuerRiskIndicatorAsOf']=verified_date
        if r['issuerTe3'] and f.get('officialTrackingError3Y') is None:
            f['officialTrackingError3Y']=float(r['issuerTe3'])
            f['officialTrackingErrorAsOf']=r['aumAsOf'] or verified_date
            f['officialTrackingErrorBasis']='Issuer reported 3-year NAV tracking error'
            counts['officialTe3']+=1
        if r['lendingReturnPct']:
            f['issuerLendingReturnAnnualPct']=float(r['lendingReturnPct'])
        if 'benchmarkChangeDate=' in r['note']:
            f['benchmarkChangeDate']=r['note'].split('benchmarkChangeDate=')[-1][:10]
        apply_issuer_performance(f)
        if f.get('issuerTrackingAsOf'):counts['issuerTrackingComparison']+=1
    counts['unmatched']=len(source)-counts['matched']
    counts.update(catalogued=len(data.get('funds',[])),missingTER=sum(f.get('terPct') is None for f in data.get('funds',[])),
      missingFundSize=sum(not f.get('fundSize') for f in data.get('funds',[])),
      missingISIN=sum(not is_isin_valid(f.get('isin')) for f in data.get('funds',[])),
      missingIssuerTrackingDifference=sum(not f.get('issuerTrackingAsOf') for f in data.get('funds',[])),
      missingOfficialTrackingError3Y=sum(f.get('officialTrackingError3Y') is None for f in data.get('funds',[])),
      missingVerifiedReplication=sum(f.get('replicationStatus')!='Fund-specific issuer verified' for f in data.get('funds',[])),
      missingTradingSpread=len(data.get('funds',[])))
    data['issuerConsolidationCoverage']=counts
    data['usDomiciledBondReference']=US_BONDS_JSON
    data.setdefault('sources',[]).append('ETF 8 Nov 2026 consolidation: issuer/ISIN-matched September-November factsheets; dated snapshots are NOT live prices; fund AUM is NOT trading volume; US bond ETFs are separate domicile references.')
    # Update the existing issuer audit counts after the screenshot fallbacks.
    parent=data.setdefault('issuerDatabaseCoverage',{})
    parent.update(catalogued=len(data.get('funds',[])),
      issuerAum=sum(bool(f.get('fundSize') and f.get('fundSizeSource')) for f in data.get('funds',[])),
      issuerReplication=sum(f.get('replicationStatus')=='Fund-specific issuer verified' for f in data.get('funds',[])),
      issuerFees=sum(f.get('terStatus')=='Issuer confirmed' for f in data.get('funds',[])),
      issuerFeeSnapshots=sum(f.get('terStatus')=='Issuer snapshot (not refreshed)' for f in data.get('funds',[])))
    return data


_BASE_ISSUER_ENRICH = enrich

def enrich(data):
    data=_BASE_ISSUER_ENRICH(data)
    matchedAudit=0;missingAuditISIN=0;vanguardMatched=0
    for f in data.get('funds',[]):
        sym=f.get('symbol');isin=(f.get('isin') or '').upper()
        r=AUDIT_BY_SYMBOL.get(sym)
        if r:
            if r['isin'] and r['isin']!=isin:
                f['auditIsinConflict']='Audit ISIN '+r['isin']+' differs from catalogue; audit metrics not applied'
            else:
                if not r['isin']:
                    missingAuditISIN+=1
                    f['auditTickerOnly']=True
                else:matchedAudit+=1
                # Exchange turnover is about this trading line, NOT underlying fund AUM.
                if r['medianTurnoverGbpM'] is not None:
                    f['auditMedianExchangeTurnoverGbpM3m']=float(r['medianTurnoverGbpM'])
                    f['auditTurnoverCapturedAt']='2026-11-08'
                    f['auditTurnoverCaveat']='Indicative Yahoo Finance close×volume 3m median; quote-currency conversion; excludes off-book and RFQ; not a spread or execution quote.'
                if r['zeroVolumeDays3m'] is not None:
                    f['auditZeroVolumeDays3m']=int(r['zeroVolumeDays3m'])
                if r['flags']:f['audit2026Flags']=r['flags']
                if r['auditAum'] is not None and not f.get('fundSize'):
                    src=r['auditAumSource'].lower()
                    unit=r['auditAumUnit']
                    # Allow only explicit issuer first-party evidence, not generic
                    # 'GitHub issuer-sourced', third-party, or share-class AUM.
                    accepted=('ishares','blackrock','vaneck','invesco','xtrackers',
                              'hsbc','amundi','franklin','l&g','vanguard')
                    issuerEvidence=any(key in src for key in accepted) and not any(
                        bad in src for bad in ('third party','third-party','github site','finanzen','tradingview'))
                    if issuerEvidence and 'share class' not in unit.lower() and unit.split(' ')[-1]=='bn':
                        ccy=unit.split(' ')[0].strip()
                        if ccy in ('USD','GBP','EUR','JPY'):
                            f['fundSize']=float(r['auditAum'])*1e9
                            f['fundSizeCurrency']=ccy
                            f['fundSizeSource']='User audit first-party issuer claim: '+r['auditAumSource']
                            f['fundSizeStatus']='Audit issuer fallback; date not independently verified'
                            match=re.search(r'\d{1,2}-[A-Za-z]{3}-\d{2}',r['auditAumSource'])
                            if match:
                                try:f['fundSizeAsOf']=dt.datetime.strptime(match.group(),'%d-%b-%y').date().isoformat()
                                except ValueError:pass
                if r['auditReplicationConfirmed'] and f.get('replicationStatus') not in ('Fund-specific issuer verified','Audit issuer-claimed verified'):
                    method=r['auditReplication'].lower()
                    classification=('Synthetic swap' if 'swap' in method or 'synthetic' in method
                         else 'Physical sampling' if 'sampling' in method or 'optimis' in method
                         else 'Physical full' if 'full' in method else '')
                    if classification:
                        f['replication']=classification
                        f['replicationStatus']='Audit issuer-claimed verified'
                        f['replicationSource']='User audit workbook: issuer document asserted, URL not captured'
                for years in (1,3,5):
                    val=r['auditTd'+str(years)+'y']
                    if val is not None:
                        f['auditClaimedTrackingDifference'+str(years)+'Y']=val
                        f['auditClaimedTrackingDifferenceCaveat']='Audit says issuer published; original report date and URL not supplied. Not promoted to official tracking series.'
                if r['lendingPolicy'] and not r['lendingPolicy'].startswith('Yes. Fund kept'):
                    f['auditLendingPolicyNote']=r['lendingPolicy']
                if r['lendingLevel'] and 'group-wide' not in r['lendingLevel']:
                    f['auditLendingLevelNote']=r['lendingLevel']
                if r['collateral'] and not r['collateral'].startswith('Sovereign debt only (Vanguard'):
                    f['auditCollateralNote']=r['collateral']
                if r['counterparty'] and r['counterparty']!='n/a (physical)':
                    f['auditCounterpartyNote']=r['counterparty']
        v=VANGUARD_BY_SYMBOL.get(sym)
        if v:
            if v['isin']!=isin:
                f['auditIsinConflict']='Vanguard report fund mapping conflicts with exchange ISIN; not applied'
                continue
            vanguardMatched+=1
            f['vanguardFY26']={k:v[k] for k in ('fy26FundReturnPct','fy26IndexReturnPct',
               'fy26TrackingDifferencePP','te3GrossPct','teExpectedPct',
               'netAssetsJun26','baseCurrency','reportedLendingRevenueNet','reportPages',
               'footnote','auditDerivedLoanPctNav','auditDerivedLoanAsOf',
               'auditDerivedLoanQualification') if k in v}
            f['vanguardFY26']['asOf']='2026-06-30'
            f['vanguardFY26']['source']='Vanguard Funds plc audited Annual Report FY2026, Investment Managers Report p5-6'
            # 2026 fund-level 3Y realised TE (gross) supersedes estimated ETF price tracking.
            f['officialTrackingError3Y']=v['te3GrossPct']
            f['officialTrackingErrorAsOf']='2026-06-30'
            f['officialTrackingErrorBasis']='Vanguard audited gross 3Y realised TE, fund-level; not share-class price TE'
            # Old catalogue sometimes says VAGP accumulating. That is wrong.
            if sym in ('VAGP.L','VAGS.L'):
                f['distribution']=v['distribution']
            if f.get('terStatus')!='Issuer confirmed' and not f.get('snapshotCapturedAt'):
                f['terPct']=float(v['terPct'])
                f['terCheckedAt']=v['terEvidenceDate']
                f['terStatus']='Vanguard issuer audited / post-year-end fee change'
                f['terProvider']='Vanguard'
                f['terSource']='Vanguard FY2026 Annual Report and issuer 2026 documentation'
            if f.get('replicationStatus')!='Fund-specific issuer verified':
                f['replication']=v['replication']
                f['replicationStatus']='Fund-specific issuer verified'
                f['issuerReplicationDetail']='Vanguard FY2026 Annual Report p5-6'
            # Historical AUM fallback ONLY, after all fresher issuer/live sources.
            if not f.get('fundSize'):
                f['fundSize']=v['netAssetsJun26']
                f['fundSizeCurrency']=v['baseCurrency']
                f['fundSizeAsOf']='2026-06-30'
                f['fundSizeStatus']='Historical FY2026 audited (not current)'
                f['fundSizeSource']='Vanguard Funds plc audited FY2026 accounts'
    audit={
      'auditBaselineRows':len(AUDIT_EVIDENCE),
      'auditIsinMatched':matchedAudit,
      'auditTickerOnly':missingAuditISIN,
      'vanguardFundClassesMatched':vanguardMatched,
      'indicativeTurnoverRows':sum(f.get('auditMedianExchangeTurnoverGbpM3m') is not None for f in data.get('funds',[])),
      'quotedBidAskSpreads':0,
      'auditFundSizeFallback':sum('Audit issuer fallback' in (f.get('fundSizeStatus') or '') for f in data.get('funds',[])),
      'auditReplicationFallback':sum(f.get('replicationStatus')=='Audit issuer-claimed verified' for f in data.get('funds',[])),
      'missingNavTrackingError3y':sum(f.get('officialTrackingError3Y') is None for f in data.get('funds',[])),
      'excludedOldListings':EXCLUDED_LONDON_LINES,
      'catalogueRows':len(data.get('funds',[])),
    }
    data['etfAudit2026Coverage']=audit
    coverage=data.get('issuerConsolidationCoverage',{})
    coverage.update(catalogued=audit['catalogueRows'],
       missingOfficialTrackingError3Y=audit['missingNavTrackingError3y'],
       missingTradingSpread=audit['catalogueRows'],
       missingFundSize=sum(not f.get('fundSize') for f in data.get('funds',[])),
       missingTER=sum(f.get('terPct') is None for f in data.get('funds',[])),
       missingISIN=sum(not is_isin_valid(f.get('isin')) for f in data.get('funds',[])),
       missingVerifiedReplication=sum(f.get('replicationStatus') not in (
           'Fund-specific issuer verified','Audit issuer-claimed verified') for f in data.get('funds',[])))
    data.setdefault('issuerDatabaseCoverage',{}).update(
       catalogued=audit['catalogueRows'],
       issuerAum=sum(bool(f.get('fundSize') and f.get('fundSizeSource')) for f in data.get('funds',[])),
       issuerReplication=sum(f.get('replicationStatus') in (
           'Fund-specific issuer verified','Audit issuer-claimed verified') for f in data.get('funds',[])))
    data.setdefault('sources',[]).append('Vanguard audited FY2026 fund data as of 30 June 2026; 78-line user audit 8 Nov 2026 for indicative turnover. Neither constitutes a live quote or a current bid-ask spread.')
    return data


_BASE_ENRICH_V4=enrich

def enrich(data):
    data=_BASE_ENRICH_V4(data)
    known={
      'MIDD.L':('IE00B00FV128',.40,'Physical sampling',
          'Issuer iShares: physical optimised / sampling',
          'https://www.ishares.com/uk/individual/en/products/251796/'),
      'XDEW.L':('IE00BLNMYC90',.15,'Physical full',
          'Issuer Xtrackers: direct physical, full replication',
          'https://etf.dws.com/en-gb/IE00BLNMYC90-s-p-500-equal-weight-ucits-etf-1c/'),
      'LCUK.L':('LU1781541096',.04,'Physical full',
          'Amundi: physical; full replication separately reported by justETF',
          'https://www.amundietf.lu/en/individual/products/equity/amundi-uk-equity-all-cap-ucits-etf-dist/lu1781541096'),
    }
    for f in data.get('funds',[]):
        item=known.get(f.get('symbol'))
        if item and str(f.get('isin') or '').upper()==item[0]:
            isin,fee,method,detail,url=item
            f['terPct']=fee
            f['terStatus']='Issuer verified (dated reference)' if f.get('terStatus')!='Issuer confirmed' else f['terStatus']
            if f.get('terStatus')!='Issuer confirmed':f['terCheckedAt']='2026-11-08'
            f['terUrl']=url
            f['replication']=method
            f['replicationType']='Physical'
            f['issuerReplicationDetail']=detail
            f['replicationStatus']='Fund-specific issuer verified' if f['symbol']!='LCUK.L' else 'Issuer physical; full replication secondary-source verified'
            f['structureSource']=url
            if f['symbol']=='MIDD.L':
                f['issuerLendingReturnAnnualPct']=0.07
                f['issuerLendingReturnAsOf']='2026-06-30'
        # Where first-party sources confirm physical but not sampling/full,
        # show P and the uncertainty, rather than presenting an invented subtype.
        if f.get('symbol') in ('XMBR.L','XMEX.L','XDEX.L') and f.get('isin') in (
              'LU0292109344','LU0476289466','IE00BM67HJ62'):
            if not f.get('replicationStatus','').startswith('Fund-specific issuer verified'):
                f['replicationType']='Physical'
                f['replicationStatus']='Issuer physical; full versus optimised unverified'
                f['issuerReplicationDetail']='Direct physical; full versus sampling not established from supplied factsheet'
    data.setdefault('issuerDatabaseCoverage',{})['issuerReplication']=sum(
        ('issuer' in str(f.get('replicationStatus','')).lower() and
         ('verified' in str(f.get('replicationStatus','')).lower() or 'physical' in str(f.get('replicationStatus','')).lower()))
        for f in data.get('funds',[]))
    return data

FRONTEND_JS = r'''
// Consolidated issuer facts, NAV tracking DIFFERENCE, and separate US bond references.
const _origRenderEtfConsolidated=renderEtfTracker;
renderEtfTracker=function(){
  _origRenderEtfConsolidated();
  try{renderEtfIssuerVerified();}catch(e){console.warn('Issuer display unavailable',e);}
};
function renderEtfIssuerVerified(){
 const host=document.getElementById('etf-issuer-snapshot');if(!host)return;
 const f=(ETF_BY_SYMBOL&&ETF_BY_SYMBOL.get(etfState.selected))||null;
 host.replaceChildren();
 const heading=document.createElement('h3');heading.textContent='ISSUER TRACKING & VERIFIED FUND STRUCTURE';host.appendChild(heading);
 if(!f){const p=document.createElement('p');p.textContent='Select an ETF to see issuer-dated benchmark observations.';host.appendChild(p);return;}
 const info=document.createElement('p');info.className='note';
 info.textContent=(f.snapshotIssuer||'No issuer snapshot')+' · ISIN '+(f.isin||'unverified')+
    ' · OCF '+(Number.isFinite(f.terPct)?f.terPct.toFixed(2)+'%':'missing')+
    ' · fund assets '+(f.fundSize?etfFundSize(f):'missing')+
    ' · dated '+(f.snapshotCapturedAt||'not checked')+
    (f.fundSize&& !f.fundSizeAsOf?' · fund AUM as-of date unconfirmed':'');
 host.appendChild(info);
 if(f.issuerTrackingAsOf){
   const sub=document.createElement('p');sub.className='note';
   sub.textContent='Official issuer fund-minus-index annualised return difference (percentage points), as of '+f.issuerTrackingAsOf+'. This is NOT tracking error.';
   host.appendChild(sub);
   const table=document.createElement('table');table.className='watch';
   const tr=document.createElement('tr');for(const s of ['Period','ETF annualised TR','Index annualised TR','Difference (pp)']){
      const th=document.createElement('th');th.textContent=s;tr.appendChild(th);}
   const head=document.createElement('thead');head.appendChild(tr);table.appendChild(head);
   const body=document.createElement('tbody');
   for(const y of [1,3,5]){
      const val=f['issuerTrackingDifference'+y+'Y'];if(val==null)continue;
      const row=document.createElement('tr');
      const vals=[y+'Y',f['issuerReturn'+y+'Y'].toFixed(2)+'%',
        f['issuerBenchmarkReturn'+y+'Y'].toFixed(2)+'%',(val>0?'+':'')+val.toFixed(2)+' pp'];
      for(const s of vals){const td=document.createElement('td');td.textContent=s;row.appendChild(td);}body.appendChild(row);
   }table.appendChild(body);host.appendChild(table);
 }else{const p=document.createElement('p');p.className='note';p.textContent='Official issuer benchmark return comparison: unavailable for this ETF.';host.appendChild(p);}
 const te=document.createElement('p');te.className='note';
 te.textContent='Official NAV tracking error 3Y: '+(f.officialTrackingError3Y!=null?Number(f.officialTrackingError3Y).toFixed(2)+'%':'not reported')+
   ' · Replication: '+(f.replication||'subtype not verified')+
   ' · Regulatory risk score: '+(f.issuerRiskIndicator7!=null?f.issuerRiskIndicator7+'/7 (dated)':'unavailable')+
   ' · Annual securities-lending return: '+(f.issuerLendingReturnAnnualPct!=null?f.issuerLendingReturnAnnualPct+'%':'not disclosed')+
   (f.benchmarkChangeDate?' · Benchmark changed: '+f.benchmarkChangeDate:'');
 host.appendChild(te);
}
function renderUsBondReferences(){
 const root=document.getElementById('etf-us-reference-body');if(!root)return;
 const records=ETF_DATA.usDomiciledBondReference||[];
 const tr=document.createElement('tr');
 for(const text of ['US ticker','Issuer fund','Net cost','Assets (USD)','12m distribution yield']){
   const th=document.createElement('th');th.textContent=text;tr.appendChild(th);}
 const table=document.createElement('table');table.className='watch';
 const hd=document.createElement('thead');hd.appendChild(tr);table.appendChild(hd);
 const body=document.createElement('tbody');
 for(const f of records){const row=document.createElement('tr');
   const vals=[f.symbol,f.name,f.netExpensePct.toFixed(2)+'%',
     '$'+(f.assetsUsd/1e9).toFixed(2)+'bn',f.trailing12mYieldPct.toFixed(2)+'%'];
   for(const s of vals){const td=document.createElement('td');td.textContent=s;row.appendChild(td);}body.appendChild(row);
 }table.appendChild(body);root.replaceChildren(table);
}
const _renderDqEtf=renderDataQuality;
renderDataQuality=function(){
 _renderDqEtf();
 const root=document.getElementById('etf-issuer-integrity');if(!root)return;
 const c=ETF_DATA.issuerConsolidationCoverage||{};
 root.textContent='ETF issuer snapshot evidence: '+(c.matched??0)+' ISIN-matched funds · '+
   (c.missingTER??'—')+' TER missing · '+(c.missingFundSize??'—')+' fund AUM missing · '+
   (c.missingISIN??'—')+' invalid/missing ISIN · '+
   (c.missingIssuerTrackingDifference??'—')+' without issuer return comparison · '+
   (c.missingOfficialTrackingError3Y??'—')+' without issuer 3Y NAV tracking error · '+
   (c.missingVerifiedReplication??'—')+' without fund-specific replication confirmation. '+
   'Historical issuer screenshots are not a live feed; spread/turnover not verified.';
};

// Audited fund-level Vanguard facts and indicative exchange turnover.
const _renderIssuerBeforeAudit=renderEtfIssuerVerified;
renderEtfIssuerVerified=function(){
 _renderIssuerBeforeAudit();
 const parent=document.getElementById('etf-issuer-snapshot');
 const f=ETF_BY_SYMBOL&&ETF_BY_SYMBOL.get(etfState.selected);
 if(!parent||!f)return;
 const make=(txt)=>{const p=document.createElement('p');p.className='note';p.textContent=txt;parent.appendChild(p);};
 if(f.vanguardFY26){
   const v=f.vanguardFY26;
   make('VANGUARD AUDITED FY26, to '+v.asOf+': fund return '+v.fy26FundReturnPct.toFixed(2)+'%, benchmark '+v.fy26IndexReturnPct.toFixed(2)+'%, fund-minus-index '+(v.fy26TrackingDifferencePP>=0?'+':'')+v.fy26TrackingDifferencePP.toFixed(2)+' pp. 3Y realised gross NAV tracking error '+v.te3GrossPct.toFixed(3)+'% (separate metric).');
   make('Historical fund AUM '+v.baseCurrency+' '+(v.netAssetsJun26/1e9).toFixed(2)+'bn at 30 June 2026 · lending income net of agent fee '+v.baseCurrency+' '+(v.reportedLendingRevenueNet/1e6).toFixed(2)+'m (not securities on loan).');
   if(v.auditDerivedLoanPctNav!=null) make('Workbook-derived securities on loan '+v.auditDerivedLoanPctNav.toFixed(2)+'% NAV at 30 June 2026. Requires reconciliation to report lending schedule.');
 }
 if(f.auditMedianExchangeTurnoverGbpM3m!=null){
    make('INDICATIVE 3-MONTH EXCHANGE TURNOVER: GBP '+f.auditMedianExchangeTurnoverGbpM3m.toFixed(2)+'m median per day; '+(f.auditZeroVolumeDays3m??'unknown')+' zero-volume days in sample. Yahoo exchange quotes, approximate; not bid/ask spread, off-exchange volume or executable liquidity. '+(f.auditTickerOnly?'WARNING: ticker-only match; ISIN absent.':''));
 }
 if(f.auditIsinConflict)make('DATA QUALITY: '+f.auditIsinConflict);
 if(f.audit2026Flags)make('AUDIT FLAG: '+f.audit2026Flags);
 if(f.auditLendingLevelNote)make('Audited workbook lending observation (dated, not refreshed): '+f.auditLendingLevelNote);
 if(f.auditCollateralNote)make('Collateral observation (audit): '+f.auditCollateralNote);
 if(f.auditCounterpartyNote)make('Counterparty research gap: '+f.auditCounterpartyNote);
};
const _renderDqBeforeAudit2=renderDataQuality;
renderDataQuality=function(){
 _renderDqBeforeAudit2();
 let el=document.getElementById('etf-extra-audit-coverage');
 if(!el){const anchor=document.getElementById('etf-issuer-integrity');if(!anchor)return;
   el=document.createElement('p');el.className='note';el.id='etf-extra-audit-coverage';anchor.insertAdjacentElement('afterend',el);}
 const x=ETF_DATA.etfAudit2026Coverage||{};
 el.textContent='External 78-line audit (NOT the full '+(x.catalogueRows||'—')+' fund catalogue): '+(x.auditIsinMatched||0)+' ISIN matches, '+(x.auditTickerOnly||0)+' ticker-only matches; '+(x.vanguardFundClassesMatched||0)+' Vanguard class records; '+(x.indicativeTurnoverRows||0)+' indicative daily turnover observations, 0 verified spreads. Delisted LSE lines removed: CECL.L, TURL.L.';
};

renderUsBondReferences();
'''

COMPACT_ETF_CSS = r"""
/* ETF v5: fixed table grid, no sideways scroll, consistent group rows. */
#etf-tracker-panel {min-width:0;max-width:100%;overflow-x:clip}
#etf-tracker-panel .etf-table-scroll {width:100%;max-width:100%;overflow-x:hidden;overflow-y:auto}
#etf-tracker-panel .etf-table {width:100%;max-width:100%;min-width:0!important;table-layout:fixed;border-collapse:collapse}
#etf-tracker-panel .etf-table thead th {position:sticky;top:0;z-index:2;text-align:left;line-height:1.25;vertical-align:middle;white-space:normal;overflow-wrap:break-word;background:#17171b}
#etf-tracker-panel .etf-table th,#etf-tracker-panel .etf-table td {box-sizing:border-box;font-size:11px;padding:8px 6px;vertical-align:middle;line-height:1.35;white-space:normal;overflow-wrap:break-word}
#etf-tracker-panel .etf-table th:nth-child(1){width:41%}
#etf-tracker-panel .etf-table th:nth-child(2){width:7%}
#etf-tracker-panel .etf-table th:nth-child(3){width:6%}
#etf-tracker-panel .etf-table th:nth-child(4){width:15%}
#etf-tracker-panel .etf-table th:nth-child(5){width:8%}
#etf-tracker-panel .etf-table th:nth-child(6){width:8%}
#etf-tracker-panel .etf-table th:nth-child(7){width:8%}
#etf-tracker-panel .etf-table th:nth-child(8){width:7%}
#etf-tracker-panel .etf-table th:nth-child(n+2),#etf-tracker-panel .etf-table td:nth-child(n+2){text-align:right}
#etf-tracker-panel .etf-table th:nth-child(3),#etf-tracker-panel .etf-table td:nth-child(3),#etf-tracker-panel .etf-table th:nth-child(8),#etf-tracker-panel .etf-table td:nth-child(8){text-align:center}
#etf-tracker-panel .etf-table tr.etf-geo-group th {text-align:left!important;font-size:11px;font-weight:700;letter-spacing:.02em;color:#a0c4de;background:#15202b;border-top:1px solid #365069;padding:10px 8px;white-space:normal}
#etf-tracker-panel .etf-table .etf-compact-fund{display:block;font-weight:650;line-height:1.3}
#etf-tracker-panel .etf-table .etf-compact-sub{display:block;font-size:10px;margin-top:3px;color:var(--muted);line-height:1.3}
#etf-tracker-panel .etf-table .etf-compact-code{font-weight:750;letter-spacing:.04em}
#etf-tracker-panel .etf-table td.etf-compact-compare input{width:15px;height:15px;vertical-align:middle;margin:0;cursor:pointer}
#etf-tracker-panel .etf-table tr.etf-active td{background:#342516}
#etf-tracker-panel .etf-table tr[data-etf-symbol]{cursor:pointer}
#etf-tracker-panel .etf-table tbody tr[data-etf-symbol]:hover td{background:#29231a}
#etf-tracker-panel .etf-peer-box {min-width:0;max-width:100%;overflow-x:hidden}
#etf-tracker-panel .etf-peer-box .small-scroll{max-width:100%;overflow-x:hidden}
#etf-tracker-panel .etf-peer-box table {width:100%;max-width:100%;min-width:0!important;table-layout:fixed}
#etf-tracker-panel .etf-peer-box td,#etf-tracker-panel .etf-peer-box th {font-size:11px;white-space:normal!important;overflow-wrap:anywhere;padding:7px 5px}
#etf-tracker-panel .etf-detail {min-width:0;max-width:100%}
#etf-tracker-panel .etf-compare-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:9px 0 16px}
#etf-tracker-panel .etf-compare-card {background:#1d2026;border:1px solid #373e48;border-radius:5px;padding:12px;min-width:0}
#etf-tracker-panel .etf-compare-card.etf-current-card{border-color:#d09a4f}
#etf-tracker-panel .etf-compare-card h4{font-size:12px;line-height:1.35;margin:0 0 5px;overflow-wrap:anywhere}
#etf-tracker-panel .etf-compare-card .etf-card-meta{font-size:10px;line-height:1.35;color:var(--muted);margin-bottom:8px}
#etf-tracker-panel .etf-card-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:7px 0}
#etf-tracker-panel .etf-card-facts div{min-width:0}
#etf-tracker-panel .etf-card-facts span{display:block;font-size:10px;color:var(--muted)}
#etf-tracker-panel .etf-card-facts strong{display:block;font-size:12px;font-weight:600;overflow-wrap:anywhere}
#etf-tracker-panel .etf-card-actions{display:flex;align-items:center;gap:8px;margin-top:9px;flex-wrap:wrap}
#etf-tracker-panel .etf-card-actions button {background:#30343b;color:#f1e9db;border:1px solid #50525b;padding:5px 9px;border-radius:4px;cursor:pointer;font-size:11px}
#etf-tracker-panel .etf-card-actions label{font-size:11px;display:flex;align-items:center;gap:5px}
#etf-tracker-panel #etf-selected-comparisons,#etf-tracker-panel #etf-extra-index-funds{margin-top:13px}
#etf-tracker-panel #etf-selected-comparisons h3,#etf-tracker-panel #etf-extra-index-funds h3{font-size:13px;color:var(--amber);margin:0 0 7px}
#etf-tracker-panel .etf-compare-card .etf-card-source{font-size:10px;color:var(--muted);margin-top:6px;overflow-wrap:anywhere}
@media(max-width:840px){
 #etf-tracker-panel .etf-table th:nth-child(7),#etf-tracker-panel .etf-table td:nth-child(7){display:none!important}
 #etf-tracker-panel .etf-table th:nth-child(1){width:43%}
 #etf-tracker-panel .etf-table th:nth-child(2){width:9%}
 #etf-tracker-panel .etf-table th:nth-child(3){width:7%}
 #etf-tracker-panel .etf-table th:nth-child(4){width:17%}
 #etf-tracker-panel .etf-table th:nth-child(5){width:9%}
 #etf-tracker-panel .etf-table th:nth-child(6){width:9%}
 #etf-tracker-panel .etf-table th:nth-child(8){width:6%}
}
@media(max-width:700px){
 #etf-tracker-panel .etf-table th,#etf-tracker-panel .etf-table td{padding:7px 4px;font-size:10px}
 #etf-tracker-panel .etf-table th:nth-child(5),#etf-tracker-panel .etf-table td:nth-child(5){display:table-cell!important}
 #etf-tracker-panel .etf-table th:nth-child(6),#etf-tracker-panel .etf-table td:nth-child(6){display:none!important}
 #etf-tracker-panel .etf-table th:nth-child(1){width:50%}
 #etf-tracker-panel .etf-table th:nth-child(2){width:10%}
 #etf-tracker-panel .etf-table th:nth-child(3){width:8%}
 #etf-tracker-panel .etf-table th:nth-child(4){width:17%}
 #etf-tracker-panel .etf-table th:nth-child(5){width:9%}
 #etf-tracker-panel .etf-table th:nth-child(8){width:6%}
 #etf-tracker-panel .etf-compare-grid{grid-template-columns:1fr}
 #etf-tracker-panel .etf-peer-box table{display:block;width:100%}
 #etf-tracker-panel .etf-peer-box table thead{display:none}
 #etf-tracker-panel .etf-peer-box table tbody{display:grid;gap:7px}
 #etf-tracker-panel .etf-peer-box table tbody tr{display:grid;gap:3px;min-width:0;padding:8px;border:1px solid var(--line);border-radius:5px}
 #etf-tracker-panel .etf-peer-box table tbody td{display:flex;justify-content:space-between;gap:6px;max-width:100%;width:100%;border:0;text-align:right!important;min-width:0}
 #etf-tracker-panel .etf-peer-box table tbody td::before{content:attr(data-compact-label);font-weight:600;color:var(--muted);text-align:left}
}
@media(max-width:470px){
 #etf-tracker-panel .etf-table th:nth-child(4),#etf-tracker-panel .etf-table td:nth-child(4){display:none!important}
 #etf-tracker-panel .etf-table th:nth-child(1){width:58%}
 #etf-tracker-panel .etf-table th:nth-child(2){width:12%}
 #etf-tracker-panel .etf-table th:nth-child(3){width:8%}
 #etf-tracker-panel .etf-table th:nth-child(5){width:13%}
 #etf-tracker-panel .etf-table th:nth-child(8){width:9%}
 #etf-tracker-panel .etf-card-facts{grid-template-columns:repeat(2,minmax(0,1fr))}
}

"""
COMPACT_ETF_JS = r"""
// ETF RESEARCH v5. The eight column positions and row cells are built together.
// This code runs after the original research/issuer/chart code and does not remove its data.
if (typeof ETF_GEO === 'object') {
  Object.assign(ETF_GEO, {
    'US equal weight':[1,3,'United States'],
    'UK FTSE All Share':[2,2,'United Kingdom'],
    'Saudi Arabia':[5,6,'Emerging markets']
  });
}
function etfV5Kind(f){
  // An issuer may confirm physical without identifying full versus sampling.
  const type=String(f.replicationType||'').toLowerCase();
  const status=String(f.replicationStatus||'').toLowerCase();
  const method=String(f.replication||'').toLowerCase();
  const issuerDetail=String(f.issuerReplicationDetail||'').toLowerCase();
  const raw=[type,method,issuerDetail].join(' ');
  if(raw.includes('synthetic')||raw.includes('swap'))return ['S','Synthetic / swap'];
  if(raw.includes('physical') || (status.includes('physical')&&!status.includes('unknown'))){
    let subtype=method.includes('sampling')||issuerDetail.includes('optimis')||issuerDetail.includes('sampling')?'Physical sampling / optimised':
        status.includes('submethod')||status.includes('subtype')?'Physical (submethod not confirmed)':
        method.includes('full')||issuerDetail.includes('full replication')?'Physical full replication':'Physical (submethod not confirmed)';
    return ['P',subtype];
  }
  return ['?','Replication method not verified'];
}
function etfV5Key(f){
  // Do not conflate hedged and unhedged share classes, nor a price proxy with a benchmark.
  const b=String(f.benchmark||'').trim().toLowerCase().replace(/\s+/g,' ');
  const h=String(f.hedged||'').trim().toLowerCase();
  return b ? [f.category,b,h].join('|') : 'unknown:'+f.symbol;
}
function etfV5PickMain(){
  const all=etfFiltered().filter(f=>f.symbol!=='GEND.L');
  const groups=new Map();
  for(const f of all){const key=etfV5Key(f);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(f);}
  const keep=new Set();
  for(const funds of groups.values()){
    funds.sort((a,b)=> (a.terPct??Infinity)-(b.terPct??Infinity) ||
       (etfAumUSD(b)??0)-(etfAumUSD(a)??0) || a.symbol.localeCompare(b.symbol));
    // The selected ETF is always visible after choosing it in the comparison area.
    const selected=funds.find(f=>f.symbol===etfState.selected);
    const first=funds.slice(0,2);
    if(selected && !first.includes(selected))first[1]=selected;
    for(const f of first)keep.add(f.symbol);
  }
  return {all,shown:all.filter(f=>keep.has(f.symbol)),suppressed:all.length-keep.size};
}
function etfV5PeerLabels(){
  for(const table of document.querySelectorAll('#etf-tracker-panel .etf-peer-box table')){
    const titles=[...table.querySelectorAll('thead th')].map(th=>th.textContent.trim());
    for(const row of table.querySelectorAll('tbody tr')){
      [...row.cells].forEach((td,i)=>{td.dataset.compactLabel=titles[i]||'Detail';});
    }
  }
}
function etfV5Choose(symbol){
  const fund=ETF_BY_SYMBOL.get(symbol);if(!fund)return;
  etfState.selected=symbol;
  if(typeof etfCompareBenchmark!=='undefined')etfCompareBenchmark=fund.benchmark||'';
  renderEtfTracker();
}
function etfV5ChangeCompare(symbol,yes){
  if(yes){
    if(!etfState.compared.has(symbol)&&etfState.compared.size>=5){
      const note=document.getElementById('etf-v5-compare-note');
      if(note)note.textContent='Maximum five additional comparison funds. Untick one to add another.';
      return false;
    }
    etfState.compared.add(symbol);
    etfState.selected=symbol;
    if(typeof etfCompareBenchmark!=='undefined')etfCompareBenchmark=ETF_BY_SYMBOL.get(symbol)?.benchmark||'';
  }else{etfState.compared.delete(symbol);}
  renderEtfTracker();
  return true;
}
function etfV5Card(f,tag,withCheckbox=true){
  const card=el('div','etf-compare-card'+(f.symbol===etfState.selected?' etf-current-card':''));
  const title=el('h4','',f.name);card.append(title);
  card.append(el('div','etf-card-meta',f.symbol+' · '+f.market+' · '+(f.benchmark||'Benchmark unknown')+' · '+(f.isin||'ISIN missing')));
  if(tag)card.append(el('div','etf-card-meta',tag));
  const metrics=el('div','etf-card-facts');
  const [code,kind]=etfV5Kind(f);
  const values=[['TER',etfFee(f)],['Structure',code+' · '+kind],['Fund AUM',etfFundSize(f)],
                ['1Y',etfPct(f.return1Y)],['3Y',etfPct(f.return3Y)],['5Y',etfPct(f.return5Y)],
                ['3Y NAV TE',f.officialTrackingError3Y!=null?etfPct(f.officialTrackingError3Y):'—'],
                ['Income',f.distribution||'—'],['Domicile',f.domicile||'—']];
  for(const [label,value] of values){const box=el('div');box.append(el('span','',label),el('strong','',value));metrics.append(box);}
  card.append(metrics);
  const buttons=el('div','etf-card-actions');
  const button=el('button','','Details');button.type='button';button.setAttribute('aria-label','Full details for '+f.symbol);
  button.onclick=()=>etfV5Choose(f.symbol);buttons.append(button);
  if(withCheckbox){
    const label=el('label');const input=el('input');input.type='checkbox';input.checked=etfState.compared.has(f.symbol);
    input.onchange=()=>{if(!etfV5ChangeCompare(f.symbol,input.checked))input.checked=false;};
    label.append(input,document.createTextNode('Compare'));buttons.append(label);
  }
  const url=f.issuerVerifiedUrl||f.terUrl||f.issuerFactsUrl;
  if(url&&/^https:\/\//.test(url)){
    const link=el('a','','Issuer / factsheet');link.href=url;link.target='_blank';link.rel='noopener noreferrer';buttons.append(link);
  }
  card.append(buttons);
  const prov=el('div','etf-card-source',
     'TER: '+(f.terStatus||'unverified')+(f.terCheckedAt?' · '+f.terCheckedAt:'')+
     ' · Replication: '+(f.replicationStatus||'not checked')+
     (f.fundSizeAsOf?' · AUM '+f.fundSizeAsOf:''));
  card.append(prov);
  return card;
}
function etfV5RenderSelectedComparisons(){
  let root=$('etf-selected-comparisons');if(!root)return;
  root.replaceChildren();
  root.append(el('h3','','CHECKED ETF COMPARISON — DETAILED DATA'));
  const msg=el('p','note','Tick Compare in the main table or benchmark section. Select Details to expand any fund. Up to five checked funds plus the selected fund can be plotted.');
  root.append(msg);
  const note=el('p','note','');note.id='etf-v5-compare-note';root.append(note);
  const members=[...etfState.compared].map(s=>ETF_BY_SYMBOL.get(s)).filter(Boolean);
  if(!members.length){root.append(el('p','mini','No ETFs selected.'));return;}
  const wrap=el('div','etf-compare-grid');members.forEach(f=>wrap.append(etfV5Card(f,'Checked for chart comparison',true)));root.append(wrap);
}
// The selector continues to work, but same-benchmark funds not shown in the main
// two-per-benchmark list live in this comparison section, with full details links.
renderSameIndexETFs=function(){
  const target=$('etf-same-index'),selector=$('etf-same-index-benchmark');if(!target||!selector)return;
  const groups=new Map();
  for(const f of ETF_FUNDS){if(f.symbol==='GEND.L'||!f.benchmark)continue;
    if(!groups.has(f.benchmark))groups.set(f.benchmark,[]);groups.get(f.benchmark).push(f);}
  const names=[...groups.keys()].filter(k=>groups.get(k).length>=2).sort();
  const chosen=typeof etfCompareBenchmark!=='undefined'?etfCompareBenchmark:'';
  const current=chosen&&names.includes(chosen)?chosen:
    (names.includes(ETF_BY_SYMBOL.get(etfState.selected)?.benchmark)?ETF_BY_SYMBOL.get(etfState.selected).benchmark:(names[0]||''));
  if(selector.options.length!==names.length||[...selector.options].some((o,i)=>o.value!==names[i])){
    selector.replaceChildren(...names.map(k=>new Option(k+' ('+groups.get(k).length+')',k)));
  }
  selector.value=current;
  target.replaceChildren();
  const all=(groups.get(current)||[]).slice().sort((a,b)=>(a.terPct??Infinity)-(b.terPct??Infinity)||a.symbol.localeCompare(b.symbol));
  if(!all.length)return;
  const selection=etfV5PickMain().shown;
  const main=new Set(selection.map(f=>f.symbol));
  const extra=all.filter(f=>!main.has(f.symbol));
  target.append(el('p','note',current+': '+all.length+' funds. The main list shows at most two per benchmark; other listings appear here. Exact benchmark identity matters; hedged funds can differ.'));
  if(extra.length){
    target.append(el('h4','','OTHER FUNDS ON THIS BENCHMARK'));
    const cards=el('div','etf-compare-grid');for(const f of extra)cards.append(etfV5Card(f,'Not in main table',true));target.append(cards);
  }
  const allDetails=el('details');const sum=el('summary','','All '+all.length+' fund lines for '+current);allDetails.append(sum);
  const wrap=el('div','etf-compare-grid');for(const f of all)wrap.append(etfV5Card(f,main.has(f.symbol)?'Main table':'Additional',true));
  allDetails.append(wrap);target.append(allDetails);
};
const _etfV5PriorRender=renderEtfTracker;
renderEtfTracker=function(){
  _etfV5PriorRender(); // existing risk, issuer facts, chart, data-quality links preserved
  const tbody=$('etf-rows'),table=tbody?.closest('table'),thead=table?.querySelector('thead');
  if(!tbody||!table||!thead)return;
  const labels=['Fund / ticker','TER','P/S','Fund AUM','1Y','3Y','5Y','Cmp'];
  const head=el('tr');
  for(const label of labels){const th=el('th','',label);th.scope='col';
    if(label==='TER')th.title='Annual ongoing charge. Not tracking error.';
    if(label==='Cmp')th.title='Tick to add this fund to the detailed comparison and display its expanded facts.';
    if(label==='P/S')th.title='P: physical; S: synthetic; ?: unknown. Click a fund for the exact replication detail.';
    if(['1Y','3Y','5Y'].includes(label))th.title='Annualised adjusted-close price proxy. Not certified NAV total return.';
    head.append(th);
  }
  thead.replaceChildren(head);
  const {all,shown,suppressed}=etfV5PickMain();
  const frag=document.createDocumentFragment();let lastGroup='';
  for(const f of shown){
    const region=typeof etfRegion==='function'?etfRegion(f)[2]:f.market;
    if($('etf-sort')?.value==='market'&&region!==lastGroup){
      const gr=el('tr','etf-geo-group'),th=el('th','',region||f.market);th.colSpan=8;th.scope='rowgroup';gr.append(th);frag.append(gr);lastGroup=region;
    }
    const row=el('tr',f.symbol===etfState.selected?'etf-active':'');row.dataset.etfSymbol=f.symbol;
    row.setAttribute('aria-label','View details of '+f.name);
    const name=etfCell(row,'');name.append(el('span','etf-compact-fund',f.name),el('span','etf-compact-sub',f.symbol+' · '+f.market));
    const fee=etfCell(row,etfFee(f),'n');fee.title=(f.terSource||f.terStatus||'Unverified')+(f.terCheckedAt?' · '+f.terCheckedAt:'');
    const [code,label]=etfV5Kind(f);const codecell=etfCell(row,code,'etf-compact-code');codecell.title=label+' · '+(f.replicationStatus||'unverified');
    const aum=etfCell(row,etfFundSize(f),'n');aum.title=(f.fundSizeSource||'Fund AUM unverified')+(f.fundSizeAsOf?' · '+f.fundSizeAsOf:'');
    etfCell(row,etfPct(f.return1Y),'n');etfCell(row,etfPct(f.return3Y),'n');etfCell(row,etfPct(f.return5Y),'n');
    const cell=etfCell(row,'','etf-compact-compare');
    const check=el('input');check.type='checkbox';check.checked=etfState.compared.has(f.symbol);
    check.setAttribute('aria-label','Compare '+f.symbol);check.onchange=()=>{if(!etfV5ChangeCompare(f.symbol,check.checked))check.checked=false;};cell.append(check);
    row.onclick=(e)=>{if(e.target.closest('input,button,a'))return;etfV5Choose(f.symbol);};
    frag.append(row);
  }
  tbody.replaceChildren(frag);
  const label=$('etf-result-count');if(label)label.textContent=shown.length+' funds · '+suppressed+' same-index alternatives · 1Y/3Y/5Y annualised';
  // Older wrappers used a seven-column layout; these eight match the headers.
  etfV5RenderSelectedComparisons();
  renderSameIndexETFs();
  etfV5PeerLabels();
};
// The expanded facts must always read from ETF_BY_SYMBOL[etfState.selected].
const _etfV5PriorDetails=etfDetails;
etfDetails=function(){
  _etfV5PriorDetails();
  const f=ETF_BY_SYMBOL.get(etfState.selected);if(!f)return;
  const detail=$('etf-detail-stats');
  if(detail){
    const nodes=[...detail.querySelectorAll('.etf-stat')];
    for(const tile of nodes){
      const name=tile.querySelector('.k')?.textContent?.trim()||'';
      if(/^(last quotation|current price|last price|1Y tracking error)$/i.test(name)){tile.remove();continue;}
      const val=tile.querySelector('.v'),description=tile.querySelector('.d');if(!val)continue;
      if(/^Annual OCF\s*\/\s*TER$/i.test(name)){
        val.textContent=etfFee(f);
        if(description)description.textContent=(f.terStatus||'Unverified')+(f.terAsOf?' · '+f.terAsOf:'');
      }else if(/^Replication$/i.test(name)){
        const [code,method]=etfV5Kind(f);val.textContent=code+' — '+method;
        if(description)description.textContent=f.replicationStatus||'Issuer replication not independently confirmed';
      }else if(/^Fund size$/i.test(name)){
        val.textContent=etfFundSize(f);
        if(description)description.textContent=(f.fundSizeStatus||'AUM not verified')+(f.fundSizeAsOf?' · '+f.fundSizeAsOf:'');
      }
    }
  }
  const host=$('etf-structure-stats');if(host){
    for(const tile of [...host.querySelectorAll('.etf-stat')]){
      const label=tile.querySelector('.k')?.textContent?.trim()||'';
      if(/^Replication type$/i.test(label)){
        const v=tile.querySelector('.v');if(v)v.textContent=etfV5Kind(f)[1];
      }
    }
  }
  etfV5PeerLabels();
};
// Put checkbox comparison cards beside the selected-fund details, not in Data Quality.
function etfV5InitComparisonHost(){
  if($('etf-selected-comparisons'))return;
  const anchor=$('etf-issuer-snapshot')||$('etf-cost-peers');if(!anchor)return;
  const section=el('section','etf-peer-box');section.id='etf-selected-comparisons';
  anchor.parentNode.insertBefore(section,anchor);
}
// init() calls renderEtfTracker; create the host once at script evaluation.
etfV5InitComparisonHost();

"""

def inject_template(path:pathlib.Path,dry_run=False):
    source=path.read_text(encoding='utf-8')
    if 'id="etf-issuer-snapshot"' in source:return False
    if source.count('id="etf-audit-panel"')!=1 or 'ETF_BY_SYMBOL' not in source:
        raise RuntimeError('ETF-generated dashboard missing; do not patch original template')
    # Preserve all panels, and relocate the existing ETF audit from Analytics to Data Quality.
    old="'compare','score-panel','etf-audit-panel']"
    new="'compare','score-panel']"
    if source.count(old)!=1:raise RuntimeError('Unexpected ETF audit workspace config')
    source=source.replace(old,new,1)
    old="['quality-panel','sources']]"
    new="['etf-audit-panel','quality-panel','sources']]"
    if source.count(old)!=1:raise RuntimeError('Missing data quality workspace config')
    source=source.replace(old,new,1)
    extra='''\n    <section class="etf-peer-box" id="etf-issuer-snapshot" aria-label="Issuer tracking comparison"></section>
    <section class="etf-peer-box" aria-label="US domiciled bond ETF references">
      <details><summary>US-DOMICILED BOND ETF COSTS &amp; FUND ASSETS — RESEARCH REFERENCE ONLY</summary>
        <p class="note">US-domiciled ETFs; PRIIPs documentation and UK retail access may restrict purchases. These fees are NOT UCITS equivalents. US dividends/yield definitions differ from UK OCF.</p>
        <div class="small-scroll" id="etf-us-reference-body"></div>
      </details>
    </section>
'''
    anchor='<div id="etf-cost-peers"'
    if source.count(anchor)!=1:raise RuntimeError('ETF peer panel insertion point changed')
    source=source.replace(anchor,extra+anchor,1)
    old='<div class="research-stats" id="etf-audit-stats"></div>'
    if source.count(old)!=1:raise RuntimeError('ETF quality status insertion anchor missing')
    source=source.replace(old,old+'<p class="note" id="etf-issuer-integrity"></p>',1)
    anchor='// UK GILT SECURITY MONITOR — conventional UK gilts, quoted clean price when sourced.'
    if source.count(anchor)!=1:raise RuntimeError('Expected ETF JS insertion marker missing')
    source=source.replace(anchor,FRONTEND_JS+'\n'+COMPACT_ETF_JS+'\n'+anchor,1)
    source=source.replace('</head>','<style>'+COMPACT_ETF_CSS+'</style></head>',1)
    if source.count('/*__DATA__*/null')!=1:raise RuntimeError('Lost dashboard data placeholder')
    if not dry_run:path.write_text(source,encoding='utf-8')
    return True

def install(repo:pathlib.Path,dry_run=False):
    validate()
    paths=[repo/x for x in ('etf_catalog.csv','build_terminal.py','terminal_template.html')]
    for p in paths:
        if not p.is_file():raise FileNotFoundError('Missing '+p.name)
    # Compute replacements for all three in isolation first; if one fails, no files are changed.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        temp=pathlib.Path(tmp)
        for p in paths:shutil.copy2(p,temp/p.name)
        counts=install_catalogue(temp/'etf_catalog.csv')
        is_build=inject_build(temp/'build_terminal.py')
        is_template=inject_template(temp/'terminal_template.html')
        if not dry_run:
            for p in paths:
                updated=(temp/p.name).read_bytes()
                if updated!=p.read_bytes():
                    backup=p.with_name(p.name+'.before-etf-issuer-update.bak')
                    if not backup.exists():shutil.copy2(p,backup)
                    p.write_bytes(updated)
    return counts,is_build,is_template

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=pathlib.Path,default=pathlib.Path.cwd())
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args(argv)
    counts,build,template=install(args.repo,args.dry_run)
    print('ISIN matched issuer evidence: %d rows; catalogue %d -> %d (+%d).'%(
       len(facts()),counts['original'],counts['final'],counts['netChange']))
    print('Conflicts:',counts['conflicts'],'build patch:',build,'template patch:',template,
          '(dry-run)' if args.dry_run else '')
    return 0

if __name__=='__main__':sys.exit(main())
