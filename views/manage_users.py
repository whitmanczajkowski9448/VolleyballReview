import pandas as pd
import streamlit as st

from services.auth import (
    current_user,
    require_admin,
)
from services.admin_users import (
    create_app_user,
    list_app_users,
    set_user_password,
    update_app_user,
)
from services.ui import (
    render_page_header,
    render_section_label,
)


# ============================================================
# ACCESS CONTROL
# ============================================================

require_admin()


# ============================================================
# HEADER
# ============================================================

render_page_header(
    "Manage Users",
    (
        "Create and manage Viewer and Admin access "
        "without leaving VolleyReview."
    ),
)


# ============================================================
# CREATE USER
# ============================================================

render_section_label(
    "Create User"
)

with st.container(
    border=True
):
    st.caption(
        (
            "Create a Supabase login and assign its "
            "VolleyReview role in one step."
        )
    )

    with st.form(
        "create_volleyreview_user",
        clear_on_submit=True,
    ):
        email = st.text_input(
            "Email",
            placeholder=(
                "name@example.com"
            ),
        )

        password = st.text_input(
            "Temporary / Initial Password",
            type="password",
            help=(
                "Minimum 8 characters. Give this password "
                "to the user securely."
            ),
        )

        role = st.segmented_control(
            "Role",
            options=[
                "Viewer",
                "Admin",
            ],
            default="Viewer",
            selection_mode="single",
        )

        create_clicked = (
            st.form_submit_button(
                "Create User",
                type="primary",
                use_container_width=True,
            )
        )

    if create_clicked:
        selected_role = (
            str(
                role
                or "Viewer"
            )
            .strip()
            .lower()
        )

        with st.spinner(
            "Creating user..."
        ):
            ok, result = (
                create_app_user(
                    email=email,
                    password=password,
                    role=selected_role,
                )
            )

        if ok:
            st.success(
                (
                    f"Created {result['email']} "
                    f"as {result['role'].title()}."
                )
            )

            st.rerun()

        else:
            st.error(
                (
                    "User creation failed: "
                    f"{result}"
                )
            )


# ============================================================
# EXISTING USERS
# ============================================================

render_section_label(
    "Existing Users"
)

try:
    users = list_app_users()

except Exception as exc:
    st.error(
        (
            "Could not load users. Check that "
            "SUPABASE_SERVICE_ROLE_KEY is present "
            "in Streamlit secrets."
        )
    )

    st.exception(exc)
    st.stop()


if not users:
    st.info(
        "No users are currently listed in app_users."
    )

else:
    user_df = pd.DataFrame(
        users
    )

    display_df = user_df[
        [
            "email",
            "role",
            "active",
            "created_at",
        ]
    ].copy()

    display_df.columns = [
        "Email",
        "Role",
        "Active",
        "Created",
    ]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        (
            f"{len(users):,} authorized user"
            f"{'' if len(users) == 1 else 's'}"
        )
    )


# ============================================================
# EDIT ACCESS
# ============================================================

if users:
    st.divider()

    render_section_label(
        "Change User Access"
    )

    current = current_user()

    user_lookup = {
        user["user_id"]:
            user
        for user in users
    }

    selected_user_id = st.selectbox(
        "User",
        options=list(
            user_lookup.keys()
        ),
        format_func=lambda uid: (
            user_lookup[
                uid
            ].get(
                "email",
                uid,
            )
        ),
        key="manage_user_selection",
    )

    selected_user = user_lookup[
        selected_user_id
    ]

    edit1, edit2 = st.columns(2)

    with edit1:
        edited_role = st.selectbox(
            "Role",
            options=[
                "viewer",
                "admin",
            ],
            index=(
                1
                if selected_user.get(
                    "role"
                )
                == "admin"
                else 0
            ),
            format_func=lambda value:
                value.title(),
            key=(
                "manage_user_role_"
                f"{selected_user_id}"
            ),
        )

    with edit2:
        edited_active = st.checkbox(
            "Account Enabled",
            value=bool(
                selected_user.get(
                    "active",
                    True,
                )
            ),
            key=(
                "manage_user_active_"
                f"{selected_user_id}"
            ),
        )

    is_self = bool(
        current
        and str(
            current.get(
                "user_id"
            )
        )
        == str(
            selected_user_id
        )
    )

    if is_self:
        st.info(
            (
                "This is your current account. The app prevents "
                "you from disabling yourself or changing your "
                "own role from Admin here."
            )
        )

    save_access = st.button(
        "Save Access Changes",
        type="primary",
        use_container_width=True,
        disabled=(
            is_self
            and (
                edited_role
                != "admin"
                or not edited_active
            )
        ),
        key="save_access_changes",
    )

    if save_access:
        try:
            update_app_user(
                user_id=selected_user_id,
                role=edited_role,
                active=edited_active,
            )

            st.success(
                "User access updated."
            )

            st.rerun()

        except Exception as exc:
            st.error(
                "Could not update user access."
            )
            st.exception(exc)


# ============================================================
# PASSWORD
# ============================================================

if users:
    st.divider()

    render_section_label(
        "Set User Password"
    )

    st.caption(
        (
            "Use this only when you need to assign a new "
            "password directly. Passwords are never displayed "
            "or stored by VolleyReview."
        )
    )

    password_user_id = st.selectbox(
        "User to Update",
        options=list(
            user_lookup.keys()
        ),
        format_func=lambda uid: (
            user_lookup[
                uid
            ].get(
                "email",
                uid,
            )
        ),
        key="password_user_selection",
    )

    new_password = st.text_input(
        "New Password",
        type="password",
        key="admin_new_user_password",
    )

    confirm_password = st.text_input(
        "Confirm New Password",
        type="password",
        key="admin_confirm_user_password",
    )

    set_password_clicked = st.button(
        "Set New Password",
        use_container_width=True,
        key="set_user_password",
    )

    if set_password_clicked:
        if not new_password:
            st.error(
                "Enter a new password."
            )

        elif (
            new_password
            != confirm_password
        ):
            st.error(
                "The two password entries do not match."
            )

        else:
            ok, error = set_user_password(
                password_user_id,
                new_password,
            )

            if ok:
                st.success(
                    "Password updated."
                )

                st.session_state[
                    "admin_new_user_password"
                ] = ""

                st.session_state[
                    "admin_confirm_user_password"
                ] = ""

            else:
                st.error(
                    (
                        "Password update failed: "
                        f"{error}"
                    )
                )
