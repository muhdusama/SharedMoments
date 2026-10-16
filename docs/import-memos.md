# Import shared Memos memories

The optional `scripts/import_memos.py` script copies approved, **PROTECTED** Memos entries and their associated original attachments into SharedMoments. It uses the existing Memos REST API and SharedMoments upload and item APIs. It does **not** delete, update or change visibility in Memos.

## Before importing

- Back up both applications and their media. Verify that the backup can be restored.
- Review the protected entries in Memos. Every imported entry becomes visible to users authorised to view the destination Home feed. **Private** and placeholder (`NEED INPUT`) entries are always skipped.
- Use an empty or isolated SharedMoments destination for the first trial. Existing items are not deleted or replaced.
- Install HEIC/HEIF support on the destination before importing those attachment types.
- Some Memos metadata, authorship and rich Markdown presentation do not map to SharedMoments. The original note text is retained, but may display as plain text. Unlinked Memos attachments and external media links require manual review.

## Running the importer

Install the application's existing `requirements.txt` dependencies, or at least the already-used `requests` library, in a separate Python 3.12+ environment.

Configure the following environment variables using your preferred local secret manager (never put credentials into Git):

| Variable | Purpose |
| --- | --- |
| `MEMOS_URL` | Memos base URL, preferably HTTPS |
| `MEMOS_TOKEN` | Read-only Memos API token |
| `SHAREDMOMENTS_URL` | SharedMoments base URL, preferably HTTPS |
| `SHAREDMOMENTS_EMAIL` | Dedicated SharedMoments user account |
| `SHAREDMOMENTS_PASSWORD` | Password for that account |

By default this command reports only counts and makes no changes:

```sh
python scripts/import_memos.py --timezone Australia/Sydney
```

After reviewing the source and destination, import the selected shared entries:

```sh
python scripts/import_memos.py --timezone Australia/Sydney --apply
```

Plaintext HTTP is refused except for loopback. For a trusted private LAN, use `--allow-http` explicitly. Do not use that option over the public internet.

## Safety and recovery

- The importer copies source data only. It never deletes the Memos records.
- An import progress file is kept outside the repository, under `~/.local/state/sharedmoments/`, with owner-only permissions. It contains source/target identifiers and attachment filenames, not memo text or media bytes.
- Repeating `--apply` skips completed entries. An interrupted attachment upload can be retried without recreating the memory.
- If an entry was created but the result was lost before the progress file could be updated, the script stops and requires manual reconciliation rather than risking a duplicate.
- Files are downloaded to a temporary directory and deleted after upload. Media uploads use SharedMoments' chunked API rather than buffering a large video.
- The script does not automatically synchronise future changes in Memos. Set up a separate reviewed integration for ongoing publishing.
- Check original orientation, video playback, visible date, creator attribution and the restored originals before retiring Memos.
