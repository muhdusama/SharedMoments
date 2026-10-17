# Family comments and reactions

SharedMoments includes a lightweight discussion panel underneath visible Home memories.

- Members with **View Home** may read comments and reactions and add supported reactions (heart, like, laugh, celebrate).
- Members with **Create Home** may add a comment of up to 1,200 characters. Comments are rendered as plain text rather than interpreted as HTML.
- The author may edit or delete their own comment. Members with **Delete Home** may moderate/delete another member's comment, but cannot impersonate or edit its author.
- Reactions are saved explicitly as on/off rather than toggled blindly, so duplicate client requests do not create duplicate reactions or notifications.
- The same current-edition and Home permission checks apply before reading, writing or moderating. Comments and reactions are deleted with their parent memory.
- Write APIs require a signed-in browser session and a per-session CSRF token. Anonymous access and public share pages do not expose discussions.

## Notifications

Under **User settings → Notifications**, each account can opt in to receiving activity alerts for memories they created. This is **off by default**. Delivery uses the user's existing push/email/Telegram choices.

The notification payload is deliberately generic: it does not contain the comment itself, photographs or a memory description. The author is not notified about their own activity. Failed delivery does not prevent a comment or reaction being saved.

This feature uses existing Flask, SQLite, account permissions and notification services. Tests use synthetic accounts and mocked notification delivery; no real messages were sent.
