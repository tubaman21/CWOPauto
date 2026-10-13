# Synoptic CWOP & Mesonet GRLevelX Placefile Generator

A Python script that dynamically queries surface weather observations from the Synoptic Data API across a targeted geographic bounding box and generates a formatted GRLevelX Placefile (cwop_observations.txt). Designed for severe weather monitoring, mesoscale analysis, and display inside GRLevel3, GR2Analyst, or other compatible radar software.

Features:
- Multi-Network Ingestion: Pulls observations from CWOP, RAWS, MnDOT, WisDOT, Wisconet, WeatherXM, Xcel Energy, Union Pacific, and general Mesonet stations.
- Hydrological & Marine Filtering: Filters out standalone river gauges, hydro sensors, C-MAN, and ASOS/AWOS stations to prevent clutter.
- Automatic SLP & Dewpoint Calculation: Standardizes station pressure to Sea Level Pressure (SLP) and estimates missing dewpoint temperatures from relative humidity.
- Dynamic Color-Coding: Highlights critical thresholds (e.g., wind gusts over 35/45 MPH, low visibility, 1-hour rainfall).
- Network Distance Thresholds: Sets range-dependent viewing thresholds (Threshold: NM) by network priority to optimize software performance.
- Atomic File Writing: Uses .tmp file swapping to prevent reading partial outputs during live placefile auto-refreshes.

Prerequisites:
- Python 3.7+
- requests library (pip install requests)
- A valid Synoptic Data API Token acquired from Synoptic Data (https://synopticdata.com/).

Configuration:
Set your Synoptic API token as an environment variable prior to execution:
- Linux / macOS: export SYNOPTIC_API_TOKEN="your_synoptic_api_token_here"
- Windows (Command Prompt): set SYNOPTIC_API_TOKEN=your_synoptic_api_token_here
- Windows (PowerShell): $env:SYNOPTIC_API_TOKEN="your_synoptic_api_token_here"

Usage:
Run the generator script directly using "python cwop_observations.py". Upon execution, the script queries the Synoptic API for recent surface observations across the lookback window, applies quality control, unit conversions, and station filtering, and outputs the compiled GRLevelX placefile to "placefiles/cwop_observations.txt". To load the file into GRLevelX, open GRLevel3 or GR2Analyst, navigate to Placefiles > Configure..., and add the local file path or URL pointing to cwop_observations.txt.

Customization:
You can adjust bounding coordinates and lookback parameters near the top of cwop_observations.py:
LAT_MIN, LAT_MAX = 42.5, 50.5
LON_MIN, LON_MAX = -97.5, -86.5
LOOKBACK_HOURS = 6

License:
This project is licensed under the MIT License — see the LICENSE file for details.
