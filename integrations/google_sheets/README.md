# VolleyReview — Simple Play Library in Google Sheets

**Purpose: find a play, see its information, watch every camera angle, and add comments. NO GRADING.**

This is an optional companion to the existing Streamlit + Supabase VolleyReview app. The existing Challenge, Fault and POI grading/review system is **not modified**.

## Your native Google Sheet

[VolleyReview — Simple Play Library](https://docs.google.com/spreadsheets/d/1tZBsHUzVrdSEiKz7X-vJPF0hDEEx17-4N0Q0uFG9NLw/edit)

Created with tabs: START HERE, Find & Import, All Plays, Saved Plays, Challenges, Faults, POIs, Touch, In-Out, Net, Attack Line, Service-Center Line, Other-Uncategorized and Comments Log. It is a **prepared shell, not live data** until the steps below are completed.

## What every play row shows

- **Download ZIP** — one time-limited link for the play's available camera angles, source information and comments
- **Watch Video** — opens the preferred available video
- **Date, Conference, Match, Play Type, Category, Set, Score and DV Sport PLAY #**
- **Angle 1–N** — individually named and clickable camera URLs, up to 30
- **Latest Comment, comment count, yellow New Comment input and tags**

No grades, referee judgments, review outcomes, or grading statistics appear in the spreadsheet, and ZIP metadata omits them.

When you enter a comment in a yellow cell, the installable Apps Script trigger calls the private API to append it to Supabase `public.play_comments`. Comments remain attached to the permanent play ID and survive sheet refreshes.

## Find & Import: a play that wasn't flagged

1. Open the **Find & Import** tab.
2. Choose a conference (or All), date range and optional team/match search text.
3. Choose **VolleyReview > Find & Import: search matches**.
4. Pick a match. The installed edit trigger automatically lists DV Sport PLAY numbers; alternatively choose **Find & Import: list plays** from the menu.
5. Choose the PLAY number and select **Find & Import: import play**.
6. The backend reads the authorized DV Sport **FULL GAME** playlist with the existing `services/dvsport_sync.py` parser and saves the play's source metadata and all available camera angles.

**Duplicate safety:** If that match/date/conference/PLAY number already belongs to a Challenge, POI or Fault, its original row is reused and only source video/metadata is enriched—no grades or review decisions are touched. Otherwise a new `play_type='Saved'` record is created using a deterministic DV Sport ID. Reimporting the same Saved Play does not create duplicates.

**No blank entries:** If DV Sport has no camera angles for the selected play, import is rejected rather than creating a play without video.

Library search uses the existing authenticated FilmRoom session and reads only matches available to that account. It caches discovery for 15 minutes. Search is limited to 92-day windows, which keeps the chooser manageable. DV Sport sessions/cookies can expire.

## Deployment prerequisites — not yet completed

1. **Supabase connection:** Administrator access to the **existing** VolleyReview project. Verify that `public.plays` has `video_urls` JSONB, `dvsport_play_number`, `dvsport_full_game_url`, `dvsport_metadata`, and `dvsport_id` with a unique constraint, and permits `play_type='Saved'`. The current app's FULL GAME migration provides the columns; if a custom `play_type` CHECK constraint excludes Saved, update that constraint after examining its current permitted values. Do **not** blindly drop or recreate old constraints or rerun old migrations.
2. **Comments table:** Run `sql/01_play_comments.sql` in the actual Supabase SQL Editor. It creates a separate `play_comments` table and does not delete or rewrite existing plays.
3. **API host:** Deploy `backend/` with the included Dockerfile **from the repository root**. Example: `docker build -f integrations/google_sheets/backend/Dockerfile .`. The backend needs HTTPS, temporary disk for ZIPs and the secret settings below. You can use any Docker-capable host.
4. **DV Sport access:** Set a working `DVSPORT_COOKIE` server-side. This backend uses that authenticated session to browse games and obtain fresh signed video URLs. Only search/import matches your account is authorized to view.
5. **Apps Script:** Open the native Google Sheet > **Extensions > Apps Script**. Create **two** script files named `Code.gs` and `Finder.gs`, using the corresponding files in `google_apps_script/`. Save, reload the Sheet and open the **VolleyReview** menu.
6. Choose **Configure backend** and enter the HTTPS API origin and the separate `SHEETS_INTEGRATION_KEY`. **Never** put a Supabase service-role key or DV Sport cookie in the Sheet.
7. Choose **Refresh all plays**, then **Enable automatic refresh and comments**. Check a few real video links, comments and ZIPs before expanding access.

The Google Drive connector can create the native spreadsheet, but it does not create a bound Apps Script project. That final Apps Script attachment is a one-time Google Sheets editor step unless a dedicated Apps Script deployment capability is available.

### Server environment variables

| Variable | Purpose |
| --- | --- |
| `SUPABASE_URL` | Existing project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Server only; never in Sheets |
| `SHEETS_INTEGRATION_KEY` | Separate random integration API key, stored in Apps Script properties |
| `DOWNLOAD_SIGNING_SECRET` | Different random secret for time-limited ZIP links |
| `PUBLIC_BASE_URL` | Public HTTPS URL of the backend |
| `DVSPORT_COOKIE` | Authenticated FilmRoom cookie, server only |
| `ALLOWED_MEDIA_HOSTS` | Comma-separated actual DV Sport video hosts; do not allow arbitrary URLs |
| `DOWNLOAD_LINK_TTL_DAYS` | Optional; default 7 days, max 30 |
| `MAX_ZIP_TOTAL_MB` | Optional source video size limit; default 1500MB |

Signed ZIP URLs are bearer URLs. Only share the Sheet with authorized reviewers. Signed camera URLs may expire and refresh when the API is synced.

### HTTP endpoints

All JSON endpoints require `X-Integration-Key`:
- `GET /api/v1/plays` — paged read of source play details and camera angles
- `GET /api/v1/comments` and `POST /api/v1/plays/{id}/comments`
- `GET /api/v1/dvsport/matches?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&conference=...&q=...`
- `GET /api/v1/dvsport/matches/{match_id}/plays`
- `POST /api/v1/dvsport/matches/{match_id}/plays/{play_number}/import`

The `GET /api/v1/plays/{id}/download?expires=...&sig=...` ZIP endpoint has time-limited HMAC authentication. It checks source media host allowlists, rejects private destinations and fails if no cameras download successfully. HLS `.m3u8` streams require a separate conversion workflow and are not packaged by this backend.

### Tests

```bash
cd integrations/google_sheets
python -m pip install -r backend/requirements.txt
python -m unittest discover -s tests -v
python -m compileall -q backend
# For both Google Apps Script files, copy to .js and run node --check
```

**Current status:** The native Sheet and GitHub integration code exist, but the comments migration is not verified as applied, the API has not been deployed, the Apps Script is not installed into the Sheet, and live DV Sport video behavior remains untested. Do not assume it is operational until those checks pass.
