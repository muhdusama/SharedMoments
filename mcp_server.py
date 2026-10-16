"""Optional SharedMoments MCP stdio adapter using the existing authenticated API."""

import os
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import requests
from mcp.server import MCPServer


mcp = MCPServer("SharedMoments")
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "heic", "heif"}
VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "webm", "mkv"}


def _api(method, path, **kwargs):
    base = os.environ["SHAREDMOMENTS_URL"].rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})
    ) or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("SHAREDMOMENTS_URL must be HTTPS or local loopback HTTP")

    email = os.environ["SHAREDMOMENTS_EMAIL"]
    password = os.environ["SHAREDMOMENTS_PASSWORD"]
    with requests.Session() as http:
        login = http.post(
            f"{base}/login",
            data={"email": email, "password": password},
            allow_redirects=False,
            timeout=(10, 30),
        )
        if login.status_code != 200 or login.json().get("status") != "success":
            raise PermissionError("SharedMoments authentication failed")
        response = http.request(
            method, f"{base}{path}", allow_redirects=False, timeout=(10, 300), **kwargs
        )
        if response.status_code in (301, 302, 303, 307, 308, 401, 403):
            raise PermissionError("SharedMoments denied this operation")
        response.raise_for_status()
        result = response.json()
        if result.get("status") != "success":
            raise RuntimeError(result.get("message", "SharedMoments request failed"))
        return result["data"]


def _date(value):
    if value:
        date.fromisoformat(value)
    return value


@mcp.tool()
def list_memories(limit: int = 20) -> list[dict]:
    """List recent visible family memories (read-only)."""
    return _api("GET", "/api/v2/items", params={"listType": 1, "limit": limit})["items"]


@mcp.tool()
def get_memory(item_id: int) -> dict:
    """Retrieve one memory and its media filenames (read-only)."""
    return _api("GET", f"/api/v2/item/{item_id}", params={"format": "json"})


@mcp.tool()
def create_memory(title: str, description: str, memory_date: str = "") -> int:
    """Publish a new family memory. Requires the user's explicit approval."""
    if not title.strip():
        raise ValueError("Title is required")
    return _api("POST", "/api/v2/items", data={
        "title": title, "content": description, "contentType": "text",
        "listType": 1, "edition": "all", "dateCreated": _date(memory_date),
    })["id"]


@mcp.tool()
def update_memory(
    item_id: int, title: str | None = None, description: str | None = None, memory_date: str | None = None
) -> int:
    """Update an existing family memory without discarding its media. Requires approval."""
    item = get_memory(item_id)
    if item["listType"] != 1:
        raise ValueError("Only family memories can be updated")
    if title is not None and not title.strip():
        raise ValueError("Title cannot be empty")
    _api("PUT", f"/api/v2/item/{item_id}", data={
        "title": item["title"] if title is None else title,
        "content": item["content"] if description is None else description,
        "contentType": item["contentType"],
        "contentURL": item["contentURL"] or "",
        "listType": item["listType"],
        "edition": item["edition"] or "all",
        "dateCreated": _date(item["dateCreated"] if memory_date is None else memory_date),
    })
    return item_id


@mcp.tool()
def attach_media(item_id: int, source_path: str) -> str:
    """Attach a local photo/video from the configured media directory; requires approval."""
    root = Path(os.environ["SHAREDMOMENTS_MEDIA_ROOT"]).expanduser().resolve(strict=True)
    source = Path(source_path).expanduser().resolve(strict=True)
    if not source.is_file() or root not in source.parents:
        raise ValueError("Media must be a file inside SHAREDMOMENTS_MEDIA_ROOT")
    extension = source.suffix.lower().lstrip(".")
    if extension not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
        raise ValueError("Unsupported media format")
    if source.stat().st_size > 2 * 1024 * 1024 * 1024:
        raise ValueError("Media file exceeds 2 GiB")

    item = get_memory(item_id)
    if item["listType"] != 1:
        raise ValueError("Only family memories can receive media")
    old_urls = [name for name in (item["contentURL"] or "").split(";") if name]
    first_ext = Path(old_urls[0]).suffix.lower().lstrip(".") if old_urls else extension
    content_type = (
        "galleryStartWithImage" if first_ext in IMAGE_EXTENSIONS else "galleryStartWithVideo"
    ) if old_urls else ("image" if extension in IMAGE_EXTENSIONS else "video")

    with source.open("rb") as media:
        uploaded = _api("POST", "/api/v2/upload", files={"file": (source.name, media)})
    filename = uploaded["filename"]
    _api("PUT", f"/api/v2/item/{item_id}", data={
        "title": item["title"],
        "content": item["content"] or "",
        "contentType": content_type,
        "contentURL": ";".join([*old_urls, filename]),
        "listType": item["listType"],
        "edition": item["edition"] or "all",
        "dateCreated": item["dateCreated"],
    })
    return filename


if __name__ == "__main__":
    mcp.run(transport="stdio")
