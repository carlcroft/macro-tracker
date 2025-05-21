import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import altair as alt
import os
import plotly.express as px
import pytz

eastern = pytz.timezone("US/Eastern")
now= datetime.now(eastern)

version = 0.20

st.set_page_config(layout="wide")
# -- Beta Warning --
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

# -- Functions --
def render_goal_editor(username, existing_goals=None):
    st.subheader("Set your macro goals")

    if existing_goals is None:
        existing_goals = {"calories": 2000, "protein": 150, "carbs": 250, "fat": 70}
    
    cal = st.number_input("Calories", min_value=0,value=existing_goals["calories"])
    pro = st.number_input("Protein (g)", min_value=0,value=existing_goals["protein"])
    carb = st.number_input("Carbs (g)", min_value=0,value=existing_goals["carbs"])
    fat = st.number_input("Fat (g)", min_value=0,value=existing_goals["fat"])

    if st.button("Save Goals"):
        new_goals = {
            "calories":cal,
            "protein": pro,
            "carbs": carb,
            "fat": fat
        }
        st.session_state["macro_goals"] = new_goals

        os.makedirs("Data/logs", exist_ok=True)
        goal_path = f"Data/logs/{username}_goals.json"
        with open(goal_path, "w") as f:
            json.dump(new_goals, f)
        
        st.success("Goals Saved")
        st.session_state["editing_goals"] = False
        st.rerun()

# -- Sidebar Login --
st.sidebar.title("Login")
st.sidebar.markdown("Enter your name to log in:")
with st.sidebar.form("login_form"):
    username_input=st.text_input("Your Name:").strip()
    login = st.form_submit_button("Login")

if login and username_input:
    st.session_state["username_cleaned"] = username_input.lower()
    goal_path = f"Data/logs/{st.session_state['username_cleaned']}_goals.json"
    if os.path.exists(goal_path):
        with open(goal_path) as f:
            st.session_state["macro_goals"] = json.load(f)
    else:
        st.session_state["macro_goals"] = {
            "calories": 2000,
            "protein": 150,
            "carbs": 250,
            "fat": 70
        }
    st.rerun()

if "username_cleaned" not in st.session_state:
    st.stop()

username = st.session_state["username_cleaned"]

# -- Load Recipes --
os.makedirs("Data/recipes", exist_ok=True)
RECIPE_PATH = f"Data/recipes/{username}_recipes.json"
try:
    with open(RECIPE_PATH, "r") as f:
        recipes = json.load(f)
except FileNotFoundError:
    recipes = {}

# -- Initial load of macro goals --
if "macro_goals" not in st.session_state:
    st.session_state["macro_goals"] = {
        "calories": 2000,
        "protein": 150,
        "carbs": 250,
        "fat": 70
    }

# -- Step 3: Main App
st.title("Macro Tracker")
st.markdown(f"Logged in as: `{username}`")
st.sidebar.caption(f"Version: {version}")
goals = st.session_state["macro_goals"]

os.makedirs("Data/logs",exist_ok=True)

# Load Existing Data
DATA_PATH = f"Data/logs/{username}_macro_log.csv"
try: 
    df = pd.read_csv(DATA_PATH)
    if "time" not in df.columns:
        df["time"] = ""
except FileNotFoundError:
    df = pd.DataFrame(columns=["date", "time" "food", "calories", "protein", "carbs", "fat"])

# -- Today's Progress Section -- 
tab1, tab2, tab3 = st.tabs(["Dashboard", "Log Food", "Recipes"])

with tab1:
    st.subheader("Today's Progress")
    st.caption(f"Target: {goals['calories']} cal, {goals['protein']}g protein, {goals['carbs']}g carbs, {goals['fat']}g fat")
    today = now.date().isoformat()
    today_df = df[df["date"] == today]

    totals = today_df[["calories", "protein", "carbs", "fat"]].sum() if not today_df.empty else{
            "calories": 0,
            "protein": 0,
            "carbs":0,
            "fat":0
        }
    percentages = {
        macro: (totals[macro] / goals[macro]) * 100 if goals[macro] > 0 else 0 for macro in goals
    }

    # - Progress Bars -
    macro_list = list(goals.keys())
    for i in range(0,len(macro_list),2):
        col1,col2 = st.columns(2)
        macro1 = macro_list[i]
        with col1:
            st.metric(label=f"{macro1.capitalize()}", value=f"{totals[macro1]} / {goals[macro1]}")
            st.progress(min(int(percentages[macro1]), 100))
        if i + 1 < len(macro_list):
            macro2 = macro_list[i + 1]
            with col2:
                st.metric(label=f"{macro2.capitalize()}", value=f"{totals[macro2]} / {goals[macro2]}")
                st.progress(min(int(percentages[macro2]), 100))
    # -- Edit Goals Section --
    goal_button_label = "Edit Macro Goals" if st.session_state["macro_goals"] else "Set Macro Goals"
    if st.button(goal_button_label):
        st.session_state["editing_goals"] = True
    if "username_cleaned" in st.session_state:
        if st.session_state.get("editing_goals"):
            render_goal_editor(username, existing_goals=st.session_state["macro_goals"])
    # - Pie Chart - 
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

        fig = px.pie(pie_df, values='Calories', names='Macro', title='Macro Calorie Breakdown',
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

    else: st.write("No data to show for today's pie chart.")

    # -- Weekly Summary --
    st.subheader("Weekly Summary")
    # Filtering last 7 days of data
    seven_days_ago = now.date() - timedelta(days=6)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    last_7_df = df[df["date"] >= seven_days_ago]

    # Reodrering to start week on Sunday
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

    # -- Tab2: Log Food --
with tab2:
    col1, col2 = st.columns([2, 1.5])
    with col1:
        st.subheader("Log Food")
        with st.expander("Log Food", expanded=False):
            if "form_submitted" not in st.session_state:
                st.session_state["form_submitted"] = False
        # Reset Fields
            if st.session_state["form_submitted"]:
                st.session_state["food_name_input"] = ""
                st.session_state["calories_input"] = 0
                st.session_state["protein_input"] = 0
                st.session_state["carb_input"] = 0
                st.session_state["fat_input"] = 0
                st.session_state["form_submitted"] = False

            with st.form("food_form"):
                food = st.text_input("Food name", key="food_name_input")
                calories = st.number_input("Calories", min_value=0.0, step=0.1, key="calories_input")
                protein = st.number_input("Protein (g)", min_value=0.0, step=0.1, key="protein_input")
                carbs = st.number_input("Carbs (g)", min_value=0.0, step=0.1, key="carb_input")
                fat = st.number_input("Fat (g)",min_value=0.0, step=0.1, key="fat_input")
                submitted = st.form_submit_button("Add")
    with col2:
# -- Log a Saved Recipe --
        st.subheader("Log a Saved Recipe")
        if recipes: 
            selected_recipe = st.selectbox("Select a recipe to log:", ["-- Select --"] + list(recipes.keys()))
            
            if selected_recipe != "-- Select --":
                recipe_data = recipes[selected_recipe]

                st.markdown(f"**Includes:** {', '.join(recipe_data['foods'])}")
                st.markdown(f"**Calories:** {recipe_data['calories']}, "
                            f"**Protein:** {recipe_data['protein']}g, "
                            f"**Carbs:** {recipe_data['carbs']}g, "
                            f"**Fat:** {recipe_data['fat']}g")

                if st.button(f"Log '{selected_recipe}'"):
                    now = datetime.now(pytz.timezone("America/New_York"))
                    new_row = {
                        "date": now.date().isoformat(),
                        "time": now.strftime("%I:%M %p").lstrip("0"),
                        "food": selected_recipe,
                        "calories": recipe_data["calories"],
                        "protein": recipe_data["protein"],
                        "carbs": recipe_data["carbs"],
                        "fat": recipe_data["fat"]
                    }
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    df.to_csv(DATA_PATH, index=False)
                    st.success(f"'{selected_recipe}' logged!")
                    st.rerun()
        if submitted:
            new_row = {
                "date": now.date().isoformat(),
                "time": now.strftime("%I:%M %p").lstrip("0"),
                "food": food,
                "calories": calories,
                "protein": protein,
                "carbs": carbs,
                "fat": fat
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_csv(DATA_PATH, index=False)
            st.success("Food Logged!")

            st.session_state["form_submitted"] = True
            st.rerun()
        with st.expander("Create a Recipe", expanded=False):
            with st.form("recipe_form", clear_on_submit=True):
                st.caption("Save a recipe with its ingredients and macros. You can edit or delete recipes in the 'Recipes' tab.")
                recipe_name = st.text_input("Recipe Name")
                recipe_foods = st.text_area("Foods (comma separated)")
                recipe_calories = st.number_input("Calories", min_value=0.0, step=0.1)
                recipe_protein = st.number_input("Protein (g)", min_value=0.0, step=0.1)
                recipe_carbs = st.number_input("Carbs (g)", min_value=0.0, step=0.1)
                recipe_fat = st.number_input("Fat (g)", min_value=0.0, step=0.1)
                save_recipe = st.form_submit_button("Create Recipe")

                if save_recipe and recipe_name:
                    if not recipe_name.strip():
                        st.warning("Please enter a valid recipe name.")
                    elif recipe_name in recipes:
                        st.warning("Recipe name already exists. Please choose a different name.")
                    elif not recipe_foods.strip():
                        st.warning("Please enter at least one food item.")
                    else:
                        recipe_foods_list = [food.strip() for food in recipe_foods.split(",")]

                        if not recipe_foods_list or all(food == "" for food in recipe_foods_list):
                            st.warning("Please enter at least one food item.")
                        else:
                            recipes[recipe_name] = {
                                "foods": recipe_foods_list,
                                "calories": recipe_calories,
                                "protein": recipe_protein,
                                "carbs": recipe_carbs,
                                "fat": recipe_fat
                            }
                            with open(RECIPE_PATH, "w") as f:
                                json.dump(recipes, f)
                            st.success("Recipe Saved!")
                            st.session_state["form_submitted"] = True
                            st.rerun()


# -- Logged Entries -- 
    st.subheader("Food Logged Today")

# Filter today's entries - Delete block
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
                        st.success("Entry Deleted")
                        st.rerun()

# Show edit form if triggered
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
            st.success("Entry Updated")
            del st.session_state["edit_row"]
            st.rerun()
        else:
            st.write("No entries logged today.")

# -- Tab3: Recipes --
with tab3:
    # -- Recipe Editor --
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
            with open(RECIPE_PATH, "w") as f:
                json.dump(recipes, f)
            del st.session_state["edit_recipe"]
            st.success("Recipe Updated")
            st.rerun()
        # -- Edit Recipe Button --
        if st.button("Edit", key=f"edit_{edit_recipe}"):
            st.session_state["edit_recipe"] = edit_recipe
            st.rerun()

    # -- View Recipes --
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
                        del recipes[recipe_name]
                        with open(RECIPE_PATH, "w") as f:
                            json.dump(recipes, f)
                        st.success("Recipe Deleted")
                        st.rerun()