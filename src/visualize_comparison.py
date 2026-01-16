#!/usr/bin/env python3
"""
ADS-B Data Visualization and Comparison
Compares adsb_decoder (custom) output with pyModeS-decoded frames
Generates graphs showing lat/lon/altitude differences
"""

import os
import sys
import csv
import re
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Try to import pyModeS
try:
    import pyModeS as pms
    PYMODES_AVAILABLE = True
except ImportError:
    PYMODES_AVAILABLE = False
    print("Error: pyModeS not installed. Install with: pip install pyModeS")
    sys.exit(1)

# Import parse_frame_file from verify_frames
try:
    from verify_frames import parse_frame_file
except ImportError:
    print("Error: Could not import parse_frame_file from verify_frames.py")
    print("Make sure verify_frames.py is in the same directory.")
    sys.exit(1)

# Input files (edit these to change which files to process)
FRAME_FILE = "./frames_adsb/frames_adsb/frames_20251019_181920.txt"
CSV_FILE = "./output/20260109/iq_output3/output181920.csv"

# Output directory will be created automatically
OUTPUT_DIR_BASE = "./graphs_out"

# Frame Decoding (pyModeS)
def decode_frames_pymodes(frames):
    """Decode frames using pyModeS and return position data."""
    aircraft_messages = {}
    decoded_positions = []
    
    for idx, hex_msg in enumerate(frames):
        try:
            df = pms.df(hex_msg)
            if df != 17:
                continue
            
            icao = pms.adsb.icao(hex_msg)
            tc = pms.adsb.typecode(hex_msg)
            
            if not (9 <= tc <= 18):
                continue
            
            altitude = pms.adsb.altitude(hex_msg)
            if altitude is None:
                continue
            
            if icao not in aircraft_messages:
                aircraft_messages[icao] = {'even': None, 'odd': None}
            
            oe_flag = pms.adsb.oe_flag(hex_msg)
            
            if oe_flag == 0:
                aircraft_messages[icao]['even'] = hex_msg
            else:
                aircraft_messages[icao]['odd'] = hex_msg
            
            lat, lon = 0.0, 0.0
            if aircraft_messages[icao]['even'] and aircraft_messages[icao]['odd']:
                try:
                    pos = pms.adsb.position(
                        aircraft_messages[icao]['even'],
                        aircraft_messages[icao]['odd'],
                        0, 1
                    )
                    if pos:
                        lat, lon = pos
                        lat = round(lat, 5)
                        lon = round(lon, 5)
                except:
                    pass
            
            decoded_positions.append({
                'index': idx,
                'icao': '0x' + icao.lower(),
                'lat': lat,
                'lon': lon,
                'alt': altitude
            })
            
        except Exception:
            continue
    
    return decoded_positions

def load_csv_data(filepath):
    """Load CSV file and return position data."""
    positions = []
    try:
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                positions.append({
                    'index': idx,
                    'icao': row['icao'],
                    'lat': float(row['lat']),
                    'lon': float(row['lon']),
                    'alt': int(row['alt'])
                })
        return positions
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return []

# Visualization
def create_comparison_plots(csv_data, pymodes_data, output_path):
    # Create comparison plots for lat/lon/alt.
    
    # Filter valid positions
    csv_valid = [p for p in csv_data if p['lat'] != 0.0 and p['lon'] != 0.0]
    pymodes_valid = [p for p in pymodes_data if p['lat'] != 0.0 and p['lon'] != 0.0]
    
    print(f"No of valid CSV points: {len(csv_valid)}")
    print(f"No of valid pyModeS points: {len(pymodes_valid)}")
    
    # Create figure with subplots
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('ADS-B Decoder Comparison: adsb_decoder (custom) vs pyModeS', fontsize=16, fontweight='bold')
    
   
    # Plot 1: Latitude vs Index
    ax1 = axes[0, 0]
    if csv_valid:
        ax1.plot([p['index'] for p in csv_valid], [p['lat'] for p in csv_valid], 
                'b-o', label='adsb_decoder (custom)', markersize=4, linewidth=1.5)
        # Add value labels for CSV data
        for p in csv_valid:
            ax1.annotate(f'{p["lat"]:.2f}', 
                        (p['index'], p['lat']), 
                        textcoords="offset points", 
                        xytext=(0,5), 
                        ha='center', 
                        fontsize=7, 
                        color='blue')
    
    if pymodes_valid:
        ax1.plot([p['index'] for p in pymodes_valid], [p['lat'] for p in pymodes_valid], 
                'r--s', label='pyModeS', markersize=4, linewidth=1.5, alpha=0.7)
        # Add value labels for pyModeS data
        for p in pymodes_valid:
            ax1.annotate(f'{p["lat"]:.2f}', 
                        (p['index'], p['lat']), 
                        textcoords="offset points", 
                        xytext=(0,5), 
                        ha='right', 
                        fontsize=7, 
                        color='red')

    ax1.set_xlabel('Message Index')
    ax1.set_ylabel('Latitude (degrees)')
    ax1.set_title('Latitude Comparison')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Ensure minimum y-axis range
    y_min, y_max = ax1.get_ylim()
    y_range = 0.1
    if y_max - y_min < y_range:
        y_center = (y_min + y_max) / 2
        ax1.set_ylim(y_center - y_range/2, y_center + y_range/2)


    # # Plot 2: Altitude vs Latitude
    # ax2 = axes[0, 1]
    # if csv_valid:
    #     ax2.plot([p['lat'] for p in csv_valid], [p['alt'] for p in csv_valid], 
    #             'b-o', label='adsb_decoder (custom)', markersize=4, linewidth=1.5)
    #     # Add value labels for CSV data
    #     for p in csv_valid:
    #         ax2.annotate(f'{p["alt"]:.2f}', 
    #                     (p['lat'], p['alt']), 
    #                     textcoords="offset points", 
    #                     xytext=(0,5), 
    #                     ha='center', 
    #                     fontsize=7, 
    #                     color='blue')
    # if pymodes_valid:
    #     ax2.plot([p['lat'] for p in pymodes_valid], [p['alt'] for p in pymodes_valid], 
    #             'r--s', label='pyModeS', markersize=4, linewidth=1.5, alpha=0.7)
    #     # Add value labels for pyModeS data
    #     for p in pymodes_valid:
    #         ax2.annotate(f'{p["alt"]:.2f}', 
    #                     (p['lat'], p['alt']), 
    #                     textcoords="offset points", 
    #                     xytext=(0,5), 
    #                     ha='right', 
    #                     fontsize=7, 
    #                     color='red')

    # ax2.set_xlabel('Latitude (degrees)')
    # ax2.set_ylabel('Altitude (feet)')
    # ax2.set_title('Latitude vs Altitude Comparison')
    # ax2.legend()
    # ax2.grid(True, alpha=0.3)
    
    # # Ensure minimum y-axis range
    # y_min, y_max = ax2.get_ylim()
    # y_range = 100
    # if y_max - y_min < y_range:
        # y_center = (y_min + y_max) / 2
        # ax2.set_ylim(y_center - y_range/2, y_center + y_range/2)

    # Plot 2: Longitude vs Index
    ax2 = axes[0, 1]
    if csv_valid:
        ax2.plot([p['index'] for p in csv_valid], [p['lon'] for p in csv_valid], 
                'b-o', label='adsb_decoder (custom)', markersize=4, linewidth=1.5)
        # Add value labels for CSV data
        for p in csv_valid:
            ax2.annotate(f'{p["lon"]:.2f}', 
                        (p['index'], p['lon']), 
                        textcoords="offset points", 
                        xytext=(0,5), 
                        ha='center', 
                        fontsize=7, 
                        color='blue')

    if pymodes_valid:
        ax2.plot([p['index'] for p in pymodes_valid], [p['lon'] for p in pymodes_valid], 
                'r--s', label='pyModeS', markersize=4, linewidth=1.5, alpha=0.7)
        # Add value labels for pyModeS data
        for p in pymodes_valid:
            ax2.annotate(f'{p["lon"]:.2f}', 
                        (p['index'], p['lon']), 
                        textcoords="offset points", 
                        xytext=(0,5), 
                        ha='right', 
                        fontsize=7, 
                        color='red')

    ax2.set_xlabel('Message Index')
    ax2.set_ylabel('Longitude (degrees)')
    ax2.set_title('Longitude Comparison')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Ensure minimum y-axis range
    y_min, y_max = ax2.get_ylim()
    y_range = 0.1
    if y_max - y_min < y_range:
        y_center = (y_min + y_max) / 2
        ax2.set_ylim(y_center - y_range/2, y_center + y_range/2)

    # # Plot 3: Altitude vs Longitude
    # ax3 = axes[1, 0]
    # if csv_valid:
    #     ax3.plot([p['lon'] for p in csv_valid], [p['alt'] for p in csv_valid], 
    #             'b-o', label='adsb_decoder (custom)', markersize=4, linewidth=1.5)
    #     # Add value labels for CSV data
    #     for p in csv_valid:
    #         ax3.annotate(f'{p["alt"]}', 
    #                     (p['index'], p['alt']), 
    #                     textcoords="offset points", 
    #                     xytext=(0,5), 
    #                     ha='center', 
    #                     fontsize=7, 
    #                     color='blue')
    # if pymodes_valid:
    #     ax3.plot([p['lon'] for p in pymodes_valid], [p['alt'] for p in pymodes_valid], 
    #             'r--s', label='pyModeS', markersize=4, linewidth=1.5, alpha=0.7)
    #     # Add value labels for pyModeS data
    #     for p in pymodes_valid:
    #         ax3.annotate(f'{p["alt"]}', 
    #                     (p['lon'], p['alt']), 
    #                     textcoords="offset points", 
    #                     xytext=(0,5), 
    #                     ha='right', 
    #                     fontsize=7, 
    #                     color='red')

    # ax3.set_xlabel('Longitude (degrees)')
    # ax3.set_ylabel('Altitude (feet)')
    # ax3.set_title('Longitude vs Altitude Comparison')
    # ax3.legend()
    # ax3.grid(True, alpha=0.3)

    # Plot 3: Altitude vs Index
    ax3 = axes[1, 0]
    if csv_valid:
        ax3.plot([p['index'] for p in csv_valid], [p['alt'] for p in csv_valid], 
                'b-o', label='adsb_decoder (custom)', markersize=4, linewidth=1.5)
        # Add value labels for CSV data
        for p in csv_valid:
            ax3.annotate(f'{p["alt"]}', 
                        (p['index'], p['alt']), 
                        textcoords="offset points", 
                        xytext=(0,5), 
                        ha='center', 
                        fontsize=7, 
                        color='blue')
    if pymodes_valid:
        ax3.plot([p['index'] for p in pymodes_valid], [p['alt'] for p in pymodes_valid], 
                'r--s', label='pyModeS', markersize=4, linewidth=1.5, alpha=0.7)
        # Add value labels for pyModeS data
        for p in pymodes_valid:
            ax3.annotate(f'{p["alt"]}', 
                        (p['index'], p['alt']), 
                        textcoords="offset points", 
                        xytext=(0,5), 
                        ha='right', 
                        fontsize=7, 
                        color='red')

    ax3.set_xlabel('Message Index')
    ax3.set_ylabel('Altitude (feet)')
    ax3.set_title('Altitude Comparison')
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # Ensure minimum y-axis range
    y_min, y_max = ax3.get_ylim()
    y_range = 100
    if y_max - y_min < y_range:
        y_center = (y_min + y_max) / 2
        ax3.set_ylim(y_center - y_range/2, y_center + y_range/2)

    # Plot 4: 2D Position (Lat vs Lon)
    ax4 = axes[1, 1]
    if csv_valid:
        ax4.plot([p['lon'] for p in csv_valid], [p['lat'] for p in csv_valid], 
                'b-o', label='adsb_decoder (custom)', markersize=6, linewidth=1.5)
        # Add index labels for CSV data points
        for p in csv_valid:
            ax4.annotate(f'#{p["index"]}', 
                        (p['lon'], p['lat']), 
                        textcoords="offset points", 
                        xytext=(5,5), 
                        ha='left', 
                        fontsize=7, 
                        color='blue')
    if pymodes_valid:
        ax4.plot([p['lon'] for p in pymodes_valid], [p['lat'] for p in pymodes_valid], 
                'r--s', label='pyModeS', markersize=6, linewidth=1.5, alpha=0.7)
        # Add index labels for pyModeS data points
        for p in pymodes_valid:
            ax4.annotate(f'#{p["index"]}', 
                        (p['lon'], p['lat']), 
                        textcoords="offset points", 
                        xytext=(5,5), 
                        ha='right', 
                        fontsize=7, 
                        color='red')    
        
    ax4.set_xlabel('Longitude (degrees)')
    ax4.set_ylabel('Latitude (degrees)')
    ax4.set_title('2D Position Track')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    ax4.axis('equal')

    # # Ensure minimum x-axis range
    # x_min, x_max = ax4.get_xlim()
    # x_range = 0.5
    # if x_max - x_min < x_range:
    #     x_center = (x_min + x_max) / 2
    #     ax4.set_xlim(x_center - x_range/2, x_center + x_range/2)
    
    # # Ensure minimum y-axis range
    # y_min, y_max = ax4.get_ylim()
    # y_range = 0.5
    # if y_max - y_min < y_range:
    #     y_center = (y_min + y_max) / 2
    #     ax4.set_ylim(y_center - y_range/2, y_center + y_range/2)

    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Graph saved to: {output_path}")
    plt.close()

def main():
    print("=" * 80)
    print("ADS-B Data Visualization and Comparison")
    print("=" * 80)
    
    # Check if pyModeS is available
    if not PYMODES_AVAILABLE:
        return
    
    """ Use current time as timestamp """
    # file_timestamp = datetime.now().strftime("%H%M%S")

    """ Uncomment to extract timestamp from CSV filename """
    # # Example: output180842.csv -> 180842
    csv_basename = os.path.basename(CSV_FILE)
    timestamp_match = re.search(r'output(\d{6})', csv_basename)
    if timestamp_match:
        file_timestamp = timestamp_match.group(1)
    else:
        # Fallback to current time if pattern not found
        file_timestamp = datetime.now().strftime("%H%M%S")
    
    # Create output directory
    today = datetime.now().strftime("%Y%m%d")
    # output_dir = os.path.join(OUTPUT_DIR_BASE, today)
    output_dir = os.path.join(OUTPUT_DIR_BASE, today,"at1905") # temp, use the above command usually
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate output filename with timestamp from CSV file
    output_filename = f"graph_{file_timestamp}.png"
    output_path = os.path.join(output_dir, output_filename)
    
    print(f"\nConfiguration:")
    print(f"  Frame file: {FRAME_FILE}")
    print(f"  CSV file:   {CSV_FILE}")
    print(f"  Timestamp:  {file_timestamp}")
    print(f"  Output:     {output_path}")
    print()
    
    # Check if input files exist
    if not os.path.exists(FRAME_FILE):
        print(f"Error: Frame file not found: {FRAME_FILE}")
        print("Please edit FRAME_FILE in the script to point to a valid file.")
        return
    
    if not os.path.exists(CSV_FILE):
        print(f"Error: CSV file not found: {CSV_FILE}")
        print("Please edit CSV_FILE in the script to point to a valid file.")
        return
    
    # Load data
    print("Loading CSV data...")
    csv_data = load_csv_data(CSV_FILE)
    print(f"  Loaded {len(csv_data)} CSV entries")
    
    print("\nParsing and decoding frames with pyModeS...")
    frames = parse_frame_file(FRAME_FILE)
    print(f"  Parsed {len(frames)} frames")
    
    pymodes_data = decode_frames_pymodes(frames)
    print(f"  Decoded {len(pymodes_data)} position messages")
    
    # Create plots
    print("\nGenerating comparison plots...")
    create_comparison_plots(csv_data, pymodes_data, output_path)
    
    print("Visualization complete!")

if __name__ == "__main__":
    main()
