import hashlib

import streamlit as st

from services.auth import (
    refresh_auth_state,
    render_login,
    sign_out,
)
from services.public_share import render_public_challenge
from services.dvsport_sync import validate_dvsport_cookie
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


# A signed challenge URL is intentionally available without login. The token
# grants read-only access to one Challenge record only.
public_challenge_token = str(
    st.query_params.get("challenge", "")
    or ""
).strip()

if public_challenge_token:
    render_public_challenge(public_challenge_token)
    st.stop()


auth_user = refresh_auth_state()

if auth_user is None:
    render_login()
    st.stop()

role = auth_user["role"]


def current_dvsport_cookie():
    return str(
        st.session_state.get("dvsport_cookie_override")
        or st.secrets.get("DVSPORT_COOKIE", "")
        or ""
    ).strip()


def refresh_dvsport_cookie_status(force=False):
    cookie = current_dvsport_cookie()
    fingerprint = hashlib.sha256(cookie.encode("utf-8")).hexdigest() if cookie else ""

    if (
        force
        or fingerprint != st.session_state.get("dvsport_cookie_fingerprint", "")
        or "dvsport_cookie_valid" not in st.session_state
    ):
        valid, error = validate_dvsport_cookie(cookie)
        st.session_state["dvsport_cookie_fingerprint"] = fingerprint
        st.session_state["dvsport_cookie_valid"] = bool(valid)
        st.session_state["dvsport_cookie_error"] = error

    return bool(st.session_state.get("dvsport_cookie_valid", False))


@st.dialog("DV Sport Connection", width="small")
def dvsport_cookie_prompt():
    st.error("The saved DV Sport cookie is missing or expired.")
    replacement = st.text_input(
        "DV Sport Cookie",
        type="password",
        key="startup_dvsport_cookie",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Dismiss", use_container_width=True):
            st.rerun()
    with c2:
        if st.button("Validate & Use", type="primary", use_container_width=True):
            candidate = replacement.strip()
            valid, error = validate_dvsport_cookie(candidate)
            if valid:
                st.session_state["dvsport_cookie_override"] = candidate
                st.session_state.pop("dvsport_cookie_fingerprint", None)
                st.session_state["dvsport_cookie_valid"] = True
                st.session_state["dvsport_cookie_error"] = ""
                st.toast("DV Sport connected.", icon="✅")
                st.rerun()
            else:
                st.error(error or "That DV Sport cookie is not valid.")


if role == "admin":
    cookie_valid = refresh_dvsport_cookie_status()
    if not cookie_valid and not st.session_state.get("dvsport_cookie_prompted", False):
        st.session_state["dvsport_cookie_prompted"] = True
        dvsport_cookie_prompt()

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

    manage_users_page = st.Page(
        "views/manage_users.py",
        title="Manage Users",
        icon=":material/manage_accounts:",
    )

    navigation_groups["REVIEW CENTER"].append(editor_page)
    navigation_groups["REPORTING"] = [coordinator_report_page]
    navigation_groups["SYSTEM"] = [dvsport_sync_page, manage_users_page]

navigation = st.navigation(navigation_groups)

with st.sidebar:
    st.divider()
    role_label = "Admin" if role == "admin" else "Viewer"
    st.caption(f"Signed in as {auth_user.get('email', '')}")
    st.caption(f"Access: {role_label}")

    if st.button(
        "Log Out",
        use_container_width=True,
        key="volleyreview_logout",
    ):
        sign_out()
        st.rerun()

render_sidebar_footer()
navigation.run()
