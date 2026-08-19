import os
import sys
import datetime
import requests
import pytz

def fetch_realtime_cwop():
    """Fetches real-time surface data for Minnesota and Wisconsin from the open IEM API."""
    print("Connecting to the public high-availability weather data API...")
    
    # query the master currents endpoint for the entire regional block
    url = "https://iastate.edu"
    
    params = {
        "state": "MN"  # Pulls the active regional matrix natively
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeatherDataCollector/1.0"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ API Server Error! Status Code: {response.status_code}")
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
        # e.g., 29.92 -> 2992 -> 992
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
                
            # Filter spatial parameters using your coordinate boundaries
            if not (LON_MIN <= float(lon) <= LON_MAX and LAT_MIN <= float(lat) <= LAT_MAX):
                continue
                
            # 🛡️ PURE CWOP FILTER:
            # Official airport nodes (ASOS/AWOS) match 3 or 4-letter alphabetical codes.
            # Citizen weather stations use longer alphanumeric callsigns or numeric tags.
            if len(st_id) <= 4 and st_id.isalpha():
                continue
                
            # Extract parameters safely from the JSON dictionary structure
            t_f = st.get("tmpf")
            w_kt = st.get("sknt")
            w_dir = st.get("drct")
            alt_in = st.get("alti")
            
            if t_f is None:
                continue
                
            # Parse wind speeds safely (handling None or missing values)
            w_kt = int(w_kt) if w_kt is not None else 0
            slp_str = format_slp(alt_in)
            
            # Generate a 30-minute validity frame around the observation time for looping stability
            start_time = dt_now - datetime.timedelta(minutes=15)
            end_time = dt_now + datetime.timedelta(minutes=15)
            f.write(f"TimeRange: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')} {end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
            
            f.write(f"Object: {float(lat):.5f},{float(lon):.5f}\n")
            f.write("  Threshold: 999\n")
            
            # Map wind direction to wind barb texture indexes
            if w_dir is not None and w_kt >= 3:
                barb_idx = min(max(int(round(float(w_kt) / 5)), 1), 25)
                f.write(f"  Icon: 0,0,{int(float(w_dir))},1,{barb_idx}\n")
            else:
                f.write("  Icon: 0,0,0,1,0\n")  # Calm wind anchor node
                
            # Render weather plot quadrants around the object layout
            f.write(f'  Text: 0, -18, 1, "{st_id}"\n')
            f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{int(round(float(t_f)))}"\n')
            if slp_str:
                f.write(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{slp_str}"\n')
                
            f.write(f'  Hover: "CWOP Station: {st_id} \\nTemp: {int(round(float(t_f)))}F \\nWind: {int(float(w_dir)) if w_dir is not None else 0}@{w_kt}kt"\n')
            f.write("End:\n\n")
            
            station_count += 1
                
    print(f"🎉 Success! Completely isolated and compiled {station_count} pure CWOP stations within the Duluth box.")

if __name__ == "__main__":
    main()
