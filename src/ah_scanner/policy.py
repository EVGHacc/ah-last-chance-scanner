"""Slanke repo-policy voor v2.

- Een wijziging in ``.github/workflows/`` vereist een wijziging in ``tests/test_workflow_*.py``.
- Een wijziging in ``src/ah_scanner/`` of ``worker/src/`` vereist een testwijziging.
- Statische review: alleen de toegestane workflows, geen ``schedule:`` (de Worker plant),
  en geen push naar ``main`` vanuit workflows.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ALLOWED_WORKFLOWS = frozenset(
    {"auth-check.yml", "ci.yml", "engineering-quality.yml", "export.yml", "scan.yml"}
)
CODE_PREFIXES = ("src/ah_scanner/", "worker/src/")
TEST_PREFIXES = ("tests/unit/", "worker/test/", "tests/test_workflow_")
WORKFLOW_PREFIX = ".github/workflows/"


def evaluate_changes(paths: list[str]) -> list[str]:
    issues: list[str] = []
    if any(p.startswith(WORKFLOW_PREFIX) for p in paths) and not any(
        p.startswith("tests/test_workflow_") for p in paths
    ):
        issues.append("workflow gewijzigd zonder tests/test_workflow_*.py")
    if any(p.startswith(CODE_PREFIXES) for p in paths) and not any(
        p.startswith(TEST_PREFIXES) for p in paths
    ):
        issues.append("code gewijzigd zonder testwijziging")
    return issues


def static_review(root: Path) -> list[str]:
    issues: list[str] = []
    workflows = root / WORKFLOW_PREFIX
    names = {p.name for p in workflows.glob("*.yml")}
    for extra in sorted(names - ALLOWED_WORKFLOWS):
        issues.append(f"niet-toegestane workflow: {extra}")
    for missing in sorted(ALLOWED_WORKFLOWS - names):
        issues.append(f"ontbrekende workflow: {missing}")
    for name in sorted(names & ALLOWED_WORKFLOWS):
        text = (workflows / name).read_text(encoding="utf-8")
        if "schedule:" in text:
            issues.append(f"{name}: geen schedule toegestaan (de Worker plant)")
        if "HEAD:main" in text:
            issues.append(f"{name}: workflows mogen niet naar main pushen")
    quality = workflows / "engineering-quality.yml"
    if quality.is_file():
        text = quality.read_text(encoding="utf-8")
        for job in ("changes:", "policy:", "ah-tests:", "independent-review:"):
            if job not in text:
                issues.append(f"engineering-quality mist job {job[:-1]}")
        if "contents: read" not in text:
            issues.append("engineering-quality moet read-only zijn")
    return issues


def changed_files(base: str, head: str) -> list[str]:
    if not base or set(base) == {"0"}:
        return []
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ah_scanner.policy")
    parser.add_argument("--static-review", action="store_true")
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args(argv)
    issues = (
        static_review(Path("."))
        if args.static_review
        else evaluate_changes(changed_files(args.base, args.head))
    )
    for issue in issues:
        print(f"POLICY FAIL: {issue}")
    if not issues:
        print("POLICY PASS")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
