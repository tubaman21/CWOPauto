import os
import sys
import datetime
import requests
import pytz

def fetch_nws_cwop_data():
    """Queries the official National Weather Service API for real-time CWOP observations."""
    print("Connecting directly to the public National Weather Service API...")
    
    # The NWS API aggregates volunteer stations via the specialized 'madis' network path
    url = "https://weather.gov"
    params = {
        "limit": "500",
        "state": "MN"  # Pulling Minnesota's regional cluster block natively
    }
    
    # The NWS API strictly requires a descriptive User-Agent naming an organization or email
    headers = {
        "User-Agent": "(gr2-analyst-project, weather-automation-bot@example.com)",
        "Accept": "application/geo+json"  # Forces the server to deliver a clean GeoJSON layout
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Failed to reach the NWS API endpoint: {e}")
        sys.exit(1)

def fetch_station_latest_obs(station_url, headers):
    """Fetches the latest single meteorological snapshot for an individual station path."""
    try:
        obs_url = f"{station_url}/observations/latest"
        response = requests.get(obs_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None

def main():
    # 🗺️ Define your spatial boundaries (WFO Duluth County Warning Area footprint)
    LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -95.0, 45.0, -89.0, 49.5
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    geojson_data = fetch_nws_cwop_data()
    features = geojson_data.get("features", [])
    
    headers = {
        "User-Agent": "(gr2-analyst-project, weather-automation-bot@example.com)",
        "Accept": "application/geo+json"
    }
    
    station_count = 0
    dt_now = datetime.datetime.now(pytz.utc)
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        # Initialize standard GR2 text headers
        f.write("Title: Looping Duluth Regional CWOP Observations Only\n")
        f.write("Refresh: 5\n\n")
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n\n')
        
        for feature in features:
            properties = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            coordinates = geometry.get("coordinates", [0, 0])
            
            # Extract coordinates from the GeoJSON array layout [Longitude, Latitude]
            lon = float(coordinates[0])
            lat = float(coordinates[1])
            st_id = properties.get("stationIdentifier", "UNKN").upper()
            
            # 🛡️ THE PERMANENT ASOS/METAR FILTER:
            # Official airport nodes strictly match 3 or 4-letter alphabetical codes.
            # Personal CWOP hardware uses longer alpha-numeric callsigns or tags.
            if len(st_id) <= 4 and st_id.isalpha():
                continue
                
            # Filter spatial parameters using your coordinate boundaries
            if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                continue
                
            # Fetch the actual weather observations for this specific station
            station_url = feature.get("id")
            if not station_url:
                continue
                
            obs_data = fetch_station_latest_obs(station_url, headers)
            if not obs_data:
                continue
                
            obs_props = obs_data.get("properties", {})
            
            # Pull metrics from the NWS structured nested dictionary system
            t_dict = obs_props.get("temperature", {}) or {}
            w_speed_dict = obs_props.get("windSpeed", {}) or {}
            w_dir_dict = obs_props.get("windDirection", {}) or {}
            
            t_c = t_dict.get("value")
            w_ms = w_speed_dict.get("value")
            w_dir = w_dir_dict.get("value")
            
            if t_c is None:
                continue
                
            # Convert units from metric to standard operational formats
            t_f = int(round((float(t_c) * 9/5) + 32))
            w_kt = int(round(float(w_ms) * 1.94384)) if w_ms is not None else 0
            
            # Create a 30-minute validity window for seamless looping integration
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
            
            # Safety limit to avoid timing out the GitHub workflow job runner
            if station_count >= 75:
                break
                
    print(f"🎉 Success! Extracted and wrote {station_count} pure NWS verified CWOP stations.")

if __name__ == "__main__":
    main()
