import streamlit as st
from db import supabase
from postgrest import APIError

@st.cache_data(ttl=300)
def fetch_goals(user_id: str) -> dict:
        res = supabase.table("macro_goals").select("*").eq("user_id", user_id).maybe_single().execute()
        
        if res is None:
            st.error("No response from Supabase when fetching macro goals.")
            return {}
        
        if hasattr(res,"error") and res.error:
            st.error(f"Supabase error: {res.errormessage}")
            return {}
        
        return res.data or {}

@st.cache_data(ttl=300)
def fetch_logs(user_id: str) -> list:
    try:       
        res = supabase.table("food_logs").select("*").eq("user_id", user_id).execute()
        return res.data or {}
    except APIError as e:
        st.error(f"Supabase error while fetching food logs: {e}")
    except Exception as e:
        st.error(f"Unexpected error while fetching food logs: {e}")
    return {}

@st.cache_data(ttl=300)
def fetch_recipes(user_id: str) -> list:
    try: 
        res = supabase.table("recipes").select("*").eq("user_id", user_id).execute()
        return res.data or {}
    except APIError as e:
        st.error(f"Supabase error while fetching recipes: {e}")
    except Exception as e:
        st.error(f"Unexpected error while fetching recipes: {e}")
    return {}