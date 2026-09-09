import os
import sys
import json
import requests

SYNOPTIC_API_TOKEN = os.environ.get("SYNOPTIC_API_TOKEN")

if not SYNOPTIC_API_TOKEN:
    print("Error: SYNOPTIC_API_TOKEN environment variable is missing.")
    sys.exit(1)

LAT_MIN, LAT_MAX = 42.5, 50.5
LON_MIN, LON_MAX = -97.5, -86.5

def check_target_station():
    """Targeted search for station RWIS-16-0048."""
    print("=== SEARCHING SPECIFICALLY FOR STID: RWIS-16-0048 ===")
    url = "https://api.synopticdata.com/v2/stations/metadata"
    params = {
        "token": SYNOPTIC_API_TOKEN,
        "stid": "RWIS-16-0048",
        "extra": "metadata"
    }
    res = requests.get(url, params=params, timeout=15).json()
    stations = res.get("STATION", [])
    if not stations:
        print("Result: Station 'RWIS-16-0048' was NOT FOUND by exact STID.\n")
    else:
        st = stations[0]
        print(f"Found STID: {st.get('STID')}")
        print(f"  Name: {st.get('NAME')}")
        print(f"  MNET_ID: {st.get('MNET_ID')}")
        print(f"  MNET_SHORTNAME: {st.get('MNET_SHORTNAME')}")
        print(f"  MNET_NAME: {st.get('MNET_NAME')}\n")

def scan_bounding_box_for_wisdot():
    """Scans the full regional bounding box for any WI DOT or RWIS stations."""
    print("=== SCANNING BOUNDING BOX FOR WISCONSIN / DOT / RWIS STATIONS ===")
    url = "https://api.synopticdata.com/v2/stations/metadata"
    params = {
        "token": SYNOPTIC_API_TOKEN,
        "bbox": f"{LON_MIN},{LAT_MIN},{LON_MAX},{LAT_MAX}",
        "extra": "metadata"
    }
    res = requests.get(url, params=params, timeout=25).json()
    stations = res.get("STATION", [])
    
    matches = []
    for st in stations:
        stid = str(st.get("STID", "")).upper()
        mnet_id = str(st.get("MNET_ID", ""))
        mnet_short = str(st.get("MNET_SHORTNAME", "")).upper()
        mnet_name = str(st.get("MNET_NAME", "")).upper()
        state = str(st.get("STATE", "")).upper()

        if (
            "WIS" in mnet_short
            or "WIS" in mnet_name
            or "RWIS" in stid
            or "RWIS" in mnet_short
            or "RWIS" in mnet_name
            or stid.startswith(("WIDOT", "WIRT"))
            or (state == "WI" and "DOT" in mnet_short)
        ):
            matches.append({
                "STID": stid,
                "MNET_ID": mnet_id,
                "MNET_SHORT": mnet_short,
                "MNET_NAME": mnet_name,
                "STATE": state
            })

    print(f"Found {len(matches)} potential WisDOT / RWIS matches inside the bbox:\n")
    print(f"{'STID':<15} | {'MNET_ID':<8} | {'MNET_SHORT':<15} | {'MNET_NAME'}")
    print("-" * 70)
    for m in matches[:30]:  # Show top 30 matches
        print(f"{m['STID']:<15} | {m['MNET_ID']:<8} | {m['MNET_SHORT']:<15} | {m['MNET_NAME']}")

if __name__ == "__main__":
    check_target_station()
    scan_bounding_box_for_wisdot()
