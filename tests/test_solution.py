import json
import unittest
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError

from solution.checks import check_summary, covered, reference_amount_errors
from solution.evaluate import check_rows
from solution.evidence import build_evidence, fiscal_pair, money, ratio
from solution.io import records, targets
from solution.model import choice, retry_wait, select
from solution.run import generate

DATA = {r["registrationNumber"]: r for r in records()}


def record(number):
    return deepcopy(DATA[f"SYN-{number:06d}"])


def payload(focus="cash", detail="liquidity"):
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"focus": focus, "detail": detail})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
    }


class Features(unittest.TestCase):
    def test_money_and_zero_denominator(self):
        self.assertEqual(money(-12500), "-RM 12,500")
        self.assertEqual(money(100.5), "RM 100.50")
        self.assertEqual(ratio(0, 100), Decimal("0"))
        for denom in (None, 0, -100):
            self.assertIsNone(ratio(30, denom))

    def test_gapped_financials(self):
        ev = build_evidence(record(286))
        self.assertIn("FY2023 is missing", ev.options["filings"].text)
        self.assertNotIn("trend", ev.options)

    def test_dates_and_period(self):
        a, b = record(29)["financials"]["years"][-2:]
        self.assertTrue(fiscal_pair(a, b))
        b["financialYearEnd"] = "2024-12-31"
        self.assertFalse(fiscal_pair(a, b))

    def test_single_and_absent_financials(self):
        self.assertIn("Only FY2024", build_evidence(record(802)).options["filings"].text)
        ev = build_evidence(record(302))
        self.assertIn("No financial statements", ev.core["financial"].text)
        self.assertNotIn("margin", ev.options)

    def test_reversed_input_order_and_traceability(self):
        r = record(29)
        r["financials"]["years"].reverse()
        ev = build_evidence(r)
        self.assertIn("rose 2.4%", ev.options["trend"].text)
        self.assertIn("/financials/years/0/statements/revenue", ev.options["trend"].sources)
        self.assertIn("/financials/years/1/statements/revenue", ev.options["trend"].sources)

    def test_missing_or_nonpositive_base(self):
        r = record(29)
        r["financials"]["years"][-2]["statements"]["revenue"] = 0
        r["financials"]["years"][-1]["statements"].pop("currentLiabilities")
        ev = build_evidence(r)
        self.assertNotIn("trend", ev.options)
        self.assertNotIn("liquidity", ev.options)

    def test_loss_not_negative_profit_growth(self):
        ev = build_evidence(record(67))
        self.assertIn("loss was RM 7,515,861", ev.core["financial"].text)
        self.assertIn("-17.4%", ev.options["margin"].text)
        self.assertIn("-RM 5,939,447", ev.options["cash"].text)

    def test_past_audits_dated(self):
        ev = build_evidence(record(217))
        text = ev.options["audit"].text
        self.assertIn("FY2023 audit opinion was “Disclaimer of opinion”", text)
        self.assertIn("FY2024 audit opinion was “Unqualified”", text)

    def test_litigation_role_status_and_claim(self):
        ev = build_evidence(record(286))
        self.assertIn("defendant in a winding-up petition (Pending, claim RM 355,900)", ev.options["case"].text)
        ev = build_evidence(record(267))
        self.assertIn("5 as plaintiff", ev.core["legal"].text)
        self.assertIn("plaintiff", ev.options["case"].text)

    def test_tied_largest_holder(self):
        r = record(29)
        r["relationships"]["shareholders"] = [{"type": "individual", "name": n, "percentage": 50} for n in ("Ali", "Lee")]
        self.assertIn("Ali and Lee share the largest disclosed stake (50% each)", build_evidence(r).core["ownership"].text)

    def test_missing_latest_profit(self):
        r = record(29)
        r["financials"]["years"][-1]["statements"].pop("profitAfterTax")
        ev = build_evidence(r)
        self.assertIn("after-tax result is unavailable", ev.core["financial"].text)
        self.assertNotIn("margin", ev.options)


class Validation(unittest.TestCase):
    def test_source_checks_and_planted_numeric_error(self):
        r = record(67)
        text = generate(r, "rules")["summary"]
        self.assertFalse(check_summary(text, r)[1])
        changed = text.replace("loss was RM 7,515,861", "profit was RM 7,515,861")
        self.assertIn("latest year, revenue, sign and PAT", check_summary(changed, r)[1])

    def test_legal_mutations(self):
        r = record(286)
        text = generate(r, "rules")["summary"]
        for wrong in (
            text.replace("defendant in a winding", "plaintiff in a winding"),
            text.replace("claim RM 355,900", "claim RM 3,559,000"),
            text.replace("(Pending, claim", "(Settled, claim"),
        ):
            self.assertTrue(check_summary(wrong, r)[1])

    def test_compound_anchor(self):
        self.assertTrue(covered("Owner has 51%.", ["51%"]))
        self.assertFalse(covered("Owner has 151%.", ["51%"]))
        self.assertFalse(covered("Was a plaintiff.\n\nAnother case settled.", ["plaintiff", "settled"]))

    def test_reject_mistyped_reference_amount(self):
        self.assertEqual(reference_amount_errors(record(1829), {"profit": ["1,491,176"]}), ["1,491,176"])
        for rid, entry in targets().items():
            self.assertEqual(reference_amount_errors(DATA[rid], entry["facts"]), [])

    def test_bad_viewer_rows(self):
        valid = {"registrationNumber": "SYN-000029", "summary": "A"}
        for rows in (
            [],
            [valid, valid],
            [dict(valid, summary="")],
            [dict(valid, registrationNumber="x")],
            [dict(valid, extra=7)],
        ):
            with self.assertRaises(ValueError):
                check_rows(rows, {valid["registrationNumber"]})

    def test_disjoint_splits(self):
        from collections import Counter

        spec = targets()
        self.assertEqual(Counter(r["split"] for r in spec.values()), {"pilot": 4, "locked": 15})
        self.assertTrue(set(spec).issubset(DATA))
        self.assertTrue(all(len(r["facts"]) == 3 for r in spec.values()))

    def test_replay_and_constraints_all(self):
        for r in DATA.values():
            text = generate(r, "hybrid")["summary"]
            self.assertLessEqual(len(text.split()), 145)
            self.assertFalse(check_summary(text, r)[1])


class ModelInterface(unittest.TestCase):
    def test_reject_unknown_and_truncated(self):
        ev = build_evidence(record(29))
        with self.assertRaises(ValueError):
            choice(payload("approve"), ev)
        out = payload()
        out["choices"][0]["finish_reason"] = "length"
        with self.assertRaises(ValueError):
            choice(out, ev)

    def test_rate_limit_and_replay(self):
        r = record(29)
        ev = build_evidence(r)
        retry = HTTPError("http://localhost/", 429, "Too many requests", {"Retry-After": "0"}, BytesIO(b"retry"))

        class Response(BytesIO):
            status = 200

        with (
            TemporaryDirectory() as tmp,
            patch("solution.model.CACHE", Path(tmp)),
            patch("solution.model.time.sleep"),
            patch("solution.model.urlopen", side_effect=[retry, Response(json.dumps(payload()).encode())]) as call,
        ):
            selected = select(r["registrationNumber"], ev, live=True)
            self.assertEqual(selected, select(r["registrationNumber"], ev))
            self.assertEqual(call.call_count, 2)
            log = json.loads(next(Path(tmp).glob("*.json")).read_text())
            self.assertEqual([e["status"] for e in log["attempts"]], [429, 200])

    def test_offline_miss_and_permanent_provider_error(self):
        r = record(29)
        ev = build_evidence(r)
        with TemporaryDirectory() as tmp, patch("solution.model.CACHE", Path(tmp)):
            with self.assertRaises(RuntimeError):
                select(r["registrationNumber"], ev)
            failure = HTTPError("http://localhost/", 400, "Bad request", {}, BytesIO(b"invalid"))
            with patch("solution.model.urlopen", side_effect=failure) as call, self.assertRaises(RuntimeError):
                select(r["registrationNumber"], ev, live=True)
            self.assertEqual(call.call_count, 1)

    def test_keyless_endpoint_stays_local(self):
        r = record(29)
        with TemporaryDirectory() as tmp, patch("solution.model.CACHE", Path(tmp)), self.assertRaises(ValueError):
            select(r["registrationNumber"], build_evidence(r), True, "https://example.com/chat")

    def test_retry_after_bound(self):
        self.assertEqual(retry_wait("80", 1), 60)
        self.assertEqual(retry_wait(None, 2), 4)
