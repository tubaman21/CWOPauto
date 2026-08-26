import os
import sys
import json
import math
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    print("Error: The 'requests' library is required to run this script.")
    print("Please install it using: pip install requests")
    sys.exit(1)

# ==========================================
# CONFIGURATION & PARAMETERS
# ==========================================
OUTPUT_DIR = "placefiles"
OUTPUT_FILE = "cwop_observations.txt"

LAT_MIN, LAT_MAX = 45.0, 49.5
LON_MIN, LON_MAX = -95.0, -89.0

SYNOPTIC_API_URL = "https://api.synopticdata.com/v2/stations/timeseries"
WIND_BARB_ICON_URL = "https://raw.githubusercontent.com/ktrue/metar-placefile/master/windbarbs_75_new.png"
SKY_COVER_ICON_URL = "https://raw.githubusercontent.com/ktrue/metar-placefile/master/cloudcover_new.png"

# ==========================================
# UTILITY HELPER FUNCTIONS
# ==========================================
def sanitize_slp(pressure_mb):
    if pressure_mb is None or math.isnan(pressure_mb):
        return "M"
    try:
        val = int(round(pressure_mb * 10))
        code_str = str(val)[-3:]
        return code_str
    except Exception:
        return "M"

def get_wind_barb_index(speed_knots, direction_deg):
    if speed_knots is None or speed_knots < 3 or direction_deg is None:
        return 0, 0
        
    base_idx = int(round(speed_knots / 5.0)) * 5
    if base_idx < 5: base_idx = 5
    if base_idx > 100: base_idx = 100
    
    return base_idx, int(direction_deg)

def get_sky_cover_icon(cloud_cov_str):
    mapping = {
        "CLR": 1, "SKC": 1,
        "FEW": 2,          
        "SCT": 3,          
        "BKN": 4,          
        "OVC": 5           
    }
    return mapping.get(str(cloud_cov_str).upper(), 1)

# ==========================================
# MAIN IMPLEMENTATION LOGIC
# ==========================================
def main():
    print("Initializing dynamic telemetry download routine from Synoptic Networks...")
    
    # Securely pull the token from the GitHub Actions environment
    api_token = os.environ.get("SYNOPTIC_API_TOKEN")
    if not api_token:
        print("Error: SYNOPTIC_API_TOKEN environment variable is missing!")
        sys.exit(1)
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=2)
    
    # Token parameter re-added here
    api_params = {
        "token": api_token,
        "bbox": f"{LON_MIN},{LAT_MIN},{LON_MAX},{LAT_MAX}",
        "vars": "air_temp,dew_point_temperature,wind_speed,wind_direction,sea_level_pressure,cloud_layer_1_code",
        "start": start_time.strftime("%Y%m%d%H%M"),
        "end": end_time.strftime("%Y%m%d%H%M"),
        "obtimezone": "UTC",
        "providers": "cwop"
    }
    
    try:
        response = requests.get(SYNOPTIC_API_URL, params=api_params, timeout=25)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Network processing exception during API fetch: {e}")
        sys.exit(1)
        
    if "STATION" not in data or not data["STATION"]:
        print("Warning: Network returned successfully but no matching active stations found.")
        return

    placefile_lines = []
    
    placefile_lines.append("; GR2Analyst Time-Sourced Historical Loop Dataset")
    placefile_lines.append("; Generated dynamically via automated GitHub Action workflows.")
    placefile_lines.append("Refresh: 5")
    placefile_lines.append("Threshold: 999")
    placefile_lines.append(f'IconFile: 1, 32, 32, 16, 16, "{WIND_BARB_ICON_URL}"')
    placefile_lines.append(f'IconFile: 2, 16, 16, 8, 8, "{SKY_COVER_ICON_URL}"')
    placefile_lines.append("Font: 1, 11, 400, 0")
    placefile_lines.append("")

    for station in data["STATION"]:
        stid = station.get("STID", "UNKNOWN")
        
        try:
            lat = float(station.get("LATITUDE"))
            lon = float(station.get("LONGITUDE"))
        except (TypeError, ValueError):
            # Skips the station if lat/lon are missing or invalid
            continue
            
        observations = station.get("OBSERVATIONS", {})
        timestamps = observations.get("date_time", [])
        
        for i, ts_str in enumerate(timestamps):
            try:
                dt_ob = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                
                window_start = dt_ob - timedelta(minutes=2, seconds=30)
                window_end = dt_ob + timedelta(minutes=2, seconds=30)
                
                start_range = window_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                end_range = window_end.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                continue

            # FIX 1: Updated keys from _value_1 to _set_1 to match Synoptic's JSON format
            fallback = [None] * len(timestamps)
            temp_c = (observations.get("air_temp_set_1") or fallback)[i]
            dew_c = (observations.get("dew_point_temperature_set_1") or fallback)[i]
            speed_ms = (observations.get("wind_speed_set_1") or fallback)[i]
            wind_dir = (observations.get("wind_direction_set_1") or fallback)[i]
            slp_mb = (observations.get("sea_level_pressure_set_1") or fallback)[i]
            
            # Note: Cloud codes sometimes still use _value_1 depending on the provider, 
            # so we use a dual-fallback just in case to be safe!
            sky_code = (observations.get("cloud_layer_1_code_set_1") or observations.get("cloud_layer_1_code_value_1") or fallback)[i]

            temp_f = int(round((temp_c * 9/5) + 32)) if temp_c is not None else None
            dew_f = int(round((dew_c * 9/5) + 32)) if dew_c is not None else None
            speed_kt = int(round(speed_ms * 1.94384)) if speed_ms is not None else 0
            slp_str = sanitize_slp(slp_mb)
            sky_icon_idx = get_sky_cover_icon(sky_code)
            
            tf_display = f"{temp_f}" if temp_f is not None else "M"
            df_display = f"{dew_f}" if dew_f is not None else "M"
            
            placefile_lines.append(f"TimeRange: {start_range} {end_range}")
            placefile_lines.append(f"Object: {lat:.5f},{lon:.5f}")
            
            placefile_lines.append(f"  Icon: 0,0,0,2,{sky_icon_idx}")
            
            if speed_kt >= 3 and wind_dir is not None:
                barb_val, rot_angle = get_wind_barb_index(speed_kt, wind_dir)
                if barb_val > 0:
                    placefile_lines.append(f"  Icon: 0,0,{rot_angle},1,{barb_val}")

            hover_text = f"Station: {stid} | Temp: {tf_display}F | Dewpt: {df_display}F | Wind: {wind_dir or 0:03d}@{speed_kt}KT | SLP: {slp_mb or 'M'}mb"
            
            # FIX 2: Order of strings swapped! {stid} (Display) is now first, {hover_text} (Hover) is second.
            placefile_lines.append(f'  Text: 0, -18, 1, "{stid}", "{hover_text}"')
            
            placefile_lines.append(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{tf_display}"')
            placefile_lines.append(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{slp_str}"')
            placefile_lines.append(f'  Color: 100 255 100\n  Text: -20, 10, 1, "{df_display}"')
            
            # The invalid Hover keyword line has been completely removed!
            
            placefile_lines.append("End:")
            placefile_lines.append("")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, OUTPUT_FILE), "w") as f:
        f.write("\n".join(placefile_lines))
        
    print(f"Success! Time-looped script processing completed. Destination file compiled: {os.path.join(OUTPUT_DIR, OUTPUT_FILE)}")

if __name__ == "__main__":
    main()
