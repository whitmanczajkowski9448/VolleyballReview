from datetime import date

import streamlit as st

from services.database import get_supabase
from services.auth import require_admin
from services.dvsport_sync import (
    DEFAULT_END_DATE,
    DEFAULT_START_DATE,
    SEASON_END_DATE,
    SEASON_START_DATE,
    TARGET_CONFERENCES,
    YEAR,
    run_dvsport_sync,
)
from services.ui import (
    render_page_header,
    render_section_label,
)


# ============================================================
# HEADER
# ============================================================

require_admin()

render_page_header(
    "DV Sport Sync",
    (
        "Pull all 2026 challenges, plays of interest, and FAULTS from "
        "DV Sport and safely refresh the review database."
    ),
    eyebrow="NCAA WVB • DATA CONNECTION",
)

supabase = get_supabase()

cookie_configured = bool(
    str(
        st.secrets.get(
            "DVSPORT_COOKIE",
            "",
        )
    ).strip()
)


# ============================================================
# CONNECTION
# ============================================================

render_section_label(
    "Connection"
)

with st.container(
    border=True
):
    c1, c2, c3, c4 = st.columns(
        4
    )

    with c1:
        st.metric(
            "Season",
            YEAR,
        )

    with c2:
        st.metric(
            "Conferences",
            len(
                TARGET_CONFERENCES
            ),
        )

    with c3:
        st.metric(
            "Import Types",
            "3",
            "Challenges + POIs + FAULTS",
            delta_color="off",
        )

    with c4:
        st.metric(
            "DV Sport Cookie",
            (
                "Ready"
                if cookie_configured
                else "Missing"
            ),
        )

    st.caption(
        "Current scope: Big Ten • MVC • MAC • "
        "ALL Challenges • ALL Plays of Interest • ALL FAULTS"
    )

    if cookie_configured:
        st.success(
            "DVSPORT_COOKIE is configured."
        )
    else:
        st.error(
            "DVSPORT_COOKIE is missing from "
            ".streamlit/secrets.toml."
        )


# ============================================================
# DATE RANGE
# ============================================================

render_section_label(
    "Date Range"
)

with st.container(
    border=True
):
    date_col1, date_col2 = st.columns(
        2
    )

    with date_col1:
        sync_start_date = st.date_input(
            "Start Date",
            value=DEFAULT_START_DATE,
            min_value=SEASON_START_DATE,
            max_value=SEASON_END_DATE,
            format="MM/DD/YYYY",
            key="dvsport_sync_start_date",
        )

    with date_col2:
        sync_end_date = st.date_input(
            "End Date",
            value=DEFAULT_END_DATE,
            min_value=SEASON_START_DATE,
            max_value=SEASON_END_DATE,
            format="MM/DD/YYYY",
            key="dvsport_sync_end_date",
        )

    date_range_valid = (
        sync_start_date
        <= sync_end_date
    )

    if date_range_valid:
        inclusive_days = (
            sync_end_date
            - sync_start_date
        ).days + 1

        st.success(
            (
                f"Sync window: {sync_start_date:%B %d, %Y} "
                f"through {sync_end_date:%B %d, %Y} "
                f"({inclusive_days:,} day"
                f"{'s' if inclusive_days != 1 else ''})."
            )
        )
    else:
        st.error(
            "Start Date must be on or before End Date."
        )

    st.caption(
        (
            "The selected dates are inclusive and apply to both "
            "Challenges and POIs. Existing database records outside "
            "this range are not deleted or changed."
        )
    )


# ============================================================
# EXPLANATION
# ============================================================

render_section_label(
    "What This Sync Does"
)

st.info(
    (
        "Challenges are pulled from each conference's "
        "REVIEWS / REVIEWS BY GAME library. POIs are pulled "
        "from each conference's POI library. FAULTS are pulled "
        "from each conference's FAULT or FAULTS library using the "
        "same combined-playlist / individual-play fallback pattern. "
        "Existing reviewer work, NCAA classifications, favorites, "
        "and notes are preserved."
    )
)


# ============================================================
# RUN
# ============================================================

run_sync = st.button(
    "Pull Challenges + POIs + FAULTS for Selected Dates",
    type="primary",
    use_container_width=True,
    disabled=(
        not cookie_configured
        or not date_range_valid
    ),
)


if run_sync:
    cookie_header = str(
        st.secrets[
            "DVSPORT_COOKIE"
        ]
    ).strip()

    result_holder = {}

    with st.status(
        "Starting full DV Sport sync...",
        expanded=True,
    ) as sync_status:

        progress_bar = st.progress(
            0,
            text="Preparing...",
        )

        stage_placeholder = st.empty()
        detail_placeholder = st.empty()
        counts_placeholder = st.empty()

        def handle_progress(event):
            fraction = float(
                event.get(
                    "fraction",
                    0,
                )
            )

            percent = int(
                round(
                    fraction * 100
                )
            )

            progress_bar.progress(
                percent,
                text=(
                    f"{percent}% complete"
                ),
            )

            stage_placeholder.markdown(
                f"**{event.get('stage', 'Working...')}**"
            )

            detail_placeholder.caption(
                event.get(
                    "message",
                    "",
                )
            )

            challenges = event.get(
                "challenges_found"
            )

            pois = event.get(
                "pois_found"
            )

            faults = event.get(
                "faults_found"
            )

            inserted = event.get(
                "plays_inserted"
            )

            updated = event.get(
                "plays_updated"
            )

            current = event.get(
                "current_item"
            )

            total = event.get(
                "total_items"
            )

            parts = []

            if (
                current is not None
                and total
            ):
                parts.append(
                    f"Item {current:,} / {total:,}"
                )

            if challenges is not None:
                parts.append(
                    f"Challenges: {challenges:,}"
                )

            if pois is not None:
                parts.append(
                    f"POIs: {pois:,}"
                )

            if inserted is not None:
                parts.append(
                    f"New: {inserted:,}"
                )

            if updated is not None:
                parts.append(
                    f"Refreshed: {updated:,}"
                )

            if parts:
                counts_placeholder.caption(
                    "  •  ".join(parts)
                )

        try:
            result = run_dvsport_sync(
                supabase,
                cookie_header,
                start_date=sync_start_date,
                end_date=sync_end_date,
                progress_callback=
                    handle_progress,
            )

            result_holder["result"] = (
                result
            )

            progress_bar.progress(
                100,
                text="100% complete",
            )

            sync_status.update(
                label=(
                    "DV Sport challenges + POIs sync complete"
                ),
                state="complete",
                expanded=True,
            )

            st.toast(
                "DV Sport sync complete.",
                icon="✅",
            )

        except Exception as exc:
            sync_status.update(
                label="DV Sport sync failed",
                state="error",
                expanded=True,
            )

            st.error(
                "The DV Sport update did not complete."
            )

            st.exception(exc)


    # ========================================================
    # RESULTS
    # ========================================================

    result = result_holder.get(
        "result"
    )

    if result:
        st.write("")

        render_section_label(
            "Sync Results"
        )

        st.caption(
            (
                f"Imported date window: "
                f"{sync_start_date:%B %d, %Y} through "
                f"{sync_end_date:%B %d, %Y}"
            )
        )

        r1, r2, r3, r4 = st.columns(
            4
        )

        with r1:
            st.metric(
                "Challenges",
                f"{result['challenges_found']:,}",
            )

        with r2:
            st.metric(
                "POIs",
                f"{result['pois_found']:,}",
            )

        with r3:
            st.metric(
                "New Plays",
                f"{result['plays_inserted']:,}",
            )

        with r4:
            st.metric(
                "Refreshed Plays",
                f"{result['plays_updated']:,}",
            )

        r5, r6, r7, r8 = st.columns(
            4
        )

        with r5:
            st.metric(
                "Challenge Playlists",
                f"{result['challenge_playlists']:,}",
            )

        with r6:
            st.metric(
                "POI Match Groups",
                f"{result['poi_match_groups']:,}",
            )

        with r7:
            st.metric(
                "POI Combined",
                f"{result['poi_combined_groups']:,}",
                "Used combined POIS",
                delta_color="off",
            )

        with r8:
            st.metric(
                "POI Fallback",
                f"{result['poi_fallback_groups']:,}",
                "Used individual POIs",
                delta_color="off",
            )

        a1, a2, a3, a4 = st.columns(
            4
        )

        with a1:
            st.metric(
                "New Video Clips",
                f"{result['angles_inserted']:,}",
            )

        with a2:
            st.metric(
                "Updated Clips",
                f"{result['angles_updated']:,}",
            )

        with a3:
            st.metric(
                "Removed Stale Clips",
                f"{result['angles_deleted']:,}",
            )

        with a4:
            st.metric(
                "Elapsed",
                f"{result['elapsed_seconds']:.1f}s",
            )

        errors = (
            result["errors"]
        )

        if errors:
            st.warning(
                f"{len(errors):,} playlist error(s) occurred."
            )

            with st.expander(
                "Show Sync Errors"
            ):
                for error in errors:
                    st.write(
                        (
                            f"**{error['type']} | "
                            f"{error['conference']} | "
                            f"{error['title']}**"
                        )
                    )

                    st.code(
                        error["error"]
                    )

        else:
            st.success(
                "Full sync completed with no playlist errors."
            )
