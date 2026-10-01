#!/usr/bin/env python3
"""Repository-wide development policy gate.

The gate is intentionally dependency-free. It maps production changes to the
minimum independent test surface that must change with them and prevents source
changes from being mixed with generated production evidence.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


AH_PRODUCTION = ("scanner.py", "scripts/")
VACANCY_PRODUCTION = ("vacancy-monitor/",)
GENERATED = ("data/", "vacancy-monitor/data/")
WORKFLOWS = (".github/workflows/",)
ENGINEERING_PRODUCTION = (
    "scripts/engineering_gate.py",
    "scripts/production_verify.py",
    "engineering/",
)

AH_EXCLUDED_PREFIXES = (
    "scripts/engineering_gate.py",
    "scripts/production_verify.py",
)
VACANCY_TEST_PREFIXES = ("vacancy-monitor/test_", "tests/test_vacancy_")
AH_TEST_PREFIXES = ("tests/test_ah_",)
ENGINEERING_TEST_PREFIXES = (
    "tests/test_engineering_",
    "tests/test_workflow_",
)


def _under(path: str, prefix: str) -> bool:
    return path == prefix.rstrip("/") or path.startswith(prefix)


def is_generated(path: str) -> bool:
    return any(_under(path, prefix) for prefix in GENERATED)


def is_workflow(path: str) -> bool:
    return any(_under(path, prefix) for prefix in WORKFLOWS)


def is_ah_production(path: str) -> bool:
    if path == "scanner.py":
        return True
    if path.startswith("scripts/") and path.endswith(".py"):
        return not any(path == excluded for excluded in AH_EXCLUDED_PREFIXES)
    return False


def is_vacancy_production(path: str) -> bool:
    return (
        path.startswith("vacancy-monitor/")
        and path.endswith(".py")
        and not path.startswith(VACANCY_TEST_PREFIXES)
        and "/probe_" not in path
    )


def is_engineering_production(path: str) -> bool:
    return (
        path in ENGINEERING_PRODUCTION[:2]
        or path.startswith("engineering/")
    )


def evaluate_changes(paths: list[str]) -> list[str]:
    """Return policy violations for a set of changed repository paths."""
    changed = set(paths)
    errors: list[str] = []

    ah_changed = any(is_ah_production(path) for path in changed)
    vacancy_changed = any(is_vacancy_production(path) for path in changed)
    engineering_changed = any(is_engineering_production(path) for path in changed)
    workflow_changed = any(is_workflow(path) for path in changed)
    source_changed = ah_changed or vacancy_changed or engineering_changed or workflow_changed

    if ah_changed and not any(path.startswith(AH_TEST_PREFIXES) for path in changed):
        errors.append(
            "AH production code changed without a dedicated tests/test_ah_*.py change"
        )

    if vacancy_changed and not any(path.startswith(VACANCY_TEST_PREFIXES) for path in changed):
        errors.append(
            "Vacancy production code changed without vacancy-monitor/test_*.py "
            "or tests/test_vacancy_*.py"
        )

    if engineering_changed and not any(
        path.startswith(ENGINEERING_TEST_PREFIXES) for path in changed
    ):
        errors.append(
            "Engineering control-plane code changed without tests/test_engineering_*.py "
            "or tests/test_workflow_*.py"
        )

    if workflow_changed and not any(path.startswith("tests/test_workflow_") for path in changed):
        errors.append(
            "GitHub Actions workflow changed without tests/test_workflow_*.py"
        )

    if source_changed and any(is_generated(path) for path in changed):
        errors.append(
            "Functional source/workflow changes may not be committed together with "
            "generated production snapshots"
        )

    return errors


def changed_files(base: str, head: str) -> list[str]:
    if not base or set(base) == {"0"}:
        return []
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        check=True,
        text=True,
        capture_output=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def static_review(root: Path) -> list[str]:
    """Read-only review of the control-plane invariants."""
    issues: list[str] = []

    quality = root / ".github/workflows/engineering-quality.yml"
    production = root / ".github/workflows/production-verifier.yml"
    roles = root / "engineering/DEVELOPMENT_SYSTEM.md"

    required_files = (quality, production, roles)
    for path in required_files:
        if not path.is_file():
            issues.append(f"missing required control-plane file: {path}")
    if issues:
        return issues

    qtext = quality.read_text(encoding="utf-8")
    ptext = production.read_text(encoding="utf-8")
    dtext = roles.read_text(encoding="utf-8")

    for job in ("policy:", "ah-tests:", "vacancy-tests:", "independent-review:"):
        if job not in qtext:
            issues.append(f"engineering-quality workflow missing job {job[:-1]}")
    if "contents: read" not in qtext:
        issues.append("engineering-quality workflow must be read-only")
    if "contents: read" not in ptext:
        issues.append("production verifier must be read-only")
    if "workflow_run:" not in ptext:
        issues.append("production verifier must run after production workflows")

    for role in (
        "Builder",
        "Test Author",
        "Independent Reviewer",
        "Production Verifier",
        "Release Controller",
        "SRE / Incident Owner",
    ):
        if role not in dtext:
            issues.append(f"role missing from development system: {role}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--static-review", action="store_true")
    args = parser.parse_args()

    if args.static_review:
        errors = static_review(Path("."))
        if errors:
            for error in errors:
                print(f"POLICY FAIL: {error}")
            return 1
        print("CONTROL-PLANE STATIC REVIEW: PASS")
        return 0

    if not args.base:
        parser.error("--base is required unless --static-review is used")

    paths = changed_files(args.base, args.head)
    errors = evaluate_changes(paths)
    print("Changed paths:")
    for path in paths:
        print(f" - {path}")
    if errors:
        for error in errors:
            print(f"POLICY FAIL: {error}")
        return 1
    print("CHANGE POLICY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
