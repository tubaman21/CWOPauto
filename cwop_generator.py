import os
import sys
import datetime
import requests
import pytz

def fetch_cwop_feed():
    """Fetches real-time public surface telemetry from the open CWOP packet mirror."""
    print("Connecting to the unthrottled public CWOP data streaming pipeline...")
    
    # 🔗 Direct open access mirror delivering pure citizen observations (No ASOS/AWOS airports)
    url = "https://iastate.edu"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NWS-WFO-Project/1.0"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Failed to reach open-source data feed: {e}")
        sys.exit(1)

def parse_cwop_row(line):
    """Parses space-delimited public mesonet text rows into a clean weather dictionary."""
    parts = line.split()
    if len(parts) < 9:
        return None
        
    try:
        # Expected Column Layout: station, lon, lat, tmpf, dwpf, sknt, drct, alti
        st_id = parts[0].strip().upper()
        lon = float(parts[1])
        lat = float(parts[2])
        
        # Pull key parameters safely, keeping track of 'M' missing metrics
        t_raw = parts[3]
        w_speed_raw = parts[5]
        w_dir_raw = parts[6]
        alt_raw = parts[7]
        
        t_f = int(round(float(t_raw))) if t_raw != 'M' else None
        w_kt = int(float(w_speed_raw)) if w_speed_raw != 'M' else 0
        w_dir = float(w_dir_raw) if w_dir_raw != 'M' else None
        
        slp_str = ""
        if alt_raw != 'M':
            # e.g., 29.92 -> 2992 -> Shorthand 992
            slp_str = str(int(float(alt_raw) * 100))[-3:]
            
        return {
            "id": st_id, "lat": lat, "lon": lon,
            "temp": t_f, "wdir": w_dir, "wkt": w_kt, "slp": slp_str
        }
    except Exception:
        return None

def main():
    # 🗺️ Precise spatial bounding limits covering WFO Duluth's operational county footprint
    LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -95.0, 45.0, -89.0, 49.5
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    raw_data_text = fetch_cwop_feed()
    lines = raw_data_text.splitlines()
    
    station_count = 0
    unique_stations = set()
    dt_now = datetime.datetime.now(pytz.utc)
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        # Initialize standard GR2 text parameters
        f.write("Title: Looping Duluth Regional CWOP Observations Only\n")
        f.write("Refresh: 5\n\n")
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n\n')
        
        for line in lines:
            # Skip documentation file lines or header labels completely
            if not line.strip() or line.startswith('#') or line.startswith('station'):
                continue
                
            obs = parse_cwop_row(line)
            if not obs:
                continue
                
            # Deduplicate entries to avoid rendering visual overlap blocks
            if obs["id"] in unique_stations:
                continue
                
            # Apply your exact geographical filter constraints
            if not (LON_MIN <= obs["lon"] <= LON_MAX and LAT_MIN <= obs["lat"] <= LAT_MAX):
                continue
                
            if obs["temp"] is None:
                continue
                
            # Generate a 30-minute time frame envelope to facilitate smooth radar loop pairing
            start_time = dt_now - datetime.timedelta(minutes=15)
            end_time = dt_now + datetime.timedelta(minutes=15)
            f.write(f"TimeRange: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')} {end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
            
            f.write(f"Object: {obs['lat']:.5f},{obs['lon']:.5f}\n")
            f.write("  Threshold: 999\n")
            
            # Map rotational angle indicators to the wind barb texture coordinates
            if obs["wdir"] is not None and obs["wkt"] >= 3:
                barb_idx = min(max(int(round(obs["wkt"] / 5)), 1), 25)
                f.write(f"  Icon: 0,0,{int(obs['wdir'])},1,{barb_idx}\n")
            else:
                f.write("  Icon: 0,0,0,1,0\n") # Calm wind center point anchor node
                
            # Write standardized surface analysis observation quadrants
            f.write(f'  Text: 0, -18, 1, "{obs["id"]}"\n')
            f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{obs["temp"]}"\n')
            if obs["slp"]:
                f.write(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{obs["slp"]}"\n')
                
            f.write(f'  Hover: "CWOP Station: {obs["id"]} \\nTemp: {obs["temp"]}F \\nWind: {int(obs["wdir"]) if obs["wdir"] is not None else 0}@{obs["wkt"]}kt"\n')
            f.write("End:\n\n")
            
            station_count += 1
            unique_stations.add(obs["id"])
            
    print(f"🎉 Success! Completely isolated and compiled {station_count} pure CWOP stations within the Duluth box.")

if __name__ == "__main__":
    main()
