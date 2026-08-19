import os
import sys
import datetime
import requests
import pytz

def fetch_raw_nws_madis():
    """Fetches real-time public surface telemetry directly from the NOAA MADIS data servers."""
    print("Connecting directly to the public NOAA MADIS data streaming pipeline...")
    
    # Target the active NOAA MADIS real-time extraction servlet engine
    url = "https://noaa.gov"
    
    # Configure precise data query parameters
    params = {
        "xml": "0",                  # Request raw text formatting layout (not XML)
        "time": "0",                 # Request the most recent real-time observations available
        "prov": "cwop",              # Restrict data gathering strictly to CWOP stations
        "qc": "1"                    # Include NWS quality control validation flags
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeatherDataCollector/1.0 (NWS Project Integration)"
    }
    
    try:
        print("DEBUG: Attempting connection to NOAA MADIS CGI script...")
        response = requests.get(url, params=params, headers=headers, timeout=45)
        response.raise_for_status()
        
        # Guard check to ensure the server returned the expected data text layout
        if "id" not in response.text.lower() and "station" not in response.text.lower():
            print("⚠ Warning: NOAA returned a blank payload or server status alert page.")
            sys.exit(1)
            
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
    LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -95.0, 45.0, -89.0, 49.5
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    raw_text = fetch_raw_nws_madis()
    lines = raw_text.splitlines()
    
    print(f"DEBUG: Successfully downloaded raw weather stream ({len(lines)} lines parsed).")
    
    station_count = 0
    unique_stations = set()
    dt_now = datetime.datetime.now(pytz.utc)
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        # Initialize standard GR2 text parameters
        f.write("Title: Regional CWOP Observations Only\n")
        f.write("Refresh: 5\n\n")
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n\n')
        
        for line in lines:
            # Skip commented text rows or file headers
            if not line.strip() or line.startswith('#') or line.startswith('STN') or line.startswith('id') or line.startswith('station'):
                continue
                
            # Split by whitespace block safely matching NOAA's variable columns
            parts = line.split()
            if len(parts) < 6:
                continue
                
            try:
                st_id = parts[0].strip().upper()
                
                # 1. Filter out airport stations
                if is_pure_metar(st_id) or st_id in unique_stations:
                    continue
                
                # 2. Extract Lat/Lon coordinates directly from columns (MADIS column layouts map positions early)
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
                
                # 4. Extract wind direction and speed fields safely if available in trailing columns
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
