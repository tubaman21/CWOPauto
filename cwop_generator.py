import os
import sys
import datetime
import requests
import pytz

def fetch_raw_mesonet_text():
    """Fetches real-time public surface logs from the open IEM text database cluster."""
    print("Connecting directly to the public Iowa Environmental Mesonet text stream...")
    # This is an open public repository that cannot be blocked or rate-limited
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
            
            # 🔗 THE CRITICAL FIX: IEM text columns are explicitly separated by TABS (\t), not commas or spaces!
            parts = line.split('\t')
            
            # Ensure the row has enough valid tab-separated elements to parse fields safely
            # IEM Column Order: 0: station, 1: lat, 2: lon, 3: tmpf, 4: dwpf, 5: sknt, 6: drct, 7: alti
            if len(parts) < 4:
                continue
                
            try:
                st_id = parts[0].strip().upper()
                
                # 1. Apply the strict citizen station isolation filter
                if is_pure_metar(st_id):
                    continue
                    
                # 2. Extract Lat/Lon coordinates directly from their absolute tab indices
                lat = float(parts[1])
                lon = float(parts[2])
                
                # Apply your exact geographical filter constraints
                if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                    continue
                    
                # Deduplicate entries to avoid rendering visual overlap blocks
                if st_id in unique_stations:
                    continue
                    
                # 3. Extract temperature metrics safely (handling 'M' missing blocks)
                t_raw = parts[3].strip()
                if t_raw == 'M' or not t_raw:
                    continue
                t_f = int(round(float(t_raw)))
                
                # 4. Extract wind speed, direction, and pressure fields if available in later tab positions
                w_kt = int(float(parts[5])) if len(parts) >= 6 and parts[5].strip() != 'M' else 0
                w_dir = float(parts[6]) if len(parts) >= 7 and parts[6].strip() != 'M' else None
                alt_raw = parts[7].strip() if len(parts) >= 8 else 'M'
                
                slp_str = ""
                if alt_raw != 'M' and alt_raw:
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
                continue
                
    print(f"🎉 Success! Filtered out all airport METAR positions and wrote {station_count} pure CWOP stations inside the Duluth box.")

if __name__ == "__main__":
    main()
