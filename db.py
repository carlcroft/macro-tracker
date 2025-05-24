import os
import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def get_supabase_client() -> Client:
    # first try st.secrets if you ever supply a TOML,
    # otherwise read from the env vars you defined in Render
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Missing Supabase URL or Key. "
                           "Make sure you’ve set them in Render’s Environment Variables.")
    return create_client(url, key)

# elsewhere in db.py
supabase: Client = get_supabase_client()