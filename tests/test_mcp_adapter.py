"""MCP adapter tests with synthetic data and no external connections."""

import pytest

pytest.importorskip("mcp")
import mcp_server


def test_insecure_remote_url_is_rejected(monkeypatch):
    monkeypatch.setenv("SHAREDMOMENTS_URL", "http://example.invalid")
    monkeypatch.setenv("SHAREDMOMENTS_EMAIL", "test@example.invalid")
    monkeypatch.setenv("SHAREDMOMENTS_PASSWORD", "synthetic-password")
    with pytest.raises(ValueError, match="HTTPS"):
        mcp_server._api("GET", "/api/v2/items")


def test_read_and_write_tools_use_existing_api(monkeypatch):
    recorded = []

    def fake_api(method, path, **kwargs):
        recorded.append((method, path, kwargs))
        if path == "/api/v2/items" and method == "GET":
            return {"items": [{"id": 12, "title": "Synthetic memory"}]}
        if path == "/api/v2/item/12":
            return {
                "id": 12, "title": "Synthetic memory", "content": "Old",
                "contentType": "text", "contentURL": "", "listType": 1,
                "edition": "all", "dateCreated": "2026-01-01",
            }
        if path == "/api/v2/items" and method == "POST":
            return {"id": 13}
        return {"id": 12}

    monkeypatch.setattr(mcp_server, "_api", fake_api)
    assert mcp_server.list_memories(5)[0]["id"] == 12
    assert mcp_server.get_memory(12)["title"] == "Synthetic memory"
    assert mcp_server.create_memory("Synthetic title", "Synthetic description", "2026-01-01") == 13
    assert mcp_server.update_memory(12, description="Updated") == 12
    assert recorded[-1][2]["data"]["content"] == "Updated"
    with pytest.raises(ValueError):
        mcp_server.create_memory("", "Cannot publish")


def test_media_tool_restricts_local_files(monkeypatch, tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"synthetic")
    monkeypatch.setenv("SHAREDMOMENTS_MEDIA_ROOT", str(allowed))
    with pytest.raises(ValueError, match="inside"):
        mcp_server.attach_media(1, str(outside))

    media = allowed / "sample.jpg"
    media.write_bytes(b"synthetic")
    calls = []

    def fake_api(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/api/v2/item/1":
            return {
                "id": 1, "title": "Test", "content": "", "contentType": "text",
                "contentURL": "", "listType": 1, "edition": "all", "dateCreated": "2026-01-01",
            }
        if path == "/api/v2/upload":
            return {"filename": "generated.jpg"}
        return {"id": 1}

    monkeypatch.setattr(mcp_server, "_api", fake_api)
    assert mcp_server.attach_media(1, str(media)) == "generated.jpg"
    assert calls[-1][2]["data"]["contentType"] == "image"
    assert calls[-1][2]["data"]["contentURL"] == "generated.jpg"
