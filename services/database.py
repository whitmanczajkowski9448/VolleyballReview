from services.auth import (
    get_authenticated_client,
)


def get_supabase():
    """
    Return the currently authenticated user's Supabase client.

    The previous cached/global client should not be used once
    user authentication is enabled because a cached client can
    be shared between Streamlit sessions.
    """
    client = get_authenticated_client()

    if client is None:
        raise RuntimeError(
            "No authenticated Supabase session is available."
        )

    return client
