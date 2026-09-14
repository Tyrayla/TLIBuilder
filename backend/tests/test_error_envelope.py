from fastapi.testclient import TestClient

import server


def test_build_code_errors_use_the_structured_error_envelope():
    response = TestClient(server.app, raise_server_exceptions=False).post(
        "/api/build-code/decode", json={"code": "not-a-build-code"}
    )

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "TLI-BUILD-001"
    assert body["error"]["operation"] == "build-code.decode"
    assert body["error"]["retryable"] is False
    assert len(body["error"]["fingerprint"]) == 16
    assert body["error"]["requestId"] == response.headers["x-request-id"]


def test_invalid_build_code_request_is_sanitized_and_typed():
    response = TestClient(server.app, raise_server_exceptions=False).post(
        "/api/build-code/decode", json={"code": 42}
    )

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "TLI-BUILD-001"
    assert body["message"] == "The request has an invalid format."
    assert body["requestId"]
