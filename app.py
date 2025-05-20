import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import altair as alt
import os

st.set_page_config(layout="wide")

def render_goal_editor(username, existing_goals=None, on_submit_step='main'):
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
        st.session_state["step"] = on_submit_step
        st.session_state["editing_goals"] = False
        st.rerun()

# -- Init session state keys -- 
if "step" not in st.session_state:
    st.session_state["step"] = "username"
if "username" not in st.session_state:
    st.session_state["username"] = ""

# -- Step 1: Enter username 
if st.session_state["step"] == "username":
    st.title("Welcome to the best fucking macro tracker of all time.")
    st.markdown("Enter your name to start tracking your goddamn macros:")
    user_input = st.text_input("Your Name:", key="username_input")
    if st.button("Continue"):
        st.session_state["username"] = user_input.strip().lower()
        goal_path = f"Data/logs/{st.session_state['username']}_goals.json"
        if os.path.exists(goal_path) and "macro_goals" not in st.session_state:
            with open(goal_path) as f:
                st.session_state["macro_goals"] = json.load(f)
        st.session_state["step"] = "startup_questions"
        st.rerun()
# -- Step 2: Startup Questions
elif st.session_state["step"] == "startup_questions":
    st.title("A Few Quick Questions")
    render_goal_editor(st.session_state["username"], on_submit_step="main")
# -- Step 3: Main App
elif st.session_state["step"] == "main":
    st.title("Macro Tracker")
    st.markdown(f"Logged in as: `{st.session_state['username']}`")
    goals = st.session_state["macro_goals"]

    username = st.session_state["username"]
    goals = st.session_state["macro_goals"]
    os.makedirs("Data/logs",exist_ok=True)

    # Load Existing Data
    DATA_PATH = f"Data/logs/{username}_macro_log.csv"
    try: 
        df = pd.read_csv(DATA_PATH)
    except FileNotFoundError:
        df = pd.DataFrame(columns=["date", "food", "calories", "protein", "carbs", "fat"])

    # -- Today's Summary -- 
    st.subheader("Today's Progress")
    today = datetime.now().date().isoformat()
    today_df = df[df["date"] == today]

    if False:
        today_totals = today_df[["calories", "protein", "carbs", "fat"]].sum()
        remaining = {k: max(goals[k] - today_totals.get(k,0), 0) for k in goals}

        # Total Calories view   
        col1, col2, col3 = st.columns([1,2,1])

        with col1:
            st.markdown(f"### {remaining['calories']:.0f}")
            st.caption("Remaining")
        with col2:
            percent = (today_totals["calories"] / goals["calories"]) * 100
            st.markdown(f"""
                <div style='text-align: center'>
                    <div style='font-size: 48px; font-weight: bold;'>{int(today_totals['calories'])}</div>
                    <div style='color: gray; margin-top: -10px;'>Consumed</div>
                    <progress value="{min(percent,100)}" max="100" style="width: 100%; height: 8px; border-radius: 4px;"></progress>
                </div>
                """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"### {goals['calories']}")
            st.caption("Target")
        
        macro_colors = {
            "protein": "#FF6F61",
            "fat": "#FFD700",
            "carbs": "#3CB371"
        }

        for macro in ["protein", "carbs", "fat"]:
            value = today_totals.get(macro,0)
            goal = goals[macro]
            percent = min((value / goal) * 100, 100)

            st.markdown(f"""
            <div style="margin-bottom: 12px;">
                <div style="font-weight: 600; color: #aaa;">{macro.capitalize()}</div>
                <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="flex-grow: 1; margin-right: 10px; background: #333; height: 8px; border-radius: 4px;">
                    <div style="width: {percent:.1f}%; height: 8px; background-color: {macro_colors[macro]}; border-radius: 4px;"></div>
                </div>
                <div style="white-space: nowrap;">{int(value)} / {goal}g</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    if not today_df.empty:
        totals = today_df[["calories", "protein", "carbs", "fat"]].sum() if not today_df.empty else{
            "calories": 0,
            "protein": 0,
            "carbs":0,
            "fat":0
        }
        percentages = {
            macro: (totals[macro] / goals[macro]) * 100 for macro in goals
        }
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
    if st.button("Edit Goals"):
        st.session_state["editing_goals"] = True
    if st.session_state.get("editing_goals"):
        render_goal_editor(st.session_state["username"], existing_goals=st.session_state["macro_goals"], on_submit_step="main")
    
    # -- Input Section --
    st.subheader("Add Food")
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