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
  Gains and weight loss not guaranteed. Data loss guaranteed.<br>
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
def save_recipes(recipes_dict,user_id):
    user_id = st.session_state["user_id"]
    existing = st.session_state.get("recipes",{})
    records_to_upsert = []
    for name, recipe in recipes_dict.items():
        records_to_upsert.append = ({
                "user_id": user_id,
                "name": name,
                "foods": recipe["foods"],
                "calories": recipe["calories"],
                "protein": recipe["protein"],
                "carbs": recipe["carbs"],
                "fat": recipe["fat"]
            })
    if records_to_upsert:
        upsert("recipes", records_to_upsert, success_msg="Recipe Saved!")
    removed = set(existing.keys()) - set (recipes_dict.keys())
    for name in removed:
        with st.spinner(f"Deleting recipes '{name}'..."):
            res = supabase.table("recipes").delete().eq("user_id", user_id).eq("name", name).execute()
        if res.status_code >= 400:
            st.error(f"Couldn't delete '{name}' ({res.status_code}): {res.status_text}")

    st.session_state["recipes"] = recipes_dict
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


#______ 4. Recipe Tab _______________
def render_recipe_tab():
    """
    Renders the right‐hand side of tab2:
    1) Log an existing recipe into food_logs
    2) Create a new recipe (persisted via save_recipes)
    """
    st.subheader("Log a Saved Recipe")
    user_id = st.session_state["user_id"]
    recipes = st.session_state.get("recipes", {})

    # --- 1) Log an existing recipe ---
    if recipes:
        selected = st.selectbox(
            "Select a recipe to log:",
            ["-- Select --"] + list(recipes.keys()),
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
            "You can edit or delete recipes in the 'Recipes' tab.'"
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
                st.warning("That name’s already in use. Pick another.")
            else:
                foods_list = [f.strip() for f in foods.split(",") if f.strip()]
                if not foods_list:
                    st.warning("Please list at least one food.")
                else:
                    # update in‐memory
                    recipes[name] = {
                        "foods":    foods_list,
                        "calories": cals,
                        "protein":  prot,
                        "carbs":    carbs,
                        "fat":      fat,
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
recipes = fetch_recipes(user_id)
food_logs = fetch_logs(user_id)

logs_df = (pd.DataFrame(food_logs)
           .reindex(columns=["date", "time", "food", "calories", "protein", "carbs", "fat"]))

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
st.session_state.setdefault("macro_goals", macro_goals)
st.session_state["macro_goals"] = macro_goals
st.session_state["recipes"] = recipes
st.session_state["food_logs"] = logs_df

# ------------------------- Main App --------------------------------------------------
st.title("Macro Tracker")
st.markdown(f"Logged in as: `{st.session_state["username_cleaned"]}`")
st.markdown(f"user_id: `{user_id}`")

# ------------------------- Tab Contents ---------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["Dashboard", "Log Food", "Recipes"])

# ------------------------- Tab1: "Today's Progress" ---------------------------------------------
with tab1:
    st.header("Today's Progress")

    # 1) Define macros and targets
    macros = ["calories", "protein", "carbs", "fat"]
    targets = pd.Series(macro_goals)


    # 2) Today's logs
    today = now.date().isoformat()
    today_df = logs_df[logs_df["date"] == today]

    # 3) Totals (zeros if no entries) and percentages
    totals = today_df[macros].sum().reindex(macros, fill_value = 0)
    percentages = (totals/targets * 100).round(1)
    percentages = (percentages.replace([np.inf,-np.inf],0).fillna(0))

    # 4) Caption with targets
    caption = ", ".join(
        f"{macro_goals[m]} {m}"
        for m in macros
    )
    st.badge(f"Target: {caption}")
    # -------------------------- Progress Bars --------------------------
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
    # ------------------------- Edit Goals Button ---------------------------
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
    # -------------------------- Pie Chart --------------------------
    st.subheader("Macro Calorie Breakdown", divider='blue')
    if not today_df.empty:
        macro_totals = today_df[["protein","carbs","fat"]].sum()
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

    # ------------------------- Weekly Summary -------------------------
    st.subheader("Weekly Summary")
    # Filtering last 7 days of data
    seven_days_ago = now.date() - timedelta(days=6)
    logs_df["date"] = pd.to_datetime(logs_df["date"]).dt.date
    last_7_df = logs_df[logs_df["date"] >= seven_days_ago]

    # ------------------------- Reordering to start the week on Sunday -------------------------
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

    # ------------------------- Tab2: Log Food -------------------------
with tab2:
    col1, col2 = st.columns([2,1])
    with col1:
        render_food_log_tab()
    with col2:    
        render_recipe_tab()

# ------------------------- Logged Entries ------------------------- 
    st.subheader("Food Logged Today")
    if not today_df.empty:
        for actual_idx, row in today_df.iterrows():
            with st.expander(f"{row.get('time')}: {row['food']} - {row['calories']} cal"):
                st.write(f"Protein: {row['protein']}g, Carbs: {row['carbs']}g, Fat: {row['fat']}g")

                col1, col2 = st.columns([1,1])
                with col1:
                    if st.button("Edit", key=f"edit_{actual_idx}"):
                        st.session_state["edit_row"] = actual_idx
                with col2:
                    if st.button("Delete", key=f"delete_{actual_idx}"):
                        df = df.drop(actual_idx)
                        df.to_csv(DATA_PATH, index=False)
                        st.session_state["entry_deleted"] = True
                        
# ------------------------- Show edit form if triggered -------------------------
    if "edit_row" in st.session_state:
        edit_idx = st.session_state["edit_row"]
        row = df.loc[edit_idx]

        st.subheader(f"Edit Entry: {row['food']}")
        with st.form("edit_form"):
            new_food = st.text_input("Food name", value = row["food"])
            new_cal = st.number_input("Calories", value=float(row["calories"]), step=0.1)
            new_pro = st.number_input("Protein (g)", value=float(row["protein"]), step=0.1)
            new_carb = st.number_input("Carbs (g)", value=float(row["carbs"]), step=0.1)
            new_fat = st.number_input("Fats (g)", value=float(row["fat"]), step=0.1)
            save = st.form_submit_button("Save")
        
        if save:
            df.loc[edit_idx, ["food", "calories", "protein", "carbs", "fat"]] = [
                new_food, new_cal, new_pro, new_carb, new_fat
            ]
            df.to_csv(DATA_PATH, index=False)
            st.session_state["form_submitted"] = True
            del st.session_state["edit_row"]
            



# ------------------------- Tab3: Recipes -------------------------
with tab3:
    # ------------------------- Recipe Editor -------------------------
    if "edit_recipe" in st.session_state: 
        edit_recipe = st.session_state["edit_recipe"]
        recipe_data = recipes[edit_recipe]

        st.subheader(f"Edit Recipe: {edit_recipe}")
        with st.form("edit_recipe_form"):
            new_foods = st.text_area("Foods (comma separated)", value=", ".join(recipe_data["foods"]))
            new_calories = st.number_input("Calories", min_value=0.0, step=0.1, value=recipe_data["calories"])
            new_protein = st.number_input("Protein (g)", min_value=0.0, step=0.1, value=recipe_data["protein"])
            new_carbs = st.number_input("Carbs (g)", min_value=0.0, step=0.1, value=recipe_data["carbs"])
            new_fat = st.number_input("Fat (g)", min_value=0.0, step=0.1, value=recipe_data["fat"])
            save_edit = st.form_submit_button("Save Changes")

        if save_edit:
            new_foods_list = [food.strip() for food in new_foods.split(",")]
            recipes[edit_recipe] = {
                "foods": new_foods_list,
                "calories": new_calories,
                "protein": new_protein,
                "carbs": new_carbs,
                "fat": new_fat
            }
            save_recipes(recipes, RECIPE_PATH)
            st.session_state["recipe_edited"] = True
            del st.session_state["edit_recipe"]
            st.rerun()
    if st.session_state.get("recipe_edited"):
        msg = st.empty()
        msg.success("Recipe Updated")
        time.sleep(2)
        msg.empty()
        st.session_state["recipe_edited"] = False

    # ------------------------- View Recipes -------------------------
    st.subheader("Saved Recipes")
    if recipes:
        for idx, (recipe_name, recipe_data) in enumerate(recipes.items()):
            with st.expander(recipe_name):
                st.write("Foods: ", ", ".join(recipe_data["foods"]))
                st.write(f"Calories: {recipe_data['calories']}, Protein: {recipe_data['protein']}g, Carbs: {recipe_data['carbs']}g, Fat: {recipe_data['fat']}g")
                
                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button("Edit", key=f"edit_{idx}_{recipe_name}"):
                        st.session_state["edit_recipe"] = recipe_name
                        st.rerun()
                with col2:
                    if st.button("Delete", key=f"delete_{idx}_{recipe_name}"):
                        st.session_state["recipe_to_delete"] = recipe_name
                        st.rerun()
    if "recipe_to_delete" in st.session_state:
        del recipes[st.session_state["recipe_to_delete"]]
        save_recipes(recipes, RECIPE_PATH)
        st.session_state["recipe_deleted"] = True
        del st.session_state["recipe_to_delete"]
    if st.session_state.get("recipe_deleted"):
            msg = st.empty()
            msg.success("Recipe Deleted")
            time.sleep(2)
            msg.empty()
            st.session_state["recipe_deleted"] = False
            st.rerun()

