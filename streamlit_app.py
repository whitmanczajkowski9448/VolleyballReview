import streamlit as st

from services.auth import (
    refresh_auth_state,
    render_login,
    sign_out,
)
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


# ============================================================
# AUTHENTICATION
# ============================================================

auth_user = refresh_auth_state()

if auth_user is None:
    render_login()
    st.stop()


role = auth_user[
    "role"
]


render_sidebar_brand()


# ============================================================
# PAGES AVAILABLE TO EVERY AUTHORIZED USER
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


weekly_report_page = st.Page(
    "views/weekly_report.py",
    title="Weekly Report",
    icon=":material/analytics:",
)


navigation_groups = {
    "REVIEW CENTER": [
        dashboard_page,
        viewer_page,
    ],
}


# ============================================================
# ADMIN-ONLY PAGES
# ============================================================

if role == "admin":
    editor_page = st.Page(
        "views/editor.py",
        title="Tag / Edit",
        icon=":material/tune:",
    )

    dvsport_sync_page = st.Page(
        "views/dvsport_sync.py",
        title="DV Sport Sync",
        icon=":material/sync:",
    )

    navigation_groups[
        "REVIEW CENTER"
    ].append(
        editor_page
    )

    navigation_groups[
        "REPORTING"
    ] = [
        weekly_report_page,
    ]

    navigation_groups[
        "SYSTEM"
    ] = [
        dvsport_sync_page,
    ]


navigation = st.navigation(
    navigation_groups
)


# ============================================================
# SIGNED-IN USER / LOGOUT
# ============================================================

with st.sidebar:
    st.divider()

    role_label = (
        "Admin"
        if role == "admin"
        else "Viewer"
    )

    st.caption(
        (
            f"Signed in as "
            f"{auth_user.get('email', '')}"
        )
    )

    st.caption(
        f"Access: {role_label}"
    )

    if st.button(
        "Log Out",
        use_container_width=True,
        key="volleyreview_logout",
    ):
        sign_out()
        st.rerun()


render_sidebar_footer()

navigation.run()
