import os
import sys
import json
import math
from datetime import datetime, timedelta, timezone

# Optional dependency for robust timezones if needed, but standard library works well for UTC.
# External API library: requests
try:
    import requests
except ImportError:
    print("Error: The 'requests' library is required to run this script.")
    print("Please install it using: pip install requests")
    sys.exit(1)

# ==========================================
# CONFIGURATION & PARAMETERS
# ==========================================
# GitHub workspace destination directory and file name
OUTPUT_DIR = "placefiles"
OUTPUT_FILE = "cwop_observations.txt"

# WFO Duluth / KDLH Approximate Geographic Boundary Center & Range bounding box
# Min/Max Lat/Lon box roughly framing the Northland WFO area for optimization
LAT_MIN, LAT_MAX = 45.0, 49.5
LON_MIN, LON_MAX = -95.0, -89.0

# Synoptic Data API Configurations (Public open Mesonet usage fallback or custom token)
# Fetch the secure GitHub environment token, fallback to demo if missing
API_TOKEN = os.environ.get("SYNOPTIC_API_TOKEN", "demotoken")
SYNOPTIC_API_URL = "https://api.synopticdata.com/v2/stations/timeseries"

# Icon assets paths on your hosted server or public repo branches
WIND_BARB_ICON_URL = "https://raw.githubusercontent.com/github-actions-wfo/gr2_assets/main/wind_barbs.png"
SKY_COVER_ICON_URL = "https://raw.githubusercontent.com/github-actions-wfo/gr2_assets/main/sky_cover.png"

# ==========================================
# UTILITY HELPER FUNCTIONS
# ==========================================
def sanitize_slp(pressure_mb):
    """Converts a millibar pressure into a 3-digit meteorological code."""
    if pressure_mb is None or math.isnan(pressure_mb):
        return "M"
    try:
        # Standard surface analysis rounding format (take last 3 digits excluding decimals)
        val = int(round(pressure_mb * 10))
        code_str = str(val)[-3:]
        return code_str
    except Exception:
        return "M"

def get_wind_barb_index(speed_knots, direction_deg):
    """
    Computes rotation index slot and file row indexes for standard GR2 wind barbs.
    Returns: (icon_index, rotation_deg)
    """
    if speed_knots is None or speed_knots < 3 or direction_deg is None:
        return 0, 0 # Calm conditions, fallback handled by central sky icon overlay
        
    # Map index boundaries roughly per 5-knot groupings matching NWS visual guides
    # Assumes a wind barb texture sheet split sequentially per step
    base_idx = int(round(speed_knots / 5.0)) * 5
    if base_idx < 5: base_idx = 5
    if base_idx > 100: base_idx = 100
    
    # Return mapping tuple (Asset slot matching your custom texture mapping logic, rotation)
    return base_idx, int(direction_deg)

def get_sky_cover_icon(cloud_cov_str):
    """Maps reported cloud layers directly to visual sprite indices (1 to 5)."""
    mapping = {
        "CLR": 1, "SKC": 1, # Clear
        "FEW": 2,           # Few Clouds
        "SCT": 3,           # Scattered
        "BKN": 4,           # Broken
        "OVC": 5            # Overcast
    }
    return mapping.get(str(cloud_cov_str).upper(), 1)

# ==========================================
# MAIN IMPLEMENTATION LOGIC
# ==========================================
def main():
    print("Initializing dynamic telemetry download routine from Synoptic Networks...")
    
    # 1. Dynamically target the historical looping period matching WFO NEXRAD data windows
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=2) # 2-hour sliding window data dump
    
    api_params = {
        "token": SYNOPTIC_API_TOKEN,
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
        print("Warning: Network returned successfully but no matching active stations found in local bounding coordinates.")
        return

    # 2. Build GR2 Analyst Text Buffers
    placefile_lines = []
    
    # Formatting Header Structure Blocks
    placefile_lines.append("; GR2Analyst Time-Sourced Historical Loop Dataset")
    placefile_lines.append("; Generated dynamically via automated GitHub Action workflows.")
    placefile_lines.append("Refresh: 5")
    placefile_lines.append("Threshold: 999")
    placefile_lines.append(f'IconFile: 1, 32, 32, 16, 16, "{WIND_BARB_ICON_URL}"')
    placefile_lines.append(f'IconFile: 2, 16, 16, 8, 8, "{SKY_COVER_ICON_URL}"')
    placefile_lines.append("Font: 1, 11, 400, 0") # Native presentation mapping engine font
    placefile_lines.append("")

    # 3. Iterating stations and parsing timeframes
    for station in data["STATION"]:
        stid = station.get("STID", "UNKNOWN")
        lat = station.get("LATITUDE")
        lon = station.get("LONGITUDE")
        
        if not lat or not lon:
            continue
            
        observations = station.get("OBSERVATIONS", {})
        timestamps = observations.get("date_time", [])
        
        # Iterate steps through history packets to compile historical loop brackets
        for i, ts_str in enumerate(timestamps):
            try:
                # Convert raw string formats to explicit datetime objects for window calculations
                # Format returned usually matches ISO layout: "2026-08-18T21:42:00Z"
                dt_ob = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                
                # Assign 5-minute visual frames mapping out surrounding radar sweep steps
                window_start = dt_ob - timedelta(minutes=2, seconds=30)
                window_end = dt_ob + timedelta(minutes=2, seconds=30)
                
                start_range = window_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                end_range = window_end.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                continue

            # Extract metrics arrays safely via indices loops
            temp_c = observations.get("air_temp_value_1", [None]*len(timestamps))[i]
            dew_c = observations.get("dew_point_temperature_value_1", [None]*len(timestamps))[i]
            speed_ms = observations.get("wind_speed_value_1", [None]*len(timestamps))[i]
            wind_dir = observations.get("wind_direction_value_1", [None]*len(timestamps))[i]
            slp_mb = observations.get("sea_level_pressure_value_1", [None]*len(timestamps))[i]
            sky_code = observations.get("cloud_layer_1_code_value_1", [None]*len(timestamps))[i]

            # Metric matrix standard conversions to NWS surface configurations
            temp_f = int(round((temp_c * 9/5) + 32)) if temp_c is not None else None
            dew_f = int(round((dew_c * 9/5) + 32)) if dew_c is not None else None
            speed_kt = int(round(speed_ms * 1.94384)) if speed_ms is not None else 0
            slp_str = sanitize_slp(slp_mb)
            sky_icon_idx = get_sky_cover_icon(sky_code)
            
            # String parsing filters fallback checks
            tf_display = f"{temp_f}" if temp_f is not None else "M"
            df_display = f"{dew_f}" if dew_f is not None else "M"
            
            # 4. Constructing Structured Output Strings
            placefile_lines.append(f"TimeRange: {start_range} {end_range}")
            placefile_lines.append(f"Object: {lat:.5f},{lon:.5f}")
            
            # Core Node Layers Intersections
            # Sky Coverage Node (Layer 2 Asset File)
            placefile_lines.append(f"  Icon: 0,0,0,2,{sky_icon_idx}")
            
            # Dynamic Rotated Wind Barb Node Layer (Layer 1 Asset File)
            if speed_kt >= 3 and wind_dir is not None:
                barb_val, rot_angle = get_wind_barb_index(speed_kt, wind_dir)
                if barb_val > 0:
                    placefile_lines.append(f"  Icon: 0,0,{rot_angle},1,{barb_val}")

            # Text Quadrant Positioning Distributions Map
            placefile_lines.append(f'  Text: 0, -18, 1, "{stid}"') # Station Tag Identifier Header
            placefile_lines.append(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{tf_display}"') # Temperature Element Left
            placefile_lines.append(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{slp_str}"') # Condensed SLP Indicator Right
            placefile_lines.append(f'  Color: 100 255 100\n  Text: -20, 10, 1, "{df_display}"') # Dew Point Element Left
            
            # Hover contextual presentation metadata blocks
            hover_text = f"Station: {stid} | Temp: {tf_display}F | Dewpt: {df_display}F | Wind: {wind_dir or 0:03d}@{speed_kt}KT | SLP: {slp_mb or 'M'}mb"
            placefile_lines.append(f'  Hover: "{hover_text}"')
            
            placefile_lines.append("End:")
            placefile_lines.append("")

    # 5. Flush output structures to relative paths directories safely
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, OUTPUT_FILE), "w") as f:
        f.write("\n".join(placefile_lines))
        
    print(f"Success! Time-looped script processing completed. Destination file compiled: {os.path.join(OUTPUT_DIR, OUTPUT_FILE)}")

if __name__ == "__main__":
    main()
