import os
import sys
import datetime
import requests
import pytz

def fetch_madis_data():
    """Fetches real-time public surface telemetry directly from the NOAA MADIS data servers."""
    print("Connecting directly to the public NOAA MADIS data streaming pipeline...")
    
    # Force a 15-minute padding delay to ensure NOAA has completely generated and posted the active file
    now = datetime.datetime.now(pytz.utc) - datetime.timedelta(minutes=15)
    current_hour = now.strftime("%Y%m%d_%H00")
    
    # 🔗 FIX: Kept the domain hardcoded as a strict base string to prevent any variable merging issues
    base_domain = "http://madis-data.ncep.noaa.gov"
    path_string = f"/madisPublic1/data/text/metar/TXT.{current_hour}"
    url = base_domain + path_string
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NWS-WFO-Project/1.0"
    }
    
    try:
        print(f"DEBUG: Attempting connection to URL: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"⚠ Warning: Current hour file not fully built yet (HTTP {response.status_code}). Tripping back-hour fallback...")
            # Fallback to the previous hour's file if right at the cusp of a transmission cycle
            prev_hour = (now - datetime.timedelta(hours=1)).strftime("%Y%m%d_%H00")
            path_string_fallback = f"/madisPublic1/data/text/metar/TXT.{prev_hour}"
            url = base_domain + path_string_fallback
            print(f"DEBUG: Attempting connection to fallback URL: {url}")
            response = requests.get(url, headers=headers, timeout=30)
            
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Failed to reach NOAA/MADIS data endpoints: {e}")
        sys.exit(1)

def parse_madis_line(line):
    """Parses standard comma-separated MADIS records into a strict data dictionary."""
    parts = line.split(',')
    if len(parts) < 15:
        return None
        
    try:
        # MADIS Text Data Standard Layout Column Mapping Indexes
        st_id = parts[0].strip()
        lat = float(parts[1])
        lon = float(parts[2])
        time_raw = parts[3].strip() # Format: YYYYMMDD_HHMM
        
        # Pull key meteorological layers (handling 'M' missing characters safely)
        t_c = float(parts[4]) if parts[4] != 'M' else None
        d_c = float(parts[5]) if parts[5] != 'M' else None
        w_dir = float(parts[6]) if parts[6] != 'M' else None
        w_speed_ms = float(parts[7]) if parts[7] != 'M' else None
        alt_in = float(parts[13]) if parts[13] != 'M' else None
        
        # Convert measurements to standard operational units
        t_f = int(round((t_c * 9/5) + 32)) if t_c is not None else None
        d_f = int(round((d_c * 9/5) + 32)) if d_c is not None else None
        w_kt = int(round(w_speed_ms * 1.94384)) if w_speed_ms is not None else 0
        
        # Format Sea-Level / Altimeter code shorthand (e.g. 29.92 -> 992)
        slp_str = str(int(round(alt_in * 100)))[-3:] if alt_in is not None else ""
        
        dt = datetime.datetime.strptime(time_raw, "%Y%m%d_%H%M").replace(tzinfo=pytz.utc)
        
        return {
            "id": st_id, "lat": lat, "lon": lon, "time": dt,
            "temp": t_f, "dewp": d_f, "wdir": w_dir, "wkt": w_kt, "slp": slp_str
        }
    except Exception:
        return None

def main():
    # 🗺️ Define your spatial boundaries (WFO Duluth County Warning Area)
    LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -95.0, 45.0, -89.0, 49.5
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    raw_text = fetch_madis_data()
    lines = raw_text.splitlines()
    
    station_count = 0
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        f.write("Title: MADIS Looping Surface Observations\n")
        f.write("Refresh: 5\n\n")
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n')
        
        for line in lines:
            if line.startswith('#') or not line.strip():
                continue
                
            obs = parse_madis_line(line)
            if not obs:
                continue
                
            # Filter positions using your exact bounding box parameters
            if not (LON_MIN <= obs["lon"] <= LON_MAX and LAT_MIN <= obs["lat"] <= LAT_MAX):
                continue
                
            if obs["temp"] is None:
                continue
                
            # Calculate a time visibility range around the data packet
            start_time = obs["time"] - datetime.timedelta(minutes=15)
            end_time = obs["time"] + datetime.timedelta(minutes=15)
            f.write(f"TimeRange: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')} {end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
            
            f.write(f"Object: {obs['lat']:.5f},{obs['lon']:.5f}\n")
            f.write("  Threshold: 999\n")
            
            # Plot wind telemetry icons
            if obs["wdir"] is not None and obs["wkt"] >= 3:
                barb_idx = min(max(int(round(obs["wkt"] / 5)), 1), 25)
                f.write(f"  Icon: 0,0,{int(obs['wdir'])},1,{barb_idx}\n")
            else:
                f.write("  Icon: 0,0,0,1,0\n") # Centered calm indicator node
                
            # Render standard weather plot quadrants
            f.write(f'  Text: 0, -18, 1, "{obs["id"]}"\n')
            f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{obs["temp"]}"\n')
            if obs["dewp"] is not None:
                f.write(f'  Color: 100 255 100\n  Text: -20, 10, 1, "{obs["dewp"]}"\n')
            if obs["slp"]:
                f.write(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{obs["slp"]}"\n')
                
            f.write(f'  Hover: "Station: {obs["id"]} \\nTime: {obs["time"].strftime("%H:%M")} UTC \\nTemp: {obs["temp"]}F \\nDew Point: {obs["dewp"] if obs["dewp"] is not None else "M"}F \\nWind: {int(obs["wdir"]) if obs["wdir"] is not None else 0}@{obs["wkt"]}kt"\n')
            f.write("End:\n\n")
            station_count += 1
            
    print(f"🎉 Success! Processed and wrote {station_count} clean observations over the Duluth grid.")

if __name__ == "__main__":
    main()
