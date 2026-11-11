# VolleyReview — Google Sheets Master Play Library

This is a **deployment-ready integration package**, not a live connected spreadsheet. It builds on the existing Supabase `public.plays` database. It is designed for the newer `plays.video_urls` JSONB format, and can also read legacy `public.video_angles` records when necessary.

## What you'll get

- `All Plays`, `Challenges`, `Faults`, `POIs` tabs
- Classification tabs: `Touch`, `In-Out`, `Net`, `Attack Line`, `Service-Center Line`, `Other-Uncategorized`
- `START HERE` instructions and a permanent `Comments Log` with comment author, timestamp, text, and hashtag tags
- One row per play in each applicable tab; named clickable links for **all available video angles** (up to 30, not just the 8 provided in the starter template)
- Column A: **Download ZIP** links, with match/date/set/category/ID filenames and all obtainable camera angles plus play metadata and saved comments
- Yellow `New Comment` cells that save to Supabase, plus `VolleyReview > Add comment to selected play`
- Refresh menu and optional 15-minute automatic sync

**Important:** Do not use this workbook as a public document. It exposes match information and signed download links. All spreadsheet editors can access the Apps Script project and may be able to access its project properties, so give editing access only to trusted personnel. The service-role key stays on your server; never put it into Google Sheets or Apps Script. The integration key also grants read and comment-write access to this integration API, so treat it as confidential.

## Prerequisites

1. Access to the correct VolleyReview Supabase project as an administrator.
2. A secure HTTPS deployment environment for Python/FastAPI, such as a Docker-compatible web service, with enough disk/temporary storage for the largest play ZIP.
3. A Google account with permission to create/edit a Google Sheet and its bound Apps Script.
4. The actual DV Sport video hostnames, `DVSPORT_COOKIE` for FilmRoom blob signing (if applicable), and working signed media URLs. **Videos can be downloaded only while their source links remain accessible.** Streaming playlists (`.m3u8`) need a separate conversion service and are not downloaded by this implementation.
5. Existing application credentials remain in your VolleyReview deployment; this package uses separate backend secrets. Never paste keys or tokens in chat.

## Step 1 — Add the comments table (one-time)

In the **existing** Supabase project, run `sql/01_play_comments.sql` in SQL Editor. It creates `public.play_comments` with a foreign key to the existing `public.plays(id)`, accommodating the existing ID type. This does not delete or overwrite historical plays, grade data, or video records. It enables row-level security without creating public access policies. The backend uses the service role key and is therefore the only authorized connection to that new table.

Don't rerun older migrations automatically. In particular, an earlier `database_video_urls_migration.sql` ends by dropping `public.video_angles`; **review your live schema** first instead of rerunning it.

## Step 2 — Deploy the backend

Copy `backend/` to a private repository or server, deploy the included Dockerfile, and set the following environment variables **in the hosting provider's secret manager**:

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Current Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase server-side service-role key — never expose to browsers or Google Sheets |
| `SHEETS_INTEGRATION_KEY` | A separate random 32+-byte secret protecting the read/comment endpoints |
| `DOWNLOAD_SIGNING_SECRET` | Another independent random 32+-byte secret for time-limited play download links |
| `PUBLIC_BASE_URL` | Exact `https://...` origin at which this API is externally reachable |
| `ALLOWED_MEDIA_HOSTS` | Comma-separated video hostnames from verified DV Sport URLs; subdomains accepted |
| `VOLLEYREVIEW_PLAY_URL_TEMPLATE` | Optional actual VolleyReview deep-link URL with `{id}` placeholder. If the existing app has no Play ID deep-link route, leave empty. |
| `DOWNLOAD_LINK_TTL_DAYS` | Optional, default 14, maximum 30. All links regenerated on refresh. |
| `MAX_ZIP_TOTAL_MB` | Optional max sum of source bytes per downloaded ZIP, default 1500. |
| `DVSPORT_COOKIE` | Optional FilmRoom cookie used to refresh Azure SAS URLs, as in the existing `services/dvsport_media.py`. Configure on the **server only**. |

Create **different** random secrets for integration and downloads (for example `python -c "import secrets; print(secrets.token_urlsafe(48))"`). Do not use Supabase's anon key as either secret. Your deployment must provide TLS/HTTPS and sufficient storage/CPU/bandwidth for multiple MP4 files.

Local startup only for a private development machine:

```bash
cd backend
python -m pip install -r requirements.txt
# Configure environment variables in the shell (see .env.example).
uvicorn app:app --host 127.0.0.1 --port 8000
```

`GET /health` confirms that the web app is running; it does **not** validate database credentials. `GET /api/v1/plays` with header `X-Integration-Key: <your integration key>` verifies the full connection. Keep the API private except for its signed ZIP route; use hosting access controls, network rules and rate limiting for production.

**Repo compatibility:** This code targets `plays.video_urls` and the five categories from `services/review_taxonomy.py` at the September 27, 2026 `master` commit. It does not change existing Streamlit pages, grading logic, or DV Sport sync. `DVSPORT_COOKIE` must be refreshed if it expires.

**ZIP route:** `GET /api/v1/plays/{play_id}/download?expires=<timestamp>&sig=<HMAC>`; the signing happens on the backend, so Sheets never needs the signing secret. The service verifies the signature, retrieves all current angles, checks destination hostnames against an allowlist, rejects non-public destinations, builds the ZIP in temporary storage, then returns it as a file. If some media cannot be fetched, it inserts `Missing_Angles.txt`. If no media can be fetched, download fails rather than providing a misleading ZIP.

**Privacy caveat:** Anyone who obtains an unexpired download link can download its play without a separate login. Share Sheets only with authorized reviewers, use the shortest practical link lifetime, and rotate the download signing secret to invalidate outstanding links. Source DV Sport URLs may themselves be signed and expire independently.

## Step 3 — Make the native Google Sheet

1. Create a **blank Google Sheet** in Google Drive (or use the previously provided starter workbook if you already downloaded it).
2. If you imported the starter `.xlsx`, choose **File > Save as Google Sheets**. A blank native Google Sheet needs no conversion.
3. Open **Extensions > Apps Script**, replace the editor contents with `google_apps_script/Code.gs`, and Save.
4. Return to the Sheet and reload the browser tab. You should now see a new **VolleyReview** menu.
5. Choose **VolleyReview > 1. Configure backend** and enter `PUBLIC_BASE_URL` and `SHEETS_INTEGRATION_KEY` (not the Supabase key). These settings are saved to Apps Script project properties, not sheet cells.
6. Choose **VolleyReview > 2. Refresh all plays** and grant the requested Google permissions. The script fetches all plays and all saved comments, resets the views, and creates the correct number of angle columns dynamically.
7. Check one Challenge, Fault, and POI for correct links and classification; click an angle and test the first-column ZIP on a small play.
8. Choose **VolleyReview > 3. Enable automatic syncing + comments**, and accept the prompt. It installs an on-edit trigger and a 15-minute refresh trigger. You can always run a manual refresh.

**Data entry:** Every play tab has one yellow `New Comment` column. Type a comment and press Enter, or choose a play and use `VolleyReview > Add comment to selected play`. Use `#Training`, `#Rules`, etc. to assign a reusable tag. A successful write updates comment summaries on matching tabs. If saving fails, the yellow cell retains your draft and displays an explanatory note. Always use the yellow cells or menu, not a native cell comment: native cell comments do not write to Supabase.

**Avoid editing other generated cells.** Play data comes from Supabase. Changes to imported columns are overwritten at the next sync. Use VolleyReview itself to edit official grading, status, notes, categories, or other review data. The `Comments Log` is read-only output of the saved comments and is regenerated from Supabase.

## How the data is mapped

| Source | Sheet columns |
|---|---|
| `plays.id`, `dvsport_id`, `dvsport_play_number` | Play ID, DV Sport ID, DV Sport Play # |
| `match_date`, `conference`, `match_name`, `set_number`, `score` | Match details |
| `play_type` | All Plays / Challenges / Faults / POIs |
| `ncaa_challenge_category`, `crs_category`, `fault_category`, or imported category | Appropriate category tab |
| `crs_original_decision`, `crs_outcome`, `challenge_outcome_detail`, `referee_judgment` | Challenge review fields |
| `review_status`, `reviewer_notes`, `weekly_summary_note`, `use_for_training` | Review workflow fields |
| `video_urls` JSONB or old `video_angles` table | All clickable camera angles |
| `play_comments` | Latest Comment, Comment Count, Comment Tags, full Comments Log |

The category mapping follows VolleyReview's five existing review categories. An unknown/unclassified value falls into Other/Uncategorized rather than being discarded. Some non-challenge plays may not have a review category; they will still appear on their main play-type tab and All Plays.

## Maintenance and limitations

- Google Sheets is useful as a browsing interface; very large datasets/30 angles per play can create many cells and exceed Google Apps Script's runtime quota. For a very large production database, use date-window incremental sync and a staging cache as a later optimization.
- Video host allowlists are mandatory. Avoid adding untrusted domains. The ZIP builder requires directly downloadable HTTPS video files and does not bypass DRM, logins, or DV Sport access controls.
- Comments do not modify existing referee grades or reviewer notes. They append entries to a separate table, retaining history.
- The script rebuilds each view at refresh; filters and customized column formatting in generated views may be reset. Use the provided menu and Comments Log instead of structural manual changes.
- No access to the user's private Supabase credentials or a connected Google Sheet was present in this environment, so this package has **not been deployed**, the database migration has **not been run**, and actual video URLs and download behavior **have not been verified against the live service**.

## Testing

From the integration folder:

```bash
python -m unittest discover -s tests -v
python -m compileall -q backend
```

These tests verify normalization, angle extraction, filenames and signed-link creation. Full end-to-end testing requires your own Supabase and media access.
