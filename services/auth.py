from pathlib import Path

import streamlit as st
from supabase import create_client


VALID_ROLES = {
    "viewer",
    "admin",
}


def _new_client():
    """
    Create a fresh Supabase client for this Streamlit session/rerun.

    Do not cache an authenticated Supabase client globally. Streamlit
    resource caches are shared across users, which is not appropriate
    for per-user authentication sessions.
    """
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


def _clear_auth_state():
    for key in [
        "auth_access_token",
        "auth_refresh_token",
        "auth_user_id",
        "auth_email",
        "auth_role",
    ]:
        st.session_state.pop(
            key,
            None,
        )


def _store_session(
    session,
    user,
):
    if session is None or user is None:
        raise ValueError(
            "Supabase did not return a valid login session."
        )

    st.session_state[
        "auth_access_token"
    ] = session.access_token

    st.session_state[
        "auth_refresh_token"
    ] = session.refresh_token

    st.session_state[
        "auth_user_id"
    ] = str(
        user.id
    )

    st.session_state[
        "auth_email"
    ] = (
        user.email
        or ""
    )


def get_authenticated_client():
    """
    Return a client carrying the currently signed-in user's JWT.

    set_session() refreshes an expired access token when a valid
    refresh token is available.
    """
    access_token = st.session_state.get(
        "auth_access_token"
    )

    refresh_token = st.session_state.get(
        "auth_refresh_token"
    )

    if (
        not access_token
        or not refresh_token
    ):
        return None

    client = _new_client()

    try:
        response = client.auth.set_session(
            access_token,
            refresh_token,
        )

        refreshed_session = getattr(
            response,
            "session",
            None,
        )

        refreshed_user = getattr(
            response,
            "user",
            None,
        )

        if refreshed_session is not None:
            st.session_state[
                "auth_access_token"
            ] = refreshed_session.access_token

            st.session_state[
                "auth_refresh_token"
            ] = refreshed_session.refresh_token

        if refreshed_user is not None:
            st.session_state[
                "auth_user_id"
            ] = str(
                refreshed_user.id
            )

            st.session_state[
                "auth_email"
            ] = (
                refreshed_user.email
                or ""
            )

        return client

    except Exception:
        _clear_auth_state()
        return None


def _load_role(
    client,
    user_id,
):
    """
    Read this user's app role through authenticated RLS.
    """
    response = (
        client
        .table("app_users")
        .select(
            "user_id,email,role,active"
        )
        .eq(
            "user_id",
            user_id,
        )
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        return None

    row = rows[0]

    if not row.get(
        "active",
        True,
    ):
        return None

    role = str(
        row.get(
            "role",
            "",
        )
    ).strip().lower()

    if role not in VALID_ROLES:
        return None

    return {
        "user_id":
            str(
                row.get(
                    "user_id"
                )
            ),
        "email":
            row.get(
                "email"
            )
            or "",
        "role":
            role,
        "active":
            True,
    }


def sign_in(
    email,
    password,
):
    email = str(
        email
        or ""
    ).strip()

    password = str(
        password
        or ""
    )

    if not email or not password:
        return (
            False,
            "Enter your email and password.",
        )

    client = _new_client()

    try:
        response = (
            client
            .auth
            .sign_in_with_password(
                {
                    "email": email,
                    "password": password,
                }
            )
        )

        session = getattr(
            response,
            "session",
            None,
        )

        user = getattr(
            response,
            "user",
            None,
        )

        if session is None or user is None:
            return (
                False,
                "Login failed. Check your email and password.",
            )

        profile = _load_role(
            client,
            str(
                user.id
            ),
        )

        if profile is None:
            try:
                client.auth.sign_out()
            except Exception:
                pass

            _clear_auth_state()

            return (
                False,
                (
                    "Your login is valid, but this account has not "
                    "been granted access to VolleyReview."
                ),
            )

        _store_session(
            session,
            user,
        )

        st.session_state[
            "auth_role"
        ] = profile[
            "role"
        ]

        return (
            True,
            None,
        )

    except Exception:
        _clear_auth_state()

        return (
            False,
            "Login failed. Check your email and password.",
        )


def refresh_auth_state():
    """
    Validate the saved session and refresh the current role.

    The role is read from app_users on each app rerun. This means
    an administrator can change a user's role in Supabase and the
    new permissions are picked up without encoding the role into
    user-editable metadata.
    """
    client = get_authenticated_client()

    if client is None:
        return None

    try:
        user_response = (
            client.auth.get_user()
        )

        user = getattr(
            user_response,
            "user",
            None,
        )

        if user is None:
            _clear_auth_state()
            return None

        profile = _load_role(
            client,
            str(
                user.id
            ),
        )

        if profile is None:
            _clear_auth_state()
            return None

        st.session_state[
            "auth_user_id"
        ] = str(
            user.id
        )

        st.session_state[
            "auth_email"
        ] = (
            user.email
            or profile.get(
                "email",
                "",
            )
        )

        st.session_state[
            "auth_role"
        ] = profile[
            "role"
        ]

        return {
            "user_id":
                st.session_state[
                    "auth_user_id"
                ],
            "email":
                st.session_state[
                    "auth_email"
                ],
            "role":
                st.session_state[
                    "auth_role"
                ],
        }

    except Exception:
        _clear_auth_state()
        return None


def current_user():
    user_id = st.session_state.get(
        "auth_user_id"
    )

    role = st.session_state.get(
        "auth_role"
    )

    if (
        not user_id
        or role not in VALID_ROLES
    ):
        return None

    return {
        "user_id":
            user_id,
        "email":
            st.session_state.get(
                "auth_email",
                "",
            ),
        "role":
            role,
    }


def is_admin():
    user = current_user()

    return bool(
        user
        and user.get(
            "role"
        )
        == "admin"
    )


def require_login():
    user = current_user()

    if user is None:
        st.error(
            "You must sign in to access this page."
        )
        st.stop()

    return user


def require_admin():
    user = require_login()

    if user.get(
        "role"
    ) != "admin":
        st.error(
            "Administrator access is required for this page."
        )
        st.stop()

    return user


def sign_out():
    client = get_authenticated_client()

    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass

    _clear_auth_state()


def render_login():
    """
    Render the signed-out login screen.
    """
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            display: none !important;
        }

        [data-testid="stMainBlockContainer"] {
            max-width: 760px;
            padding-top: 7rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    app_root = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    logo_path = (
        app_root
        / "assets"
        / "ncaa-wvblogo.png"
    )

    logo_left, logo_center, logo_right = st.columns(
        [
            1.0,
            1.6,
            1.0,
        ]
    )

    with logo_center:
        if logo_path.exists():
            st.image(
                str(
                    logo_path
                ),
                use_container_width=True,
            )

    st.markdown(
        """
        <div style="
            text-align:center;
            margin-top:0.4rem;
            margin-bottom:0.25rem;
        ">
            <div style="
                font-size:2rem;
                font-weight:800;
                letter-spacing:-0.03em;
            ">
                NCAA Women's Volleyball Review
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style="
            text-align:center;
            color:#9CB0C8;
            margin-bottom:1.4rem;
        ">
            Authorized access only
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(
        border=True
    ):
        st.markdown(
            "### Sign In"
        )

        with st.form(
            "volleyreview_login",
            clear_on_submit=False,
        ):
            email = st.text_input(
                "Email",
                autocomplete="email",
            )

            password = st.text_input(
                "Password",
                type="password",
                autocomplete="current-password",
            )

            submitted = st.form_submit_button(
                "Sign In",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            with st.spinner(
                "Signing in..."
            ):
                ok, error = sign_in(
                    email,
                    password,
                )

            if ok:
                st.rerun()

            st.error(
                error
                or "Login failed."
            )
