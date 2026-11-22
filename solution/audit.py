"""Profile the frozen assessment snapshot and cross-check selected accounting fields."""

import hashlib
from collections import Counter
from datetime import date
from decimal import Decimal

from .io import DATA, ROOT, records, save_json


def profile(rows):
    legal_ids = set()
    counts = Counter()
    hist = {
        k: Counter()
        for k in (
            "financial_year_count",
            "years_supplied",
            "industry",
            "state",
            "status",
            "audit_opinion",
            "case_role",
            "case_status",
            "null_ratio",
            "case_counts_per_company",
        )
    }
    flags = {
        k: []
        for k in (
            "no_financials",
            "one_filing",
            "gapped_filings",
            "historical_audit_attention",
            "winding_up",
            "share_total_mismatch",
            "duplicate_fiscal_year",
            "balance_mismatch",
            "net_margin_mismatch",
            "duplicate_case_number",
            "dated_after_snapshot",
            "nonpositive_revenue",
        )
    }
    for r in rows:
        reg = r["registrationNumber"]
        p = r["profile"]
        for k in ("industry", "state", "status"):
            hist[k][p[k]] += 1
        if p["status"] == "Winding up":
            flags["winding_up"].append(reg)
        ys = sorted(r["financials"]["years"], key=lambda y: y["financialYear"])
        years = [y["financialYear"] for y in ys]
        hist["financial_year_count"][len(years)] += 1
        hist["years_supplied"][",".join(map(str, years)) or "none"] += 1
        if not years:
            flags["no_financials"].append(reg)
        if len(years) == 1:
            flags["one_filing"].append(reg)
        if len(years) != len(set(years)):
            flags["duplicate_fiscal_year"].append(reg)
        if any(b - a > 1 for a, b in zip(years, years[1:])):
            flags["gapped_filings"].append(reg)
        if ys:
            latest = ys[-1]["statements"]
            counts["loss_in_latest_filing"] += latest["profitAfterTax"] < 0
            counts["negative_operating_cash_in_latest_filing"] += latest["operatingCashFlow"] < 0
            counts["latest_current_assets_below_current_liabilities"] += latest["currentAssets"] < latest["currentLiabilities"]
        owners = r["relationships"]["shareholders"]
        directors = r["relationships"]["directors"]
        counts["director_entries"] += len(directors)
        counts["shareholder_entries"] += len(owners)
        counts["companies_with_corporate_shareholder"] += any(h["type"] == "company" for h in owners)
        people = {d["name"] for d in directors}
        counts["companies_with_director_shareholder_overlap"] += any(
            h["type"] == "individual" and h["name"] in people for h in owners
        )
        if sum(Decimal(str(h["percentage"])) for h in owners) != 100:
            flags["share_total_mismatch"].append(reg)
        if p.get("formerNames"):
            counts["companies_with_former_names"] += 1
        dates = [p["incorporationDate"], *(d["appointedOn"] for d in directors), *(f["changedOn"] for f in p["formerNames"])]
        for y in ys:
            fy, s, m = y["financialYear"], y["statements"], y["ratiosAndMetrics"]
            dates.append(y["financialYearEnd"])
            opinion = y["audit"]["opinion"]
            hist["audit_opinion"][opinion] += 1
            if opinion != "Unqualified" and fy != years[-1]:
                flags["historical_audit_attention"].append(f"{reg}/FY{fy}")
            for group in m.values():
                hist["null_ratio"].update(k for k, v in group.items() if v is None)
            if s["totalAssets"] != s["totalLiabilities"] + s["totalEquity"]:
                flags["balance_mismatch"].append(f"{reg}/FY{fy}")
            if s["revenue"] <= 0:
                flags["nonpositive_revenue"].append(f"{reg}/FY{fy}")
            else:
                calc = Decimal(s["profitAfterTax"]) / Decimal(s["revenue"])
                if abs(calc - Decimal(str(m["profitability"]["netProfitMargin"]))) > Decimal("0.00005"):
                    flags["net_margin_mismatch"].append(f"{reg}/FY{fy}")
        cases = r["litigation"]["cases"]
        hist["case_counts_per_company"][len(cases)] += 1
        counts["companies_with_cases"] += bool(cases)
        counts["companies_with_both_legal_roles"] += len({k["role"] for k in cases}) > 1
        for c in cases:
            dates.append(c["filedOn"])
            hist["case_role"][c["role"]] += 1
            hist["case_status"][c["status"]] += 1
            if c["caseNumber"] in legal_ids:
                flags["duplicate_case_number"].append(c["caseNumber"])
            legal_ids.add(c["caseNumber"])
        if any(date.fromisoformat(d) > date(2025, 12, 31) for d in dates):
            flags["dated_after_snapshot"].append(reg)
    return {
        "as_of": "2025-12-31",
        "data_sha256": hashlib.sha256(DATA.read_bytes()).hexdigest(),
        "companies": len(rows),
        "unique_ids": len({r["registrationNumber"] for r in rows}),
        "financial_periods": sum(hist["audit_opinion"].values()),
        "court_cases": sum(hist["case_role"].values()),
        "counts": counts,
        "distributions": hist,
        "detail": flags,
    }


if __name__ == "__main__":
    results = profile(records())
    save_json(ROOT / "evaluation" / "data-audit.json", results)
    print(f"{results['companies']} companies, {results['financial_periods']} reported periods, {results['court_cases']} cases")
