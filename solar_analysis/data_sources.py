"""
data_sources.py
================
JOB OF THIS FILE: get raw numbers in. Nothing clever happens here —
no comparisons, no health scores. Just: go fetch the data, hand it back
as a clean table (a "DataFrame").

Two things this file can fetch:
  1. Weather/sunlight data for any location (used to calculate "expected power")
  2. Real panel output data, loaded from a CSV file (used as "actual power")
"""

import pandas as pd
import requests


def get_weather_data(latitude, longitude, start_date, end_date, timezone="Asia/Kolkata"):
    """
    Fetches real historical weather for any location on Earth — free, no signup.
    Returns hourly sunlight strength (W/m^2) and temperature (C).

    Example:
        weather = get_weather_data(12.9716, 77.5946, "2025-06-01", "2025-06-30")
        # -> a table with one row per hour, columns: ghi, temp_air
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "shortwave_radiation,temperature_2m",
        "timezone": timezone,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    hourly = response.json()["hourly"]

    weather = pd.DataFrame({
        "time": pd.to_datetime(hourly["time"]),
        "ghi": hourly["shortwave_radiation"],   # how strong the sunlight was
        "temp_air": hourly["temperature_2m"],   # air temperature
    })
    weather = weather.set_index("time")
    return weather


def get_panel_output_data(csv_path, time_column, power_column):
    """
    Loads real panel output readings from a CSV file exported from an
    inverter's app/portal (SolarEdge, Enphase, Growatt, whatever brand).

    You tell it which column holds the timestamp and which holds the
    power reading, since every inverter brand names these differently.

    Example:
        actual = get_panel_output_data("my_export.csv", time_column="DATE_TIME", power_column="AC_POWER")
    """
    df = pd.read_csv(csv_path)
    df[time_column] = pd.to_datetime(df[time_column])
    df = df.set_index(time_column)
    return df[power_column].rename("actual_kw")


def find_location(place_name):
    """
    Turns a place name (like "Bangalore" or "Koramangala, Bangalore") into
    latitude/longitude coordinates. Free, no signup -- uses Open-Meteo's
    geocoding service (a different, separate API from the weather one).

    Example:
        results = find_location("Bangalore")
        # -> a list of matches, each with name, latitude, longitude, country

    This is what gives the app "freedom to select any location" instead of
    a hardcoded city -- the user types a place name, this finds its
    coordinates, and those coordinates get passed to get_weather_data().
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": place_name, "count": 5}
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    results = response.json().get("results", [])

    return [
        {
            "label": f"{r['name']}, {r.get('admin1', '')}, {r['country']}",
            "latitude": r["latitude"],
            "longitude": r["longitude"],
        }
        for r in results
    ]
