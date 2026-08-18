import os
import sys
import datetime
import requests
import pytz

def fetch_weather_data(token, bbox):
    """Fetches the latest real-time weather observations from the Synoptic API."""
    print("Initializing lightweight telemetry download routine from Synoptic Networks...")
    
    if token == "demotoken":
        print("\n❌ CRITICAL STOP: The script is using 'demotoken'. GitHub secrets are not being read!")
        sys.exit(1)
        
    url = "https://api.synopticdata.com/v2/stations/latest"
    
    params = {
        "token": token,
        "bbox": bbox,
        "within": "60",
        "obtimezone": "UTC",
        "providers": "cwop"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeatherDataCollector/1.0 (NWS Project Integration)"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        
        # 1. Print status code immediately to diagnose HTTP issues
        print(f"DEBUG: HTTP Response Status Code: {response.status_code}")
        
        # 2. Check if the response can be decoded as JSON directly
        try:
            return response.json()
        except Exception:
            # 🚨 FORCE-PRINT THE TEXT: Show the user exactly what Synoptic sent back
            print("\n❌ CRITICAL CRASH: Server response could not be parsed into JSON!")
            print("==================== RAW SERVER RESPONSE ====================")
            print(response.text if response.text else "[Response body is entirely empty]")
            print("=============================================================")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Network processing exception during API fetch: {e}")
        sys.exit(1)

def format_slp(slp_val):
    """Formats raw millibar sea-level pressure into standard 3-digit NWS shorthand."""
    if slp_val is None:
        return ""
    try:
        slp_str = f"{float(slp_val):.1f}"
        parts = slp_str.replace('.', '')
        return parts[-3:]
    except (ValueError, TypeError):
        return ""

def c_to_f(c_val):
    """Converts Celsius to Fahrenheit integer."""
    if c_val is None:
        return None
    try:
        return int(round((float(c_val) * 9/5) + 32))
    except (ValueError, TypeError):
        return None

def ms_to_kt(ms_val):
    """Converts meters per second to knots integer."""
    if ms_val is None:
        return 0
    try:
        return int(round(float(ms_val) * 1.94384))
    except (ValueError, TypeError):
        return 0

def main():
    SYNOPTIC_API_TOKEN = os.environ.get("SYNOPTIC_API_TOKEN", "demotoken")
    
    print("--- ENVIRONMENT INJECTION VERIFICATION ---")
    print(f"Token variable length: {len(SYNOPTIC_API_TOKEN)} characters")
    print("------------------------------------------")
    
    # Broad regional box footprint covering Northeast MN, Northwest WI, and Western Lake Superior
    TARGET_BBOX = "-95.0,45.0,-89.0,49.5"
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    raw_data = fetch_weather_data(SYNOPTIC_API_TOKEN, TARGET_BBOX)
    
    if "STATION" not in raw_data or not raw_data["STATION"]:
        print("⚠ Operational Warning: API returned success code, but zero stations reported in this bounding box.")
        return

    with open(output_file_path, "w", encoding="utf-8") as f:
        f.write("Title: CWOP Surface Observations\n")
        f.write("Refresh: 5\n\n")
        
        # Wind barb/sky cover pointers (Placeholder assets)
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n')
        f.write('IconFile: 2, 16, 16, 8, 8, "https://githubusercontent.com"\n\n')
        
        station_count = 0
        
        for st in raw_data["STATION"]:
            st_id = st.get("STID", "UNKN")
            lat = st.get("LATITUDE")
            lon = st.get("LONGITUDE")
            
            if not lat or not lon:
                continue
                
            # The /latest endpoint returns a clean 'LATEST' dictionary inside 'OBSERVATIONS'
            latest_obs = st.get("OBSERVATIONS", {})
            
            # Extract variables safely
            t_raw = latest_obs.get("air_temp_value_1", {}).get("value")
            d_raw = latest_obs.get("dew_point_temperature_value_1", {}).get("value")
            w_speed_raw = latest_obs.get("wind_speed_value_1", {}).get("value")
            w_dir_raw = latest_obs.get("wind_direction_value_1", {}).get("value")
            slp_raw = latest_obs.get("sea_level_pressure_value_1", {}).get("value")
            time_str = latest_obs.get("air_temp_value_1", {}).get("date_time")
            
            if not time_str:
                continue
                
            try:
                dt = datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            except ValueError:
                continue
                
            t_f = c_to_f(t_raw)
            d_f = c_to_f(d_raw)
            w_kt = ms_to_kt(w_speed_raw)
            w_dir = float(w_dir_raw) if w_dir_raw is not None else None
            slp_str = format_slp(slp_raw)
            
            if t_f is None:
                continue
                
            # Generate a 15-minute validity window for this single packet so GR2 displays it cleanly
            start_time = dt - datetime.timedelta(minutes=5)
            end_time = dt + datetime.timedelta(minutes=10)
            f.write(f"TimeRange: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')} {end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
            
            f.write(f"Object: {float(lat):.5f},{float(lon):.5f}\n")
            f.write("  Threshold: 999\n")
            
            # 1. Plot Rotated Wind Barb
            if w_dir is not None and w_kt >= 3:
                barb_idx = min(max(int(round(w_kt / 5)), 1), 25)
                f.write(f"  Icon: 0,0,{int(w_dir)},1,{barb_idx}\n")
            else:
                f.write("  Icon: 0,0,0,2,1\n") # Center plot circle
            
            # 2. Plot Text Surrounding Map Anchor
            f.write(f'  Text: 0, -18, 1, "{st_id}"\n')
            f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{t_f}"\n')
            if d_f is not None:
                f.write(f'  Color: 100 255 100\n  Text: -20, 10, 1, "{d_f}"\n')
            if slp_str:
                f.write(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{slp_str}"\n')
            
            f.write(f'  Hover: "Station: {st_id} \\nTime: {dt.strftime("%H:%M")} UTC \\nTemp: {t_f}F \\nDew Point: {d_f if d_f is not None else "M"}F \\nWind: {int(w_dir) if w_dir else 0}@{w_kt}kt"\n')
            f.write("End:\n\n")
            
            station_count += 1
                
        print(f"🎉 Success! Processed {station_count} active reporting stations across the Duluth region.")

if __name__ == "__main__":
    main()
