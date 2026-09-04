"""
health_engine.py
=================
JOB OF THIS FILE: this is the "brain" of the app. It takes the raw numbers
that data_sources.py fetched, and turns them into an answer to the one
question that matters: "is this panel healthy or not?"

It does three things, in order:
  1. Turn sunlight data into "expected power" (how much the panel SHOULD make)
  2. Compare that to "actual power" (how much it REALLY made)
  3. Flag any day where the gap between the two is unusually large
"""

import pandas as pd
import numpy as np


def calculate_expected_power(weather, capacity_kw):
    """
    STEP 1: "How much power should this panel have made?"

    The idea: on a hot, cloudy day, even a perfectly healthy panel makes
    less power than on a cool, sunny day. This function accounts for that,
    so we're always comparing against a FAIR expectation for that exact day
    -- not just a flat number.

    weather       -> table with columns 'ghi' (sunlight strength) and 'temp_air'
    capacity_kw   -> the panel's rated size, e.g. 5.0 for a 5kW system

    Returns: expected power, in kW, for every hour in the weather table
    """
    # Sunlight strength is measured in W/m^2. Divide by 1000 to turn it into
    # a simple "how full is the tank" fraction, then scale by the panel's size.
    sunlight_fraction = weather["ghi"] / 1000.0

    # Panels lose a little efficiency when they get hot. This knocks off
    # roughly 0.4% for every degree above 25C -- a well-known rule of thumb.
    heat_penalty = 1 - 0.004 * (weather["temp_air"] - 25).clip(lower=0)

    expected_kw = capacity_kw * sunlight_fraction * heat_penalty
    return expected_kw.clip(lower=0).rename("expected_kw")


def calculate_health(expected_kw, actual_kw, sensitivity=1.5):
    """
    STEP 2 + 3: compare "should have" vs "actually did", then flag problem days.

    expected_kw   -> output from calculate_expected_power()
    actual_kw     -> real readings from data_sources.get_panel_output_data()
    sensitivity   -> how strict the "flag this as a problem" trigger is.
                     Lower number = flags more things (more sensitive).
                     Higher number = only flags bigger, more obvious problems.

    Returns three things:
        daily_health  -> one health score per day (1.0 = perfect, 0.8 = making 80% of expected)
        anomaly_days  -> True/False for each day: was this flagged as a problem?
        details       -> the full hour-by-hour table, in case you want to inspect it
    """
    # Line up the two data sources by matching timestamps
    combined = pd.concat([expected_kw, actual_kw], axis=1).dropna()

    # Only judge performance during meaningful daylight -- comparing during
    # nighttime (when both numbers are ~0) would be meaningless noise
    is_daylight = combined["expected_kw"] > 0.3
    combined["ratio"] = np.where(
        is_daylight,
        combined["actual_kw"] / combined["expected_kw"].clip(lower=0.01),
        np.nan,
    )

    # Averaging to one number per day smooths out minor noise (a passing
    # cloud, a brief reading glitch) so we only react to real patterns
    daily_health = combined["ratio"].resample("1D").mean().rename("daily_health")

    # "Is today unusual compared to this panel's own recent normal?"
    # rather than some fixed number -- this way it adapts to each panel/site.
    # IMPORTANT: shift(1) means "look only at PAST days" -- otherwise a bad
    # day would end up included in its own baseline, making it look less
    # unusual than it really is.
    recent_average = daily_health.shift(1).rolling(7, min_periods=3).mean()
    recent_variation = daily_health.shift(1).rolling(7, min_periods=3).std()
    how_unusual = (daily_health - recent_average) / recent_variation

    anomaly_days = how_unusual < -sensitivity

    return daily_health, anomaly_days, combined


def calculate_daily_expected_energy(expected_kw):
    """
    Turns hour-by-hour expected power into ONE total per day, in kWh.

    Why this exists: someone manually typing in numbers doesn't have
    hour-by-hour readings -- they know things like "we generated 18 kWh
    yesterday." So we need to turn our hourly expected_kw into the same
    daily-total shape, to compare like against like.

    (Each hourly kW reading, added up over 24 of them, gives kWh for the day
    -- kWh is just "kW multiplied by how many hours it ran".)
    """
    return expected_kw.resample("1D").sum().rename("expected_kwh")


def calculate_health_from_manual_entries(expected_daily_kwh, actual_daily_kwh, sensitivity=1.5):
    """
    Same idea as calculate_health() above, but for manually-typed daily
    totals instead of detailed hourly readings from a file.

    expected_daily_kwh  -> output from calculate_daily_expected_energy()
    actual_daily_kwh    -> a table the user typed in by hand: one row per
                            day, with the kWh they generated that day

    Returns the same three things as calculate_health(): daily_health,
    anomaly_days, and the combined details table.
    """
    combined = pd.concat([expected_daily_kwh, actual_daily_kwh], axis=1).dropna()
    combined["ratio"] = combined["actual_kwh"] / combined["expected_kwh"].clip(lower=0.01)
    daily_health = combined["ratio"].rename("daily_health")

    recent_average = daily_health.shift(1).rolling(7, min_periods=3).mean()
    recent_variation = daily_health.shift(1).rolling(7, min_periods=3).std()
    how_unusual = (daily_health - recent_average) / recent_variation

    anomaly_days = how_unusual < -sensitivity
    return daily_health, anomaly_days, combined
