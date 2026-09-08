"""server.py: /api/engine/stats relays engine.guards.ImmunityThresholdError as a structured 422
instead of a bare 500, so the renderer can show the user why a calculation failed (see the 1FrxGVV
investigation). Must be scoped to that one guardrail type — an unrelated internal ValueError is a real
bug, not a build-state guardrail, and must keep surfacing as an unhandled 500 with a server traceback.
"""
from fastapi.testclient import TestClient

import server
from engine.guards import ImmunityThresholdError

client = TestClient(server.app, raise_server_exceptions=False)

_MINIMAL_BODY = {"slots": [None, None, None, None]}


def test_immunity_threshold_error_surfaces_as_422_with_the_real_message(monkeypatch):
    def _raise(*_a, **_k):
        raise ImmunityThresholdError("Damage-taken reduction reached immunity (>=100%) on a single stat: "
                                      "dmg_taken_additional: total=-1.2142 -> x-0.2142.")
    monkeypatch.setattr("engine.compute.compute", _raise)

    r = client.post("/api/engine/stats", json=_MINIMAL_BODY)

    assert r.status_code == 422
    assert "dmg_taken_additional" in r.json()["detail"]
    assert "immunity" in r.json()["detail"].lower()


def test_an_unrelated_value_error_is_not_relabeled_as_a_guardrail(monkeypatch):
    # A generic ValueError from a real bug elsewhere in compute() must NOT be caught by the same
    # handler — narrowing to ImmunityThresholdError specifically (not bare ValueError) is load-bearing.
    def _raise(*_a, **_k):
        raise ValueError("some unrelated internal bug, not a damage-taken guardrail")
    monkeypatch.setattr("engine.compute.compute", _raise)

    r = client.post("/api/engine/stats", json=_MINIMAL_BODY)

    assert r.status_code == 500
