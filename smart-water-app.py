import requests
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

def group_by_day_and_range(hourly_forecasts):
    """Group ideal hourly times into daily time ranges."""
    ideal_times = []

    for forecast in hourly_forecasts[:48]:  # Next 48 hours
        dt = datetime.fromtimestamp(forecast["dt"])
        hour = dt.hour

        if hour in EVENING_HOURS:
            temp = forecast["temp"]
            rain = forecast.get("rain", {}).get("1h", 0.0) or 0.0

            if TEMP_MIN_F <= temp <= TEMP_MAX_F and rain < RAIN_THRESHOLD_IN:
                ideal_times.append(dt)

    if not ideal_times:
        return {}

    # Group into day -> list of time ranges
    grouped = {}
    start = end = ideal_times[0]

    for current in ideal_times[1:]:
        if (current - end) == timedelta(hours=1):
            end = current
        else:
            day_key = start.date()
            grouped.setdefault(day_key, []).append((start, end))
            start = end = current
    # Add final range
    grouped.setdefault(start.date(), []).append((start, end))

    return grouped

def format_day_label(day):
    today = datetime.now().date()
    if day == today:
        return "Today"
    elif day == today + timedelta(days=1):
        return "Tomorrow"
    else:
        return day.strftime("%A")

def check_and_schedule():
    print(f"[{datetime.now()}] Checking forecast for watering...")

    try:
        lat, lon = get_lat_lon(ZIP, WEATHER_API_KEY)
        hourly = get_hourly_forecast(lat, lon, WEATHER_API_KEY)
    except Exception as e:
        print(f"Weather fetch failed: {e}")
        return

    grouped_ranges = group_by_day_and_range(hourly)

    if not grouped_ranges:
        send_push_notification("⚠️ No good watering time found for today or tomorrow.")
        return

    lines = ["💧 Ideal watering times:"]
    for day, ranges in sorted(grouped_ranges.items()):
        day_label = format_day_label(day)
        range_strs = []
        for start, end in ranges:
            if start == end:
                range_strs.append(start.strftime("%-I %p"))
            else:
                range_strs.append(f"{start.strftime('%-I %p')} to {end.strftime('%-I %p')}")
        lines.append(f"• {day_label}: {', '.join(range_strs)}")

    send_push_notification("\n".join(lines))

print("🧠 Smart Lawn Watering Assistant running...")
check_and_schedule()