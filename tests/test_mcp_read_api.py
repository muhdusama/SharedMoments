"""Read API permissions and data shape used by the optional MCP adapter."""

from datetime import datetime


def test_read_routes_require_login(client):
    assert client.get("/api/v2/items").status_code == 302
    assert client.get("/api/v2/item/1?format=json").status_code == 302


def test_read_api_works_for_view_only_family_user(admin_client, child_client):
    from app.db_queries import create_item, delete_item

    item_id = create_item(
        "Synthetic family memory", "Test only", "text", 1, "", 2, datetime(2026, 1, 1)
    )
    try:
        listed = child_client.get("/api/v2/items?listType=1&limit=5")
        assert listed.status_code == 200
        assert any(entry["id"] == item_id for entry in listed.json["data"]["items"])
        retrieved = child_client.get(f"/api/v2/item/{item_id}?format=json")
        assert retrieved.status_code == 200
        assert retrieved.json["data"]["title"] == "Synthetic family memory"
        assert retrieved.json["data"]["dateCreated"] == "2026-01-01"
        assert retrieved.json["data"]["contentURL"] == ""

        # Normal edit-page GET still requires Update permission.
        assert child_client.get(f"/api/v2/item/{item_id}").status_code == 403
        assert admin_client.get(f"/api/v2/item/{item_id}").status_code == 200
    finally:
        delete_item(item_id)


def test_read_api_rejects_invalid_limits(admin_client):
    assert admin_client.get("/api/v2/items?limit=0").status_code == 400
    assert admin_client.get("/api/v2/items?limit=101").status_code == 400
    assert admin_client.get("/api/v2/items?limit=wrong").status_code == 400
