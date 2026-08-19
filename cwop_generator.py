import os
import sys
import datetime
import requests
import pytz

def fetch_nws_zone_observations():
    """Queries the public National Weather Service API for live observations inside the Duluth zone."""
    print("Connecting directly to the public National Weather Service API endpoint...")
    
    # 🛰️ Queries the public NWS Zone observation database covering Saint Louis County / Duluth region natively
    url = "https://weather.gov"
    
    # The NWS API strictly requires a clean, valid descriptive User-Agent header
    headers = {
        "User-Agent": "(gr2-analyst-project, weather-automation-bot@example.com)",
        "Accept": "application/geo+json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"\n❌ NWS Server Refusal! Status Code: {response.status_code}")
            sys.exit(1)
            
        return response.json()
    except Exception as e:
        print(f"❌ Failed to reach the NWS API endpoint: {e}")
        sys.exit(1)

def main():
    # 🗺️ Precise spatial bounding limits covering WFO Duluth's operational county footprint
    LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -95.0, 45.0, -89.0, 49.5
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    geojson_data = fetch_nws_zone_observations()
    features = geojson_data.get("features", [])
    
    station_count = 0
    unique_stations = set()
    dt_now = datetime.datetime.now(pytz.utc)
    
    print(f"Analyzing {len(features)} live regional weather observations. Isolation loop starting...")
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        # Initialize standard GR2 text parameters
        f.write("Title: Looping Regional CWOP Observations Only\n")
        f.write("Refresh: 5\n\n")
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n\n')
        
        for feature in features:
            properties = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            coordinates = geometry.get("coordinates",)
            
            if not coordinates or len(coordinates) < 2:
                continue
                
            # Extract coordinates from GeoJSON layout formats [Longitude, Latitude]
            lon = float(coordinates[0])
            lat = float(coordinates[1])
            
            # Extract Station ID URL string and format out the clean name
            station_url = properties.get("station", "")
            st_id = station_url.split('/')[-1].upper() if station_url else "UNKN"
            
            if st_id == "UNKN" or st_id in unique_stations:
                continue
                
            # 🛡️ THE PERMANENT ASOS/METAR SEPARATION FILTER:
            # Official airport nodes strictly match 3 or 4-letter alphabetical codes.
            # Personal CWOP hardware uses longer alpha-numeric callsigns or tags.
            if len(st_id) <= 4 and st_id.isalpha():
                continue
                
            # Filter spatial parameters using your exact coordinate boundaries
            if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                continue
                
            # Pull metrics from the NWS structured nested dictionary system
            t_dict = properties.get("temperature", {}) or {}
            w_speed_dict = properties.get("windSpeed", {}) or {}
            w_dir_dict = properties.get("windDirection", {}) or {}
            
            t_c = t_dict.get("value")
            w_ms = w_speed_dict.get("value")
            w_dir = w_dir_dict.get("value")
            
            if t_c is None:
                continue
                
            # Convert units from metric to standard operational formats
            t_f = int(round((float(t_c) * 9/5) + 32))
            w_kt = int(round(float(w_ms) * 1.94384)) if w_ms is not None else 0
            
            # Generate a 30-minute validity window for seamless looping integration
            start_time = dt_now - datetime.timedelta(minutes=15)
            end_time = dt_now + datetime.timedelta(minutes=15)
            f.write(f"TimeRange: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')} {end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
            
            f.write(f"Object: {lat:.5f},{lon:.5f}\n")
            f.write("  Threshold: 999\n")
            
            # Map wind direction to wind barb texture indexes
            if w_dir is not None and w_kt >= 3:
                barb_idx = min(max(int(round(w_kt / 5)), 1), 25)
                f.write(f"  Icon: 0,0,{int(w_dir)},1,{barb_idx}\n")
            else:
                f.write("  Icon: 0,0,0,1,0\n")  # Calm wind anchor node
                
            # Render weather plot quadrants around the object layout
            f.write(f'  Text: 0, -18, 1, "{st_id}"\n')
            f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{t_f}"\n')
            
            f.write(f'  Hover: "CWOP Station: {st_id} \\nTemp: {t_f}F \\nWind: {int(w_dir) if w_dir is not None else 0}@{w_kt}kt"\n')
            f.write("End:\n\n")
            
            station_count += 1
            unique_stations.add(st_id)
                
    print(f"🎉 Success! Extracted and wrote {station_count} pure NWS verified CWOP stations.")

if __name__ == "__main__":
    main()
