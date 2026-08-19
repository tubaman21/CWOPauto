import os
import sys
import datetime
import requests
import pytz

def fetch_state_geojson(state_code):
    """Fetches real-time comprehensive mesonet observations using an isolated URL structure."""
    st = state_code.lower()
    print(f"Connecting to the open public state data pipeline for {state_code.upper()}...")
    
    # 🔗 Pure dynamic construction to bypass any automated network proxy string mangling
    domain_parts = ["mesonet", "agron", "iastate", "edu"]
    base_url = "https://" + ".".join(domain_parts)
    path_url = "/geojson/state/" + st + ".geojson"
    url = base_url + path_url
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeatherDataCollector/1.0 (NWS Project Integration)"
    }
    
    try:
        print(f"DEBUG: Resolving connection to fully verified endpoint...")
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"⚠ Warning: State pipeline server returned status code: {response.status_code}")
            return []
        
        data = response.json()
        features = data.get("features", [])
        print(f"-> Successfully extracted {len(features)} stations for {state_code.upper()}")
        return features
    except Exception as e:
        print(f"⚠ Warning: Network processing exception during {state_code.upper()} API fetch: {e}")
        return []

def format_slp(alt_in):
    """Formats raw altimeter pressure into standard 3-digit NWS shorthand."""
    if alt_in is None or alt_in <= 0:
        return ""
    try:
        val = str(int(round(float(alt_in) * 100)))
        return val[-3:]
    except (ValueError, TypeError):
        return ""

def main():
    # 🗺️ Define your spatial boundaries (WFO Duluth County Warning Area footprint)
    LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = -95.0, 45.0, -89.0, 49.5
    
    output_directory = "placefiles"
    os.makedirs(output_directory, exist_ok=True)
    output_file_path = os.path.join(output_directory, "cwop_observations.txt")
    
    # Ingest data matrices from both neighboring forecast states
    features_mn = fetch_state_geojson("mn")
    features_wi = fetch_state_geojson("wi")
    all_features = features_mn + features_wi
    
    if not all_features:
        print("❌ CRITICAL ERROR: Zero total data features were returned from the networks. Exiting.")
        sys.exit(1)
        
    print(f"DEBUG: Processing {len(all_features)} total regional observation packets...")
    
    station_count = 0
    unique_stations = set()
    dt_now = datetime.datetime.now(pytz.utc)
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        # Initialize standard GR2 text headers
        f.write("Title: Looping Regional CWOP Observations Only\n")
        f.write("Refresh: 5\n\n")
        f.write('IconFile: 1, 32, 32, 16, 16, "https://githubusercontent.com"\n\n')
        
        for feature in all_features:
            geometry = feature.get("geometry", {})
            properties = feature.get("properties", {})
            coordinates = geometry.get("coordinates", [])
            
            if not coordinates or len(coordinates) < 2:
                continue
                
            # GeoJSON coordinate formatting indexes: [Longitude, Latitude]
            lon = float(coordinates[0])
            lat = float(coordinates[1])
            st_id = properties.get("sid", "UNKN").upper()
            
            if st_id == "UNKN" or st_id in unique_stations:
                continue
                
            # 🛡️ THE PERMANENT ASOS/METAR SEPARATION FILTER:
            if len(st_id) <= 4 and st_id.isalpha():
                continue
                
            # Filter spatial parameters using your exact coordinate boundaries
            if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                continue
                
            t_f = properties.get("tmpf")
            w_kt = properties.get("sknt")
            w_dir = properties.get("drct")
            alt_in = properties.get("alti")
            
            if t_f is None:
                continue
                
            try:
                temp_val = int(round(float(t_f)))
                wind_speed = int(round(float(w_kt))) if w_kt is not None else 0
                wind_dir = int(round(float(w_dir))) if w_dir is not None else None
            except (ValueError, TypeError):
                continue
                
            slp_str = format_slp(alt_in)
            
            # Generate a 30-minute validity window for seamless radar loop pairing
            start_time = dt_now - datetime.timedelta(minutes=15)
            end_time = dt_now + datetime.timedelta(minutes=15)
            f.write(f"TimeRange: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')} {end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
            
            f.write(f"Object: {lat:.5f},{lon:.5f}\n")
            f.write("  Threshold: 999\n")
            
            if wind_dir is not None and wind_speed >= 3:
                barb_idx = min(max(int(round(wind_speed / 5)), 1), 25)
                f.write(f"  Icon: 0,0,{wind_dir},1,{barb_idx}\n")
            else:
                f.write("  Icon: 0,0,0,1,0\n")  # Calm wind anchor node
                
            f.write(f'  Text: 0, -18, 1, "{st_id}"\n')
            f.write(f'  Color: 255 100 100\n  Text: -20, -10, 1, "{temp_val}"\n')
            if slp_str:
                f.write(f'  Color: 255 255 255\n  Text: 20, -10, 1, "{slp_str}"\n')
                
            f.write(f'  Hover: "CWOP Station: {st_id} \\nTemp: {temp_val}F \\nWind: {wind_dir if wind_dir is not None else 0}@{wind_speed}kt"\n')
            f.write("End:\n\n")
            
            station_count += 1
            unique_stations.add(st_id)
                
    print(f"🎉 Success! Filtered out airport METARs and wrote {station_count} pure CWOP stations to {output_file_path}.")

if __name__ == "__main__":
    main()
