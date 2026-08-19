import os
import sys
import datetime
import requests
import pytz

def fetch_iem_data():
    """Fetches the absolute latest real-time surface weather reports from the IEM data pipeline."""
    print("Connecting to the real-time public weather data streaming pipeline...")
    url = "https://iastate.edu"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NWS-WFO-Project/1.0"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Failed to reach data endpoint mirror: {e}")
        sys.exit(1)

def is_pure_metar(station_id):
    """
    Returns True if a station matches official airport conventions (ASOS/AWOS/METAR).
    Returns False if the ID follows amateur radio callsigns or citizen CWOP/DW alphanumeric tracking tags.
    """
    # 1. Clean the string layer
    sid = station_id.strip().upper()
    
    # 2. Extract standard international 4-character airport codes starting with 'K'
    if len(sid) == 4 and sid.startswith('K') and sid[1:].isalpha():
        return True
        
    # 3. Extract 3-character regional airport identifiers
    if len(sid) == 3 and sid.isalpha():
        return True
        
    return False

def parse_iem_metar(line):
    """Parses standard space-delimited text reports safely into a structured dictionary."""
    parts = line.split()
    if len(parts) < 8:
        return None
        
    try:
        st_id = parts[0].strip().upper()
        
        # 🛡️ THE PERMANENT SEPARATION GUARD: Drop the line immediately if it belongs to an airport node
        if is_pure_metar(st_id):
            return None
            
        lat = float(parts[2])
        lon = float(parts[3])
        
        # Temperature formatting
        t_raw = parts[4]
        t_f = int(round(float(t_raw))) if t_raw != 'M' else None
        
        # Wind components
        w_dir = float(parts[5]) if parts[5] != 'M' else None
        w_kt = int(float(parts[6])) if parts[6] != 'M' else 0
        
        # Sea-Level Altimeter pressure reading
        alt_raw = parts[7]
        slp_str = ""
        if alt_raw != 'M':
            slp_str = str(int(float(alt_raw) * 100))[-3:]
            
        dt = datetime.datetime.now(pytz.utc)
        
        return {
            "id": st_id, "lat": lat, "lon": lon, "time": dt,
            "temp": t_f, "dewp": None, "wdir": w_dir, "wkt": w_kt, "slp": slp_str
        }
    except Exception:
        return None

def main():
    # 🗺️ Define your spatial boundaries (WFO Duluth County Warning Area footprint)
    LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -95.0, 45.0, -89.0, 49.5
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    raw_text = fetch_iem_data()
    lines = raw_text.splitlines()
    
    station_count = 0
    unique_stations = set()
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        f.write("Title: Looping Regional CWOP Observations Only\n")
        f.write("Refresh: 5\n\n")
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n\n')
        
        for line in lines:
            if not line.strip() or line.startswith('STN') or line.startswith('id'):
                continue
                
            obs = parse_iem_metar(line)
            if not obs:
                continue
                
            if obs["id"] in unique_stations:
                continue
                
            if not (LON_MIN <= obs["lon"] <= LON_MAX and LAT_MIN <= obs["lat"] <= LAT_MAX):
                continue
                
            if obs["temp"] is None:
                continue
                
            # Establish the 30-minute looping visibility boundary
            start_time = obs["time"] - datetime.timedelta(minutes=15)
            end_time = obs["time"] + datetime.timedelta(minutes=15)
            f.write(f"TimeRange: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')} {end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
            
            f.write(f"Object: {obs['lat']:.5f},{obs['lon']:.5f}\n")
            f.write("  Threshold: 999\n")
            
            if obs["wdir"] is not None and obs["wkt"] >= 3:
                barb_idx = min(max(int(round(obs["wkt"] / 5)), 1), 25)
                f.write(f"  Icon: 0,0,{int(obs['wdir'])},1,{barb_idx}\n")
            else:
                f.write("  Icon: 0,0,0,1,0\n")
                
            f.write(f'  Text: 0, -18, 1, "{obs["id"]}"\n')
            f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{obs["temp"]}"\n')
            if obs["slp"]:
                f.write(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{obs["slp"]}"\n')
                
            f.write(f'  Hover: "CWOP Station: {obs["id"]} \\nTemp: {obs["temp"]}F \\nWind: {int(obs["wdir"]) if obs["wdir"] is not None else 0}@{obs["wkt"]}kt"\n')
            f.write("End:\n\n")
            
            station_count += 1
            unique_stations.add(obs["id"])
            
    print(f"🎉 Success! Filtered out all airport METAR positions and wrote {station_count} pure CWOP stations.")

if __name__ == "__main__":
    main()
