"""Convert one supplied record into sentences with source JSON pointers."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Fact:
    section: str
    text: str
    sources: tuple[str, ...]
    question: str = ""


@dataclass
class Evidence:
    core: dict[str, Fact]
    options: dict[str, Fact]


def decimal(value):
    return Decimal(str(value)) if value is not None else None


def rounded(value, places=1):
    unit = Decimal(1).scaleb(-places)
    return f"{value.quantize(unit, rounding=ROUND_HALF_UP):.{places}f}"


def ratio(numerator, denominator) -> Decimal | None:
    if numerator is None or denominator is None or decimal(denominator) <= 0:
        return None
    return decimal(numerator) / decimal(denominator)


def money(value) -> str:
    amount = decimal(value)
    places = 0 if amount == amount.to_integral_value() else 2
    return f"{'-' if amount < 0 else ''}RM {abs(amount):,.{places}f}"


def percentage(value):
    return format(decimal(value).normalize(), "f") + "%"


def fiscal_pair(previous, current):
    """A YoY comparison needs adjacent FYs and corresponding year-end dates."""
    try:
        older = date.fromisoformat(previous["financialYearEnd"])
        newer = date.fromisoformat(current["financialYearEnd"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        current["financialYear"] == previous["financialYear"] + 1
        and 364 <= (newer - older).days <= 366
        and older.month == newer.month
    )


def context(record):
    p = record["profile"]
    r = record["relationships"]
    profile = Fact(
        "profile",
        f"{p['companyName']} is listed as {p['status'].lower()} in {p['state']} ({p['industry']}).",
        tuple("/profile/" + k for k in ("companyName", "status", "state", "industry")),
    )
    directors = r["directors"]
    owners = r["shareholders"]
    ownership = f"The register lists {len(directors)} director{'s' if len(directors) != 1 else ''}."
    if owners:
        largest = max(decimal(h["percentage"]) for h in owners)
        leaders = [h["name"] for h in owners if decimal(h["percentage"]) == largest]
        if len(leaders) == 1:
            ownership += f" {leaders[0]} holds the largest disclosed stake ({percentage(largest)})."
        else:
            ownership += f" {' and '.join(leaders)} share the largest disclosed stake ({percentage(largest)} each)."
    else:
        ownership += " No shareholder entries are supplied."
    core = {
        "profile": profile,
        "ownership": Fact("profile", ownership, ("/relationships/directors", "/relationships/shareholders")),
    }
    options = {
        "register": Fact(
            "profile",
            f"It was incorporated on {p['incorporationDate']}.",
            ("/profile/incorporationDate",),
            "Verify the current register and signing authority.",
        )
    }
    if p["status"] != "Active":
        options["status"] = Fact(
            "profile", "", ("/profile/status",), "Obtain a current registry extract and verify who can sign for the company."
        )
    return Evidence(core, options)


def financials(ev, record):
    entries = sorted(enumerate(record["financials"]["years"]), key=lambda t: t[1]["financialYear"])
    years_path = "/financials/years"
    if not entries:
        ev.core["financial"] = Fact("finance", "No financial statements are supplied.", (years_path,))
        ev.options["filings"] = Fact(
            "finance", "", (years_path,), "Request the latest financial statements and a comparative period."
        )
        return
    idx, y = entries[-1]
    fy = y["financialYear"]
    stmt = y["statements"]
    root = f"{years_path}/{idx}"
    revenue, profit = stmt.get("revenue"), stmt.get("profitAfterTax")
    label = "loss" if profit is not None and profit < 0 else "profit"
    sales_text = "revenue is unavailable" if revenue is None else f"revenue was {money(revenue)}"
    profit_text = "the after-tax result is unavailable" if profit is None else f"the after-tax {label} was {money(abs(profit))}"
    ev.core["financial"] = Fact(
        "finance",
        f"In FY{fy}, {sales_text} and {profit_text}.",
        (root + "/financialYear", root + "/statements/revenue", root + "/statements/profitAfterTax"),
    )

    def option(key, text, fields, question):
        ev.options[key] = Fact(
            "finance", text, (root + "/financialYear", *(root + "/statements/" + f for f in fields)), question
        )

    margin = ratio(profit, revenue)
    if margin is not None:
        option(
            "margin",
            f"FY{fy} after-tax margin was {rounded(100 * margin)}%.",
            ("revenue", "profitAfterTax"),
            "Check the operating costs behind the reported margin.",
        )
    cash = stmt.get("operatingCashFlow")
    if cash is not None:
        option(
            "cash",
            f"FY{fy} operating cash flow was {money(cash)}.",
            ("operatingCashFlow",),
            "Review the cash-flow statement and reconcile operating cash flow to profit.",
        )
    current = ratio(stmt.get("currentAssets"), stmt.get("currentLiabilities"))
    if current is not None:
        option(
            "liquidity",
            f"The FY{fy} current ratio was {rounded(current, 2)}×.",
            ("currentAssets", "currentLiabilities"),
            "Check receivable timing against liabilities falling due.",
        )
    debt = stmt.get("borrowings")
    if debt is not None:
        option(
            "debt",
            f"FY{fy} borrowings were {money(debt)}.",
            ("borrowings",),
            "Request the borrowing maturity schedule and check upcoming repayments.",
        )

    if len(entries) == 1:
        ev.options["filings"] = Fact(
            "finance",
            f"Only FY{fy} is supplied.",
            (years_path,),
            "Request a comparable prior-year filing before assessing the trend.",
        )
    else:
        j, prev = entries[-2]
        prior = prev["financialYear"]
        prior_ref = f"{years_path}/{j}"
        prev_sales = prev["statements"].get("revenue")
        prev_profit = prev["statements"].get("profitAfterTax")
        if not fiscal_pair(prev, y):
            missing = [f"FY{n}" for n in range(prior + 1, fy)]
            text = (
                f"{', '.join(missing)} is missing between FY{prior} and FY{fy}."
                if len(missing) == 1
                else f"Intermediate filings are missing between FY{prior} and FY{fy}."
                if missing
                else f"FY{prior} and FY{fy} have noncomparable year ends."
            )
            ev.options["filings"] = Fact(
                "finance", text, (years_path,), "Obtain comparable filings before interpreting the change in revenue."
            )
        else:
            growth = ratio(None if revenue is None or prev_sales is None else revenue - prev_sales, prev_sales)
            if growth is not None:
                if growth == 0:
                    change = "was unchanged"
                else:
                    change = f"{'rose' if growth > 0 else 'fell'} {rounded(abs(growth) * 100)}%"
                ev.options["trend"] = Fact(
                    "finance",
                    f"Revenue {change} from FY{prior} to FY{fy}.",
                    (
                        prior_ref + "/statements/revenue",
                        root + "/statements/revenue",
                        prior_ref + "/financialYearEnd",
                        root + "/financialYearEnd",
                    ),
                    "Check the sales breakdown behind the year-on-year movement.",
                )
            if prev_profit is not None and profit is not None:
                prior_label = "loss" if prev_profit < 0 else "profit"
                ev.options["earnings"] = Fact(
                    "finance",
                    f"FY{prior} recorded an after-tax {prior_label} of {money(abs(prev_profit))}.",
                    (prior_ref + "/financialYear", prior_ref + "/statements/profitAfterTax"),
                    "Review the income statement for changes behind the after-tax results.",
                )
    unusual = [(j, a) for j, a in entries if a.get("audit", {}).get("opinion") not in (None, "", "Unqualified")]
    if unusual:
        opinions = list(unusual)
        if unusual[-1][0] != idx and y.get("audit", {}).get("opinion"):
            opinions.append((idx, y))
        audit = ". ".join(f"The FY{v['financialYear']} audit opinion was “{v['audit']['opinion']}”" for _, v in opinions) + "."
        paths = tuple(f"{years_path}/{j}/{key}" for j, _ in opinions for key in ("financialYear", "audit/opinion"))
        ev.options["audit"] = Fact(
            "finance",
            audit,
            paths,
            "Read the auditor’s report and management’s response to the earlier findings."
            if unusual[-1][0] != idx
            else "Read the auditor’s report and management’s response.",
        )


def case_priority(case):
    pending = case["status"] == "Pending"
    judgment = case["status"] == "Judgment entered"
    defendant = case["role"] == "defendant"
    petition = case["caseType"] == "Winding-up petition"
    ranks = (
        defendant and petition and pending,
        defendant and petition and judgment,
        defendant and pending,
        defendant and judgment,
        pending,
        judgment,
    )
    return (next((i for i, match in enumerate(ranks) if match), len(ranks)), -decimal(case["claimAmount"]), case["caseNumber"])


def litigation(ev, record):
    cases = record["litigation"]["cases"]
    base = "/litigation/cases"
    if not cases:
        ev.core["legal"] = Fact("legal", "No court cases appear in the supplied record.", (base,))
        return
    roles = [f"{count} as {role}" for role in ("defendant", "plaintiff") if (count := sum(c["role"] == role for c in cases))]
    count = len(cases)
    pending = sum(c["status"] == "Pending" for c in cases)
    overview = f"The record lists {count} court case{'s' if count != 1 else ''} ({' and '.join(roles)})."
    if pending:
        overview += f" {pending} {'is' if pending == 1 else 'are'} marked pending."
    ev.core["legal"] = Fact("legal", overview, (base,))
    idx, selected = min(enumerate(cases), key=lambda pair: case_priority(pair[1]))
    c = selected
    kind = c["caseType"].lower()
    article = "an" if kind[0] in "aeiou" else "a"
    text = (
        f"In {c['caseNumber']}, the company is the {c['role']} in {article} {kind} "
        f"({c['status']}, claim {money(c['claimAmount'])})."
    )
    if c["status"] == "Pending":
        action = f"Check the latest docket entry for {c['caseNumber']}."
    elif c["status"] == "Judgment entered":
        action = f"Obtain the judgment for {c['caseNumber']} to establish its terms."
    else:
        action = f"Verify the recorded disposition of {c['caseNumber']} in the case file."
    ev.options["case"] = Fact("legal", text, (f"{base}/{idx}",), action)


def build_evidence(record: dict) -> Evidence:
    ev = context(record)
    financials(ev, record)
    litigation(ev, record)
    return ev
