from .model import Coverage, InventoryProof, Source
from .transport import fetch_json
from .providers.ashby import inventory


def ashby_inventory(board_name: str):
    endpoint = f"https://api.ashbyhq.com/posting-api/job-board/{board_name}"
    return inventory(board_name, lambda _: fetch_json(endpoint))


def ashby_proof(source: Source, board_name: str) -> InventoryProof:
    jobs = ashby_inventory(board_name)
    proof = InventoryProof(
        source=source,
        coverage=Coverage.VERIFIED_COMPLETE,
        unique_jobs=len(jobs),
        authoritative_total=None,
        exhausted=True,
        evidence_kind="official_complete_payload",
    )
    proof.validate()
    return proof
