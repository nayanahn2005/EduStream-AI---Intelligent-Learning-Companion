"""
EduStream AI — Integration Test Suite
======================================
Tests all API endpoints to verify the server is functioning correctly.
"""

import sys
import json
import urllib.request
import urllib.error
import os
import tempfile

BASE_URL = "http://127.0.0.1:8000"
passed = 0
failed = 0
total = 0


def test(name, fn):
    global passed, failed, total
    total += 1
    try:
        fn()
        passed += 1
        print(f"  ✅ PASS: {name}")
    except Exception as e:
        failed += 1
        print(f"  ❌ FAIL: {name} — {e}")


def get(path):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode())


def get_raw(path):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode(), resp.headers.get("Content-Type", "")


def post_json(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode()


def post_json_expect_error(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


# ──────────────────────────────────────────────
# Test 1: Health Check
# ──────────────────────────────────────────────
def test_health_check():
    status, data = get("/")
    assert status == 200, f"Expected 200, got {status}"
    assert data["service"] == "EduStream AI", f"Unexpected service: {data['service']}"
    assert data["status"] == "operational", f"Unexpected status: {data['status']}"
    assert data["version"] == "2.0.0", f"Unexpected version: {data['version']}"
    assert data["engine"] == "Groq (Llama 3.3 70B)", f"Unexpected engine: {data['engine']}"


# ──────────────────────────────────────────────
# Test 2: Capabilities Endpoint
# ──────────────────────────────────────────────
def test_capabilities():
    status, data = get("/api/capabilities")
    assert status == 200, f"Expected 200, got {status}"
    assert set(data["modes"]) == {"flashcard", "notes", "quiz", "simplify"}, f"Unexpected modes: {data['modes']}"
    assert set(data["languages"]) == {"english", "hindi", "kannada"}, f"Unexpected languages: {data['languages']}"
    assert data["max_content_length"] == 50000
    assert data["model"] == "llama-3.3-70b-versatile"
    assert data["version"] == "2.0.0"


# ──────────────────────────────────────────────
# Test 3: Frontend Serving
# ──────────────────────────────────────────────
def test_frontend_serving():
    status, body, content_type = get_raw("/app")
    assert status == 200, f"Expected 200, got {status}"
    assert "text/html" in content_type, f"Expected text/html, got {content_type}"
    assert "EduStream AI" in body, "Frontend HTML should contain 'EduStream AI'"
    assert "Plus Jakarta Sans" in body, "Frontend should use Plus Jakarta Sans font"
    assert "handleStream" in body, "Frontend should contain handleStream function"


# ──────────────────────────────────────────────
# Test 4: Stream — Invalid Mode
# ──────────────────────────────────────────────
def test_stream_invalid_mode():
    status, body = post_json_expect_error("/api/stream", {
        "content": "Test content",
        "mode": "invalid_mode",
        "target_language": "english"
    })
    assert status == 422, f"Expected 422, got {status}"


# ──────────────────────────────────────────────
# Test 5: Stream — Invalid Language
# ──────────────────────────────────────────────
def test_stream_invalid_language():
    status, body = post_json_expect_error("/api/stream", {
        "content": "Test content",
        "mode": "notes",
        "target_language": "invalid_lang"
    })
    assert status == 422, f"Expected 422, got {status}"


# ──────────────────────────────────────────────
# Test 6: Stream — Empty Content
# ──────────────────────────────────────────────
def test_stream_empty_content():
    status, body = post_json_expect_error("/api/stream", {
        "content": "",
        "mode": "notes",
        "target_language": "english"
    })
    assert status == 422, f"Expected 422, got {status}"


# ──────────────────────────────────────────────
# Test 7: Stream — Missing Fields
# ──────────────────────────────────────────────
def test_stream_missing_fields():
    status, body = post_json_expect_error("/api/stream", {
        "content": "Test content"
    })
    assert status == 422, f"Expected 422, got {status}"


# ──────────────────────────────────────────────
# Test 8: Upload — Unsupported File Type
# ──────────────────────────────────────────────
def test_upload_bad_type():
    # Create a multipart form with a .jpg file
    boundary = "----TestBoundary12345"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="test.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
        f"fake image data\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert False, f"Expected error, got {resp.status}"
    except urllib.error.HTTPError as e:
        assert e.code == 400, f"Expected 400, got {e.code}"


# ──────────────────────────────────────────────
# Test 9: Upload — Valid TXT File
# ──────────────────────────────────────────────
def test_upload_txt():
    boundary = "----TestBoundary67890"
    file_content = "Hello, this is a test document for EduStream AI."
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
        f"{file_content}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        data = json.loads(resp.read().decode())
        assert data["filename"] == "test.txt"
        assert data["text"] == file_content
        assert data["characters"] == len(file_content)


# ──────────────────────────────────────────────
# Test 10: CORS Headers
# ──────────────────────────────────────────────
def test_cors():
    req = urllib.request.Request(f"{BASE_URL}/", method="OPTIONS")
    req.add_header("Origin", "http://localhost:3000")
    req.add_header("Access-Control-Request-Method", "POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            cors_header = resp.headers.get("Access-Control-Allow-Origin", "")
            assert cors_header == "*", f"Expected CORS *, got '{cors_header}'"
    except urllib.error.HTTPError as e:
        # Some versions return 400 for OPTIONS but still set CORS
        cors_header = e.headers.get("Access-Control-Allow-Origin", "")
        assert cors_header == "*", f"Expected CORS *, got '{cors_header}'"


# ──────────────────────────────────────────────
# Run all tests
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  EduStream AI — Integration Test Suite")
    print("=" * 60 + "\n")

    test("Health Check (GET /)", test_health_check)
    test("Capabilities (GET /api/capabilities)", test_capabilities)
    test("Frontend Serving (GET /app)", test_frontend_serving)
    test("Stream — Invalid Mode", test_stream_invalid_mode)
    test("Stream — Invalid Language", test_stream_invalid_language)
    test("Stream — Empty Content", test_stream_empty_content)
    test("Stream — Missing Fields", test_stream_missing_fields)
    test("Upload — Unsupported File Type (.jpg)", test_upload_bad_type)
    test("Upload — Valid TXT File", test_upload_txt)
    test("CORS Headers", test_cors)

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 60}\n")

    sys.exit(0 if failed == 0 else 1)
