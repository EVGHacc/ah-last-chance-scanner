"""Fail-closed same-run GitHub Actions step attestations for Vacancy v4."""
from functools import lru_cache
import json
import os
from urllib.request import Request, urlopen

WORKFLOW = ".github/workflows/vacancy-v4-providers.yml"
STEP_GROUPS = {
    "unit_tests": ("Clean-sheet manifest tests", "Vacancy match-engine regression gate",
                   "Shared certification and transport tests"),
    "contract_tests": ("Provider unit and contract tests",),
    "independent_qa": ("Provider independent QA",),
    "canary": ("Live provider canary",),
    "live_proof": ("Production proof 1", "Production proof 2"),
}

def evaluate_provider_steps(run, job_page, provider, run_id, attempt, code_sha):
    """Return boolean gates from actual job steps, never from proof JSON alone."""
    closed = {gate: False for gate in STEP_GROUPS}
    if not isinstance(run, dict) or not isinstance(job_page, dict):
        return closed
    if (run.get("id") != run_id or run.get("run_attempt") != attempt or
            run.get("head_sha") != code_sha or
            run.get("head_branch") != "vacancy-v4-clean-sheet" or
            run.get("path") != WORKFLOW or
            run.get("status") not in ("in_progress", "completed") or
            (run.get("status") == "completed" and run.get("conclusion") != "success")):
        return closed
    jobs = job_page.get("jobs")
    if (not isinstance(jobs, list) or
            type(job_page.get("total_count")) is not int or
            job_page["total_count"] != len(jobs)):
        return closed
    matches = [j for j in jobs if isinstance(j, dict) and j.get("name") == f"proof ({provider})"]
    if len(matches) != 1:
        return closed
    job = matches[0]
    if (job.get("run_id") != run_id or job.get("status") != "completed" or
            job.get("conclusion") != "success" or
            (job.get("run_attempt") is not None and job.get("run_attempt") != attempt)):
        return closed
    steps = job.get("steps")
    if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
        return closed
    names = [s.get("name") for s in steps]
    if len(names) != len(set(names)) or any(not isinstance(n, str) for n in names):
        return closed
    statuses = {s["name"]: (s.get("status"), s.get("conclusion")) for s in steps}
    return {gate: all(statuses.get(name) == ("completed", "success") for name in required)
            for gate, required in STEP_GROUPS.items()}

def _get_json(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "vacancy-v4-certification"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=12) as response:
        return json.load(response)

@lru_cache(maxsize=4)
def _run_evidence(repo, run_id):
    if repo != "EVGHacc/ah-last-chance-scanner" or type(run_id) is not int or run_id <= 0:
        raise ValueError("invalid proof run identity")
    base = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
    return _get_json(base), _get_json(base + "/jobs?per_page=100&filter=latest")

def provider_release_gates(provider, run_id, attempt, code_sha):
    """Fail closed on GitHub API outages, rate limits or missing evidence."""
    closed = {gate: False for gate in STEP_GROUPS}
    if (not isinstance(provider, str) or not provider or
            type(run_id) is not int or type(attempt) is not int or
            not isinstance(code_sha, str) or len(code_sha) != 40):
        return closed
    try:
        run, jobs = _run_evidence("EVGHacc/ah-last-chance-scanner", run_id)
        return evaluate_provider_steps(run, jobs, provider, run_id, attempt, code_sha)
    except (OSError, ValueError, TypeError, KeyError, TimeoutError):
        return closed
