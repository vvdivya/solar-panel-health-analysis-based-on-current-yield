"""
app_sprint1.py
==============
SPRINT 1 SCOPE: the Panel Owner's core loop only.
  1. Add panel details (location + size)
  2. See expected yield calculated automatically
  3. Upload or manually enter actual yield
  4. See the comparison + plain-language feedback

Deliberately NOT included yet (later sprints): login/accounts, carbon
accounting, Installer/Admin roles, email/SMS notifications, the landing page.

Run with:
    python -m streamlit run app_sprint1.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from data_sources import get_weather_data, get_panel_output_data, find_location
from health_engine import calculate_expected_power, calculate_health

st.set_page_config(page_title="Solar Yield Comparison — Sprint 1 Demo", layout="wide")
st.title("☀️ Solar Panel Yield Comparison")
st.caption("Sprint 1: add your panel, see expected yield, upload actual yield, get feedback.")

MIN_DAYS_FOR_CONFIDENT_FLAGGING = 3
IDEAL_DAYS_FOR_FLAGGING = 7


# ---------------------------------------------------------------------------
# STEP 1: PANEL DETAILS
# ---------------------------------------------------------------------------
st.header("1️⃣  Panel details")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📍 Location")
    place_name = st.text_input("Search for a city/place", value="Bangalore")
    if "location_matches" not in st.session_state:
        st.session_state.location_matches = None
    if st.button("Search location"):
        matches = find_location(place_name)
        if not matches:
            st.error("No matches found. Try a different spelling.")
        else:
            st.session_state.location_matches = matches

    if st.session_state.location_matches:
        labels = [m["label"] for m in st.session_state.location_matches]
        chosen_label = st.selectbox("Confirm the right match:", labels)
        chosen = next(m for m in st.session_state.location_matches if m["label"] == chosen_label)
        lat, lon = chosen["latitude"], chosen["longitude"]
        st.success(f"Using: {chosen['label']} ({lat:.2f}, {lon:.2f})")
    else:
        lat, lon = 12.9716, 77.5946
        st.info("Using default: Bangalore (search above to change)")

with col2:
    st.subheader("🔧 Panel size")
    preset = st.selectbox(
        "Choose a size, or Custom",
        ["Small residential (3 kW)", "Medium residential (5 kW)", "Large residential (10 kW)", "Custom"],
    )
    presets = {"Small residential (3 kW)": 3.0, "Medium residential (5 kW)": 5.0, "Large residential (10 kW)": 10.0}
    capacity_kw = st.number_input("Enter capacity (kW)", value=5.0, min_value=0.1) if preset == "Custom" else presets[preset]

    with st.expander("Optional: panel orientation (improves accuracy)"):
        tilt = st.number_input("Tilt (degrees)", value=int(round(lat)), min_value=0, max_value=90)
        st.caption("Defaulted to your latitude, a common rule of thumb, if left unchanged.")

st.divider()


# ---------------------------------------------------------------------------
# STEP 2: DATE RANGE + EXPECTED YIELD (shown as soon as panel details exist)
# ---------------------------------------------------------------------------
st.header("2️⃣  Expected yield")

date_col1, date_col2 = st.columns(2)
with date_col1:
    start_date = st.date_input("Start date", value=pd.Timestamp.today() - pd.Timedelta(days=14))
with date_col2:
    end_date = st.date_input("End date", value=pd.Timestamp.today())

with st.spinner("Fetching weather data and calculating expected yield..."):
    try:
        weather = get_weather_data(lat, lon, str(start_date), str(end_date))
        expected_kw = calculate_expected_power(weather, capacity_kw)
        expected_daily_kwh = expected_kw.resample("1D").sum()
        fetch_ok = True
    except Exception as e:
        fetch_ok = False
        st.error(f"Couldn't fetch weather data: {e}")

if fetch_ok:
    total_expected = expected_daily_kwh.sum()
    avg_daily = expected_daily_kwh.mean()
    m1, m2 = st.columns(2)
    m1.metric("Total expected yield (period)", f"{total_expected:,.1f} kWh")
    m2.metric("Average expected per day", f"{avg_daily:,.1f} kWh")

    fig0, ax0 = plt.subplots(figsize=(11, 2.8))
    ax0.plot(expected_daily_kwh.index, expected_daily_kwh, color="#5B8DEF", marker="o")
    ax0.set_ylabel("Expected kWh/day")
    st.pyplot(fig0)
    st.caption("This is calculated automatically from your location and panel size — no action needed from you.")

st.divider()


# ---------------------------------------------------------------------------
# STEP 3: ACTUAL YIELD — upload or manual entry
# ---------------------------------------------------------------------------
st.header("3️⃣  Your actual yield")

entry_mode = st.radio("How do you want to provide your actual generation data?", ["Upload a CSV", "Type it in by hand"], horizontal=True)

actual_daily_kwh = None

if entry_mode == "Upload a CSV":
    template = pd.DataFrame({"DATE_TIME": ["2025-06-01 00:00:00", "2025-06-01 01:00:00"], "AC_POWER": [0.0, 0.0]})
    st.download_button(
        "📄 Download a sample CSV template",
        data=template.to_csv(index=False),
        file_name="sample_inverter_template.csv",
        mime="text/csv",
        help="Your file should have one timestamp column and one power (kW) column, like this.",
    )

    uploaded_file = st.file_uploader("Upload your inverter's CSV export", type="csv")
    st.caption("⚠️ Using the sample/demo CSV? It's synthetic data, not tied to real weather for your dates — expect the percentages to look off. It's meant to demonstrate the mechanism, not give an accurate reading. Real inverter data will be accurate.")
    if uploaded_file is not None:
        time_col = st.text_input("Which column is the timestamp?", value="DATE_TIME")
        power_col = st.text_input("Which column is the power reading (kW)?", value="AC_POWER")
        try:
            uploaded_file.seek(0)
            actual_kw = get_panel_output_data(uploaded_file, time_col, power_col)
            actual_daily_kwh = actual_kw.resample("1D").sum()
            st.success(f"Loaded {actual_daily_kwh.notna().sum()} days of actual data.")
        except Exception as e:
            st.error(
                f"Couldn't read that file — please check the column names match your file exactly. "
                f"(Technical detail: {e})"
            )

else:
    st.caption("Enter the total kWh your panel generated each day (check your inverter app or meter).")
    default_rows = pd.DataFrame({
        "Date": pd.date_range(start=start_date, end=min(end_date, pd.Timestamp.today().date()), freq="D").date,
        "Generated (kWh)": [None] * len(pd.date_range(start=start_date, end=min(end_date, pd.Timestamp.today().date()), freq="D")),
    })
    edited = st.data_editor(
        default_rows,
        num_rows="dynamic",
        use_container_width=True,
        key="manual_entry",
        column_config={
            "Generated (kWh)": st.column_config.NumberColumn("Generated (kWh)", min_value=0.0, step=0.1, format="%.1f"),
        },
    )
    edited["Generated (kWh)"] = pd.to_numeric(edited["Generated (kWh)"], errors="coerce")
    edited = edited.dropna(subset=["Generated (kWh)"])
    if not edited.empty:
        actual_daily_kwh = pd.Series(edited["Generated (kWh)"].values, index=pd.to_datetime(edited["Date"])).sort_index()
        actual_daily_kwh.index = actual_daily_kwh.index.tz_localize(expected_daily_kwh.index.tz) if expected_daily_kwh.index.tz else actual_daily_kwh.index

st.divider()


# ---------------------------------------------------------------------------
# STEP 4: COMPARISON + FEEDBACK
# ---------------------------------------------------------------------------
st.header("4️⃣  Comparison & feedback")

if actual_daily_kwh is None or actual_daily_kwh.empty:
    st.info("⬆️ Add your actual yield above to see the comparison and feedback.")
else:
    combined = pd.concat([expected_daily_kwh.rename("expected"), actual_daily_kwh.rename("actual")], axis=1).dropna()

    if combined.empty:
        st.warning("The dates in your actual data don't overlap with the expected-yield date range above. Check your dates and try again.")
    else:
        n_days = len(combined)

        # --- honest handling of limited history ---
        if n_days < MIN_DAYS_FOR_CONFIDENT_FLAGGING:
            st.warning(
                f"📊 You have {n_days} day(s) of overlapping data. We need at least "
                f"{MIN_DAYS_FOR_CONFIDENT_FLAGGING} days (ideally {IDEAL_DAYS_FOR_FLAGGING}+) before we can "
                f"reliably flag unusual days — for now, here's the raw comparison so you can see the numbers."
            )
        else:
            if n_days < IDEAL_DAYS_FOR_FLAGGING:
                st.caption(f"ℹ️ Based on {n_days} days — flagging will get more reliable as more days are added.")

        combined["expected"] = pd.to_numeric(combined["expected"], errors="coerce")
        combined["actual"] = pd.to_numeric(combined["actual"], errors="coerce")
        combined = combined.dropna()
        combined["ratio"] = combined["actual"] / combined["expected"].clip(lower=0.1)
        avg_health = combined["ratio"].mean()

        # --- plain-language feedback ---
        if avg_health >= 1.5:
            verdict, color, msg = (
                "Unusually high output — worth double-checking",
                "warning",
                "Actual output is far above what's expected for your panel size and location. "
                "This usually means the panel capacity entered doesn't match your real system, "
                "or the uploaded data is in different units than expected (e.g. watts instead of kW). "
                "It's rarely the panel actually overperforming by this much."
            )
        elif avg_health >= 0.9:
            verdict, color, msg = "Healthy", "success", "Your panel is performing close to expectations. No action needed."
        elif avg_health >= 0.75:
            verdict, color, msg = "Slightly underperforming", "warning", "Output is a bit below expected — worth keeping an eye on. Common causes: light dust buildup or minor shading."
        else:
            verdict, color, msg = "Significantly underperforming", "error", "Output is well below what's expected for your location and panel size. Common causes: heavy soiling, shading, or a hardware fault — worth a physical check."

        getattr(st, color)(f"**{verdict}** ({avg_health:.0%} of expected output on average) — {msg}")

        m1, m2, m3 = st.columns(3)
        m1.metric("Average health score", f"{avg_health:.0%}")
        m2.metric("Days compared", n_days)
        m3.metric("Total actual vs expected", f"{combined['actual'].sum():,.0f} / {combined['expected'].sum():,.0f} kWh")

        fig1, ax1 = plt.subplots(figsize=(11, 3.5))
        ax1.plot(combined.index, combined["expected"], label="Expected", color="#5B8DEF", marker="o")
        ax1.plot(combined.index, combined["actual"], label="Actual", color="#F2545B", marker="o")
        ax1.set_ylabel("kWh/day")
        ax1.legend()
        st.pyplot(fig1)

        st.subheader("Day-by-day breakdown")
        table = pd.DataFrame({
            "Date": combined.index.date,
            "Expected (kWh)": combined["expected"].round(1),
            "Actual (kWh)": combined["actual"].round(1),
            "Health score": (combined["ratio"] * 100).round(0).astype(int).astype(str) + "%",
        })
        st.dataframe(table, use_container_width=True)