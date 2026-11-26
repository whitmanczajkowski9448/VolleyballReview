import streamlit as st

from services.auth import refresh_auth_state
from services.database import database_path
from services.ui import (
    inject_global_css,
    render_sidebar_brand,
    render_sidebar_footer,
)


st.set_page_config(
    page_title="NCAA WVB Review",
    page_icon="🏐",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_global_css()


auth_user = refresh_auth_state()
role = auth_user['role']

render_sidebar_brand()


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

coordinator_report_page = st.Page(
    "views/weekly_report.py",
    title="Coordinator Report",
    icon=":material/analytics:",
)

navigation_groups = {
    "REVIEW CENTER": [
        dashboard_page,
        viewer_page,
    ],
}

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

    navigation_groups["REVIEW CENTER"].append(editor_page)
    navigation_groups["REPORTING"] = [coordinator_report_page]
    navigation_groups["SYSTEM"] = [dvsport_sync_page]

navigation = st.navigation(navigation_groups)

with st.sidebar:
    st.divider()
    st.caption('Local owner • SQLite')
    st.caption(str(database_path()))
    st.caption('Public sharing is disabled in local mode.')

render_sidebar_footer()
navigation.run()
