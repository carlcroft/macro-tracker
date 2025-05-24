import os
import streamlit as st
from supabase import create_client, Client
from streamlit.runtime.secrets import StreamlitSecretNotFoundError

@st.cache_resource
def get_supabase_client() -> Client:
    # 1) Try environment variables first
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    # 2) Only if they’re not set, try st.secrets (i.e. a local secrets.toml)
    if not url or not key:
        try:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
        except StreamlitSecretNotFoundError:
            pass

    # 3) If still missing, fail with a clear message
    if not url or not key:
        raise RuntimeError(
            "Supabase credentials not found!  \n"
            "• For local dev: export SUPABASE_URL and SUPABASE_KEY in your shell  \n"
            "• On Render: set them under Service → Environment → Environment Variables"
        )

    return create_client(url, key)

supabase: Client = get_supabase_client()