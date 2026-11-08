#!/usr/bin/env python3
"""Apply ISIN-matched ETF issuer snapshots to the existing Market Terminal.

Run AFTER install_etf_trackers.py and BEFORE build_terminal.py.

The November 2026 photos are a dated fallback, not live data. Live first-party
issuer data wins. Fund AUM never represents exchange volume or spreads.
US-domiciled IVV, IEMG, IEFA etc. are deliberately excluded from UK UCITS rows.
"""
import argparse
import csv
import io
from pathlib import Path
import shutil
import sys

SOURCE = 'symbol,isin,ter,aum,currency,asof,method,evidence,te3,issuer,source_date,url,note\nINRG.L,IE00B1XNHC34,0.65,2975290000,USD,2026-10-31,,"Physical, replication detail not specified",,iShares,2026-11-04,https://www.ishares.com/uk/individual/en/products/251911/,"Fund AUM $2,975.29m; distinct from share class $2,600.26m."\nITKY.L,IE00B1FZS574,0.74,101850000,USD,2026-10-31,,"Physical, replication detail not specified",,iShares,2026-11-04,https://www.ishares.com/uk/individual/en/products/251879/,\nSPOL.L,IE00B4M7GH52,0.74,1120830000,USD,2026-10-31,,"Physical, replication detail not specified",,iShares,2026-11-04,https://www.ishares.com/uk/individual/en/products/251875/,\nCMX1.L,IE00B5WHFQ43,0.65,116480000,USD,2026-10-31,,"Physical, replication detail not specified",,iShares,2026-11-04,https://www.ishares.com/uk/individual/en/products/253734/,\nLTAM.L,IE00B27YCK28,0.2,1921140000,USD,2026-10-31,Physical sampling,Physical optimised; matches sampling classification,,iShares,2026-11-04,https://www.ishares.com/uk/individual/en/products/251856/,\nFWRG.L,IE000716YHJ7,0.15,5184690000,USD,2026-09-30,,"Physical, replication detail not specified",,Invesco,2026-09-30,https://www.invesco.com/content/dam/invesco/emea/en/product-documents/etf/share-class/factsheet/IE000716YHJ7_factsheet_en.pdf,\nEQQQ.L,IE0032077012,0.3,21610380000,USD,2026-09-30,,"Physical, replication detail not specified",,Invesco,2026-09-30,https://www.invesco.com/content/dam/invesco/emea/en/product-documents/etf/share-class/factsheet/IE0032077012_factsheet_en.pdf,\nHMCX.L,IE00B64PTF05,0.09,60311075,GBP,2026-09-30,Physical full,Physical full; 3-year tracking error is 0.07%,0.07,HSBC,2026-09-30,,"Issuer\'s reported 3Y NAV tracking error, not indicative price-based TE."\nISPY.L,IE00BYPLS672,0.69,3924100000,USD,2026-11-05,Physical full,Physical full,,L&G,2026-11-05,,\nSMH.L,IE00BMC38736,0.35,8324900000,USD,2026-10-31,Physical full,Physical full,,VanEck,2026-10-31,https://www.vaneck.com/uk/en/library/fact-sheets/smh-fact-sheet.pdf,USD LSE listing SMH; GBP LSE listing SMGB. Old SEMI.L line was not evidenced.\nFRIN.L,IE00BHZRQZ17,0.19,2400000000,USD,2026-11-06,Physical full,Physical full,,Franklin Templeton,2026-11-06,https://www.franklintempleton.co.uk/our-funds/etf/price-and-performance/products/27853/SINGLCLASS/IE00BHZRQZ17,FRIN is the GBP LSE ticker; USD LSE listing is FLXI.\nFRXT.L,IE000CM02H85,0.19,1120000000,USD,2026-11-06,Physical full,Physical full,,Franklin Templeton,2026-11-06,https://www.franklintempleton.co.uk/our-funds/etf/price-and-performance/products/32637/SINGLCLASS/IE000CM02H85,FRXT is the GBP LSE ticker; USD LSE listing is FLXT.\nFVUB.L,IE00BHZRQY00,0.19,229440000,USD,2026-11-06,Physical full,Physical full,,Franklin Templeton,2026-11-06,https://www.franklintempleton.co.uk/our-funds/etf/price-and-performance/products/27851/SINGLCLASS/IE00BHZRQY00,FVUB is the GBP LSE ticker; USD LSE listing is FLXB.\nFLXK.L,IE00BHZRR030,0.09,4030000000,USD,2026-11-06,Physical full,Physical full,,Franklin Templeton,2026-11-06,https://www.franklintempleton.co.uk/our-funds/etf/price-and-performance/products/27854/SINGLCLASS/IE00BHZRR030,\nKSA.L,IE000C7DDDX4,0.39,5780000,USD,2026-11-06,Physical full,Physical full,,Franklin Templeton,2026-11-06,https://www.franklintempleton.co.uk/our-funds/etf/price-and-performance/products/41675/SINGLCLASS/IE000C7DDDX4,"KSA is the LSE USD ticker, FLXS is the Xetra ticker; very small fund."\nCG1.L,FR0010655712,0.1,1446410000,EUR,,,Direct physical; full vs sampled unspecified,,Amundi,2026-11-08,https://www.amundietf.co.uk/en/individual/products/equity/amundi-dax-ucits-etf/fr0010655712,"Amount €1,446.41m captured 8 November; exact NAV date not visible. Different ISIN from C001.DE."\nCAC.PA,FR0007052782,0.25,4233280000,EUR,,,Direct physical; full vs sampled unspecified,,Amundi,2026-11-08,https://www.amundietf.co.uk/en/professional/products/equity/amundi-cac-40-ucits-etf-dist/fr0007052782,"Amount €4,233.28m captured 8 November; precise fund reporting date not visible."\n'

EXTRA_ROWS = {
    "FLXK.L": ("Equity", "South Korea", "Franklin FTSE Korea", "FTSE Korea 30/18 Capped",
               "^KS11", "KOSPI is a proxy, not the fund benchmark."),
    "KSA.L": ("Equity", "Saudi Arabia", "Franklin FTSE Saudi Arabia",
              "FTSE Saudi Arabia 30/18 Capped", "", "Small fund; check spread/liquidity."),
    "CG1.L": ("Equity", "Germany DAX", "Amundi DAX UCITS ETF (FR)",
              "DAX", "^GDAXI", "FR0010655712; not the same fund as C001.DE."),
}
DISTRIBUTIONS = {
    "INRG.L": "Dist", "ITKY.L": "Dist", "SPOL.L": "Acc", "CMX1.L": "Acc",
    "LTAM.L": "Dist", "FWRG.L": "Acc", "EQQQ.L": "Dist", "HMCX.L": "Dist",
    "ISPY.L": "Acc", "SMH.L": "Acc", "FRIN.L": "Acc", "FRXT.L": "Acc",
    "FVUB.L": "Acc", "FLXK.L": "Acc", "KSA.L": "Acc",
    "CG1.L": "Mixed", "CAC.PA": "Dist",
}
# These factsheets merely say physical/replicated, without specifying whether
# the portfolio contains every constituent or is optimised/sampled.
UNSPECIFIED_PHYSICAL = {"INRG.L", "ITKY.L", "SPOL.L", "CMX1.L",
                        "FWRG.L", "EQQQ.L", "CG1.L", "CAC.PA"}


def snapshots():
    return {r["symbol"]: r for r in csv.DictReader(io.StringIO(SOURCE))}


def validate(records):
    expected = snapshots()
    seen = set()
    for symbol, row in records.items():
        assert symbol not in seen
        seen.add(symbol)
        assert len(row["isin"]) == 12 and row["isin"][:2].isalpha()
        assert row["currency"] in ("GBP", "EUR", "USD")
        assert 0.0 <= float(row["ter"]) <= 5.0
        assert float(row["aum"]) > 0
        assert row["source_date"]
    assert len(expected) == 17, "Unexpected issuer evidence count"


def patch_catalog(path, dry_run=False):
    if not path.is_file():
        raise FileNotFoundError("Missing etf_catalog.csv in "+str(path.parent))
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    if not fields or "isin" not in fields or "symbol" not in fields:
        raise RuntimeError("Unexpected ETF catalogue format")
    sources = snapshots()
    if any(r["symbol"] == "SEMI.L" and "VanEck Semiconductor" in r["name"]
           for r in rows):
        if any(r["symbol"] == "SMH.L" for r in rows):
            raise RuntimeError("Both SEMI.L and SMH.L present. Review duplicate before migration.")
        for r in rows:
            if r["symbol"] == "SEMI.L" and "VanEck Semiconductor" in r["name"]:
                r["symbol"] = "SMH.L"
                r["note"] = ("USD London ticker verified by VanEck. " +
                             (r.get("note") or ""))
    found = {r["symbol"]: r for r in rows}
    for symbol, s in sources.items():
        if symbol not in found and symbol in EXTRA_ROWS:
            category, market, name, benchmark, reference, note = EXTRA_ROWS[symbol]
            added = {k:"" for k in fields}
            added.update(category=category, market=market, symbol=symbol, name=name,
                         benchmark=benchmark, reference=reference, note=note)
            rows.append(added); found[symbol]=added
        r = found.get(symbol)
        if r is None:
            print("No matching catalogue line (not added):",symbol)
            continue
        current_isin=(r.get("isin") or "").upper()
        if current_isin and current_isin != s["isin"]:
            raise RuntimeError(
                "Refusing screenshot mapping for %s: catalogue ISIN %s != %s" %
                (symbol,current_isin,s["isin"]))
        r["isin"]=s["isin"]
        r["terPct"]=("%.2f" % float(s["ter"]))
        if s.get("method"):
            r["replication"]=s["method"]
        elif symbol in UNSPECIFIED_PHYSICAL:
            r["replication"]=""  # Physical known; full/sampling unproven.
        if symbol in DISTRIBUTIONS:
            r["distribution"]=DISTRIBUTIONS[symbol]
        if symbol in ("FWRG.L","EQQQ.L","SMH.L","ISPY.L"):
            r["domicile"]="Ireland"
        if symbol in ("CAC.PA","CG1.L"):
            r["domicile"]="France"
        comment="Source: %s issuer data, %s; fund size separately dated in snapshot." % (
            s["issuer"], s["source_date"])
        old=(r.get("note") or "")
        if comment not in old:
            r["note"]=(old+" | "+comment).strip(" |")
    if len({r["symbol"] for r in rows}) != len(rows):
        raise RuntimeError("Duplicate symbols after issuer patch")
    temp=io.StringIO(newline="")
    writer=csv.DictWriter(temp,fieldnames=fields,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    updated=temp.getvalue()
    original=path.read_text(encoding="utf-8-sig")
    if updated.replace("\r\n","\n") != original.replace("\r\n","\n"):
        if not dry_run:
            back=path.with_suffix(".before-issuer-snapshots.bak")
            if not back.exists(): shutil.copy2(path,back)
            path.write_text(updated,encoding="utf-8")
    return len(rows)


def patch_build(path, dry_run=False):
    text=path.read_text(encoding="utf-8")
    flag="    etf_data=apply_etf_issuer_data.enrich(etf_data)\n"
    if flag in text:
        return False
    marker="    warnings.extend(issuer_warnings);cached_count+=issuer_cached\n"
    imp="import etf_issuer_db\n"
    if marker not in text or imp not in text:
        raise RuntimeError("Unexpected build_terminal.py: issuer extension missing")
    updated=text.replace(imp,imp+"import apply_etf_issuer_data\n",1)
    updated=updated.replace(marker,marker+flag,1)
    compile(updated,str(path),"exec")
    if not dry_run: path.write_text(updated,encoding="utf-8")
    return True


def patch_template(path, dry_run=False):
    text=path.read_text(encoding="utf-8")
    updated=text.replace("Vanguard official NAV-based · ",
                         "Issuer-reported NAV tracking error · ")
    updated=updated.replace("Official Vanguard NAV tracking error when sourced",
                            "Issuer-reported NAV tracking error when sourced")
    if not dry_run and updated!=text:
        path.write_text(updated,encoding="utf-8")
    return updated!=text


def enrich(data):
    """Add only exact-ISIN issuer snapshots, after all online issuer enrichment."""
    rows=snapshots()
    stats={"matched":0,"fees":0,"aum":0,"replication":0,"te3":0,"conflicts":0}
    for f in data.get("funds", []):
        s=rows.get(f.get("symbol"))
        if not s:
            continue
        if (f.get("isin") or "").upper()!=s["isin"]:
            f["identifierWarning"]="Screenshot issuer ISIN conflicts with catalogue"
            stats["conflicts"]+=1
            continue
        stats["matched"]+=1
        source="%s dated issuer factsheet / screenshot" % s["issuer"]
        date=s["source_date"]
        # Never downgrade a successful, issuer-confirmed live TER.
        if f.get("terStatus")!="Issuer confirmed":
            f.update(terPct=float(s["ter"]),terStatus="Dated issuer factsheet",
                     terSource=source,terProvider=s["issuer"],
                     terCheckedAt=date,terUrl=s.get("url") or "")
            stats["fees"]+=1
        # Published fund AUM is a snapshot in the fund's base currency.
        # Keep previously fetched first-party fund-level AUM wherever present.
        if not f.get("fundSize") or not f.get("fundSizeSource"):
            f.update(fundSize=float(s["aum"]),fundSizeCurrency=s["currency"],
                     fundSizeAsOf=s["asof"],
                     fundSizeCheckedAt=date,
                     fundSizeSource=source + ("; exact fund AUM reporting date not shown" if not s["asof"] else ""),
                     fundSizeStatus="Dated issuer screenshot; not live",
                     issuerProvider=s["issuer"],issuerVerifiedUrl=s.get("url") or "")
            stats["aum"]+=1
        if s.get("method") and f.get("replicationStatus")!="Fund-specific issuer verified":
            f["replication"]=s["method"]
            f["replicationStatus"]="Fund-specific issuer verified"
            f["replicationCheckedAt"]=date
            f["issuerReplicationDetail"]=s["evidence"]
            f["issuerProvider"]=s["issuer"]
            stats["replication"]+=1
        elif not s.get("method") and not f.get("issuerReplicationDetail"):
            f["issuerReplicationDetail"]=s["evidence"]
        if s.get("te3") and f.get("officialTrackingError3Y") is None:
            f["officialTrackingError3Y"]=float(s["te3"])
            f["officialTrackingErrorAsOf"]=s["asof"]
            stats["te3"]+=1
        f["issuerPhotoSourceDate"]=date
        f["issuerPhotoSource"]=s["issuer"]
        f["issuerPhotoNote"]=s.get("note") or ""
    coverage=data.setdefault("issuerDatabaseCoverage",{})
    coverage.update(
        issuerAum=sum(bool(f.get("fundSize") and f.get("fundSizeSource")) for f in data.get("funds",[])),
        issuerFees=sum(f.get("terStatus") in ("Issuer confirmed","Dated issuer factsheet")
                       for f in data.get("funds",[])),
        issuerReplication=sum(f.get("replicationStatus")=="Fund-specific issuer verified"
                              for f in data.get("funds",[])),
        missingAum=sum(not f.get("fundSize") for f in data.get("funds",[])),
        photoSnapshotMatched=stats["matched"],
        photoSnapshotFeeFallback=stats["fees"],
        photoSnapshotAumFallback=stats["aum"],
        photoSnapshotReplications=stats["replication"],
        photoSnapshotTrackingError3Y=stats["te3"],
        photoSnapshotIsinConflicts=stats["conflicts"],
    )
    data.setdefault("sources",[]).append(
        "Dated issuer fact sheets / screenshots (September-November 2026), "
        "matched by ISIN; live official publisher records take precedence. "
        "Amundi CAC and DAX fund-AUM reporting dates were not visible. "
        "US-domiciled iShares examples were not mapped to UK UCITS funds.")
    return data


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=Path,default=Path("."))
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args(argv)
    root=args.repo.resolve()
    validate(snapshots())
    n=patch_catalog(root/"etf_catalog.csv",args.dry_run)
    b=patch_build(root/"build_terminal.py",args.dry_run)
    t=patch_template(root/"terminal_template.html",args.dry_run)
    print("ETF issuer evidence: 17 ISIN-verified rows, %d catalogued ETFs." % n)
    print("Collector extension:", "added" if b else "already installed",
          "| tracking-error label:", "updated" if t else "unchanged")
    return 0


if __name__=="__main__":
    sys.exit(main())
