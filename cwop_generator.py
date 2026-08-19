import os
import sys
import datetime
import requests
import pytz

def fetch_raw_nws_madis():
    """Fetches real-time public surface telemetry dynamically from the NOAA MADIS extraction servlet engine."""
    print("Connecting directly to the public NOAA MADIS data extraction engine...")
    
    # 🔗 FIX: Switched from static folder text files to the live, on-demand query script
    url = "https://noaa.gov"
    
    # Query parameters explicitly telling the NOAA engine to bundle live citizen data
    params = {
        "xml": "0",                  # Request standard space-separated text columns
        "time": "0",                 # Grab the absolute latest real-time observations available
        "prov": "cwop",              # Restrict data gathering strictly to citizen CWOP stations
        "qc": "1"                    # Include standard NWS quality control metrics
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeatherDataCollector/1.0 (NWS Project Integration)"
    }
    
    try:
        print("DEBUG: Executing real-time database dump query to NOAA servers...")
        response = requests.get(url, params=params, headers=headers, timeout=60)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Failed to reach NOAA/MADIS data endpoints: {e}")
        sys.exit(1)

def is_pure_metar(station_id):
    """Filters out official airport ASOS/AWOS/METAR stations."""
    sid = station_id.strip().upper()
    if len(sid) == 4 and sid.startswith('K') and sid[1:].isalpha():
        return True
    if len(sid) == 3 and sid.isalpha():
        return True
    return False

def main():
    # 🗺️ Define your spatial boundaries (WFO Duluth County Warning Area footprint)
    # Longitude (-95.0 to -89.0), Latitude (45.0 to 49.5)
    LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -95.0, 45.0, -89.0, 49.5
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    raw_text = fetch_raw_nws_madis()
    lines = raw_text.splitlines()
    
    print(f"DEBUG: Successfully downloaded weather log stream ({len(lines)} lines parsed).")
    
    station_count = 0
    unique_stations = set()
    dt_now = datetime.datetime.now(pytz.utc)
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        # Initialize standard GR2 text parameters
        f.write("Title: Regional CWOP Observations Only\n")
        f.write("Refresh: 5\n\n")
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n\n')
        
        for line in lines:
            # Strip outer padding and skip comments/headers
            l_strip = line.strip()
            if not l_strip or l_strip.startswith('#') or l_strip.startswith('id') or l_strip.startswith('station'):
                continue
                
            # Split the row by any whitespace block matching NOAA's output template
            parts = l_strip.split()
            if len(parts) < 6:
                continue
                
            try:
                st_id = parts[0].strip().upper()
                
                # 1. Filter out airport stations
                if is_pure_metar(st_id) or st_id in unique_stations:
                    continue
                
                # 2. Extract Lat/Lon coordinates directly from columns
                # NOAA sfcdump text format lists latitude early in the row alignment
                lat = float(parts[1])
                lon = float(parts[2])
                
                # Apply your exact geographical filter constraints
                if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                    continue
                    
                # 3. Extract temperature metrics safely (handling 'M' missing blocks)
                t_raw = parts[3].strip()
                if t_raw == 'M':
                    continue
                # Convert Celsius to Fahrenheit
                t_f = int(round((float(t_raw) * 9/5) + 32))
                
                # 4. Extract wind speed and direction fields if available in trailing columns
                w_dir_raw = parts[4].strip() if len(parts) >= 5 else 'M'
                w_speed_raw = parts[5].strip() if len(parts) >= 6 else 'M'
                
                w_dir = float(w_dir_raw) if w_dir_raw != 'M' else None
                # Convert meters/second to knots
                w_kt = int(round(float(w_speed_raw) * 1.94384)) if w_speed_raw != 'M' else 0
                
                # Generate a 30-minute time frame envelope to facilitate smooth radar loop pairing
                start_time = dt_now - datetime.timedelta(minutes=15)
                end_time = dt_now + datetime.timedelta(minutes=15)
                f.write(f"TimeRange: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')} {end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
                
                f.write(f"Object: {lat:.5f},{lon:.5f}\n")
                f.write("  Threshold: 999\n")
                
                # Map rotational wind direction angle to the wind barb texture coordinates
                if w_dir is not None and w_kt >= 3:
                    barb_idx = min(max(int(round(w_kt / 5)), 1), 25)
                    f.write(f"  Icon: 0,0,{int(w_dir)},1,{barb_idx}\n")
                else:
                    f.write("  Icon: 0,0,0,1,0\n") # Calm wind anchor node
                    
                # Write standardized weather plot quadrants
                f.write(f'  Text: 0, -18, 1, "{st_id}"\n')
                f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{t_f}"\n')
                    
                f.write(f'  Hover: "CWOP Station: {st_id} \\nTemp: {t_f}F \\nWind: {int(w_dir) if w_dir is not None else 0}@{w_kt}kt"\n')
                f.write("End:\n\n")
                
                station_count += 1
                unique_stations.add(st_id)
                
            except (ValueError, IndexError):
                continue
                
    print(f"🎉 Success! Processed and wrote {station_count} pure CWOP stations inside the Duluth box.")

if __name__ == "__main__":
    main()
