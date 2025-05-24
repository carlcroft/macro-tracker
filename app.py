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
import pytz
import uuid
# ------------------------- App Variables -------------------------
eastern = pytz.timezone("US/Eastern")
now = datetime.now(eastern)
version = 0.32
# ------------------------- Beta Warning -------------------------
st.markdown(f"""
<div style="
    background-color:rgba(50, 50, 50, 0.85);
    color:white;
    padding:15px; 
    border-left:5px solid #ffa502; 
    border-radius:6px; 
    margin-bottom:20px">
  <strong>🧪 Very Beta v{version}</strong><br>
  Gains and weight loss not guaranteed. Data loss shouldn't be a problem anymore? We'll see.<br>
</div>
""", unsafe_allow_html=True)

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
                st.experimental_rerun()


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

tab1, tab2 = st.tabs(["Dashboard", "Food Log"])

#---------------------------------------------------------------------------------------------------
#                           Tab1: Dashboard
# --------------------------------------------------------------------------------------------------
with tab1:
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
    st.subheader("Macro Calorie Breakdown", divider='blue')
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
        st.plotly_chart(fig, use_container_width=True)

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
with tab2:
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
        st.header("Food Logged Today")
        today_logs["time"] = pd.to_datetime(today_logs["time"], format="%H:%M:%S").dt.strftime("%-I:%M %p")
        st.dataframe(today_logs[["time","food","calories","protein","carbs","fat"]], use_container_width=True)

#----------------------------------------------------
#  Food log UI, Edit, and Delete
# ---------------------------------------------------
        if today_logs.empty:
            st.info("No food logged today yet.")
        else:     
            # 1) Get a proper list of row‐dicts
            records = today_logs.to_dict(orient="records")

            for rec in records:
                # 2) format the header
                header = f"{rec['time']}: {rec['food']} — {rec['calories']} cal"

                with st.expander(header, expanded=False):
                    # 0) Detect Streamlit’s theme
                    mode = st.get_option("theme.base")     # “light” or “dark”

                    # 1) Pick a Plotly template
                    template = "plotly_white" if mode == "light" else "plotly_dark"
                    fig.update_layout(template=template)

                    # 2) Pick an annotation color (and maybe a semi-opaque background)
                    if mode == "light":
                        ann_color = "#000"                    # black text on light
                        ann_bg    = "rgba(255,255,255,0.6)"   # light translucent box
                    else:
                        ann_color = "#fff"                    # white text on dark
                        ann_bg    = "rgba(0,0,0,0.6)"  
                    # 3) build the 1×3 pie subplot
                    fig = make_subplots(rows=1, cols=3, specs=[[{"type":"domain"}]*3],
                                        subplot_titles=["Protein","Carbs","Fat"])
                    colors = {
                        "protein": ["#6A5ACD","#E0E0FF"],
                        "carbs":   ["#FFD700","#FFF8B0"],
                        "fat":     ["#3CB371","#B0EFB0"]
                    }

                    for i, macro in enumerate(["protein","carbs","fat"], start=1):
                        eaten    = float(rec[macro])
                        goal     = float(macro_goals.get(macro, 1))
                        remaining= max(goal - eaten, 0)
                        pct      = round(eaten/goal*100, 1) if goal else 0

                        fig.add_trace(
                            go.Pie(
                                labels=["Eaten","Remaining"],
                                values=[eaten, remaining],
                                hole=0.6,
                                marker=dict(colors=colors[macro]),
                                hovertemplate="%{label}: %{percent} of daily goal",
                                textinfo="none"
                            ),
                            row=1, col=i
                        )
                    for idx, trace in enumerate(fig.data):
                        dom = trace.domain
                        mid_x = (dom.x[0] + dom.x[1]) / 2
                        mid_y = (dom.y[0] + dom.y[1]) / 2
                        fig.add_annotation(
                            x= mid_x,
                            y= mid_y,
                            text=f"{percentages[idx]}%",
                            showarrow=False,
                            font=dict(size=20,color=ann_color),
                            xanchor="center",
                            align="center"
                        )

                    fig.update_layout(margin=dict(l=0,r=0,t=20,b=0), height=200, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"pies_{rec['log_id']}")  
            if False:
                for actual_idx, row in today_logs.iloc[::-1].iterrows():
                    with st.expander(f"{row['time']}: {row['food']} - {row['calories']} cal"):
                        df = logs_df
                        totals = df[["protein","carbs","fat"]].sum().to_dict()

                        # 2) build a subplot figure with 3 pies
                        fig = make_subplots(
                            rows=1, cols=3,
                            specs=[[{"type":"domain"}, {"type":"domain"}, {"type":"domain"}]],
                            subplot_titles=["Protein","Carbs","Fat"]
                        )

                        colors = {
                            "protein": ["#6A5ACD", "#E0E0FF"],
                            "carbs":   ["#FFD700", "#FFF8B0"],
                            "fat":     ["#3CB371", "#B0EFB0"]
                        }

                        for i, macro in enumerate(["protein","carbs","fat"], start=1):
                            eaten = float(totals.get(macro, 0))
                            goal = float(macro_goals.get(macro, 1))
                            remaining = max(goal - eaten, 0)

                            fig.add_trace(go.Pie(
                                labels = ["Eaten", "Remaining"],
                                values = [eaten, remaining],
                                hole = 0.6,
                                marker=dict(colors=colors[macro],
                                            line=dict(color="white",width=2)),
                                hovertemplate = "%{label}: %{percent} of daily goal",        
                                textinfo=None,
                                textfont_size=14),
                                row=1,col=i)
                            
                            pct = round(eaten/goal * 100, 1) if goal else 0

                        fig.update_layout(
                            margin=dict(l=0, r=0, t=30, b=0),
                            height=200,
                            showlegend=False
                        )
                        fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=200, showlegend=False)

                        st.plotly_chart(fig, use_container_width=True, key=f"macropies_{row['log_id']}")
                    
                    if False:
                        cal, protein, carbs, fat = row["calories"], row["protein"], row["carbs"], row["fat"]
                        cal_goal, p_goal, c_goal, f_goal = (macro_goals[k] for k in ("calories","protein", "carbs", "fat"))
                        if not today_logs.empty:
                            # 1) sum up grams consumed today
                            df = logs_df
                            totals = df[["protein","carbs","fat"]].sum().to_dict()

                            # 2) build a subplot figure with 3 pies
                            fig = make_subplots(
                                rows=1, cols=3,
                                specs=[[{"type":"domain"}, {"type":"domain"}, {"type":"domain"}]],
                                subplot_titles=["Protein","Carbs","Fat"]
                            )

                            colors = {
                                "Protein": ["#6A5ACD", "#E0E0FF"],
                                "Carbs":   ["#FFD700", "#FFF8B0"],
                                "Fat":     ["#3CB371", "#B0EFB0"]
                            }

                            for i, macro in enumerate(["protein","carbs","fat"], start=1):
                                eaten    = float(totals.get(macro, 0))
                                goal     = float(macro_goals.get(macro, 1))
                                remaining = max(goal - eaten, 0)

                                fig.add_traces(go.Pie(

                                    textinfo='percent+label',textfont_size=14))
                                pct = round(eaten/goal * 100, 1) if goal else 0
                                fig.add_annotation(
                                    x= (i - 1)/3 + 1/6, y=0.5, 
                                    text=f"{pct}%",
                                    showarrow=False,
                                    font=dict(size=14)
                                )

                            fig.update_layout(
                                margin=dict(l=0, r=0, t=30, b=0),
                                height=200,
                                showlegend=False
                            )

                            st.plotly_chart(fig, use_container_width=True)



                    if False:
                        cal_pct = round(cal / cal_goal * 100, 1) if cal_goal else 0
                        p_pct = round(protein/p_goal * 100, 1) if p_goal else 0
                        c_pct = round(carbs/c_goal * 100,1 ) if c_goal else 0
                        f_pct = round(fat/f_goal * 100, 1) if f_goal else 0

                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("🔥 Calories", f"{cal} / {cal_goal}", f"{cal_pct}%", border=True)
                        col2.metric("Protein", f"{protein}g/ {p_goal}g", f"{p_pct}%", border=True)
                        col3.metric("Carbs", f"{carbs}g/ {c_goal}g", f"{c_pct}%", border=True)
                        col4.metric("Fats", f"{fat}g/ {f_goal}g", f"{f_pct}%", border=True)

                        bar1, bar2, bar3, bar4 = st.columns(4)
                        bar1.progress(min(int(cal_pct), 100))
                        bar2.progress(min(int(p_pct),100))
                        bar3.progress(min(int(c_pct),100))
                        bar4.progress(min(int(f_pct),100))

                    col1, col2 = st.columns([1,1])
                    with col1:
                        if st.button("Edit", key=f"edit_{actual_idx}"):
                            st.session_state["edit_row"] = actual_idx
                    with col2:
                        if st.button("Delete", key=f"delete_{actual_idx}"):
                            res = supabase.table("food_logs").delete().eq("log_id",row['log_id']).execute()
                            st.session_state["entry_deleted"] = True
            if "edit_row" in st.session_state:
                edit_idx = st.session_state["edit_row"]
                row = today_logs.loc[edit_idx]
    #----------------------------------------------------
    #  Food log UI, Edit, and Delete
    # ---------------------------------------------------
                st.subheader(f"Edit Entry: {row['food']}")
                with st.form("edit_form"):
                    new_food = st.text_input("Food name", value = row["food"])
                    new_cal = st.number_input("Calories", value=float(row["calories"]), step=0.1)
                    new_pro = st.number_input("Protein (g)", value=float(row["protein"]), step=0.1)
                    new_carb = st.number_input("Carbs (g)", value=float(row["carbs"]), step=0.1)
                    new_fat = st.number_input("Fats (g)", value=float(row["fat"]), step=0.1)
                    save = st.form_submit_button("Save")
                
                if save:
                    today_logs.loc[edit_idx, ["food", "calories", "protein", "carbs", "fat"]] = [
                        new_food, new_cal, new_pro, new_carb, new_fat
                    ]
                    df.to_csv(DATA_PATH, index=False)
                    st.session_state["form_submitted"] = True
                    del st.session_state["edit_row"]                    