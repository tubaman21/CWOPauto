import os
import sys
import datetime
import requests
import pytz

def fetch_madis_data():
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NWS-WFO-Project/1.0"
    }
    
    try:
        print(f"DEBUG: Attempting connection to NOAA MADIS CGI script...")
        response = requests.get(url, params=params, headers=headers, timeout=45)
        response.raise_for_status()
        
        # Guard check to ensure the server returned the expected column file and not an error
        if "id" not in response.text.lower() and "station" not in response.text.lower():
            print("⚠ Warning: NOAA returned a blank payload or server status alert page.")
            print(f"👉 Raw Response Sample:\n{response.text[:300]}")
            sys.exit(1)
            
        return response.text
    except Exception as e:
        print(f"❌ Failed to reach NOAA/MADIS data endpoints: {e}")
        sys.exit(1)

def parse_madis_line(line):
    """Parses standard space-separated NOAA surface records into a strict data dictionary."""
    # Split by any whitespace block safely
    parts = line.split()
    if len(parts) < 10:
        return None
        
    try:
        # Map parameters from NOAA's live surface record text columns
        st_id = parts[0].strip()
        lat = float(parts[1])
        lon = float(parts[2])
        
        # Safely convert temperature vectors (handling 'M' missing blocks)
        t_raw = parts[3]
        t_f = int(round((float(t_raw) * 9/5) + 32)) if t_raw != 'M' else None
        
        # Wind configurations
        w_dir = float(parts[4]) if parts[4] != 'M' else None
        w_speed = float(parts[5]) if parts[5] != 'M' else 0
        w_kt = int(round(w_speed * 1.94384))
        
        # Default to the current time since we requested real-time active data
        dt = datetime.datetime.now(pytz.utc)
        
        return {
            "id": st_id, "lat": lat, "lon": lon, "time": dt,
            "temp": t_f, "dewp": None, "wdir": w_dir, "wkt": w_kt, "slp": ""
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
