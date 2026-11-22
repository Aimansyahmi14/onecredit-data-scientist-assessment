"""Generate viewer files, replay cached selections, or inspect one evidence ledger."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .evidence import build_evidence
from .io import ROOT, records, save_jsonl, targets
from .model import select

VERSIONS = {"baseline": "01-baseline", "pilot": "02-pilot-hybrid", "rules": "03-priority-rules", "hybrid": "04-hybrid"}


def first_available(ev, keys):
    return next(k for k in keys if k in ev.options)


def baseline(ev):
    focus = first_available(ev, ("status", "filings", "case", "trend", "cash", "register"))
    details = [k for k in ("filings", "trend", "liquidity", "case") if k in ev.options]
    return focus, details


def material(ev):
    return [k for k in ("filings", "trend", "audit", "case") if k in ev.options]


def urgent_focus(record, ev):
    if "status" in ev.options:
        return "status"
    if not record["financials"]["years"]:
        return "filings"
    if "audit" in ev.options:
        return "audit"
    if any(c["role"] == "defendant" and c["status"] in {"Pending", "Judgment entered"} for c in record["litigation"]["cases"]):
        return "case"
    return None


def fixed_choices(record, ev):
    years = record["financials"]["years"]
    latest = max(years, key=lambda y: y["financialYear"])["statements"] if years else {}
    priority = []
    if (latest.get("operatingCashFlow") or 0) < 0:
        priority.append("cash")
    if (
        latest.get("currentAssets") is not None
        and latest.get("currentLiabilities") is not None
        and latest["currentAssets"] < latest["currentLiabilities"]
    ):
        priority.append("liquidity")
    priority.extend(("filings", "case", "trend", "liquidity", "cash", "register"))
    available = list(dict.fromkeys(k for k in priority if k in ev.options))
    focus = urgent_focus(record, ev) or available[0]
    return focus, next((k for k in available if k != focus and k not in material(ev)), "none")


def render(ev, focus, detail_keys):
    paragraphs = {k: [] for k in ("profile", "finance", "legal")}
    facts = [*ev.core.values(), *(ev.options[k] for k in dict.fromkeys(detail_keys) if k != "none")]
    for f in facts:
        if f.text:
            paragraphs[f.section].append(f.text)
    text = [" ".join(group) for group in paragraphs.values() if group]
    text.append("**Next check** " + ev.options[focus].question)
    return "\n\n".join(text)


def final_text(record, ev, focus, detail):
    focus = urgent_focus(record, ev) or focus
    keep = material(ev)
    for key in (focus, detail):
        if key in ev.options and key not in keep and len(render(ev, focus, [*keep, key]).split()) <= 145:
            keep.append(key)
    return render(ev, focus, keep)


def generate(
    record: dict, version: str, live=False, endpoint="http://127.0.0.1:8181/v1/chat/completions", cache_dir=None
) -> dict[str, str]:
    ev = build_evidence(record)
    if version == "baseline":
        focus, details = baseline(ev)
        summary = render(ev, focus, details)
    elif version == "rules":
        focus, detail = fixed_choices(record, ev)
        summary = final_text(record, ev, focus, detail)
    else:
        picked = select(record["registrationNumber"], ev, live, endpoint, cache_dir)
        focus, detail = picked["focus"], picked["detail"]
        summary = render(ev, focus, [focus, detail]) if version == "pilot" else final_text(record, ev, focus, detail)
    return {"registrationNumber": record["registrationNumber"], "summary": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=[*VERSIONS, "explain"])
    parser.add_argument("--id", help="Registration number for explain")
    parser.add_argument("--live", action="store_true", help="Generate missing selections using a running local server")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8181/v1/chat/completions")
    parser.add_argument("--cache-dir", type=Path, help="Use a separate response directory for a fresh experiment")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "summaries", help="Destination for this run's viewer file")
    args = parser.parse_args()
    rows = sorted(records(), key=lambda r: r["registrationNumber"])
    if args.mode == "explain":
        record = next((r for r in rows if r["registrationNumber"] == args.id), None)
        if record is None:
            parser.error("Use --id with a registration number in the dataset")
        print(json.dumps(asdict(build_evidence(record)), indent=2, ensure_ascii=False))
        return
    if args.mode == "pilot":
        sample = targets()
        rows = [r for r in rows if sample.get(r["registrationNumber"], {}).get("split") == "pilot"]
    out = [generate(r, args.mode, args.live, args.endpoint, args.cache_dir) for r in rows]
    path = args.output_dir / (VERSIONS[args.mode] + ".jsonl")
    save_jsonl(path, out)
    print(f"{path.name}: {len(out)} summaries")


if __name__ == "__main__":
    main()
