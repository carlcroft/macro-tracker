# ------------------------- Libraries -------------------------
import streamlit as st
st.set_page_config(
    page_title="Macro Tracker",
    layout="wide",
    initial_sidebar_state="expanded")
from db import supabase
from postgrest.exceptions import APIError
from data import fetch_goals, fetch_logs, fetch_recipes
from typing import Union, List, Dict
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import altair as alt
import plotly.express as px
from streamlit_option_menu import option_menu
from streamlit_lottie import st_lottie
import requests
import pytz
import uuid
# ------------------------- App Variables -------------------------
eastern = pytz.timezone("US/Eastern")
now = datetime.now(eastern)
version = 0.32

@st.cache_data
def load_lottie_url(url: str):
    r = requests.get(url)
    if r.status_code != 200:
        return None
    return r.json()



if "animation" not in st.session_state:
    st.session_state["animation"] = True

if "user_id" in st.session_state:
    st.session_state["animation"] = False

# 1) pick any Lottie JSON URL you like
lottie_url = "https://assets10.lottiefiles.com/packages/lf20_x62chJ.json"
anim = load_lottie_url(lottie_url)

# 2) display it (height in pixels)
if anim and st.session_state["animation"]:
    st.subheader("Welcome to Your Macro Dashboard. Enter your Username to continue.")
    st_lottie(
        anim,
        speed=1.0,      # 0.5 = half speed, 2.0 = double
        loop=True,
        quality="high",
        height=200,
        key="dashboard_lottie"
    )

# ------------------------- Functions -------------------------
# ______ 1. Upsert ______
def upsert(
        table: str, 
        records: Union[Dict, List[Dict]],
        success_msg: str = "Saved!"
):
    with st.spinner(f"Saving to {table}..."):
        try:
            res = supabase.table(table).upsert(records).execute()
        except APIError as e:
            st.error(f"Database error on upsert to '{table}':{e}")
            return None
    st.success(success_msg)
    return res.data

# ______ 2. Edit and Save Goals ______
def render_goal_editor(): 
    st.subheader("Set your macro goals")
    
    existing = st.session_state.get("macro_goals", {
        "calories": 2000,
        "protein": 150,
        "carbs": 250,
        "fat": 70
    })
    
    cal = st.number_input("Calories", min_value=0,value=existing["calories"])
    pro = st.number_input("Protein (g)", min_value=0,value=existing["protein"])
    carb = st.number_input("Carbs (g)", min_value=0,value=existing["carbs"])
    fat = st.number_input("Fat (g)", min_value=0,value=existing["fat"])

    if st.button("Save Goals"):
        new_goals = {
            "user_id": st.session_state["user_id"],
            "calories":cal,
            "protein": pro,
            "carbs": carb,
            "fat": fat
        }
        saved = upsert("macro_goals", new_goals, success_msg = "Goals saved!")
        if saved:
            st.session_state["macro_goals"] = new_goals
            st.session_state["editing_goals"] = False
            st.session_state["goals_saved"] = True

            st.rerun()
# ______ 2. Recipe Functions ______
def save_recipes(recipes_dict: dict[str, dict]):
    """
    recipes_dict: maps recipe_name → {foods, calories, protein, carbs, fat}
    Uses st.session_state['recipes_list'] (a list of full record-dicts with recipe_id)
    """

    user_id      = st.session_state["user_id"]
    existing_lst = st.session_state.get("recipes_list", [])

    # build a name → id map for convenience
    existing_map = {
        rec["recipe_name"]: rec["recipe_id"]
        for rec in existing_lst
    }

    # 1) Collect upserts
    to_upsert = []
    for name, data in recipes_dict.items():
        rec = {
            "user_id":      user_id,
            "recipe_name":  name,
            "foods":        data["foods"],
            "calories":     data["calories"],
            "protein":      data["protein"],
            "carbs":        data["carbs"],
            "fat":          data["fat"],
        }
        # if it already existed, include the PK so Supabase updates instead of inserting
        if name in existing_map:
            rec["recipe_id"] = existing_map[name]

        to_upsert.append(rec)    # ← correct usage, not `append = rec`

    # 2) Fire off the upsert
    if to_upsert:
        saved = upsert("recipes", to_upsert, success_msg="Recipes saved!")
        if not saved:
            return  # abort if upsert failed

    # 3) Delete any recipes the user removed
    removed = set(existing_map) - set(recipes_dict)
    for name in removed:
        rid = existing_map[name]
        with st.spinner(f"Deleting '{name}'…"):
            res = (
                supabase
                  .table("recipes")
                  .delete()
                  .eq("recipe_id", rid)
                  .execute()
            )
        if res.error:
            st.error(f"Couldn’t delete '{name}': {res.error.message}")

    # 4) Refresh your in-memory list of full records
    resp = (
        supabase
          .table("recipes")
          .select("recipe_id,recipe_name,foods,calories,protein,carbs,fat")
          .eq("user_id", user_id)
          .execute()
    )

    st.session_state["recipes_list"] = resp.data or []
    st.success("Recipes synced!")

# ______ 3. Food Log Functions______
FOOD_FIELDS = [
    ("food_name_input", "Food name", ""),
    ("calories_input", "Calories", 0.0),
    ("protein_input", "Protein (g)", 0.0),
    ("carbs_input", "Carbs (g)", 0.0),
    ("fat_input", "Fat (g)", 0.0)
]

def reset_food_form():
    """Zero out inputs"""
    for key, _, default in FOOD_FIELDS:
        st.session_state[key] = default

def render_food_log_tab():
    col1, _ = st.columns([2, 1.5])
    with col1:
        st.subheader("Log Food")

        # ── Expander state ───────────────────────────────────────────────────
        if "expander_open" not in st.session_state:
            st.session_state["expander_open"] = False

        with st.expander("Add a meal", expanded=st.session_state["expander_open"]):
            # ── The form ──────────────────────────────────────────────────────
            with st.form("food_form"):
                food     = st.text_input("Food name", key="food_name_input")
                calories = st.number_input("Calories",     min_value=0.0, step=0.1, key="calories_input")
                protein  = st.number_input("Protein (g)",  min_value=0.0, step=0.1, key="protein_input")
                carbs    = st.number_input("Carbs (g)",    min_value=0.0, step=0.1, key="carb_input")
                fat      = st.number_input("Fat (g)",      min_value=0.0, step=0.1, key="fat_input")
                submitted = st.form_submit_button("Add")

            # ── On submit, insert into Supabase ───────────────────────────────
            if submitted:
                new_row = {
                    "user_id": st.session_state["user_id"],
                    "date":    now.date().isoformat(),
                    "time":    now.strftime("%-I:%M %p"),
                    "food":    food,
                    "calories":calories,
                    "protein": protein,
                    "carbs":   carbs,
                    "fat":     fat,
                }

                with st.spinner("Saving to Supabase…"):
                    res = supabase.table("food_logs").insert(new_row).execute()

                if hasattr(res, "status_code") and res.status_code >= 400:
                    st.error(f"Error logging food ({res.status_code}): {res.status_text}")
                else:
                    st.success("✅ Food logged!")
                    # clear the cache so fetch_logs returns fresh data
                    fetch_logs.clear()
                    # close the expander and rerun so the new log shows up
                    st.session_state["expander_open"] = False
                    st.rerun()

def render_log_tab2():
    st.subheader("Log Food or Recipe")

    # 1) Fetch recipes once
    resp = (
        supabase
          .table("recipes")
          .select("recipe_id,recipe_name,foods,calories,protein,carbs,fat")
          .eq("user_id", st.session_state["user_id"])
          .order("recipe_name")
          .execute()
    )
    recipes = resp.data or []
    names   = [r["recipe_name"] for r in recipes]

    # 2) Let them pick a recipe or manual
    choice = st.selectbox(
        "What would you like to log?",
        ["–– Manual food entry ––"] + names,
        key="log_choice"
    )

    # 3a) Manual entry form
    if choice == "–– Manual food entry ––":
        with st.form("manual_form"):
            food     = st.text_input("Food name")
            calories = st.number_input("Calories",    min_value=0.0, step=0.1)
            protein  = st.number_input("Protein (g)", min_value=0.0, step=0.1)
            carbs    = st.number_input("Carbs (g)",   min_value=0.0, step=0.1)
            fat      = st.number_input("Fat (g)",     min_value=0.0, step=0.1)
            submit   = st.form_submit_button("Log Food")

        if submit:
            new_row = {
                "user_id":  st.session_state["user_id"],
                "date":     now.date().isoformat(),
                "time":     now.strftime("%-I:%M %p"),
                "food":     food,
                "calories": calories,
                "protein":  protein,
                "carbs":    carbs,
                "fat":      fat
            }
            with st.spinner("Logging…"):
                res = supabase.table("food_logs").insert(new_row).execute()
            if res.error:
                st.error(res.error.message)
            else:
                st.success(f"Logged '{food}'")
                fetch_logs.clear()
                st.experimental_rerun()

    # 3b) Recipe entry
    else:
        recipe = next(r for r in recipes if r["name"] == choice)
        st.markdown(f"**Includes:** {', '.join(recipe['foods'])}")
        st.markdown(
            f"**Calories:** {recipe['calories']}, "
            f"**Protein:** {recipe['protein']}g, "
            f"**Carbs:** {recipe['carbs']}g, "
            f"**Fat:** {recipe['fat']}g"
        )
        if st.button(f"Log Recipe: {choice}", key="log_recipe"):
            new_row = {
                "user_id":  st.session_state["user_id"],
                "date":     now.date().isoformat(),
                "time":     now.strftime("%-I:%M %p"),
                "food":     choice,
                "calories": recipe["calories"],
                "protein":  recipe["protein"],
                "carbs":    recipe["carbs"],
                "fat":      recipe["fat"]
            }
            with st.spinner("Logging…"):
                res = supabase.table("food_logs").insert(new_row).execute()
            if res.error:
                st.error(res.error.message)
            else:
                st.success(f"Logged recipe '{choice}'")
                fetch_logs.clear()
                st.rerun()

from streamlit_option_menu import option_menu

# at top of your main script


#______ 4. Recipe Tab _______________
def render_recipe_tab():
    st.subheader("Log a Saved Recipe")

    recipes = {
        row["recipe_name"]: {
            "recipe_id": row["recipe_id"],
            "foods": row["foods"],
            "calories": row["calories"],
            "protein": row["protein"],
            "carbs": row["carbs"],
            "fat": row["fat"]
        }
        for row in raw_recipes
    }
    
    # --- 1) Log an existing recipe ---
    if recipes:
        selected = st.selectbox(
            "Select a recipe to log:",
            ["-- Select --"] + sorted(recipes.keys()),
            key="select_recipe"
        )
        if selected != "-- Select --":
            data = recipes[selected]
            st.markdown(f"**Includes:** {', '.join(data['foods'])}")
            st.markdown(
                f"**Calories:** {data['calories']}, "
                f"**Protein:** {data['protein']}g, "
                f"**Carbs:** {data['carbs']}g, "
                f"**Fat:** {data['fat']}g"
            )
            if st.button(f"Log '{selected}'", key="log_saved_recipe"):
                new_row = {
                    "user_id":  user_id,
                    "date":     now.date().isoformat(),
                    "time":     now.strftime("%-I:%M %p"),
                    "food":     selected,
                    "calories": data["calories"],
                    "protein":  data["protein"],
                    "carbs":    data["carbs"],
                    "fat":      data["fat"],
                }
                with st.spinner("Logging recipe…"):
                    res = supabase.table("food_logs").insert(new_row).execute()
                # supabase-py v2 raises on HTTP errors, so if we reach here:
                st.success(f"✅ '{selected}' logged!")
                fetch_logs.clear()                         # clear cache so logs refetch
                st.session_state["saved_recipe_logged"] = True
                st.rerun()
    else:
        st.info("No recipes saved yet. Create one below!")

    # flash a one-time success for logging
    if st.session_state.pop("saved_recipe_logged", False):
        st.success("Recipe entry added!")

    # --- 2) Create a new recipe ---
    with st.expander("Create a Recipe", expanded=False):
        st.caption(
            "Save a recipe with its ingredients and macros. "
            "You can edit or delete recipes in the 'Recipes' tab."
        )
        with st.form("recipe_form", clear_on_submit=True):
            name   = st.text_input("Recipe Name", key="new_recipe_name")
            foods  = st.text_area("Foods (comma separated)", key="new_recipe_foods")
            cals   = st.number_input("Calories",    min_value=0.0, step=0.1, key="new_recipe_calories")
            prot   = st.number_input("Protein (g)", min_value=0.0, step=0.1, key="new_recipe_protein")
            carbs  = st.number_input("Carbs (g)",   min_value=0.0, step=0.1, key="new_recipe_carbs")
            fat    = st.number_input("Fat (g)",     min_value=0.0, step=0.1, key="new_recipe_fat")
            save   = st.form_submit_button("Create Recipe")

        if save:
            # basic validation
            if not name.strip():
                st.warning("Please enter a valid recipe name.")
            elif name in recipes:
                st.warning("That name is already in use. Pick another.")
            else:
                foods_list = [f.strip() for f in foods.split(",") if f.strip()]
                if not foods_list:
                    st.warning("Please list at least one food item.")
                else:
                    # update in‐memory
                    recipes[name] = {
                        "user_id": user_id,
                        "foods":    foods_list,
                        "calories": cals,
                        "protein":  prot,
                        "carbs":    carbs,
                        "fat":      fat
                    }
                    # persist via your helper
                    save_recipes(recipes)
                    fetch_recipes.clear()                   # clear cache so recipes refetch
                    st.session_state["recipe_saved"] = True
                    st.rerun()

    if st.session_state.pop("recipe_saved", False):
        st.success("Recipe saved!")

#______ 5. Ensure Goals Exist for New Users _______________
def ensure_goals_exist(user_id:str):
    existing = fetch_goals(user_id)
    if existing:
        return
    supabase.table("macro_goals").insert({
        "user_id": user_id,
        "calories": 2000,
        "protein": 150,
        "carbs": 250,
        "fat": 70
    }).execute()

def log_entry(food_name: str, macros: dict):
    new_row = {
        "user_id":  user_id,
        "date":     now.date().isoformat(),
        "time":     now.strftime("%-I:%M %p"),
        "food":     food_name,
        "calories": macros["calories"],
        "protein":  macros["protein"],
        "carbs":    macros["carbs"],
        "fat":      macros["fat"],
    }
    with st.spinner(f"Logging '{food_name}'…"):
        res = supabase.table("food_logs").insert(new_row).execute()
        st.success(f"Logged “{food_name}”")
        fetch_logs.clear()
        st.rerun()

st.markdown(
    """
    <style>
      /* target all expander header buttons */
      section[data-testid="stExpander"] > div > div > button {
        font-size: 18px !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)
#---------------------------------------------------------------------------------------------------
#                           App UI
# --------------------------------------------------------------------------------------------------


# ------------------------- A. Login ---------------------------------------------
if "user_id" not in st.session_state:
    st.sidebar.title("Login")
    st.sidebar.markdown("Enter your name to log in:")
    st.sidebar.caption(f"Version: {version}")
    
    with st.sidebar.form("login_form"):
        username = st.text_input("Your Name:").strip().lower()
        login = st.form_submit_button("Login")

    if not (login and username):
        st.stop()
    #______ 1) Look up existing user, or create a new user _______     
    user_res = (supabase
                .table("users")
                .select("id")
                .eq("username", username)
                .single()
                .execute()
            )
        
    if user_res.data:
        user_id = user_res.data["id"]
    else:
        user_id = str(uuid.uuid4())
        supabase.table("users").insert({
            "id": user_id,
            "username": username
        }).execute()
    # ______ 2) Save 'user_id' & 'username' into session ______
    st.session_state["user_id"] = user_id
    st.session_state["username_cleaned"] = username
    st.rerun()
# ______ 3) Load user data ______
user_id = st.session_state["user_id"]
ensure_goals_exist(user_id)
macro_goals = fetch_goals(user_id)
raw_recipes = fetch_recipes(user_id)
food_logs = fetch_logs(user_id)

logs_df = (pd.DataFrame(food_logs)
           .reindex(columns=["log_id","date", "time", "food", "calories", "protein", "carbs", "fat"]))

macro_resp = supabase.table("macro_goals")\
                        .select("calories","protein","carbs","fat")\
                        .eq("user_id", user_id)\
                        .single()\
                        .execute()
if macro_resp.data: 
    macro_goals = macro_resp.data
else: 
    macro_goals = {
        "calories": 2000,
        "protein": 150,
        "carbs": 250,
        "fat": 70
    }

recipe_resp = supabase.table("recipes")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()

if recipe_resp.data:
    raw_recipes = recipe_resp.data

st.session_state.setdefault("macro_goals", macro_goals)
st.session_state["macro_goals"] = macro_goals
st.session_state["recipes"] = raw_recipes
st.session_state["food_logs"] = logs_df

st.title("Macro Tracker")
st.markdown(f"Logged in as: `{st.session_state['username_cleaned']}`")

#---------------------------------------------------------------------------------------------------
#                           Tab1: Dashboard
# --------------------------------------------------------------------------------------------------
def render_dashboard():
    st.header("Today's Progress")
    #----------------------------------------------------
    #  Defining macros and targets
    # ---------------------------------------------------
    macros = ["calories", "protein", "carbs", "fat"]
    targets = pd.Series(macro_goals)

    #----------------------------------------------------
    #  2) Today's logs
    # ---------------------------------------------------
    today = now.date().isoformat()
    today_logs = logs_df[logs_df["date"] == today]

    #----------------------------------------------------
    #  3) Totals (zeros if no entries) and percentages
    # ---------------------------------------------------
    totals = today_logs[macros].sum().reindex(macros, fill_value = 0)
    percentages = (totals/targets * 100).round(1)
    percentages = (percentages.replace([np.inf,-np.inf],0).fillna(0))

    #----------------------------------------------------
    #  4) Caption with targets
    # ---------------------------------------------------
    caption = ", ".join(
        f"{macro_goals[m]} {m}"
        for m in macros
    )
    st.badge(f"Target: {caption}")
    #----------------------------------------------------
    #  Progress Bars
    # ---------------------------------------------------
    for i in range(0,len(macros),2):
        col1,col2 = st.columns(2)
        macro1 = macros[i]
        with col1:
            st.metric(label=f"{macro1.capitalize()}", value=f"{totals[macro1]} / {macro_goals[macro1]}")
            st.progress(min(int(percentages[macro1]), 100))
        if i + 1 < len(macros):
            macro2 = macros[i + 1]
            with col2:
                st.metric(label=f"{macro2.capitalize()}", value=f"{totals[macro2]} / {macro_goals[macro2]}")
                st.progress(min(int(percentages[macro2]), 100))
    #----------------------------------------------------
    #  Edit Goals Button
    # ---------------------------------------------------
    goal_button_label = (
        "Edit Macro Goals" 
        if st.session_state.get("macro_goals") 
        else "Set Macro Goals") 
    if st.button(goal_button_label):
        st.session_state["editing_goals"] = True
    if st.session_state.get("editing_goals"):
        render_goal_editor()
    if st.session_state.get("goals_saved"):
        st.success("Goals Saved")
        st.session_state["goals_saved"] = False
    #----------------------------------------------------
    #  Pie Chart
    # ---------------------------------------------------
    st.subheader("Macro Calorie Breakdown")
    if not today_logs.empty:
        macro_totals = today_logs[["protein","carbs","fat"]].sum()
        macro_calories = {
            "Protein": macro_totals["protein"] * 4,
            "Carbs": macro_totals["carbs"] * 4,
            "Fat": macro_totals["fat"] * 9
        }

        pie_df = pd.DataFrame({
            "Macro": list(macro_calories.keys()),
            "Calories": list(macro_calories.values())
        })

        fig = px.pie(pie_df, values='Calories', names='Macro',
                hole=0.5,
                color="Macro",
                color_discrete_map={
                    "Protein": "#6A5ACD",
                    "Carbs": "#FFD700",
                    "Fat": "#3CB371"
                },
                labels={'Calories': 'Calories', 'Macro': 'Macro'},
                template='plotly_dark')
        fig.update_traces(textposition='inside', textinfo='percent+label',textfont_size=14)
        st.plotly_chart(fig, use_container_width=False,width=300)

    else: 
        st.write("No data to show for today's pie chart.")
    #----------------------------------------------------
    #  Weekly Summary
    # ---------------------------------------------------
    st.subheader("Weekly Summary")

    seven_days_ago = now.date() - timedelta(days=6)
    logs_df["date"] = pd.to_datetime(logs_df["date"]).dt.date
    last_7_df = logs_df[logs_df["date"] >= seven_days_ago]
    #----------------------------------------------------
    #  Reordering to start the week on Sunday
    # ---------------------------------------------------
    all_days = pd.date_range(seven_days_ago, now.date())
    weekly_summary = (
        last_7_df.groupby("date")[["calories", "protein","carbs","fat"]]
        .sum()
        .reindex(all_days, fill_value=0)
    )
    weekly_summary.index = pd.Categorical(
        [d.strftime("%a") for d in weekly_summary.index],
        categories = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        ordered=True
    )

    weekly_summary = weekly_summary.sort_index()

    def macro_bar_chart(chart_data, column, color, title):
        chart_data = pd.DataFrame({
            "day": weekly_summary.index,
            column: weekly_summary[column].values
        })
        return alt.Chart(chart_data).mark_bar(color=color).encode(
            x=alt.X("day", sort=["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], axis=alt.Axis(labelAngle = 45)),
            y=alt.Y(column),
            tooltip=["day", column]
        ).properties(width=250,height=300,title=title)

    col1, col2 = st.columns(2)
    with col1:
        st.altair_chart(macro_bar_chart(weekly_summary, "calories", "#FF6F61", "Calories"), use_container_width=True)
        st.altair_chart(macro_bar_chart(weekly_summary, "protein", "#6A5ACD", "Protein"), use_container_width=True)
    with col2:  
        st.altair_chart(macro_bar_chart(weekly_summary, "carbs", "#FFD700", "Carbs"), use_container_width=True)
        st.altair_chart(macro_bar_chart(weekly_summary, "fat", "#3CB371", "Fats"), use_container_width=True)
                    
#---------------------------------------------------------------------------------------------------
#                           Tab2: Food Log
# --------------------------------------------------------------------------------------------------

def render_food_log():
    col1, col2 = st.columns(2)
    with col1:
        if "recipe_expander_open" not in st.session_state:
            st.session_state["recipe_expander_open"] = False

        choice = st.radio(
            "Choose an entry type:",
            ["Manual Entry", "Recipes"],
            key = "log_mode",
            horizontal=True
        )
        if choice == "Recipes":
            names = [r["recipe_name"] for r in raw_recipes]
            sel = st.selectbox("Pick a recipe", ["—"] + names)
            if sel != "—":
                rec = next(r for r in raw_recipes if r["recipe_name"] == sel)
                st.markdown(f"**Includes:** {', '.join(rec['foods'])}")
                st.write(f"Calories: {rec['calories']}, Protein: {rec['protein']}g, Fat {rec['fat']}g, Carbs {rec['carbs']}g")
                if st.button("Log Recipe"):
                    log_entry(rec["recipe_name"], rec)
                    st.success(f"Logged recipe “{sel}”!")
            with st.expander("Create a Recipe", expanded=st.session_state["recipe_expander_open"]):
                with st.form("new_recipe_form", clear_on_submit=True):
                    name_input = st.text_input("Recipe Name")
                    foods_input = st.text_input("Foods (comma-separated)")
                    cals_input = st.number_input("Calories", min_value=0.0, step=1.0)
                    protein_input = st.number_input("Protein (g)", min_value=0.0, step=1.0)
                    carbs_input = st.number_input("Carbs (g)", min_value=0.0, step=1.0)
                    fat_input = st.number_input("Fat (g)", min_value=0.0, step=1.0)
                    r_save_btn = st.form_submit_button("Save Recipe")
                    if r_save_btn:
                        recipe_name = name_input.strip()
                        if not recipe_name:
                            st.warning("Give your recipe a name!")
                        else:
                            foods_list = [f.strip() for f in foods_input.split(",") if f.strip()]
                            if not foods_list:
                                st.warning("list at least one ingredient.")
                            else: 
                                new_recipe = {
                                    "recipe_name": name_input,
                                    "foods": foods_list,
                                    "calories": cals_input,
                                    "protein": protein_input,
                                    "carbs": carbs_input,
                                    "fat": fat_input
                                }
                                save_recipes({recipe_name: new_recipe})
                                fetch_recipes.clear()
                                st.success(f"Created recipe {recipe_name}!")
                                st.rerun()
        else:
            with st.form("manual"):
                food     = st.text_input("Food name")
                calories = st.number_input("Calories", min_value=0.0)
                protein  = st.number_input("Protein (g)", min_value=0.0)
                carbs    = st.number_input("Carbs (g)", min_value=0.0)
                fat      = st.number_input("Fat (g)", min_value=0.0)
                submit   = st.form_submit_button("Log Food")
            if submit:
                log_entry(food, {"calories":calories, "protein":protein, "carbs": carbs, "fat":fat})
                st.success(f"Logged “{food}”!")
    with col2:
        today = now.date().isoformat()
        today_logs = logs_df[logs_df["date"] == today]
        st.header("Food Logged Today")
        today_logs["time"] = pd.to_datetime(today_logs["time"], format="%H:%M:%S").dt.strftime("%-I:%M %p")
#----------------------------------------------------
#  Food log UI, Edit, and Delete
# ---------------------------------------------------
        if today_logs.empty:
            st.info("No food logged today yet.")
        else:
            # turn into list of dicts once
            records = today_logs.to_dict(orient="records")

            for rec in records:
                # 1) Build your expander header
                header = f"{rec['time']}: {rec['food']} — Cals: {rec['calories']}, Protein: {rec['protein']} (g), Carbs: {rec['carbs']} (g), Fat: {rec['fat']} (g)"

                with st.expander(header, expanded=False):
                    st.caption("Impact on macros goals")
                    # 2) Prepare & style your Plotly figure
                    mode     = st.get_option("theme.base")  # "light" or "dark"
                    template = "plotly_white" if mode=="light" else "plotly_dark"

                    fig = make_subplots(
                        rows=1, cols=3,
                        specs=[[{"type":"domain"}]*3],
                        subplot_titles=[f"Protein: {rec['protein']} (g)", f"Carbs: {rec['carbs']} (g)", f"Fat: {rec['fat']} (g)"]
                    )
                    fig.update_layout(template=template, margin=dict(l=0,r=0,t=10,b=0), height=120, width=300, showlegend=False)

                    colors = {
                        "protein": ["#6A5ACD","#E0E0FF"],
                        "carbs":   ["#FFD700","#FFF8B0"],
                        "fat":     ["#3CB371","#B0EFB0"]
                    }

                    percentages = []
                    for i, macro in enumerate(["protein","carbs","fat"], start=1):
                        eaten     = float(rec[macro])
                        goal      = float(macro_goals.get(macro,1))
                        remaining = max(goal - eaten, 0)
                        pct       = round(eaten/goal*100,1) if goal else 0
                        percentages.append(pct)

                        fig.add_trace(
                            go.Pie(
                                labels=["Eaten","Remaining"],
                                values=[eaten, remaining],
                                hole=0.68,
                                sort= False,
                                marker=dict(colors=colors[macro]),
                                hoverinfo='none',
                                textinfo='none'
                            ),
                            row=1, col=i
                        )

                    # center the % annotation in each donut
                    for idx, trace in enumerate(fig.data):
                        dom   = trace.domain
                        mid_x = (dom.x[0] + dom.x[1]) / 2
                        mid_y = (dom.y[0] + dom.y[1]) / 2
                        fig.add_annotation(
                            x=mid_x, y=mid_y,
                            text=f"{percentages[idx]}%",
                            showarrow=False,
                            font=dict(size=16, color=("#000" if mode=="light" else "#fff")),
                            xanchor="center", yanchor="middle"
                        )
                    fig.update_layout(
                        margin=dict(l=0, r=0, t=20, b=0),   # more space at top
                        height=140,                         # a bit shorter overall
                        width=300,
                        showlegend=False
                    )

                    # 2) Tweak each subplot‐title annotation
                    for ann in fig.layout.annotations:
                        # these first three are your subplot_titles
                        if ann.text in ["Protein","Carbs","Fat"]:
                            ann.font.size = 13              # smaller title font
                            ann.y = ann.y           # nudge down a bit

                    st.plotly_chart(fig, use_container_width=True, config={"staticPlot": True, "displayModeBar": False}, key=f"pies_{rec['log_id']}")

                    # 3) Action buttons for this entry
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Edit", key=f"edit_{rec['log_id']}"):
                            st.session_state["edit_log_id"] = rec["log_id"]
                            st.rerun()
                    with col2:
                        if st.button("Delete", key=f"del_{rec['log_id']}"):
                            res = (
                                supabase.table("food_logs")
                                        .delete()
                                        .eq("log_id", rec["log_id"])
                                        .execute()
                            )
                            if res.error:
                                st.error(f"Delete failed: {res.error.message}")
                            else:
                                st.success("Entry deleted.")
                                fetch_logs.clear()
                                st.rerun()

            # 4) Edit‐form outside the loop, triggered by the “Edit” button
            if "edit_log_id" in st.session_state:
                log_id = st.session_state.pop("edit_log_id")
                rec    = next(r for r in records if r["log_id"] == log_id)

                st.subheader(f"Edit Entry: {rec['food']}")
                with st.form("edit_form", clear_on_submit=False):
                    new_food    = st.text_input("Food name", value=rec["food"])
                    new_cal     = st.number_input("Calories",   value=rec["calories"], step=0.1)
                    new_protein = st.number_input("Protein (g)",value=rec["protein"],  step=0.1)
                    new_carbs   = st.number_input("Carbs (g)",  value=rec["carbs"],    step=0.1)
                    new_fat     = st.number_input("Fat (g)",    value=rec["fat"],       step=0.1)
                    save_btn    = st.form_submit_button("Save changes")

                if save_btn:
                    upd = (
                        supabase.table("food_logs")
                                .update({
                                    "food":     new_food,
                                    "calories": new_cal,
                                    "protein":  new_protein,
                                    "carbs":    new_carbs,
                                    "fat":      new_fat
                                })
                                .eq("log_id", log_id)
                                .execute()
                    )
                    if upd.error:
                        st.error(f"Update failed: {upd.error.message}")
                    else:
                        st.success("Entry updated.")
                        fetch_logs.clear()
                        st.rerun()
TAB_NAMES = ["Dashboard", "Food Log"]
default = st.session_state.get("active_tab_index", 0)

selected = option_menu(
    menu_title=None,                        # no title
    options=TAB_NAMES,
    icons=["bar-chart", "journal-medical"],  
    menu_icon="app-indicator",
    default_index=default,
    orientation="horizontal",
)
# store so it survives any rerun
st.session_state["active_tab_index"] = TAB_NAMES.index(selected)

# dispatch
if selected == "Dashboard":
    render_dashboard()
else:
    render_food_log()