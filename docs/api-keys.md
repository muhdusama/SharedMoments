# Scoped API keys for integrations

Create an integration key under **User settings → API keys**.

- Keys belong to one existing account and inherit that user's permissions.
- Choose **Read only** or **Read and write**; writes require both the key scope and the account's underlying role permissions.
- Keys expire in 30, 90 or 365 days by default. You may explicitly choose **Never (not recommended)** after a confirmation warning. Never-expiring keys remain valid until revoked or the owner is deleted; they still count toward the 20-active-key limit. All keys are shown only once and may be revoked immediately.
- Only a SHA-256 digest is stored in SQLite; the original random 256-bit secret is never stored and cannot be recovered.
- API keys work only with the application's allowlisted memory, media and upload API routes. They cannot open HTML pages or change security settings, users, notifications, credentials or other application administration routes.
- When the optional iPhone Quick Capture feature is installed, a read/write key may also **create a private capture draft**. The key cannot preview drafts or publish them; those actions remain browser-session-only.
- Key creation and revocation require a browser login and session-based CSRF protection. An API key cannot issue another API key.

Supply an API key over **HTTPS** as an HTTP request header, never as a URL parameter:

```http
Authorization: Bearer smk_YOUR_KEY_SHOWN_ONCE
```

Keep API keys out of Git repositories, shell history, logs and exported documents. Prefer a dedicated integration user with only the required app permissions; revoke an unused or compromised key.

The API-key implementation uses existing Flask/SQLAlchemy authentication and the normal permission checks. It requires no second database, sidecar, MCP service or new network port. On first start after upgrading, the new `api_keys` table is created through the application's existing SQLAlchemy table creation path. The stored token metadata is not intended to be included in a public data export.

For detailed memory listing and structured retrieval, see the separate MCP/JSON read-interface contribution, if installed. The token feature does not change existing browser routes or add unrestricted data exports.
