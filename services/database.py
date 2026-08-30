import streamlit as st
from supabase import create_client


@st.cache_resource
def get_supabase():
    """
    Return the shared Supabase client using Streamlit secrets.

    Required .streamlit/secrets.toml values:
        SUPABASE_URL
        SUPABASE_KEY
    """
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]

    return create_client(
        url,
        key,
    )
