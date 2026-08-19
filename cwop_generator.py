import os
import sys
import datetime
import requests
import pytz

def fetch_raw_mesonet_text():
    """Fetches real-time public surface logs from the open IEM text database cluster."""
    print("Connecting directly to the public Iowa Environmental Mesonet text stream...")
    
    # 🔗 Direct, raw static URL stream requiring no API parameters, tokens, or complex joins
    url = "https://iastate.edu"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeatherDataCollector/1.0 (NWS Project Integration)"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Failed to reach open-source text stream: {e}")
        sys.exit(1)

def is_pure_metar(station_id):
    """
    Returns True if a station matches airport conventions (ASOS/AWOS/METAR).
    Returns False if it is a personal citizen weather station (CWOP/DW tag).
    """
    sid = station_id.strip().upper()
    
    # Extract standard international 4-character airport codes starting with 'K'
    if len(sid) == 4 and sid.startswith('K') and sid[1:].isalpha():
        return True
        
    # Extract 3-character regional airport identifiers
    if len(sid) == 3 and sid.isalpha():
        return True
        
    return False

def main():
    # 🗺️ Precise spatial bounding limits covering WFO Duluth's operational footprint
    # Longitude (-95.0 to -89.0), Latitude (45.0 to 49.5)
    LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -95.0, 45.0, -89.0, 49.5
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    raw_text = fetch_raw_mesonet_text()
    lines = raw_text.splitlines()
    
    print(f"DEBUG: Successfully downloaded text database stream ({len(lines)} raw lines discovered).")
    
    station_count = 0
    unique_stations = set()
    dt_now = datetime.datetime.now(pytz.utc)
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        # Initialize standard GR2 text parameters
        f.write("Title: Regional CWOP Observations Only\n")
        f.write("Refresh: 5\n\n")
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n\n')
        
        for line in lines:
            # Skip documentation file lines or header labels completely
            if not line.strip() or line.startswith('#') or line.startswith('station') or line.startswith('id'):
                continue
            
            # Standardize separation markers (replace commas with spaces)
            cleaned_line = line.replace(',', ' ')
            parts = cleaned_line.split()
            
            # Ensure the row has enough valid space-separated elements to parse variables
            if len(parts) < 7:
                continue
                
            try:
                st_id = parts[0].strip().upper()
                
                # 1. Apply the strict citizen station isolation filter
                if is_pure_metar(st_id):
                    continue
                    
                # 2. Extract spatial metadata points safely from IEM columns
                # IEM Text format column alignment: station[0], lon[1], lat[2], tmpf[3]
                lon = float(parts[1])
                lat = float(parts[2])
                
                # Apply your exact geographical filter constraints
                if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                    continue
                    
                # Deduplicate entries to avoid rendering visual overlap blocks
                if st_id in unique_stations:
                    continue
                    
                # 3. Extract temperature metrics (handling 'M' missing blocks safely)
                t_raw = parts[3]
                if t_raw == 'M':
                    continue
                t_f = int(round(float(t_raw)))
                
                # 4. Extract wind speed and direction fields safely by indexing later columns
                w_speed_raw = parts[5] if len(parts) >= 6 else 'M'
                w_dir_raw = parts[6] if len(parts) >= 7 else 'M'
                alt_raw = parts[7] if len(parts) >= 8 else 'M'
                
                w_kt = int(float(w_speed_raw)) if w_speed_raw != 'M' else 0
                w_dir = float(w_dir_raw) if w_dir_raw != 'M' else None
                
                slp_str = ""
                if alt_raw != 'M':
                    # e.g., 29.92 -> 2992 -> Shorthand 992
                    slp_str = str(int(float(alt_raw) * 100))[-3:]
                
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
                if slp_str:
                    f.write(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{slp_str}"\n')
                    
                f.write(f'  Hover: "CWOP Station: {st_id} \\nTemp: {t_f}F \\nWind: {int(w_dir) if w_dir is not None else 0}@{w_kt}kt"\n')
                f.write("End:\n\n")
                
                station_count += 1
                unique_stations.add(st_id)
                
            except Exception:
                # Silently pass malformed rows to prevent whole-file parsing failure
                continue
                
    print(f"🎉 Success! Filtered out all airport METAR positions and wrote {station_count} pure CWOP stations inside the Duluth box.")

if __name__ == "__main__":
    main()
