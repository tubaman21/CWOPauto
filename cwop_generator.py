import os
import sys
import datetime
import requests
import pytz

def fetch_weather_data(token, bbox):
    """Fetches real-time weather stations timeseries data from Synoptic API."""
    print("Initializing dynamic telemetry download routine from Synoptic Networks...")
    
    if token == "demotoken":
        print("\n❌ CRITICAL STOP: The script is using 'demotoken'. GitHub secrets are not being read!")
        sys.exit(1)
        
    now = datetime.datetime.now(pytz.utc)
    # ⏱️ CHANGE 1: Reduce historical depth from 3 hours to 1.5 hours to dramatically cut data size
    start_time = (now - datetime.timedelta(hours=1, minutes=30)).strftime("%Y%m%d%H%M")
    end_time = now.strftime("%Y%m%d%H%M")
    
    url = "https://api.synopticdata.com/v2/stations/timeseries"
    
    # 📝 CHANGE 2: Request ONLY critical telemetry paths to ensure payload fits free restrictions
    params = {
        "token": token,
        "bbox": bbox,
        "vars": "air_temp,dew_point_temperature,wind_speed,wind_direction", # Dropped complex cloud layers
        "start": start_time,
        "end": end_time,
        "obtimezone": "UTC",
        "providers": "cwop"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeatherDataCollector/1.0 (NWS Project Integration)"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=25)
        
        # EXPLICIT ERROR INTERCEPTOR: Read what Synoptic says before crashing
        if "authentication returned" in response.text.lower() or "summary" not in response.text.lower():
            print("\n❌ SYNOPTIC API FIREWALL REFUSAL:")
            print(f"👉 Raw Server Notice Text: {response.text.strip()}\n")
            print("Action Needed: If the notice text says 'Authentication failed', re-check your token string.")
            print("If it indicates allowance profiles, your account cannot query this specific service path.")
            sys.exit(1)
            
        return response.json()
        
    except Exception as e:
        print(f"\n❌ Network processing exception during API fetch: {e}")
        sys.exit(1)

def format_slp(slp_val):
    """Formats raw millibar sea-level pressure into standard 3-digit NWS shorthand."""
    if slp_val is None:
        return ""
    try:
        # e.g., 1013.2 -> 132 | 998.7 -> 987
        slp_str = f"{float(slp_val):.1f}"
        parts = slp_str.replace('.', '')
        return parts[-3:]
    except ValueError:
        return ""

def format_time_range(dt_obj):
    """Generates 5-minute GR2 format validity brackets."""
    # Round down to the nearest 5-minute interval for stability
    discard = datetime.timedelta(minutes=dt_obj.minute % 5, seconds=dt_obj.second, microseconds=dt_obj.microsecond)
    start = dt_obj - discard
    end = start + datetime.timedelta(minutes=5)
    return f"TimeRange: {start.strftime('%Y-%m-%dT%H:%M:%SZ')} {end.strftime('%Y-%m-%dT%H:%M:%SZ')}"

def c_to_f(c_val):
    """Converts Celsius to Fahrenheit integer."""
    if c_val is None:
        return None
    return int(round((float(c_val) * 9/5) + 32))

def ms_to_kt(ms_val):
    """Converts meters per second to knots integer."""
    if ms_val is None:
        return 0
    return int(round(float(ms_val) * 1.94384))

def get_sky_cover_idx(cloud_code):
    """Maps cloud strings into a 1-5 icon layer index."""
    # Maps basic codes to an icon sheet column index
    mapping = {"CLR": 1, "FEW": 2, "SCT": 3, "BKN": 4, "OVC": 5}
    return mapping.get(str(cloud_code).upper(), 1)

def get_wind_barb_idx(speed_kt):
    """Calculates wind speed icon sheet base offsets."""
    if speed_kt < 3:
        return 0 # Calm symbol
    # Base index configuration matching standard 5-knot increment barb sheets
    idx = int(round(speed_kt / 5))
    return min(max(idx, 1), 25)

def main():
    # Securely extract token directly within main operational loop execution scope
    SYNOPTIC_API_TOKEN = os.environ.get("SYNOPTIC_API_TOKEN", "demotoken")
    
    # SAFE DEBUG PRINTS
    print("--- ENVIRONMENT INJECTION VERIFICATION ---")
    print(f"Token variable length: {len(SYNOPTIC_API_TOKEN)} characters")
    if SYNOPTIC_API_TOKEN == "demotoken":
        print("Status: ❌ FAILED. Script fell back to hardcoded demo string.")
    else:
        print("Status:  Loaded variable from GitHub Environment.")
    print("------------------------------------------")
    
    # Tightened footprint (West Longitude, South Latitude, East Longitude, North Latitude)
    TARGET_BBOX = "-92.5,46.5,-91.5,47.2"
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    # Query API Data
    raw_data = fetch_weather_data(SYNOPTIC_API_TOKEN, TARGET_BBOX)
    
    if "STATION" not in raw_data or not raw_data["STATION"]:
        print("⚠ Operational Warning: API returned valid payload structural schema but contains 0 active stations.")
        return

    # Write output placefile formatting arrays
    with open(output_file_path, "w", encoding="utf-8") as f:
        # Define structural Placefile headers
        f.write("Title: CWOP Looping Surface Observations\n")
        f.write("Refresh: 5\n\n")
        
        # Define mock remote Icon Textures pointers
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n')
        f.write('IconFile: 2, 16, 16, 8, 8, "https://githubusercontent.com"\n\n')
        
        station_count = 0
        
        for st in raw_data["STATION"]:
            st_id = st.get("STID", "UNKN")
            lat = st.get("LATITUDE")
            lon = st.get("LONGITUDE")
            
            if not lat or not lon:
                continue
                
            observations = st.get("OBSERVATIONS", {})
            time_list = observations.get("date_time", [])
            
            # Extract variables
            temps = observations.get("air_temp", [])
            dps = observations.get("dew_point_temperature", [])
            w_speeds = observations.get("wind_speed", [])
            w_dirs = observations.get("wind_direction", [])
            slps = observations.get("sea_level_pressure", [])
            clouds = observations.get("cloud_layer_1_code", [])
            
            # Loop historically through all packets reported by this station
            for i, time_str in enumerate(time_list):
                try:
                    dt = datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
                except ValueError:
                    continue
                
                # Safely parse indexing boundaries
                t_f = c_to_f(temps[i]) if i < len(temps) else None
                d_f = c_to_f(dps[i]) if i < len(dps) else None
                w_kt = ms_to_kt(w_speeds[i]) if i < len(w_speeds) else 0
                w_dir = float(w_dirs[i]) if (i < len(w_dirs) and w_dirs[i] is not None) else None
                slp_str = format_slp(slps[i]) if i < len(slps) else ""
                cloud_str = clouds[i] if i < len(clouds) else "CLR"
                
                # Skip plots if core data elements are fully null
                if t_f is None:
                    continue
                    
                # Print explicit time structural envelope
                f.write(f"{format_time_range(dt)}\n")
                f.write(f"Object: {float(lat):.5f},{float(lon):.5f}\n")
                f.write("  Threshold: 999\n")
                
                # 1. Centered Sky Cover Icon
                sky_idx = get_sky_cover_idx(cloud_str)
                f.write(f"  Icon: 0,0,0,2,{sky_idx}\n")
                
                # 2. Rotated Centered Wind Barb
                if w_dir is not None and w_kt >= 3:
                    barb_idx = get_wind_barb_idx(w_kt)
                    f.write(f"  Icon: 0,0,{int(w_dir)},1,{barb_idx}\n")
                
                # 3. Text Fields: Station ID, Temp, Dew Point, SLP
                f.write(f'  Text: 0, -18, 1, "{st_id}"\n')
                f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{t_f}"\n')
                f.write(f'  Color: 100 255 100\n  Text: -20, 10, 1, "{d_f if d_f is not None else ""}"\n')
                if slp_str:
                    f.write(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{slp_str}"\n')
                
                # Hover Block Details
                f.write(f'  Hover: "Station: {st_id} \\nTime: {dt.strftime("%H:%M")} UTC \\nTemp: {t_f}F \\nDew Point: {d_f}F \\nWind: {int(w_dir) if w_dir else 0}@{w_kt}kt"\n')
                f.write("End:\n\n")
                station_count += 1
                
        print(f"Success! Correctly generated {station_count} looping frame segments in {output_file_path}")

if __name__ == "__main__":
    main()
