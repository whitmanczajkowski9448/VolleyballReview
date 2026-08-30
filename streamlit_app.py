import streamlit as st

from services.ui import (
    inject_global_css,
    render_sidebar_brand,
    render_sidebar_footer,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="NCAA WVB Review",
    page_icon="🏐",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# GLOBAL DESIGN SYSTEM
# ============================================================

inject_global_css()

render_sidebar_brand()


# ============================================================
# NAVIGATION
# ============================================================

dashboard_page = st.Page(
    "views/dashboard.py",
    title="Dashboard",
    icon=":material/space_dashboard:",
    default=True,
)


viewer_page = st.Page(
    "views/viewer.py",
    title="View Plays",
    icon=":material/slideshow:",
)


editor_page = st.Page(
    "views/editor.py",
    title="Tag / Edit",
    icon=":material/tune:",
)


weekly_report_page = st.Page(
    "views/weekly_report.py",
    title="Weekly Report",
    icon=":material/analytics:",
)


dvsport_sync_page = st.Page(
    "views/dvsport_sync.py",
    title="DV Sport Sync",
    icon=":material/sync:",
)


navigation = st.navigation(
    {
        "REVIEW CENTER": [
            dashboard_page,
            viewer_page,
            editor_page,
        ],

        "REPORTING": [
            weekly_report_page,
        ],

        "SYSTEM": [
            dvsport_sync_page,
        ],
    }
)


render_sidebar_footer()

navigation.run()
