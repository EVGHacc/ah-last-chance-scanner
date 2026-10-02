from app.release_gate import REQUIRED_GATES, release_decision

def test_all_required_gates_must_be_green():
    gates = {name: True for name in REQUIRED_GATES}
    assert release_decision(gates)["release_allowed"] is True

def test_missing_gate_fails_closed():
    gates = {name: True for name in REQUIRED_GATES if name != "independent_qa"}
    decision = release_decision(gates)
    assert decision["release_allowed"] is False
    assert decision["failed_gates"] == ["independent_qa"]

def test_explicit_false_gate_fails_closed():
    gates = {name: True for name in REQUIRED_GATES}
    gates["persistence_safety"] = False
    assert release_decision(gates)["release_allowed"] is False
