import os
import sys
import datetime
import requests
import pytz

def fetch_raw_nws_madis():
    """Downloads the raw public hourly MADIS weather data text dump directly from the correct NOAA file path."""
    print("Connecting directly to the federal open-access NOAA text servers...")
    
    # Target an older, completely compiled text log file (2 hours ago)
    # This ensures the hourly text file is completely written and finalized on NOAA's servers
    now = datetime.datetime.now(pytz.utc) - datetime.timedelta(hours=2)
    hour_str = now.strftime("%Y%m%d_%H00")
    
    # 🔗 PERMANENT FIX: Corrected directory folder routing to match the true NOAA server structure
    base_domain = "https://madis-data.ncep.noaa.gov"
    file_path = f"/madisPublic1/data/text/metar/TXT.{hour_str}"
    url = base_domain + file_path
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NWS-Project-Integration/1.0"
    }
    
    try:
        print(f"DEBUG: Resolving connection straight to URL: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        
        # Fall back to 3 hours ago if the 2-hour file isn't fully written yet
        if response.status_code != 200:
            print(f"⚠ Target file missing (HTTP {response.status_code}). Falling back one extra hour...")
            prev_hour = (now - datetime.timedelta(hours=1)).strftime("%Y%m%d_%H00")
            file_path_fallback = f"/madisPublic1/data/text/metar/TXT.{prev_hour}"
            url = base_domain + file_path_fallback
            print(f"DEBUG: Resolving fallback connection to URL: {url}")
            response = requests.get(url, headers=headers, timeout=30)
            
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Failed to reach NOAA/MADIS data servers: {e}")
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
            # Skip commented text rows, empty blanks, or file headers completely
            if not line.strip() or line.startswith('#') or line.startswith('STN') or line.startswith('id') or line.startswith('station'):
                continue
                
            # Split by any whitespace block matching NOAA's native text log columns
            # Layout schema matching raw data files: station, lat, lon, tmpc, dwpc, sknt, drct, alti
            parts = line.split()
            if len(parts) < 8:
                continue
                
            try:
                st_id = parts[0].strip().upper()
                
                # 1. Filter out airport stations
                if is_pure_metar(st_id) or st_id in unique_stations:
                    continue
                
                # 2. Extract Lat/Lon coordinates directly from text columns
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
                w_speed_raw = parts[5].strip() if len(parts) >= 6 else 'M'
                w_dir_raw = parts[6].strip() if len(parts) >= 7 else 'M'
                
                w_dir = float(w_dir_raw) if w_dir_raw != 'M' else None
                # Knots are native to this NOAA database text feed layout
                w_kt = int(float(w_speed_raw)) if w_speed_raw != 'M' else 0
                
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
