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

LAT_MIN, LAT_MAX = 42.5, 50.5
LON_MIN, LON_MAX = -97.5, -86.5

SYNOPTIC_API_URL = "https://api.synopticdata.com/v2/stations/timeseries"
WIND_BARB_ICON_URL = "https://raw.githubusercontent.com/ktrue/metar-placefile/master/windbarbs_75_new.png"
SKY_COVER_ICON_URL = "https://raw.githubusercontent.com/ktrue/metar-placefile/master/cloudcover_new.png"

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

NLI_HYDRO_SUFFIXES = ("M5", "W3", "I4", "N6", "S2", "M4")

# Whitelist both native callsigns and Synoptic's internal short IDs
WHITELIST_STATIONS = {"DW8249", "D8249", "EW9591", "E9591"}

# ==========================================
# UTILITY HELPER FUNCTIONS
# ==========================================
def normalize_pressure_to_mb(val):
    """Converts pressure (Pascals, inHg, or hPa/mb) safely to millibars (hPa)."""
    if val is None or math.isnan(val) or val <= 0:
        return None
    try:
        val = float(val)
        if val > 50000:
            val_mb = val / 100.0
        elif 20.0 <= val <= 33.0:
            val_mb = val * 33.8639
        elif 800.0 <= val <= 1100.0:
            val_mb = val
        else:
            return None

        if 800.0 <= val_mb <= 1100.0:
            return val_mb
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

def format_precip_str(precip_in):
    if precip_in is None or math.isnan(precip_in) or precip_in < 0.01:
        return None
    if precip_in < 1.0:
        return f"{precip_in:.2f}".lstrip('0')
    return f"{precip_in:.2f}"

def calculate_dewpoint_f(temp_f, rh_percent):
    if temp_f is None or rh_percent is None or rh_percent <= 0:
        return None
    try:
        temp_c = (temp_f - 32) * 5/9
        a = 17.625
        b = 243.04
        alpha = ((a * temp_c) / (b + temp_c)) + math.log(rh_percent / 100.0)
        dew_c = (b * alpha) / (a - alpha)
        return int(round((dew_c * 9/5) + 32))
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

def extract_first_valid(observations, var_prefixes, index):
    """
    Scans EVERY key matching var_prefixes across all sensor sets.
    Iterates until it finds the FIRST valid non-null, non-NaN numeric reading at `index`.
    """
    for key, values in observations.items():
        if any(prefix in key for prefix in var_prefixes):
            if isinstance(values, list) and index < len(values):
                val = values[index]
                if val is not None:
                    try:
                        fval = float(val)
                        if not math.isnan(fval):
                            return fval
                    except (ValueError, TypeError):
                        pass
    return None

def get_best_slp(observations, index):
    """Finds Sea Level Pressure, Altimeter, or Station Pressure across any sensor set."""
    slp_raw = extract_first_valid(observations, ["sea_level_pressure"], index)
    if slp_raw is not None:
        p_mb = normalize_pressure_to_mb(slp_raw)
        if p_mb: return p_mb

    alt_raw = extract_first_valid(observations, ["altimeter"], index)
    if alt_raw is not None:
        p_mb = normalize_pressure_to_mb(alt_raw)
        if p_mb: return p_mb

    stn_raw = extract_first_valid(observations, ["pressure"], index)
    if stn_raw is not None:
        p_mb = normalize_pressure_to_mb(stn_raw)
        if p_mb: return p_mb

    return None

def clean_rain_value_to_inches(val):
    """Converts metric precipitation (mm) or raw tipping bucket counts to inches."""
    if val is None or math.isnan(val) or val < 0:
        return 0.0
    try:
        val = float(val)
        if val >= 50.0:
            return val / 100.0
        elif val >= 0.254:
            return val * 0.0393701
        else:
            return val
    except Exception:
        return 0.0

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
    
    api_params = {
        "token": api_token,
        "bbox": f"{LON_MIN},{LAT_MIN},{LON_MAX},{LAT_MAX}",
        "vars": "air_temp,dew_point_temperature,relative_humidity,wind_speed,wind_direction,wind_gust,sea_level_pressure,altimeter,pressure,precip_accum,precip_accum_one_hour,precip_accum_24_hour",
        "varsoperator": "OR",
        "recent": LOOKBACK_HOURS * 60,
        "obtimezone": "UTC",
        "output": "json",
        "extra": "metadata"
    }
    
    try:
        response = requests.get(SYNOPTIC_API_URL, params=api_params, timeout=25)
        if response.status_code != 200:
            print(f"HTTP Error {response.status_code}: {response.text}")
            sys.exit(1)
            
        data = response.json()
    except Exception as e:
        print(f"Network processing exception during API fetch: {e}")
        sys.exit(1)

    response_code = data.get("SUMMARY", {}).get("RESPONSE_CODE") or data.get("RESPONSE_CODE")
    if response_code != 1:
        error_msg = data.get("SUMMARY", {}).get("RESPONSE_MESSAGE") or data.get("RESPONSE_MESSAGE") or response.text
        print(f"Synoptic API Error Code [{response_code}]: {error_msg}")
        sys.exit(1)

    network_blocks = {}
    rain_counter = 0

    if "STATION" in data and data["STATION"]:
        for station in data["STATION"]:
            raw_stid = station.get("STID", "UNKNOWN").upper()

            # Canonical alias translation for CWOP stations in output
            if raw_stid == "D8249":
                stid = "DW8249"
            elif raw_stid == "E9591":
                stid = "EW9591"
            else:
                stid = raw_stid

            mnet_id = str(station.get("MNET_ID", ""))
            mnet_short = str(station.get("MNET_SHORTNAME", "")).upper()
            mnet_name = str(station.get("MNET_NAME", "")).upper()

            # --- NETWORK CLASSIFICATION ---
            if (
                raw_stid in WHITELIST_STATIONS
                or stid in WHITELIST_STATIONS
                or mnet_id == "153" 
                or "CWOP" in mnet_short 
                or "CWOP" in mnet_name
                or stid.startswith("DW") 
                or stid.startswith("CW")
                or stid.startswith("EW")
                or (len(stid) == 5 and stid[0] in ['C', 'E', 'F', 'G', 'W', 'A', 'D', 'K'] and stid[1:].isdigit())
            ):
                mnet = "CWOP"
            elif mnet_id == "2" or "RAWS" in mnet_short:
                mnet = "RAWS"
            elif mnet_id in ["66", "172"] or "MNDOT" in mnet_short or "MN_DOT" in mnet_short or "MINNESOTA" in mnet_name or stid.startswith("MNDOT"):
                mnet = "MnDOT"
            elif mnet_id in ["67", "173"] or "WISDOT" in mnet_short or "WI_DOT" in mnet_short or "WISCONSIN" in mnet_name or stid.startswith("WIDOT"):
                mnet = "WisDOT"
            elif "DOT" in mnet_short or "DOT" in mnet_name:
                mnet = "DOT"
            elif mnet_short and mnet_short != "UNKNOWN":
                mnet = mnet_short
            else:
                mnet = "Mesonet"

            # --- FILTERS (BYPASS IF WHITELISTED) ---
            if raw_stid not in WHITELIST_STATIONS and stid not in WHITELIST_STATIONS:
                # 1. Manual Exclusions
                if stid in ["SLVM5", "PNGW3", "DISW3", "SXHW3", "ROAM4", "WMNM5", "WILM5", "PKGM5", "SDYM5"]:
                    continue

                # 2. Official ASOS/AWOS Airport Stations
                if mnet_id == "1" or mnet_short in ["NWS/FAA", "ASOS", "AWOS"]:
                    continue

                # 3. Strict HADS, USGS, USACE, and River/Dam Hydrologic Gages
                if mnet != "CWOP":
                    if (
                        mnet_short in ["HADS", "USGS", "USACE", "NWS-HYDRO", "COOP"] 
                        or mnet_id in ["128", "130", "208", "180"] 
                        or any(kw in mnet_name for kw in ["HADS", "RIVER", "DAM", "GAGE", "CREEK", "STREAM", "LAKE", "POND"])
                        or stid.endswith(NLI_HYDRO_SUFFIXES)
                        or stid.startswith("HADS")
                    ):
                        continue

                # 4. Marine Buoys and 5-digit WMO numeric stations
                if stid.startswith("NDBC") or (len(stid) == 5 and stid.isdigit()):
                    continue
            # ---------------------------------
            
            try:
                lat = float(station.get("LATITUDE"))
                lon = float(station.get("LONGITUDE"))
            except (TypeError, ValueError):
                continue
                
            observations = station.get("OBSERVATIONS", {})
            timestamps = observations.get("date_time", [])
            
            station_lines = []
            prev_bucket_in = None
            rolling_24h_sum = 0.0

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
                    ob_time_str = dt_ob.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    continue

                # --- METEOROLOGICAL CONVERSIONS ---
                temp_c = extract_first_valid(observations, ["air_temp"], i)
                dew_c = extract_first_valid(observations, ["dew_point_temperature"], i)
                rh_pct = extract_first_valid(observations, ["relative_humidity"], i)
                speed_ms = extract_first_valid(observations, ["wind_speed"], i)
                gust_ms = extract_first_valid(observations, ["wind_gust"], i)
                wind_dir = extract_first_valid(observations, ["wind_direction"], i)
                
                temp_f = int(round((temp_c * 9/5) + 32)) if temp_c is not None else None
                dew_f = int(round((dew_c * 9/5) + 32)) if dew_c is not None else None
                
                # Direct dew point calculation fallback if derived dewpoint is missing
                if dew_f is None and temp_f is not None and rh_pct is not None:
                    dew_f = calculate_dewpoint_f(temp_f, rh_pct)

                speed_mph = int(round(speed_ms * 2.23694)) if speed_ms is not None else 0
                gust_mph = int(round(gust_ms * 2.23694)) if gust_ms is not None else None
                speed_kt = int(round(speed_ms * 1.94384)) if speed_ms is not None else 0

                slp_mb = get_best_slp(observations, i)

                # --- RAINFALL PARSING & DELTA CALCULATION ---
                raw_p1h = extract_first_valid(observations, ["precip_accum_one_hour"], i)
                raw_p24h = extract_first_valid(observations, ["precip_accum_24_hour"], i)
                raw_pbucket = extract_first_valid(observations, ["precip_accum"], i)

                p1h_in = 0.0
                if raw_p1h is not None:
                    p1h_in = clean_rain_value_to_inches(raw_p1h)
                elif raw_pbucket is not None:
                    curr_bucket = clean_rain_value_to_inches(raw_pbucket)
                    if prev_bucket_in is not None and curr_bucket >= prev_bucket_in:
                        delta = curr_bucket - prev_bucket_in
                        if delta < 4.0:
                            p1h_in = delta
                    prev_bucket_in = curr_bucket

                p24h_in = clean_rain_value_to_inches(raw_p24h) if raw_p24h is not None else 0.0
                
                rolling_24h_sum += p1h_in
                if p24h_in == 0.0 and rolling_24h_sum > 0.0:
                    p24h_in = rolling_24h_sum

                p1h_str = format_precip_str(p1h_in)
                p24h_str = format_precip_str(p24h_in)

                if p1h_str:
                    rain_counter += 1

                sky_code = extract_first_valid(observations, ["cloud_layer_1_code"], i)

                # Quality Control
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

                color_temp = "255 100 100"   # Light Red
                color_dew  = "100 255 100"   # Light Green
                color_slp  = "255 255 255"   # White
                color_rain = "0 255 255"     # Cyan

                max_wind_mph = gust_mph if (gust_mph is not None) else speed_mph

                if max_wind_mph >= 45:
                    color_barb = "255 0 255"    # Magenta
                    color_temp = "255 50 255"
                elif max_wind_mph >= 35:
                    color_barb = "255 255 0"    # Yellow
                    color_temp = "255 200 0"
                else:
                    color_barb = "255 255 255"  # White

                if gust_mph is not None and gust_mph > speed_mph and gust_mph >= 12:
                    wind_display = f"{wind_dir_display:03d}@{speed_mph}G{gust_mph}MPH"
                else:
                    wind_display = f"{wind_dir_display:03d}@{speed_mph}MPH"

                p1h_hover = f"{p1h_str}\"" if p1h_str else "0.00\""
                p24h_hover = f"{p24h_str}\"" if p24h_str else "0.00\""
                
                hover_text = (
                    f"Obs Time: {ob_time_str} | Station: {stid} | Type: {mnet} | "
                    f"Temp: {tf_display}F | Dewpt: {df_display}F | Wind: {wind_display} | "
                    f"SLP: {f'{slp_mb:.1f}' if slp_mb else 'M'}mb | "
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
    else:
        print("Warning: Network returned successfully but no matching active stations found.")

    # --- COMPILE FINAL PLACEFILE ---
    header_lines = [
        f'Title: CWOP Surface Observations ({run_time})',
        "; Created by [Your Name] & Gemini AI",
        "; Script Version Updated: August 29, 2026",
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

    # --- ATOMIC SAFE FILE WRITE ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    full_output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    temp_output_path = full_output_path + ".tmp"
    
    with open(temp_output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header_lines + body_lines))
        f.flush()
        os.fsync(f.fileno())
        
    os.replace(temp_output_path, full_output_path)
        
    print(f"Success! Processed dataset. Found {rain_counter} total observation points with measurable rainfall (>=0.01\").")
    print(f"Destination file compiled: {full_output_path}")

if __name__ == "__main__":
    main()
