"""Independent checks against the raw record. These do not call the generator."""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

AMOUNT = r"-?RM [\d,]+(?:\.\d{2})?"


def numeric(text):
    return Decimal(text.replace("RM ", "").replace(",", "").replace("%", ""))


def displayed(value, precision):
    return Decimal(value).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)


def check_summary(text, record):
    issues = []
    checked = 0

    def check(name, condition):
        nonlocal checked
        checked += 1
        if not condition:
            issues.append(name)

    p = record["profile"]
    check(
        "company/status",
        text.startswith(f"{p['companyName']} is listed as {p['status'].lower()} in {p['state']} ({p['industry']})."),
    )
    directors = record["relationships"]["directors"]
    check("board size", bool(re.search(rf"\bregister lists {len(directors)} directors?\.", text)))
    owners = record["relationships"]["shareholders"]
    if owners:
        top = max(o["percentage"] for o in owners)
        leaders = [o["name"] for o in owners if o["percentage"] == top]
        owner_phrase = " and ".join(leaders) + (
            " holds the largest disclosed stake " if len(leaders) == 1 else " share the largest disclosed stake "
        )
        m = re.search(re.escape(owner_phrase) + r"\(([\d.]+)%(?: each)?\)", text)
        check("largest holding", m is not None and Decimal(m[1]) == Decimal(str(top)))
    if "incorporated on" in text:
        check("incorporation date", f"incorporated on {p['incorporationDate']}." in text)

    years = {y["financialYear"]: y for y in record["financials"]["years"]}
    if years:
        latest = max(years)
        s = years[latest]["statements"]
        if s.get("revenue") is not None and s.get("profitAfterTax") is not None:
            pattern = rf"In FY(\d+), revenue was ({AMOUNT}) and the after-tax (profit|loss) was ({AMOUNT})\."
            m = re.search(pattern, text)
            check(
                "latest year, revenue, sign and PAT",
                m is not None
                and int(m[1]) == latest
                and numeric(m[2]) == s["revenue"]
                and numeric(m[4]) == abs(s["profitAfterTax"])
                and m[3] == ("loss" if s["profitAfterTax"] < 0 else "profit"),
            )
        check("financial availability", "No financial statements" not in text)
    else:
        check("financial availability", "No financial statements are supplied." in text and "revenue was" not in text)

    for match in re.finditer(rf"FY(\d+) (operating cash flow|borrowings) (?:was|were) ({AMOUNT})", text):
        fy, label, amt = match.groups()
        field = {"operating cash flow": "operatingCashFlow", "borrowings": "borrowings"}[label]
        check(label, numeric(amt) == years.get(int(fy), {}).get("statements", {}).get(field))
    for fy, role, amt in re.findall(rf"FY(\d+) recorded an after-tax (profit|loss) of ({AMOUNT})", text):
        value = years.get(int(fy), {}).get("statements", {}).get("profitAfterTax")
        check(
            "prior earnings", value is not None and numeric(amt) == abs(value) and role == ("loss" if value < 0 else "profit")
        )
    for fy, field, value in re.findall(r"FY(\d+) (current ratio|after-tax margin) was (-?[\d.]+)[×%]", text):
        s = years.get(int(fy), {}).get("statements", {})
        a, b, factor, digits = (
            ("currentAssets", "currentLiabilities", 1, 2) if field == "current ratio" else ("profitAfterTax", "revenue", 100, 1)
        )
        check(
            field,
            s.get(a) is not None
            and (s.get(b) or 0) > 0
            and Decimal(value) == displayed(Decimal(s[a]) * factor / Decimal(s[b]), digits),
        )
    for direction, pct, a, b in re.findall(r"Revenue (rose|fell) ([\d.]+)% from FY(\d+) to FY(\d+)", text):
        prev, last = years.get(int(a)), years.get(int(b))
        comparable = prev and last and int(b) == int(a) + 1
        if comparable:
            d0, d1 = [date.fromisoformat(x["financialYearEnd"]) for x in (prev, last)]
            comparable = d0.month == d1.month and 364 <= (d1 - d0).days <= 366
        v0, v1 = (prev or {}).get("statements", {}).get("revenue"), (last or {}).get("statements", {}).get("revenue")
        check(
            "revenue growth and period",
            comparable
            and v0
            and v0 > 0
            and v1 is not None
            and displayed(abs(Decimal(v1 - v0) * 100 / Decimal(v0)), 1) == Decimal(pct)
            and direction == ("rose" if v1 > v0 else "fell"),
        )
    for a, b in re.findall(r"Revenue was unchanged from FY(\d+) to FY(\d+)", text):
        check(
            "flat revenue",
            int(a) in years
            and int(b) in years
            and int(b) == int(a) + 1
            and years[int(a)]["statements"]["revenue"] == years[int(b)]["statements"]["revenue"],
        )
    for fy, opinion in re.findall(r"The FY(\d+) audit opinion was “([^”]+)”", text):
        check("audit period/opinion", years.get(int(fy), {}).get("audit", {}).get("opinion") == opinion)
    for fy in re.findall(r"Only FY(\d+) is supplied", text):
        check("single financial period", set(years) == {int(fy)})
    for gap, left, right in re.findall(r"FY(\d+) is missing between FY(\d+) and FY(\d+)", text):
        check(
            "missing period",
            int(gap) not in years and int(left) in years and int(right) in years and int(left) < int(gap) < int(right),
        )

    cases = record["litigation"]["cases"]
    if not cases:
        check("empty court record", "No court cases appear in the supplied record." in text)
    else:
        overview = re.search(r"The record lists (\d+) court cases? \(([^)]*)\)\.", text)
        counts = {} if not overview else {r: int(n) for n, r in re.findall(r"(\d+) as (defendant|plaintiff)", overview[2])}
        check(
            "case count and roles",
            overview is not None
            and int(overview[1]) == len(cases)
            and all(counts.get(role, 0) == sum(c["role"] == role for c in cases) for role in ("defendant", "plaintiff")),
        )
        pending = sum(c["status"] == "Pending" for c in cases)
        pend = re.search(r"(\d+) (?:is|are) marked pending", text)
        check("pending count", (int(pend[1]) if pend else 0) == pending)
    by_id = {c["caseNumber"]: c for c in cases}
    case_pattern = rf"In (CASE-[\d-]+), the company is the (plaintiff|defendant) in an? (.+?) \(([^,]+), claim ({AMOUNT})\)"
    named = re.findall(case_pattern, text)
    check("named case format", len(named) == len(re.findall(r"\bIn CASE-", text)))
    for ref, role, kind, status, amount in named:
        case = by_id.get(ref, {})
        check(
            "case ID, role, type, status and claim amount",
            case.get("role") == role
            and case.get("caseType", "").lower() == kind
            and case.get("status") == status
            and Decimal(str(case.get("claimAmount", -1))) == numeric(amount),
        )
    listed_ids = set(re.findall(r"\bCASE-\d{4}-\d{4}\b", text))
    check("court case references", listed_ids <= set(by_id))
    check(
        "unsupported decision language",
        not re.search(
            r"\b(?:creditworthy|insolvent|bankrupt|guilty|won the case|lost the case|owes|must pay|approve the supplier|reject the supplier)\b",
            text,
            re.I,
        ),
    )
    return checked, issues


def covered(text, terms):
    def present(term, paragraph):
        pattern = re.escape(term)
        if term[0].isdigit():
            pattern = r"(?<![\d.,])" + pattern
        if term[-1].isdigit():
            pattern += r"(?!\d)"
        return re.search(pattern, paragraph, flags=re.I) is not None

    return any(all(present(term, paragraph) for term in terms) for paragraph in text.split("\n\n"))


def reference_amount_errors(record, facts):
    """Check transcribed RM magnitudes directly against company statements and claims."""
    amounts = {abs(Decimal(str(v))) for y in record["financials"]["years"] for v in y["statements"].values() if v is not None}
    amounts.update(abs(Decimal(str(c["claimAmount"]))) for c in record["litigation"]["cases"])
    return [
        token
        for terms in facts.values()
        for term in terms
        for token in re.findall(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b", term)
        if Decimal(token.replace(",", "")) not in amounts
    ]
