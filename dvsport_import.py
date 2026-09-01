"""
Standalone DV Sport -> VolleyReview sync.

IMPORTANT:
This file intentionally contains NO separate DV Sport parsing logic.
It calls services.dvsport_sync.run_dvsport_sync so the Streamlit app and
command-line importer always use the exact same Challenge/POI/Fault,
FULL GAME enrichment, duplicate prevention, metadata, and video-angle logic.
"""

import argparse
import os
from datetime import datetime
from getpass import getpass
from pathlib import Path

from supabase import create_client

from services.dvsport_sync import (
    DEFAULT_END_DATE,
    DEFAULT_START_DATE,
    run_dvsport_sync,
)

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib


PROJECT_DIR = Path(__file__).resolve().parent
SECRETS_FILE = PROJECT_DIR / ".streamlit" / "secrets.toml"


def load_secrets():
    if not SECRETS_FILE.exists():
        return {}

    with SECRETS_FILE.open("rb") as file:
        return tomllib.load(file)


def get_supabase_client(secrets):
    url = str(
        os.environ.get("SUPABASE_URL")
        or secrets.get("SUPABASE_URL")
        or ""
    ).strip()

    key = str(
        os.environ.get("SUPABASE_KEY")
        or secrets.get("SUPABASE_KEY")
        or ""
    ).strip()

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be available in "
            ".streamlit/secrets.toml or environment variables."
        )

    return create_client(url, key)


def get_dvsport_cookie(secrets):
    cookie = str(
        os.environ.get("DVSPORT_COOKIE")
        or secrets.get("DVSPORT_COOKIE")
        or ""
    ).strip()

    if cookie:
        return cookie

    print(
        "DVSPORT_COOKIE was not found in .streamlit/secrets.toml or the "
        "environment. Paste ONLY the Cookie request-header value below."
    )
    cookie = getpass("DV Sport Cookie (hidden): ").strip()

    if not cookie:
        raise RuntimeError("No DV Sport cookie was provided.")

    return cookie


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Dates must use YYYY-MM-DD format."
        ) from exc


def print_progress(event):
    fraction = float(event.get("fraction", 0) or 0)
    percent = int(round(fraction * 100))
    stage = str(event.get("stage") or "Working")
    message = str(event.get("message") or "")

    print(f"[{percent:3d}%] {stage}: {message}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Sync Challenges, POIs, and Faults using the same standardized "
            "FULL GAME enrichment logic as VolleyReview."
        )
    )
    parser.add_argument(
        "--start",
        type=parse_date,
        default=DEFAULT_START_DATE,
        help=f"Start date YYYY-MM-DD (default {DEFAULT_START_DATE})",
    )
    parser.add_argument(
        "--end",
        type=parse_date,
        default=DEFAULT_END_DATE,
        help=f"End date YYYY-MM-DD (default {DEFAULT_END_DATE})",
    )
    args = parser.parse_args()

    secrets = load_secrets()
    supabase = get_supabase_client(secrets)
    cookie = get_dvsport_cookie(secrets)

    print("=" * 72)
    print("VOLLEYREVIEW DV SPORT STANDARDIZED FULL GAME SYNC")
    print("=" * 72)
    print(f"Date range: {args.start} through {args.end}")
    print("Types:      Challenges + POIs + Faults")
    print("Media:      FULL GAME checked for every imported play")
    print()

    result = run_dvsport_sync(
        supabase,
        cookie,
        start_date=args.start,
        end_date=args.end,
        progress_callback=print_progress,
    )

    print("\n" + "=" * 72)
    print("SYNC COMPLETE")
    print("=" * 72)
    print(f"Challenges:              {int(result.get('challenges_found', 0)):,}")
    print(f"POIs:                    {int(result.get('pois_found', 0)):,}")
    print(f"Faults:                  {int(result.get('faults_found', 0)):,}")
    print(f"New plays:               {int(result.get('plays_inserted', 0)):,}")
    print(f"Updated plays:           {int(result.get('plays_updated', 0)):,}")
    print(f"Video clips attached:    {int(result.get('video_clips_attached', 0)):,}")
    print(f"Full-game plays checked: {int(result.get('full_game_plays_checked', 0)):,}")
    print(f"Full-game plays matched: {int(result.get('full_game_plays_matched', 0)):,}")
    print(f"Full-game angles found:  {int(result.get('full_game_angles_found', 0)):,}")
    print(f"Playlist missing:        {int(result.get('full_game_playlist_missing', 0)):,}")
    print(f"PLAY # missing:          {int(result.get('full_game_play_number_missing', 0)):,}")
    print(f"PLAY not in full game:   {int(result.get('full_game_play_missing', 0)):,}")
    print(f"Matched with 0 angles:   {int(result.get('full_game_zero_angle_plays', 0)):,}")
    print(f"Errors:                  {len(result.get('errors', []) or []):,}")
    print(f"Elapsed:                 {float(result.get('elapsed_seconds', 0)):.1f}s")

    errors = result.get("errors", []) or []
    if errors:
        print("\nErrors:")
        for error in errors[:25]:
            print(
                f"- {error.get('type', 'Unknown')} | "
                f"{error.get('conference', '')} | "
                f"{error.get('title', '')}\n"
                f"  {error.get('error', '')}"
            )

        if len(errors) > 25:
            print(f"...and {len(errors) - 25:,} more error(s).")


if __name__ == "__main__":
    main()
