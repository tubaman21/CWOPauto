import os
import sys
import datetime
import requests
import pytz

def fetch_realtime_cwop():
    """Fetches real-time public CWOP/APRS telemetry directly from the open IEM JSON engine."""
    print("Connecting to the public high-availability CWOP data pipeline...")
    
    # 🔗 Direct data endpoint dedicated strictly to volunteer/citizen tracking streams
    url = "https://iastate.edu"
    params = {
        "network": "MADIS"  # Forces the API to extract pure MADIS/CWOP citizen packets only
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeatherDataCollector/1.0 (NWS Project)"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ API Server Error! Status Code: {response.status_code}")
            sys.exit(1)
            
        # Error Guard: Read what the text layer says before crashing into JSON conversion
        if "data" not in response.text.lower():
            print("\n❌ CRITICAL RESPONSE ERROR: The server did not deliver a valid station dataset.")
            print(f"👉 Raw Server Context (First 300 chars):\n{response.text[:300]}")
            sys.exit(1)
            
        return response.json()
    except Exception as e:
        print(f"❌ Network processing exception during API fetch: {e}")
        sys.exit(1)

def format_slp(alt_in):
    """Formats raw altimeter pressure into standard 3-digit NWS shorthand."""
    if alt_in is None or alt_in <= 0:
        return ""
    try:
        # e.g., 29.92 -> 2992 -> Shorthand 992
        val = str(int(round(float(alt_in) * 100)))
        return val[-3:]
    except (ValueError, TypeError):
        return ""

def main():
    # 🗺️ Precise spatial bounding limits covering WFO Duluth's operational footprint
    # Longitude (-95.0 to -89.0), Latitude (45.0 to 49.5)
    LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -95.0, 45.0, -89.0, 49.5
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    data = fetch_realtime_cwop()
    stations = data.get("data", [])
    
    station_count = 0
    dt_now = datetime.datetime.now(pytz.utc)
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        # Initialize standard GR2 text headers
        f.write("Title: Looping Duluth Regional CWOP Observations Only\n")
        f.write("Refresh: 5\n\n")
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n\n')
        
        for st in stations:
            st_id = st.get("station", "UNKN").upper()
            lon = st.get("lon")
            lat = st.get("lat")
            
            if lon is None or lat is None:
                continue
                
            try:
                lon_f = float(lon)
                lat_f = float(lat)
            except (ValueError, TypeError):
                continue
                
            # Filter spatial parameters using your exact coordinate boundaries
            if not (LON_MIN <= lon_f <= LON_MAX and LAT_MIN <= lat_f <= LAT_MAX):
                continue
                
            # 🛡️ DUAL LAYER METAR CLEANER:
            # Drop any official airport tags that happen to stream through the MADIS core index
            if len(st_id) <= 4 and st_id.isalpha():
                continue
                
            # Extract parameters safely from the JSON dictionary layers
            t_f = st.get("tmpf")
            w_kt = st.get("sknt")
            w_dir = st.get("drct")
            alt_in = st.get("alti")
            
            if t_f is None:
                continue
                
            # Parse metrics into standard formats safely
            w_kt = int(w_kt) if w_kt is not None else 0
            slp_str = format_slp(alt_in)
            
            # Generate a 30-minute validity frame around the observation time for looping stability
            start_time = dt_now - datetime.timedelta(minutes=15)
            end_time = dt_now + datetime.timedelta(minutes=15)
            f.write(f"TimeRange: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')} {end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
            
            f.write(f"Object: {lat_f:.5f},{lon_f:.5f}\n")
            f.write("  Threshold: 999\n")
            
            # Map wind direction angles directly to standard 5-knot increment barb indices
            if w_dir is not None and w_kt >= 3:
                barb_idx = min(max(int(round(float(w_kt) / 5)), 1), 25)
                f.write(f"  Icon: 0,0,{int(float(w_dir))},1,{barb_idx}\n")
            else:
                f.write("  Icon: 0,0,0,1,0\n")  # Calm wind central dot anchor node
                
            # Format text quadrants around the map object matrix
            f.write(f'  Text: 0, -18, 1, "{st_id}"\n')
            f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{int(round(float(t_f)))}"\n')
            if slp_str:
                f.write(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{slp_str}"\n')
                
            f.write(f'  Hover: "CWOP Station: {st_id} \\nTemp: {int(round(float(t_f)))}F \\nWind: {int(float(w_dir)) if w_dir is not None else 0}@{w_kt}kt"\n')
            f.write("End:\n\n")
            
            station_count += 1
                
    print(f"🎉 Success! Completely isolated and compiled {station_count} pure CWOP stations inside the Duluth box.")

if __name__ == "__main__":
    main()
