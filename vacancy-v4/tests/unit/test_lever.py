import pytest

from app.providers.lever import LeverError, inventory


def _job(job_id="1"):
    return {
        "id": job_id,
        "text": "Risk Lead",
        "descriptionPlain": "Own the enterprise risk programme.",
        "hostedUrl": f"https://jobs.eu.lever.co/pnlfin/{job_id}",
        "applyUrl": f"https://jobs.eu.lever.co/pnlfin/{job_id}/apply",
        "categories": {
            "location": "Amsterdam",
            "department": "Risk",
            "team": "Compliance",
            "office": "Amsterdam",
        },
        "createdAt": 1,
        "updatedAt": 2,
    }


def test_inventory_preserves_hard_job_data_invariant():
    jobs = inventory("pnlfin", lambda site, offset, limit: [_job()])
    assert len(jobs) == 1
    job = jobs[0]
    assert job.job_id == "1"
    assert job.title == "Risk Lead"
    assert job.short_summary
    assert job.job_url.endswith("/1")
    assert job.apply_url.endswith("/1/apply")
    assert job.location == "Amsterdam"
    assert job.department == "Risk"
    assert job.team == "Compliance"
    assert job.office == "Amsterdam"
    assert job.created_at == 1
    assert job.updated_at == 2


@pytest.mark.parametrize("field", ["id", "text", "descriptionPlain", "hostedUrl", "applyUrl"])
def test_inventory_fails_closed_when_required_field_missing(field):
    raw = _job()
    raw.pop(field)
    with pytest.raises(LeverError, match="required posting fields missing"):
        inventory("pnlfin", lambda site, offset, limit: [raw])


def test_inventory_rejects_duplicate_ids_across_pages():
    def fetch(site, offset, limit):
        return [_job(str(i)) for i in range(100)] if offset == 0 else [_job("0")]
    with pytest.raises(LeverError, match="duplicate/page-wrap"):
        inventory("pnlfin", fetch)


def test_inventory_rejects_non_array_payload():
    with pytest.raises(LeverError, match="expected JSON array"):
        inventory("pnlfin", lambda site, offset, limit: {"jobs": []})
