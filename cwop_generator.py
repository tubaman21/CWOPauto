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

LAT_MIN, LAT_MAX = 43.0, 50.0
LON_MIN, LON_MAX = -97.0, -87.0

SYNOPTIC_API_URL = "https://api.synopticdata.com/v2/stations/timeseries"
WIND_BARB_ICON_URL = "https://raw.githubusercontent.com/ktrue/metar-placefile/master/windbarbs_75_new.png"
SKY_COVER_ICON_URL = "https://raw.githubusercontent.com/ktrue/metar-placefile/master/cloudcover_new.png"

# Set lookback window in hours
LOOKBACK_HOURS = 6

NETWORK_THRESHOLDS = {
    "RAWS": 999,
    "MnDOT": 100,
    "WisDOT": 100,
    "DOT": 100,
    "Mesonet": 80,
    "CWOP": 60
}

NETWORK_ORDER = ["RAWS", "MnDOT", "WisDOT", "DOT", "Mesonet", "CWOP"]

# ==========================================
# UTILITY HELPER FUNCTIONS
# ==========================================
def normalize_pressure_to_mb(val):
    """Detects raw unit type (Pa, inHg, or mb) and converts cleanly to millibars/hPa."""
    if val is None or math.isnan(val) or val <= 0:
        return None
    try:
        val = float(val)
        if val > 50000:
            return val / 100.0
        elif 20.0 <= val <= 33.0:
            return val * 33.8639
        elif 800.0 <= val <= 1100.0:
            return val
        else:
            return None
    except Exception:
        return None

def sanitize_slp(pressure_mb):
    if pressure_mb is None or math.isnan(pressure_mb):
        return "M"
    try:
        val = int(round(pressure_mb * 10))
        code_str = str(val)[-3:]
        return code_str
    except Exception:
        return "M"

def format_precip(precip_mm):
    """Converts mm to inches and formats as .XX or X.XX. Returns None if 0 or missing."""
    if precip_mm is None or math.isnan(precip_mm):
        return None
    try:
        precip_in = precip_mm * 0.0393701
        # Check against 0.005 in to safely handle floating-point precision
        if precip_in < 0.005:
            return None
        if precip_in < 1.0:
            return f"{precip_in:.2f}".lstrip('0')  # Returns ".25" instead of "0.25"
        return f"{precip_in:.2f}"
    except Exception:
        return None

def calculate_dewpoint_c(temp_c, rh_percent):
    if temp_c is None or rh_percent is None or rh_percent <= 0:
        return None
    try:
        a = 17.625
        b = 243.04
        alpha = ((a * temp_c) / (b + temp_c)) + math.log(rh_percent / 100.0)
        return (b * alpha) / (a - alpha)
    except Exception:
        return None

def get_wind_barb_index(speed_knots, direction_deg):
    if speed_knots is None or speed_knots < 3 or direction_deg is None:
        return 0, 0
    idx = int(round(speed_knots / 5.0))
    if idx < 1: idx = 1
    if idx > 26: idx = 26 
    return idx, int(direction_deg)

def get_sky_cover_icon(cloud_cov_str):
    return 5            

def get_obs_val(observations, var_base, index, fallback_list):
    """Iterates through set_1, set_2, set_1d, etc. to prevent skipping multi-sensor stations."""
    for key in observations.keys():
        if key.startswith(var_base) and observations[key] and index < len(observations[key]):
            val = observations[key][index]
            if val is not None:
                return val
    return fallback_list[index]

# ==========================================
# MAIN IMPLEMENTATION LOGIC
# ==========================================
def main():
    print("Initializing dynamic telemetry download routine from Synoptic Networks...")
    
    api_token = os.environ.get("SYNOPTIC_API_TOKEN")
    if not api_token:
        print("Error: SYNOPTIC_API_TOKEN environment variable is missing!")
        sys.exit(1)
    
    run_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=LOOKBACK_HOURS)
    
    api_params = {
        "token": api_token,
        "bbox": f"{LON_MIN},{LAT_MIN},{LON_MAX},{LAT_MAX}",
        "vars": "air_temp,dew_point_temperature,relative_humidity,wind_speed,wind_direction,wind_gust,sea_level_pressure,altimeter,pressure,precip_accum,precip_accum_one_hour,precip_accum_twenty_four_hour",
        "varsoperator": "OR",
        "start": start_time.strftime("%Y%m%d%H%M"),
        "end": end_time.strftime("%Y%m%d%H%M"),
        "obtimezone": "UTC",
        "output": "json",
        "extra": "metadata"
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

    network_blocks = {}
    rain_counter = 0  # Debug counter

    for station in data["STATION"]:
        stid = station.get("STID", "UNKNOWN").upper()
        
        mnet_id = str(station.get("MNET_ID", ""))
        mnet_short = str(station.get("MNET_SHORTNAME", "")).upper()
        mnet_name = str(station.get("MNET_NAME", "")).upper()
        
        if mnet_id == "153" or "CWOP" in mnet_short or "CWOP" in mnet_name:
            mnet = "CWOP"
        elif mnet_id == "2" or "RAWS" in mnet_short:
            mnet = "RAWS"
        elif mnet_id == "66" or "MNDOT" in mnet_short or "MINNESOTA DOT" in mnet_name or stid.startswith("MN"):
            mnet = "MnDOT"
        elif mnet_id == "67" or "WISDOT" in mnet_short or "WISCONSIN DOT" in mnet_name or stid.startswith("WI"):
            mnet = "WisDOT"
        elif "DOT" in mnet_short or "DOT" in mnet_name:
            mnet = "DOT"
        elif mnet_short and mnet_short != "UNKNOWN":
            mnet = mnet_short
        else:
            if (len(stid) >= 4 and stid[0] in ['C', 'E', 'F', 'G', 'W', 'A', 'D', 'K']) or stid.startswith("CW") or stid.startswith("DW"):
                mnet = "CWOP"
            else:
                mnet = "Mesonet"
        
        # --- FILTERS ---
        if stid in ["SLVM5", "PNGW3", "DISW3", "SXHW3", "ROAM4", "WMNM5"]:
            continue

        if mnet_short == "HADS" or mnet_id == "128":
            continue

        if len(stid) in [3, 4] and stid.isalpha() and not stid.startswith("D"):
            continue
            
        if stid.startswith("NDBC") or (len(stid) == 5 and stid.isdigit()):
            continue
        # ---------------
        
        try:
            lat = float(station.get("LATITUDE"))
            lon = float(station.get("LONGITUDE"))
        except (TypeError, ValueError):
            continue
            
        observations = station.get("OBSERVATIONS", {})
        timestamps = observations.get("date_time", [])
        
        station_lines = []
        for i, ts_str in enumerate(timestamps):
            try:
                dt_ob = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                
                window_start = dt_ob
                if i == 0:
                    window_start = dt_ob - timedelta(minutes=5)
                
                window_end = dt_ob + timedelta(hours=1)
                if i + 1 < len(timestamps):
                    next_dt_ob = datetime.strptime(timestamps[i + 1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    if window_end > next_dt_ob:
                        window_end = next_dt_ob
                
                start_range = window_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                end_range = window_end.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                continue

            fallback = [None] * len(timestamps)
            
            temp_c = get_obs_val(observations, "air_temp", i, fallback)
            dew_c = get_obs_val(observations, "dew_point_temperature", i, fallback)
            rh_pct = get_obs_val(observations, "relative_humidity", i, fallback)
            speed_ms = get_obs_val(observations, "wind_speed", i, fallback)
            gust_ms = get_obs_val(observations, "wind_gust", i, fallback)
            wind_dir = get_obs_val(observations, "wind_direction", i, fallback)
            
            raw_slp = get_obs_val(observations, "sea_level_pressure", i, fallback)
            raw_alt = get_obs_val(observations, "altimeter", i, fallback)
            raw_stn = get_obs_val(observations, "pressure", i, fallback)
            
            slp_mb = normalize_pressure_to_mb(raw_slp)
            if slp_mb is None:
                slp_mb = normalize_pressure_to_mb(raw_alt)
            if slp_mb is None:
                slp_mb = normalize_pressure_to_mb(raw_stn)

            # --- PRECIPITATION EXTRACTION ---
            raw_p1h = get_obs_val(observations, "precip_accum_one_hour", i, fallback)
            if raw_p1h is None:
                raw_p1h = get_obs_val(observations, "precip_accum", i, fallback)
            
            raw_p24h = get_obs_val(observations, "precip_accum_twenty_four_hour", i, fallback)

            p1h_str = format_precip(raw_p1h)
            p24h_str = format_precip(raw_p24h)

            if p1h_str:
                rain_counter += 1

            sky_code = get_obs_val(observations, "cloud_layer_1_code", i, fallback)

            if dew_c is None and temp_c is not None and rh_pct is not None:
                dew_c = calculate_dewpoint_c(temp_c, rh_pct)

            temp_f = int(round((temp_c * 9/5) + 32)) if temp_c is not None else None
            dew_f = int(round((dew_c * 9/5) + 32)) if dew_c is not None else None
            
            # QC Checks
            if temp_f is not None and (temp_f < -50 or temp_f > 130):
                temp_f = None
            if dew_f is not None and (dew_f < -60 or dew_f > 100):
                dew_f = None
            if temp_f is not None and dew_f is not None and dew_f > temp_f:
                dew_f = None

            slp_str = sanitize_slp(slp_mb)
            sky_icon_idx = get_sky_cover_icon(sky_code)
            
            tf_display = f"{temp_f}" if temp_f is not None else "M"
            df_display = f"{dew_f}" if dew_f is not None else "M"
            wind_dir_display = int(wind_dir) if wind_dir is not None else 0
            
            speed_mph = int(round(speed_ms * 2.23694)) if speed_ms is not None else 0
            gust_mph = int(round(gust_ms * 2.23694)) if gust_ms is not None else None
            speed_kt = int(round(speed_ms * 1.94384)) if speed_ms is not None else 0

            color_temp = "255 100 100"   # Light Red
            color_dew  = "100 255 100"   # Light Green
            color_slp  = "255 255 255"   # White
            color_rain = "0 255 255"     # Cyan

            max_wind_mph = gust_mph if (gust_mph is not None) else speed_mph

            if max_wind_mph >= 45:
                color_barb = "255 0 255"    # Magenta (45+ MPH)
                color_temp = "255 50 255"
            elif max_wind_mph >= 35:
                color_barb = "255 255 0"    # Yellow (35-44 MPH)
                color_temp = "255 200 0"
            else:
                color_barb = "255 255 255"  # White (<35 MPH)

            if gust_mph is not None and gust_mph > speed_mph and gust_mph >= 12:
                wind_display = f"{wind_dir_display:03d}@{speed_mph}G{gust_mph}MPH"
            else:
                wind_display = f"{wind_dir_display:03d}@{speed_mph}MPH"

            p1h_hover = f"{p1h_str}\"" if p1h_str else "0.00\""
            p24h_hover = f"{p24h_str}\"" if p24h_str else "0.00\""
            
            hover_text = (
                f"Type: {mnet} | Station: {stid} | Temp: {tf_display}F | Dewpt: {df_display}F | "
                f"Wind: {wind_display} | SLP: {f'{slp_mb:.1f}' if slp_mb else 'M'}mb | "
                f"Rain 1hr: {p1h_hover} | Rain 24hr: {p24h_hover}"
            )
            
            station_lines.append(f"TimeRange: {start_range} {end_range}")
            station_lines.append(f"Object: {lat:.5f},{lon:.5f}")
            
            if speed_kt >= 3 and wind_dir is not None:
                barb_val, rot_angle = get_wind_barb_index(speed_kt, wind_dir)
                if barb_val > 0:
                    station_lines.append(f"  Color: {color_barb}")
                    station_lines.append(f"  Icon: 0,0,{rot_angle},1,{barb_val}")

            station_lines.append("  Color: 255 255 255")
            station_lines.append(f'  Icon: 0,0,0,2,{sky_icon_idx}, "{hover_text}"')
            
            # Temperature: Top-Left (-20, 10)
            if tf_display != "M":
                station_lines.append(f"  Color: {color_temp}")
                station_lines.append(f'  Text: -20, 10, 1, "{tf_display}"')
            
            # Pressure / SLP Code: Top-Right (20, 10)
            if slp_str != "M":
                station_lines.append(f"  Color: {color_slp}")
                station_lines.append(f'  Text: 20, 10, 1, "{slp_str}"')
                
            # Dew Point: Bottom-Left (-20, -10)
            if df_display != "M":
                station_lines.append(f"  Color: {color_dew}")
                station_lines.append(f'  Text: -20, -10, 1, "{df_display}"')

            # 1-Hour Rainfall: Bottom-Right (20, -10) - Hidden if < 0.01"
            if p1h_str:
                station_lines.append(f"  Color: {color_rain}")
                station_lines.append(f'  Text: 20, -10, 1, "{p1h_str}"')
            
            station_lines.append("End:")
            station_lines.append("")

        if station_lines:
            network_blocks.setdefault(mnet, []).extend(station_lines)

    # --- COMPILE FINAL PLACEFILE ---
    header_lines = [
        f'Title: CWOP Surface Observations ({run_time})',
        "; GR2Analyst Time-Sourced Historical Loop Dataset",
        f"; Generated dynamically: {run_time}",
        "Refresh: 5",
        f'IconFile: 1, 43, 68, 29, 67, "{WIND_BARB_ICON_URL}"',
        f'IconFile: 2, 15, 15, 8, 8, "{SKY_COVER_ICON_URL}"',
        "Font: 1, 11, 400, 0",
        ""
    ]

    body_lines = []
    
    processed_nets = set()
    for net in NETWORK_ORDER:
        if net in network_blocks:
            threshold = NETWORK_THRESHOLDS.get(net, 60)
            body_lines.append(f"; --- Network: {net} (Threshold: {threshold} NM) ---")
            body_lines.append(f"Threshold: {threshold}\n")
            body_lines.extend(network_blocks[net])
            processed_nets.add(net)

    for net, lines in network_blocks.items():
        if net not in processed_nets:
            threshold = NETWORK_THRESHOLDS.get(net, 60)
            body_lines.append(f"; --- Network: {net} (Threshold: {threshold} NM) ---")
            body_lines.append(f"Threshold: {threshold}\n")
            body_lines.extend(lines)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    full_output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    
    with open(full_output_path, "w") as f:
        f.write("\n".join(header_lines + body_lines))
        
    print(f"Success! Processed dataset. Found {rain_counter} total observation points with measurable rainfall (>=0.01\").")
    print(f"Destination file compiled: {full_output_path}")

if __name__ == "__main__":
    main()
