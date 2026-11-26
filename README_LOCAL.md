# VolleyReview — private local SQLite edition

This branch is for a single owner on a trusted Windows computer. Do not deploy it to Render or expose the Streamlit port to your network. The original master branch is unchanged.

## Install
1. Install Python 3.11 or newer (https://www.python.org/downloads/windows/).
2. Download the sqlite-local branch ZIP from GitHub, extract it to a permanent folder, and double-click setup_local.bat.
3. If available, export the original public.plays table from Supabase as CSV (all rows and all columns) or preferably a JSON array preserving native types. Also export email_recipients, play_comments, video_angles and app_users if present. Save private exports inside the ignored data folder. Do not share them or commit them.
4. From Command Prompt in the extracted folder, run:
```bat
.venv\Scripts\python.exe migrate_local.py --table plays data\plays.csv
.venv\Scripts\python.exe migrate_local.py --table email_recipients data\email_recipients.csv
.venv\Scripts\python.exe migrate_local.py --table play_comments data\play_comments.csv
.venv\Scripts\python.exe migrate_local.py --table video_angles data\video_angles.csv
.venv\Scripts\python.exe migrate_local.py --table app_users data\app_users.csv
```
Run only the commands for exports you have. Substitute .json if appropriate. Import is transactional and refuses a nonempty table; it does not merge or replace existing records. Compare imported counts to source exports. CSV cannot distinguish empty strings from null and requires valid JSON in JSON columns; prefer JSON if available. If the source is inaccessible, start with an empty database and use DV Sport Sync; historical manual edits cannot be recovered by DV Sport alone. Supplemental comments, angles and user records are stored for archival purposes; the current dashboard uses plays (including embedded video_urls and notes) and email_recipients, not these separate archival tables.
5. Double-click launch_local.bat and visit http://127.0.0.1:8501. Keep the command window open. The database is data/volleyball_review.db. It persists across launches.

## DV Sport
Keep or create .streamlit/secrets.toml locally, with DVSPORT_COOKIE = "your cookie" if required. Preserve other non-Supabase settings used for DV Sport and email. Never commit cookies or secrets. Video retrieval still needs network access and authorization. CLI sync also uses SQLite: .venv\Scripts\python.exe dvsport_import.py --start YYYY-MM-DD --end YYYY-MM-DD

## Backups
Each launcher run creates a consistent backup for the day if a database exists. Run .venv\Scripts\python.exe migrate_local.py --backup manually as needed (one snapshot per day). Backups are in data/backups. Keep a separate secure copy off the computer. To restore, stop the app and all writers, preserve the current data directory, then copy a backup into a new data directory named volleyball_review.db (no old WAL/SHM sidecars).

## Differences from the cloud version
- Local administrator, no Supabase sign-in or Manage Users page.
- Public challenge links disabled; reports remain available without public links.
- The separate Google Sheets web API is legacy cloud-only and is not migrated or launched. Its source is retained for reference.
- The former Render blueprint is removed from this branch. Do not deploy this branch.
- A limited SQLite query adapter retains the existing dashboard, viewer, editor, report, and DV Sport query interface; nested JSON is preserved. No default row cap. Test actual exports and live sync before relying on the new version.
- Never synchronize the live SQLite database via OneDrive/Dropbox while it is open.

## Tests
```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```
