# Optional local MCP adapter

SharedMoments has a bundled **MCP stdio adapter** for assistants running on a trusted machine. It reuses the existing Flask API and account permissions. It does not open an additional HTTP listener or bypass login.

Install only on the assistant machine with Python 3.12 or newer:

```sh
python -m pip install -r requirements-mcp.txt
```

Configure the process environment (never commit credentials):

| Variable | Purpose |
| --- | --- |
| `SHAREDMOMENTS_URL` | HTTPS URL to the existing SharedMoments instance |
| `SHAREDMOMENTS_EMAIL` | Email address of a dedicated SharedMoments account |
| `SHAREDMOMENTS_PASSWORD` | Password for that account |
| `SHAREDMOMENTS_MEDIA_ROOT` | Optional local directory from which approved media may be uploaded |

The adapter refuses plaintext HTTP except for loopback. Run it from the source checkout:

```sh
python mcp_server.py
```

Configure your MCP client to launch this command with transport `stdio`, a private working directory and the necessary environment variables. Do not expose credentials through command arguments or source files. Use a dedicated Adult or otherwise appropriately restricted account, not the installation administrator.

Available tools: `list_memories`, `get_memory`, `create_memory`, `update_memory` and `attach_media`. The write tools should be invoked only after explicit user approval. The media tool can only read files inside `SHAREDMOMENTS_MEDIA_ROOT`. Without that variable, media upload remains unavailable. The application enforces its normal list permissions on all memory API operations.

This initial adapter uses the Home feed (list type 1). The JSON read routes added to the existing API are `GET /api/v2/items?listType=1&limit=20` and `GET /api/v2/item/<id>?format=json`. The current browser edit route is unchanged.

The adapter is not an always-running daemon or a remote Streamable HTTP endpoint. Configure an authenticated HTTP MCP endpoint separately if one is needed later, using the SDK's standard HTTP authorisation rather than exposing stdio without access controls.
