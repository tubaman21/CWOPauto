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
    # ⏱️ Look back 3 hours to capture slower or slightly delayed CWOP updates
    start_time = (now - datetime.timedelta(hours=3)).strftime("%Y%m%d%H%M")
    end_time = now.strftime("%Y%m%d%H%M")
    
    url = "https://synopticdata.com"
    
    # Broad regional box footprint that free-tier accounts can pull if fields are default
    params = {
        "token": token,
        "bbox": bbox,
        "start": start_time,
        "end": end_time,
        "obtimezone": "UTC",
        "providers": "cwop"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeatherDataCollector/1.0 (NWS Project Integration)"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        
        if "authentication returned" in response.text.lower() or "summary" not in response.text.lower():
            print("\n❌ SYNOPTIC API FIREWALL REFUSAL:")
            print(f"👉 Raw Server Notice Text: {response.text.strip()}\n")
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
        slp_str = f"{float(slp_val):.1f}"
        parts = slp_str.replace('.', '')
        return parts[-3:]
    except ValueError:
        return ""

def format_time_range(dt_obj):
    """Generates 5-minute GR2 format validity brackets."""
    discard = datetime.timedelta(minutes=dt_obj.minute % 5, seconds=dt_obj.second, microseconds=dt_obj.microsecond)
    start = dt_obj - discard
    end = start + datetime.timedelta(minutes=5)
    return f"TimeRange: {start.strftime('%Y-%m-%dT%H:%M:%SZ')} {end.strftime('%Y-%m-%dT%H:%M:%SZ')}"

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
    
    # 🗺️ Broad WFO Duluth footprint covering Northeast MN, Northwest WI, and Western Lake Superior
    TARGET_BBOX = "-95.0,45.0,-89.0,49.5"
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    raw_data = fetch_weather_data(SYNOPTIC_API_TOKEN, TARGET_BBOX)
    
    if "STATION" not in raw_data or not raw_data["STATION"]:
        print("⚠ Operational Warning: API returned success code, but zero stations reported in this bounding box.")
        return

    with open(output_file_path, "w", encoding="utf-8") as f:
        f.write("Title: CWOP Looping Surface Observations\n")
        f.write("Refresh: 5\n\n")
        
        # Base wind barb/sky cover pointers (Placeholder asset domains)
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n')
        f.write('IconFile: 2, 16, 16, 8, 8, "https://githubusercontent.com"\n\n')
        
        station_count = 0
        total_plots = 0
        
        for st in raw_data["STATION"]:
            st_id = st.get("STID", "UNKN")
            lat = st.get("LATITUDE")
            lon = st.get("LONGITUDE")
            
            if not lat or not lon:
                continue
                
            observations = st.get("OBSERVATIONS", {})
            time_list = observations.get("date_time", [])
            
            # Fetch variables using .get() fallback options to prevent structural exceptions
            temps = observations.get("air_temp", []) if observations.get("air_temp") else []
            dps = observations.get("dew_point_temperature", []) if observations.get("dew_point_temperature") else []
            w_speeds = observations.get("wind_speed", []) if observations.get("wind_speed") else []
            w_dirs = observations.get("wind_direction", []) if observations.get("wind_direction") else []
            slps = observations.get("sea_level_pressure", []) if observations.get("sea_level_pressure") else []
            
            station_has_plots = False
            
            for i, time_str in enumerate(time_list):
                try:
                    dt = datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
                except ValueError:
                    continue
                
                # Check list lengths explicitly before pulling structural indexes
                t_f = c_to_f(temps[i]) if i < len(temps) else None
                d_f = c_to_f(dps[i]) if i < len(dps) else None
                w_kt = ms_to_kt(w_speeds[i]) if i < len(w_speeds) else 0
                w_dir = float(w_dirs[i]) if (i < len(w_dirs) and w_dirs[i] is not None) else None
                slp_str = format_slp(slps[i]) if i < len(slps) else ""
                
                # We need at least a valid temperature metric to render a surface analysis plot
                if t_f is None:
                    continue
                    
                f.write(f"{format_time_range(dt)}\n")
                f.write(f"Object: {float(lat):.5f},{float(lon):.5f}\n")
                f.write("  Threshold: 999\n")
                
                # 1. Plot Rotated Wind Barb (if wind speed is significant)
                if w_dir is not None and w_kt >= 3:
                    # Generic formula mapping 5-knot speed intervals to a base 25-icon grid
                    barb_idx = min(max(int(round(w_kt / 5)), 1), 25)
                    f.write(f"  Icon: 0,0,{int(w_dir)},1,{barb_idx}\n")
                else:
                    # Opaque placeholder circle for calm/missing icons
                    f.write("  Icon: 0,0,0,2,1\n")
                
                # 2. Add Surrounding Text Elements
                f.write(f'  Text: 0, -18, 1, "{st_id}"\n')
                f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{t_f}"\n')
                if d_f is not None:
                    f.write(f'  Color: 100 255 100\n  Text: -20, 10, 1, "{d_f}"\n')
                if slp_str:
                    f.write(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{slp_str}"\n')
                
                f.write(f'  Hover: "Station: {st_id} \\nTime: {dt.strftime("%H:%M")} UTC \\nTemp: {t_f}F \\nDew Point: {d_f if d_f is not None else "M"}F \\nWind: {int(w_dir) if w_dir else 0}@{w_kt}kt"\n')
                f.write("End:\n\n")
                
                total_plots += 1
                station_has_plots = True
                
            if station_has_plots:
                station_count += 1
                
        print(f"🎉 Success! Processed {station_count} unique reporting stations.")
        print(f"📝 Wrote {total_plots} total time-looped frame blocks to {output_file_path}")

if __name__ == "__main__":
    main()
