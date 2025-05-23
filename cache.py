import os, json
from datetime import datetime, timedelta

CACHE_FILE = "/data/weather_cache.json"

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