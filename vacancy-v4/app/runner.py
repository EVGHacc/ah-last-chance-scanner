from .model import Coverage, InventoryProof, Source
from .transport import fetch_json
from .providers.ashby import inventory

ASHBY_MAX_BYTES = 64_000_000


def ashby_endpoint(board_name: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{board_name}"


def ashby_fetch_json(url: str):
    return fetch_json(url, max_bytes=ASHBY_MAX_BYTES)


def ashby_inventory(board_name: str, fetcher=None):
    endpoint = ashby_endpoint(board_name)
    transport = fetcher or ashby_fetch_json
    return inventory(board_name, lambda _: transport(endpoint))


def ashby_run(source: Source, board_name: str, fetcher=None):
    jobs = ashby_inventory(board_name, fetcher)
    proof = InventoryProof(
        source=source,
        coverage=Coverage.VERIFIED_COMPLETE,
        unique_jobs=len(jobs),
        authoritative_total=None,
        exhausted=True,
        evidence_kind="official_complete_payload",
    )
    proof.validate()
    return proof, jobs


def ashby_proof(source: Source, board_name: str, fetcher=None) -> InventoryProof:
    return ashby_run(source, board_name, fetcher)[0]
