"""Single-owner mode, only when Streamlit is bound to loopback."""
import streamlit as st


def require_local_server():
    if st.get_option("server.address") not in {"127.0.0.1", "::1", "localhost"}:
        st.error("Local mode requires a loopback server address. Use launch_local.bat.")
        st.stop()


def current_user():
    require_local_server()
    return {"user_id": "local-owner", "email": "Local owner", "role": "admin"}


def refresh_auth_state():
    return current_user()


def is_admin():
    return current_user()["role"] == "admin"


def require_login():
    return current_user()


def require_admin():
    return current_user()
