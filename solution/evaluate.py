"""Evaluate the committed viewer files, saved API responses and paired readings."""

import argparse
import csv
import hashlib
import json
import random
import statistics

from .checks import check_summary, covered, reference_amount_errors
from .evidence import build_evidence
from .io import ROOT, read_jsonl, records, save_json, targets
from .model import artifact
from .run import VERSIONS

DIR = ROOT / "evaluation"


def check_rows(rows, expected):
    checked = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"registrationNumber", "summary"}:
            raise ValueError("Invalid viewer row")
        rid, text = row["registrationNumber"], row["summary"]
        if rid in checked or rid not in expected or not isinstance(text, str) or not text.strip():
            raise ValueError(f"Duplicate, unknown ID, or empty text: {rid}")
        checked[rid] = text
    if set(checked) != set(expected):
        raise ValueError(f"Missing IDs: {sorted(set(expected) - set(checked))}")
    return checked


def blind_order(ids):
    rng = random.Random(711)
    mapping = {}
    for rid in sorted(ids):
        versions = ["baseline", "hybrid"]
        rng.shuffle(versions)
        mapping[rid] = dict(zip(("A", "B"), versions))
    return mapping


def score_versions(data, spec):
    report, texts = {}, {}
    for method, version in VERSIONS.items():
        path = ROOT / "summaries" / f"{version}.jsonl"
        expected = {rid for rid in data if method != "pilot" or spec.get(rid, {}).get("split") == "pilot"}
        texts[method] = check_rows(read_jsonl(path), expected)
        validation = 0
        errors = {}
        words = []
        for rid, text in texts[method].items():
            n, issues = check_summary(text, data[rid])
            validation += n
            if issues:
                errors[rid] = issues
            words.append(len(text.split()))
        item = {
            "viewer_rows": len(words),
            "source_checks": validation,
            "flagged": errors,
            "word_count": {"median": statistics.median(words), "max": max(words), "over_145": sum(n > 145 for n in words)},
        }
        for split in ("pilot", "locked"):
            detail = {}
            for rid, ref in spec.items():
                if ref["split"] != split or rid not in texts[method]:
                    continue
                result = {key: covered(texts[method][rid], terms) for key, terms in ref["facts"].items()}
                detail[rid] = {
                    "hits": sum(result.values()),
                    "total": len(result),
                    "omitted": [k for k, ok in result.items() if not ok],
                }
            if detail:
                item[split] = {
                    "hits": sum(x["hits"] for x in detail.values()),
                    "total": sum(x["total"] for x in detail.values()),
                    "companies": detail,
                }
        report[method] = item
    return report, texts


def model_usage(data):
    tokens = {"prompt_tokens": 0, "completion_tokens": 0}
    elapsed, attempts, failed, focus = [], 0, 0, {}
    for rid, record in data.items():
        p, _ = artifact(rid, build_evidence(record))
        log = json.loads(p.read_text(encoding="utf-8"))
        for event in log["attempts"]:
            attempts += 1
            elapsed.append(event["elapsed_seconds"])
            failed += not event["accepted"]
            res = event.get("response", {})
            for k in tokens:
                tokens[k] += res.get("usage", {}).get(k, 0)
            if event["accepted"]:
                key = json.loads(res["choices"][0]["message"]["content"])["focus"]
                focus[key] = focus.get(key, 0) + 1
    live_paths = {artifact(rid, build_evidence(r))[0] for rid, r in data.items()}
    saved = sorted(next(iter(live_paths)).parent.glob("*.json")) if live_paths else []
    superseded = []
    for path in saved:
        if path not in live_paths:
            for event in json.loads(path.read_text(encoding="utf-8"))["attempts"]:
                superseded.append(
                    {
                        "file": path.name,
                        "elapsed_seconds": event["elapsed_seconds"],
                        "usage": event.get("response", {}).get("usage", {}),
                    }
                )
    return {
        "companies": len(data),
        "requests": attempts,
        "failed_attempts": failed,
        **tokens,
        "total_request_seconds": round(sum(elapsed), 2),
        "median_request_seconds": round(statistics.median(elapsed), 2),
        "external_api_charge_usd": 0,
        "model_focus_counts": focus,
        "superseded_attempts": superseded,
    }


def packet(texts, spec, order):
    for rid, labels in order.items():
        print(rid, spec[rid]["reason"])
        print(f"Full source in the local viewer: http://127.0.0.1:8000/api/companies/{rid}")
        print("Source checks", json.dumps(spec[rid]["facts"], ensure_ascii=False))
        for label, version in labels.items():
            print(label, texts[version][rid])
        print()


def ratings(path, spec, texts, order):
    if not path.exists():
        return None
    grouped = {"baseline": [], "hybrid": []}
    seen = set()
    paired = {}
    with path.open(encoding="utf-8", newline="") as fp:
        for row in csv.DictReader(fp):
            rid, label = row["registrationNumber"], row["blind_label"]
            if (rid, label) in seen or rid not in order or label not in order[rid]:
                raise ValueError("Duplicate or unexpected rating")
            seen.add((rid, label))
            version = order[rid][label]
            text = texts[version][rid]
            if row["text_sha256"] != hashlib.sha256(text.encode()).hexdigest():
                raise ValueError(f"Changed text for {rid} {label}, repeat the reading")
            hits = sum(covered(text, terms) for terms in spec[rid]["facts"].values())
            grades = [int(row["accuracy"]), max(0, hits - 1), int(row["usefulness"]), int(row["clarity"])]
            if any(s not in (0, 1, 2) for s in grades) or not row["rationale"].strip():
                raise ValueError("Incomplete rating")
            score = sum(w * v / 2 for w, v in zip((35, 30, 20, 15), grades))
            grouped[version].append((grades, score))
            paired.setdefault(rid, {})[version] = score
    if seen != {(rid, side) for rid in order for side in ("A", "B")}:
        raise ValueError("Incomplete paired review")
    result = {
        v: {
            "n": len(items),
            "weighted_mean": round(statistics.mean(s for _, s in items), 2),
            "mean_grade_0_to_2": dict(
                zip(
                    ("accuracy", "coverage", "usefulness", "clarity"),
                    [round(statistics.mean(g[i] for g, _ in items), 2) for i in range(4)],
                )
            ),
        }
        for v, items in grouped.items()
    }
    delta = [v["hybrid"] - v["baseline"] for v in paired.values()]
    result["paired_hybrid_vs_baseline"] = {
        "higher": sum(d > 0 for d in delta),
        "tied": delta.count(0),
        "lower": sum(d < 0 for d in delta),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", action="store_true", help="Print the paired, version-masked review packet")
    args = parser.parse_args()
    data = {r["registrationNumber"]: r for r in records()}
    spec = targets()
    for rid, entry in spec.items():
        if errors := reference_amount_errors(data[rid], entry["facts"]):
            raise ValueError(f"Reference amount absent from {rid}: {errors}")
    report, texts = score_versions(data, spec)
    order = blind_order(r for r in spec if spec[r]["split"] == "locked")
    if args.packet:
        packet(texts, spec, order)
        return
    review = ratings(DIR / "assisted-review.csv", spec, texts, order)
    result = {"versions": report, "model_usage": model_usage(data), "paired_reading": review}
    save_json(DIR / "results.json", result)
    print(json.dumps({k: {s: (m[s]["hits"], m[s]["total"]) for s in ("pilot", "locked") if s in m} for k, m in report.items()}))
    if any(v["flagged"] for v in report.values()):
        raise SystemExit("A source check failed. See evaluation/results.json.")


if __name__ == "__main__":
    main()
