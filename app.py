import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import altair as alt
import os

version = 0.12

st.set_page_config(layout="wide")

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
except FileNotFoundError:
    df = pd.DataFrame(columns=["date", "food", "calories", "protein", "carbs", "fat"])

# -- Today's Progress Section -- 
st.subheader("Today's Progress")
st.caption(f"Target: {goals['calories']} cal, {goals['protein']}g protein, {goals['carbs']}g carbs, {goals['fat']}g fat")
today = datetime.now().date().isoformat()
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
# Side-by-side columns
progress_col, pie_col = st.columns([2,1])

# - Progress Bars -
with progress_col:
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
# - Pie Chart - 
with pie_col:
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
        
        color_scale = alt.Scale(
            domain=["Protein", "Carbs", "Fat"],
            range=["#6A5ACD", "#FFD700", "#3CB371"]
        )

        pie_chart = alt.Chart(pie_df).mark_arc(innerRadius=80).encode(
            theta = "Calories:Q",
            color = alt.Color("Macro:N", scale=color_scale),
            tooltip = ["Macro", "Calories"]
        ).properties(
            title="Macro Calorie Breakdown"
        )
        st.altair_chart(pie_chart, use_container_width=True)
    else: st.write("No data to show for today's pie chart.")
# -- Edit Goals Section --
goal_button_label = "Edit Macro Goals" if st.session_state["macro_goals"] else "Set Macro Goals"
if st.button(goal_button_label):
    st.session_state["editing_goals"] = True
if "username" in st.session_state:
    if st.session_state.get("editing_goals"):
        render_goal_editor(st.session_state["username"], existing_goals=st.session_state["macro_goals"])

# -- Input Section --
if "form_submitted" not in st.session_state:
    st.session_state["form_submitted"] = False
    # Reset Fields
if st.session_state["form_submitted"]:
    st.session_state["food_name_input"] = ""
    st.session_state["calories_input"] = 0.0
    st.session_state["protein_input"] = 0.0
    st.session_state["carb_input"] = 0.0
    st.session_state["fat_input"] = 0.0
    st.session_state["form_submitted"] = False

st.subheader("Add Food")
with st.form("food_form"):
    food = st.text_input("Food name", key="food_name_input")
    calories = st.number_input("Calories", min_value=0.0, step=0.1, key="calories_input")
    protein = st.number_input("Protein (g)", min_value=0.0, step=0.1, key="protein_input")
    carbs = st.number_input("Carbs (g)", min_value=0.0, step=0.1, key="carb_input")
    fat = st.number_input("Fat (g)",min_value=0.0, step=0.1, key="fat_input")
    submitted = st.form_submit_button("Add")

if submitted:
    new_row = {
        "date": datetime.now().date().isoformat(),
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

# -- Weekly Summary --
st.subheader("Weekly Summary")
# Filtering last 7 days of data
seven_days_ago = datetime.now().date() - timedelta(days=6)
df["date"] = pd.to_datetime(df["date"]).dt.date
last_7_df = df[df["date"] >= seven_days_ago]

# Reodrering to start week on Sunday
all_days = pd.date_range(seven_days_ago, datetime.now().date())
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

# -- Logged Entries -- 
st.subheader("Food Logged Today")

    # Filter today's entries - Delete block
if not today_df.empty:
    for actual_idx, row in today_df.iterrows():
        with st.expander(f"{row['food']} - {row['calories']} cal"):
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