# Email delivery and notification settings

SharedMoments already supports browser push, email and Telegram notifications with per-user preferences. An administrator can now configure SMTP under **Settings → Email delivery**, including host, port, STARTTLS or SSL/TLS, sender address, username and password.

## Security

- SMTP credentials are stored encrypted using Fernet, with an encryption key derived from the application's existing `SECRET_KEY`.
- The saved password is never returned by the API, included in HTML, or redisplayed in the settings form. Leaving the password field empty preserves the existing credential.
- Changing `SECRET_KEY` without migrating the saved SMTP credential makes it unreadable. Re-enter the SMTP password after a key rotation.
- Only accounts with `Update Setting` may view/change SMTP connection details or request a delivery test. Saving requires a logged-in browser session and CSRF token.
- A test email is sent only when an administrator explicitly selects **Send test email**, and goes to that administrator's existing account address.
- TLS is required: choose STARTTLS (typically port 587) or SSL/TLS (typically 465). Unencrypted SMTP is not supported by the UI.

When no SMTP settings are saved, the existing environment variables (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`) continue to work unchanged. Saving UI settings makes them authoritative; disabling SMTP in the UI also disables mail delivery.

Registered users may opt into or out of email under **User settings → Notifications**. These settings are independent of the global SMTP connection and remain in place.

This feature reuses Flask, SQLite and the existing notification system. It adds no new network service or new dependency.
