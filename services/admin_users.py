import streamlit as st
from supabase import create_client


VALID_ROLES = {
    "viewer",
    "admin",
}


@st.cache_resource
def get_admin_supabase():
    """
    Server-side Supabase client using the service-role key.

    IMPORTANT:
    - Never expose this key in the UI.
    - Never place it in GitHub.
    - Store it only in Streamlit secrets.
    - Use this client only on admin-protected server-side operations.
    """
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets[
            "SUPABASE_SERVICE_ROLE_KEY"
        ],
    )


def normalize_email(value):
    return str(
        value
        or ""
    ).strip().lower()


def validate_role(role):
    role = str(
        role
        or ""
    ).strip().lower()

    if role not in VALID_ROLES:
        raise ValueError(
            "Role must be viewer or admin."
        )

    return role


def create_app_user(
    email,
    password,
    role,
):
    """
    Create:
      1. Supabase Auth user
      2. Matching public.app_users role row

    If role-row creation fails after the Auth user is created,
    this attempts to remove the just-created Auth user so the
    operation does not leave a half-configured account.
    """
    email = normalize_email(
        email
    )

    password = str(
        password
        or ""
    )

    role = validate_role(
        role
    )

    if not email:
        return (
            False,
            "Email is required.",
        )

    if "@" not in email:
        return (
            False,
            "Enter a valid email address.",
        )

    if len(password) < 8:
        return (
            False,
            "Password must be at least 8 characters.",
        )

    admin = get_admin_supabase()

    created_user_id = None

    try:
        auth_response = (
            admin.auth.admin.create_user(
                {
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                }
            )
        )

        user = getattr(
            auth_response,
            "user",
            None,
        )

        if user is None:
            return (
                False,
                "Supabase did not return the newly created user.",
            )

        created_user_id = str(
            user.id
        )

        admin.table(
            "app_users"
        ).upsert(
            {
                "user_id":
                    created_user_id,
                "email":
                    email,
                "role":
                    role,
                "active":
                    True,
            },
            on_conflict="user_id",
        ).execute()

        return (
            True,
            {
                "user_id":
                    created_user_id,
                "email":
                    email,
                "role":
                    role,
            },
        )

    except Exception as exc:
        if created_user_id:
            try:
                admin.auth.admin.delete_user(
                    created_user_id
                )
            except Exception:
                pass

        message = str(
            exc
        )

        if (
            "already"
            in message.lower()
            and "registered"
            in message.lower()
        ):
            message = (
                "A Supabase Auth account already exists "
                "for that email."
            )

        return (
            False,
            message,
        )


def list_app_users():
    admin = get_admin_supabase()

    response = (
        admin
        .table("app_users")
        .select(
            "user_id,email,role,active,created_at,updated_at"
        )
        .order(
            "email"
        )
        .execute()
    )

    return response.data or []


def update_app_user(
    user_id,
    role,
    active,
):
    role = validate_role(
        role
    )

    admin = get_admin_supabase()

    response = (
        admin
        .table("app_users")
        .update(
            {
                "role":
                    role,
                "active":
                    bool(
                        active
                    ),
            }
        )
        .eq(
            "user_id",
            str(
                user_id
            ),
        )
        .execute()
    )

    return response.data or []


def set_user_password(
    user_id,
    new_password,
):
    password = str(
        new_password
        or ""
    )

    if len(password) < 8:
        return (
            False,
            "Password must be at least 8 characters.",
        )

    admin = get_admin_supabase()

    try:
        admin.auth.admin.update_user_by_id(
            str(
                user_id
            ),
            {
                "password":
                    password,
            },
        )

        return (
            True,
            None,
        )

    except Exception as exc:
        return (
            False,
            str(
                exc
            ),
        )
