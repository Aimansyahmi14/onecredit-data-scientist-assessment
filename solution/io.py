"""Read the assessment inputs and replace complete outputs atomically."""

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "companies.jsonl"
TARGETS = ROOT / "evaluation" / "targets.json"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def records():
    rows = read_jsonl(DATA)
    ids = [r["registrationNumber"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate registration number in source records")
    return rows


def targets():
    return json.loads(TARGETS.read_text(encoding="utf-8"))


def atomic_text(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(contents)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def save_json(path, data):
    atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def save_jsonl(path, rows):
    atomic_text(path, "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows))
