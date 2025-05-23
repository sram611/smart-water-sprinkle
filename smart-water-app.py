import requests
from datetime import datetime, timedelta
import os, json
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

CACHE_FILE = "weather_cache.json"

app = Flask(__name__)

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
        cache = clean_old_cache(cache)
        return cache
    else:
        # Create an empty cache if the file doesn't exist
        with open(CACHE_FILE, "w") as f:
            json.dump({}, f)
        print("Cache file created.")
        return {}

def save_cache(cache):
    cache = clean_old_cache(cache)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

def clean_old_cache(cache, days_to_keep=7):
    today = datetime.now().date()
    cutoff_date = today - timedelta(days=days_to_keep)
    keys_to_remove = [key for key in cache if datetime.strptime(key, "%Y-%m-%d").date() < cutoff_date]

    for key in keys_to_remove:
        del cache[key]
    return cache


# --- Configuration ---

ZIP = os.getenv("ZIP_CODE", "60560")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
NTFY_URL = os.getenv("NTFY_URL", "https://ntfy.sh/sram611_time_to_sprinkle")

# Temperature thresholds in Fahrenheit (59°F to 86°F)
TEMP_MIN_F = 59
TEMP_MAX_F = 86
RAIN_THRESHOLD_IN = 0.02  # roughly 0.5mm

# Evening hours (5 PM to 8 PM)
EVENING_HOURS = [17, 18, 19, 20]

def log_today_conditions(hourly_forecasts):
    today = datetime.now().date()
    rain_total = 0.0
    max_temp = float("-inf")

    for forecast in hourly_forecasts:
        dt = datetime.fromtimestamp(forecast["dt"])
        if dt.date() == today:
            rain = forecast.get("rain", {}).get("1h", 0.0) or 0.0
            temp = forecast.get("temp", 0.0)
            rain_total += rain
            max_temp = max(max_temp, temp)

    cache = load_cache()
    cache[str(today)] = {
        "rain": round(rain_total, 3),
        "max_temp": round(max_temp, 1)
    }
    save_cache(cache)

def get_recent_cached_rain(days=2):
    cache = load_cache()
    total_rain = 0.0
    max_temp = 0.0
    today = datetime.now().date()

    for i in range(1, days + 1):
        day = today - timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        data = cache.get(date_str)
        if data:
            total_rain += data.get("rain", 0.0)
            max_temp = max(max_temp, data.get("max_temp", 0.0))
    
    return total_rain, max_temp

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
        raise ValueError(f"Could not find coordinates for zip: {zip}")
    
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
    
    # 💾 Log today for future decisions
    log_today_conditions(hourly)

    # 🌧️ Check past rain
    hist_rain, hist_max_temp = get_recent_cached_rain(days=2)
    print(f"📊 Past 2 days: {hist_rain:.2f}\" rain, max temp {hist_max_temp:.1f}°F")

    if hist_rain > 0.3 and hist_max_temp < 80:
        send_push_notification("🌧️ Recent rain and cool temps. No need to water today.")
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

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_and_schedule,
        trigger=CronTrigger(hour=7, minute=0, timezone=ZoneInfo("America/Chicago")),
        id="daily_watering_check",
        replace_existing=True
    )
    scheduler.start()

@app.route("/check", methods=["GET"])
def trigger_check():
    try:
        check_and_schedule()
        return jsonify({"status": "success", "message": "Check completed"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

if __name__ == "__main__":
    print("🧠 Smart Lawn Watering Assistant running...")
    start_scheduler()
    app.run(host="0.0.0.0", port=8000)