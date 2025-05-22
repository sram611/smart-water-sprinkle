import requests
import schedule
import time
from datetime import datetime, timedelta

# --- Configuration ---
ZIP = 60560
WEATHER_API_KEY = ""

NTFY_URL = "https://ntfy.sh/sram611_time_to_sprinkle"

# Temperature thresholds in Fahrenheit (59°F to 86°F)
TEMP_MIN_F = 59
TEMP_MAX_F = 86
RAIN_THRESHOLD_IN = 0.02  # roughly 0.5mm

# Evening hours (5 PM to 8 PM)
EVENING_HOURS = [17, 18, 19, 20]

def send_push_notification(message):
    try:
        requests.post(NTFY_URL, data=message.encode('utf-8'))
    except Exception as e:
        print(f"Notification error: {e}")

def get_lat_lon(zip, api_key):
    url = "https://api.openweathermap.org/geo/1.0/zip"
    params = {"zip": zip, "appid": api_key}
    response = requests.get(url, params=params)
    data = response.json()
    if data:
        return data["lat"], data["lon"]
    else:
        raise ValueError(f"Could not find coordinates for city: {city}")
    
def get_hourly_forecast(lat, lon, api_key):
    url = "https://api.openweathermap.org/data/3.0/onecall"
    params = {
        "lat": lat,
        "lon": lon,
        "exclude": "current,minutely,daily,alerts",
        "units": "imperial",
        "appid": api_key
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()["hourly"]

def choose_ideal_times(hourly_forecasts):
    """Return all evening slots with ideal temp and no rain within next 48 hours."""
    ideal_times = []

    for forecast in hourly_forecasts[:48]:  # next 48 hours
        dt = datetime.fromtimestamp(forecast["dt"])
        hour = dt.hour

        if hour in EVENING_HOURS:
            temp = forecast["temp"]
            rain = forecast.get("rain", {}).get("1h", 0.0) or 0.0
            print(f"Checking forecast for {dt}: Temp: {temp}°F, Rain: {rain} in")

            if TEMP_MIN_F <= temp <= TEMP_MAX_F and rain < RAIN_THRESHOLD_IN:
                ideal_times.append(dt)

    return ideal_times

def check_and_schedule():
    print(f"[{datetime.now()}] Checking forecast for watering...")

    try:
        lat, lon = get_lat_lon(ZIP, WEATHER_API_KEY)
        hourly = get_hourly_forecast(lat, lon, WEATHER_API_KEY)
    except Exception as e:
        print(f"Weather fetch failed: {e}")
        return

    ideal_times = choose_ideal_times(hourly)
    if not ideal_times:
        send_push_notification("⚠️ No good watering time found for today.")
        return

    # Format time range nicely (e.g. 5:00 PM, 6:00 PM, etc.)
    formatted_times = [dt.strftime("%-I:%M %p") for dt in ideal_times]
    time_range_msg = ", ".join(formatted_times)

    send_push_notification(
        f"💧 Ideal lawn watering times: {time_range_msg}. Conditions look great!"
    )

print("🧠 Smart Lawn Watering Assistant running...")
check_and_schedule()