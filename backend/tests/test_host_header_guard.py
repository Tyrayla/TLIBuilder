"""DNS-rebinding Host-header guard on server.py (CWE-352).

The guard rejects a mismatched/attacker Host on the NETWORK-served (uvicorn) path only. It must NOT
apply to the in-process ASGI dispatch used by the Pyodide web-build worker
(src/renderer/src/web/computeWorker.ts), which imports `server` and calls `server.app` directly with a
headerless scope and never runs __main__. Pinning that exemption is the whole point of the second half
of this file — it is the exact regression a prior patch introduced by validating the shared app object
unconditionally.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

import server

_PORT = 8765


@pytest.fixture
def network_client(monkeypatch):
    # Simulate the uvicorn/__main__ bind path: arm the network flag and pin a known bound port, then
    # drive the *real* ASGI middleware stack (CORS + dev-gate + host guard) through TestClient.
    monkeypatch.setattr(server, "_SERVED_OVER_NETWORK", True)
    monkeypatch.setattr(server, "_SERVER_PORT", _PORT)
    return TestClient(server.app)


@pytest.mark.parametrize(
    "host",
    [
        f"127.0.0.1:{_PORT}",   # the real bind address the desktop clients use
        f"localhost:{_PORT}",   # equivalent loopback name
        f"[::1]:{_PORT}",       # IPv6 loopback — deliberately allowed (non-rebindable literal)
        f"LOCALHOST:{_PORT}",   # HTTP authority is case-insensitive
    ],
)
def test_loopback_host_accepted_on_network_path(network_client, host):
    r = network_client.get("/api/active-season", headers={"host": host})
    assert r.status_code == 200, f"legitimate loopback Host {host!r} was rejected ({r.status_code})"


@pytest.mark.parametrize(
    "host",
    [
        f"attacker.com:{_PORT}",     # DNS-rebinding attacker's own hostname
        f"evil.example:{_PORT}",
        "attacker.com",              # no port at all
        f"127.0.0.1:{_PORT + 1}",    # loopback host, wrong (unbound) port
    ],
)
def test_mismatched_host_rejected_on_network_path(network_client, host):
    r = network_client.get("/api/active-season", headers={"host": host})
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid host header"


def test_allowlist_tracks_the_real_bound_port(monkeypatch):
    # The allowlist is derived from _SERVER_PORT (the same source of truth set at bind time), so a
    # server that binds a different port only accepts that port's loopback authority.
    monkeypatch.setattr(server, "_SERVED_OVER_NETWORK", True)
    monkeypatch.setattr(server, "_SERVER_PORT", 8770)
    client = TestClient(server.app)
    assert client.get("/api/active-season", headers={"host": "127.0.0.1:8770"}).status_code == 200
    assert client.get("/api/active-season", headers={"host": "127.0.0.1:8765"}).status_code == 400


# ── The web-worker exemption — the regression this fix must not reintroduce ──────────────────────

def _raw_asgi_dispatch(method: str, path: str, body_text: str = "") -> tuple[int, str]:
    """Replicate src/renderer/src/web/computeWorker.ts's raw dispatch: build an ASGI http scope whose
    only header is content-type (NO Host header) and call server.app directly, exactly as the Pyodide
    worker does for every compute request in the web build."""
    raw, _, qs = path.partition("?")
    scope = {
        "type": "http", "http_version": "1.1", "method": method, "path": raw,
        "raw_path": raw.encode(), "query_string": qs.encode(),
        "headers": [(b"content-type", b"application/json")],  # <- no host header, like the worker
        "scheme": "http", "server": ("localhost", 80), "client": ("127.0.0.1", 0),
        "root_path": "", "asgi": {"version": "3.0", "spec_version": "2.3"},
    }
    body = (body_text or "").encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    state = {"status": 500, "chunks": []}

    async def send(m):
        if m["type"] == "http.response.start":
            state["status"] = m["status"]
        elif m["type"] == "http.response.body":
            state["chunks"].append(bytes(m.get("body", b"")))

    async def _run():
        await server.app(scope, receive, send)

    asyncio.run(_run())
    return state["status"], b"".join(state["chunks"]).decode("utf-8")


def test_web_worker_headerless_dispatch_is_not_rejected():
    # The plain imported module never ran __main__, so the flag is False and the headerless dispatch
    # (the web-build compute path) is served normally — NOT rejected 400. This is the exact regression
    # the verifier caught in the prior attempt.
    assert server._SERVED_OVER_NETWORK is False, "module default must be False for the web-worker path"
    status, _body = _raw_asgi_dispatch("GET", "/api/active-season")
    assert status == 200, f"headerless web-worker dispatch was rejected with {status}"


def test_flag_is_precisely_what_exempts_the_worker(monkeypatch):
    # Prove the exemption is the flag and nothing else: with the guard armed, the SAME headerless
    # scope would be rejected — so leaving the flag False on the in-process path is load-bearing.
    monkeypatch.setattr(server, "_SERVED_OVER_NETWORK", True)
    status, body = _raw_asgi_dispatch("GET", "/api/active-season")
    assert status == 400 and "Invalid host header" in body
