# iPhone Quick Capture with Apple Shortcuts

SharedMoments can receive a photo or video as a **private draft**. It never appears in the Home feed, gallery, shared links or public media routes until its owner explicitly publishes it from the **Capture inbox**.

On iOS, Safari-installed PWAs do not currently implement the Web Share Target API. Use an **Apple Shortcuts Share Sheet action** instead. The iOS Shortcuts app supports Images, Media and Files as Share Sheet input.

## Prerequisite: scoped integration API key

For a password-free Share Sheet workflow, this PR requires the separate **Scoped API keys** PR #20 (or a release incorporating it). The capture route is registered for read/write API-key authentication only; a read-only key must not work. Before PR #20 is installed, a logged-in browser can use the protected capture endpoint with its CSRF token, but a standalone iPhone Shortcut cannot authenticate with an API key.

Create a dedicated account with **Create Home** permissions or an appropriately scoped user. Under User settings → API keys create a **Read and write** key with a short expiration. Store the key privately in your Shortcut, never include it in a publicly shared Shortcut, repository or screenshot. Revoke the key if the phone is lost.

## Configure the Shortcut

1. In iPhone **Shortcuts**, create a Shortcut named *Save to SharedMoments*. In its Details, enable **Show in Share Sheet**. Accept input types **Images, Media, Files**.
2. Add **Repeat with Each** item in **Shortcut Input**, so multiple selected photos or videos are sent as separate drafts.
3. Inside the loop add **Get Contents of URL** with Method **POST** and URL `https://sharedmoments.example.org/api/v2/capture/drafts` (replace this example URL with your authorised HTTPS endpoint).
4. Set HTTP request header **Authorization** to `Bearer YOUR_KEY`. Do not append the key to the URL or place it in the form body.
5. Set Request Body to **Form**. Add a field named **file**, type **File**, value **Repeat Item**. An optional text field named **title** can be set from the shared filename; **description** and **date** (YYYY-MM-DD) are also accepted.
6. Use **Show Result** on the returned JSON to confirm `status=success` and `data.status=pending`. The API returns a draft ID, not a published family memory.
7. From Photos on iPhone choose the photos/videos, tap Share, and select **Save to SharedMoments**.

In the SharedMoments app, open **Capture inbox**, review the media and text, optionally edit the title and description, then explicitly select **Publish to family**. The entry appears in the currently selected edition only after that action.

## Security and limitations

- Draft media is stored separately under private uploads; the ordinary media route cannot access it. Only the account that uploaded a draft can preview, edit, publish or discard it.
- Publishing is idempotent: repeated requests do not create duplicate memories. An interrupted, ambiguous publication is marked for manual reconciliation rather than retried automatically.
- One file per POST, up to 512 MiB; repeat per shared item. If a large video exceeds that limit, use the standard browser/chunked uploader.
- Direct HEIC uploads are accepted as private drafts, but displaying the HEIC still after publication requires the separate HEIC/HEIF PR #15.
- Live Photos shared as separate files become separate drafts. Automatic still+motion pairing in ordinary Home creation is provided by the separate video/Live Photo PR.
- Shortcuts holding credentials may synchronise across your Apple devices through iCloud; treat them as secrets. Use HTTPS externally and never enable unauthenticated uploads.

Apple documentation:
- [Use Shortcuts from the Share Sheet](https://support.apple.com/guide/shortcuts/run-a-shortcut-from-another-app-apd163eb9f95/ios)
- [Shortcut input types](https://support.apple.com/guide/shortcuts/understanding-input-types-apd7644168e1/ios)
