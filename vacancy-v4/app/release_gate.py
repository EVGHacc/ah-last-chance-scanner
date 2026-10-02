"""Central fail-closed release decision for v4 proof promotion."""
REQUIRED_GATES = ("unit_tests","contract_tests","independent_qa","canary","live_proof","authority_contract","persistence_safety")

def release_decision(gates):
    failed = [name for name in REQUIRED_GATES if gates.get(name) is not True]
    return {"release_allowed": not failed, "failed_gates": failed,
            "evaluated_gates": {name: gates.get(name) is True for name in REQUIRED_GATES}}
