#!/usr/bin/env python3
"""Read-only production evidence verifier for the AH scanner."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise AssertionError(f"missing production artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _ah_result(report: dict) -> str:
    """Only a complete, independently reconciled AH publication can pass."""
    assert report.get("usable") is True, "AH dataset is not usable"
    assert report.get("complete") is True, "AH dataset is partial; production acceptance requires 101/101 raw and 61/61 canonical"
    assert report.get("quality") == "complete", "AH quality classification is not complete"
    return "PASS"


def verify_ah(root: Path = Path(".")) -> dict:
    """Verify AH integrity; incomplete publications fail production acceptance."""
    module_path = root / "scripts" / "independent_qa.py"
    spec = importlib.util.spec_from_file_location("ah_independent_qa", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.verify(root / "data", require_complete=True)
    return {"project": "ah", **report, "result": _ah_result(report)}


def main() -> int:
    verify_ah()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
