import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import altair as alt

# Load macro goals
with open("config/macro_goals.json") as f:
    goals = json.load(f)

# -- Welcome -- 
st.sidebar.title("Welcome")
username = st.sidebar.text_input("Enter your name",value="guest")

# Load Existing Data
DATA_PATH = "Data/logs/{username}_macro_log.csv"
try: 
    df = pd.read_csv(DATA_PATH)
except FileNotFoundError:
    df = pd.DataFrame(columns=["date", "food", "calories", "protein", "carbs", "fat"])



# -- Input Section --
st.title("Macro Tracker")

st.subheader("Add Food Entry")
with st.form("food_form"):
    food = st.text_input("Food name")
    calories = st.number_input("Calories", min_value=0.0, step=0.1)
    protein = st.number_input("Protein", min_value=0.0, step=0.1)
    carbs = st.number_input("Carbs", min_value=0.0, step=0.1)
    fat = st.number_input("Fat",min_value=0.0, step=0.1)
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

# -- Today's Summary -- 
st.subheader("Today's Progress")
today = datetime.now().date().isoformat()
today_df = df[df["date"] == today]

if not today_df.empty:
    totals = today_df[["calories", "protein", "carbs", "fat"]].sum()
    percentages = {
        macro: (totals[macro] / goals[macro]) * 100 for macro in goals
    }
    for macro in goals: 
       st.metric(label=f"{macro.capitalize()}", value=F"{totals[macro]} / {goals[macro]}")
       st.progress(min(int(percentages[macro]), 100))
else: 
    st.write("No entries today.")

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

if not today_df.empty:
    # Reset index so we can reference rows easily
    today_df = today_df.reset_index(drop=True)

    for idx, row in today_df.iterrows():
        with st.expander(f"{row['food']} - {row['calories']} cal"):
            st.write(f"Protein: {row['protein']}g, Carbs: {row['carbs']}g, Fat: {row['fat']}g")

            col1, col2 = st.columns([1,1])
            with col1:
                if st.button("Edit", key=f"edit_{idx}"):
                    st.session_state["edit_row"] = idx
            with col2:
                if st.button("Delete", key=f"delete_{idx}"):
                    df = df.drop(today_df.index[idx])
                    df.to_csv(DATA_PATH, index=False)
                    st.success("Entry Deleted")
                    st.rerun()

    # Show edit form if triggered
    if "edit_row" in st.session_state:
        edit_idx = st.session_state["edit_row"]
        row = today_df.loc[edit_idx]

        st.subheader(f"Edit Entry: {row['food']}")
        with st.form("edit_form"):
            new_food = st.text_input("Food name", value = row["food"])
            new_cal = st.number_input("Calories", value=float(row["calories"]), step=0.1)
            new_pro = st.number_input("Protein (g)", value=float(row["protein"]), step=0.1)
            new_carb = st.number_input("Carbs (g)", value=float(row["carbs"]), step=0.1)
            new_fat = st.number_input("Fats (g)", value=float(row["fat"]), step=0.1)
            save = st.form_submit_button("Save")
        
        if save:
            idx_to_update = today_df.index[edit_idx]
            df.loc[idx_to_update, ["food", "calories", "protein", "carbs", "fat"]] = [
                new_food, new_cal, new_pro, new_carb, new_fat
            ]
            df.to_csv(DATA_PATH, index=False)
            st.success("Entry Updated")
            del st.session_state["edit_row"]
            st.rerun()
else:
    st.write("No entries logged today.")
