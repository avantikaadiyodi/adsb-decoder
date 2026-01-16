#!/usr/bin/env python3
"""
Frame Verification Tool
Decodes raw ADS-B frames from ./frames_adsb/ and compares with CSV outputs from ./output/
"""

import os
import sys
import csv
import math
import re
import argparse
from collections import defaultdict

try:
    import pyModeS as pms
    PYMODES_AVAILABLE = True
except ImportError:
    PYMODES_AVAILABLE = False
    print("Note: pyModeS not available. Install with: pip install pyModeS")

# Import CPR decoder from adsb_decoder
try:
    from adsb_decoder import cpr_decode
except ImportError:
    print("Error: Could not import cpr_decode from adsb_decoder.py")
    print("Make sure adsb_decoder.py is in the same directory.")
    sys.exit(1)

# ============================================================================
# Frame Parsing and Decoding
# ============================================================================

def parse_frame_file(filepath):
    """
    Parses a frame file and returns list of hex messages.
    Format: YYYYMMDD_HHMMSS NNNNNN *HEXMESSAGE;
    """
    frames = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # Extract hex message (between * and ;)
                match = re.search(r'\*([0-9A-Fa-f]+);', line)
                if match:
                    hex_msg = match.group(1).upper()
                    frames.append(hex_msg)
        
        return frames
    except Exception as e:
        print(f"Error reading frame file {filepath}: {e}")
        return []

def decode_df17_frame(hex_msg):
    """
    Decodes a DF17 hex message and extracts ICAO, altitude, and CPR data.
    Returns dict or None if not a valid airborne position message.
    """
    try:
        # Convert hex to binary
        b = bin(int(hex_msg, 16))[2:].zfill(len(hex_msg) * 4)
        
        # Need at least 112 bits for Mode S
        if len(b) < 112:
            return None
        
        df = int(b[0:5], 2)
        if df != 17:
            return None
        
        icao = int(b[8:32], 2)
        data = b[32:88]
        tc = int(data[0:5], 2)
        
        # Only process airborne position messages (TC 9-18)
        if not (9 <= tc <= 18):
            return None
        
        # Extract altitude (12 bits at data[8:20])
        alt_bits = data[8:20]
        q_bit = alt_bits[7]
        
        raw_alt = int(alt_bits, 2)
        val = ((raw_alt >> 5) << 4) | (raw_alt & 0xF)
        
        if q_bit == '1':
            altitude = val * 25 - 1000
        else:
            altitude = val * 100 - 1000
        
        # Extract CPR data
        f_flag = int(data[21], 2)
        lat_enc = int(data[22:39], 2)
        lon_enc = int(data[39:56], 2)
        
        return {
            'icao': hex(icao),
            'altitude': altitude,
            'f_flag': f_flag,
            'lat_enc': lat_enc,
            'lon_enc': lon_enc
        }
        
    except Exception as e:
        return None

def decode_frames_pymodes(frames):
    """
    Decodes a list of hex frames using pyModeS library.
    Returns position data.
    """
    if not PYMODES_AVAILABLE:
        print("Error: pyModeS not installed. Use --decoder=custom instead.")
        return []
    
    aircraft_messages = {}
    decoded_positions = []
    
    for hex_msg in frames:
        try:
            # Check if it's a DF17 message
            df = pms.df(hex_msg)
            if df != 17:
                continue
            
            # Get ICAO
            icao = pms.adsb.icao(hex_msg)
            
            # Get type code
            tc = pms.adsb.typecode(hex_msg)
            
            # Only process airborne position messages (TC 9-18)
            if not (9 <= tc <= 18):
                continue
            
            # Get altitude
            altitude = pms.adsb.altitude(hex_msg)
            if altitude is None:
                continue
            
            # Store message for position decoding
            if icao not in aircraft_messages:
                aircraft_messages[icao] = {'even': None, 'odd': None}
            
            # Determine if even or odd
            oe_flag = pms.adsb.oe_flag(hex_msg)
            
            if oe_flag == 0:  # Even
                aircraft_messages[icao]['even'] = hex_msg
            else:  # Odd
                aircraft_messages[icao]['odd'] = hex_msg
            
            # Try to decode position if we have both
            lat, lon = 0.0, 0.0
            if aircraft_messages[icao]['even'] and aircraft_messages[icao]['odd']:
                try:
                    pos = pms.adsb.position(
                        aircraft_messages[icao]['even'],
                        aircraft_messages[icao]['odd'],
                        0,  # t0 (time of even message)
                        1   # t1 (time of odd message)
                    )
                    if pos:
                        lat, lon = pos
                        lat = round(lat, 5)
                        lon = round(lon, 5)
                except:
                    pass
            
            decoded_positions.append({
                'icao': '0x' + icao.lower(),
                'lat': lat,
                'lon': lon,
                'alt': altitude
            })
            
        except Exception as e:
            continue
    
    return decoded_positions

def decode_frames(frames):
    """
    Decodes a list of hex frames using custom CPR decoder.
    Returns position data.
    """
    aircraft_messages = {}
    decoded_positions = []
    
    for hex_msg in frames:
        frame_data = decode_df17_frame(hex_msg)
        if not frame_data:
            continue
        
        icao = frame_data['icao']
        
        # Store CPR frames
        if icao not in aircraft_messages:
            aircraft_messages[icao] = {}
        
        if frame_data['f_flag'] == 0:
            aircraft_messages[icao]['even'] = (frame_data['lat_enc'], frame_data['lon_enc'])
        else:
            aircraft_messages[icao]['odd'] = (frame_data['lat_enc'], frame_data['lon_enc'])
        
        # Try to decode position if we have both even and odd
        lat, lon = 0.0, 0.0
        if 'even' in aircraft_messages[icao] and 'odd' in aircraft_messages[icao]:
            try:
                lat, lon = cpr_decode(
                    aircraft_messages[icao]['even'],
                    aircraft_messages[icao]['odd']
                )
            except:
                pass
        
        # Store decoded position
        decoded_positions.append({
            'icao': icao,
            'lat': lat,
            'lon': lon,
            'alt': frame_data['altitude']
        })
    
    return decoded_positions

# ============================================================================
# CSV Loading
# ============================================================================

def load_csv_output(filepath):
    """
    Loads a CSV file and returns list of position data.
    """
    positions = []
    try:
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                positions.append({
                    'icao': row['icao'],
                    'lat': float(row['lat']),
                    'lon': float(row['lon']),
                    'alt': int(row['alt'])
                })
        return positions
    except Exception as e:
        print(f"Error reading CSV {filepath}: {e}")
        return []

# ============================================================================
# Comparison Logic
# ============================================================================

def compare_positions(reference_data, csv_data, tolerance_deg=0.01, tolerance_alt=50):
    """
    Compares reference decoded positions with CSV output.
    Returns comparison statistics.
    """
    matches = []
    mismatches = []
    
    # Filter out partial decodes (lat/lon = 0.0)
    ref_valid = [p for p in reference_data if p['lat'] != 0.0 and p['lon'] != 0.0]
    csv_valid = [p for p in csv_data if p['lat'] != 0.0 and p['lon'] != 0.0]
    
    print(f"\nReference: {len(ref_valid)} valid positions (out of {len(reference_data)} total)")
    print(f"CSV Output: {len(csv_valid)} valid positions (out of {len(csv_data)} total)")
    
    # Compare each reference position with CSV
    for ref_pos in ref_valid:
        best_match = None
        best_distance = float('inf')
        
        ref_icao = ref_pos['icao'].replace('0x', '').lower()
        
        for csv_pos in csv_valid:
            csv_icao = csv_pos['icao'].replace('0x', '').lower()
            
            if ref_icao != csv_icao:
                continue
            
            # Calculate differences
            d_lat = abs(ref_pos['lat'] - csv_pos['lat'])
            d_lon = abs(ref_pos['lon'] - csv_pos['lon'])
            d_alt = abs(ref_pos['alt'] - csv_pos['alt'])
            
            distance = math.sqrt(d_lat**2 + d_lon**2)
            
            if distance < best_distance:
                best_distance = distance
                best_match = {
                    'csv_pos': csv_pos,
                    'd_lat': d_lat,
                    'd_lon': d_lon,
                    'd_alt': d_alt,
                    'distance': distance
                }
        
        if best_match and best_match['d_lat'] < tolerance_deg and \
           best_match['d_lon'] < tolerance_deg and best_match['d_alt'] <= tolerance_alt:
            matches.append({
                'ref': ref_pos,
                'csv': best_match['csv_pos'],
                'diff': best_match
            })
        else:
            mismatches.append({
                'ref': ref_pos,
                'best_match': best_match
            })
    
    return matches, mismatches

# ============================================================================
# File Matching and Main Logic
# ============================================================================

def find_matching_csv(frame_filename, output_dirs):
    """
    Finds the corresponding CSV file for a frame file.
    Example: frames_20251019_170733.txt -> output170733.csv
    """
    # Extract timestamp from frame filename
    match = re.search(r'frames_(\d{8}_)?(\d{6})', frame_filename)
    if not match:
        return None
    
    time_part = match.group(2)  # HHMMSS
    csv_name = f"output{time_part}.csv"
    
    # Search in output directories
    for output_dir in output_dirs:
        csv_path = os.path.join(output_dir, csv_name)
        if os.path.exists(csv_path):
            return csv_path
    
    return None

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Verify ADS-B decoder output against reference frames',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Decoder Options:
  custom   - Use custom CPR decoder (default)
  pymodes  - Use pyModeS library (requires: pip install pyModeS)

Examples:
  python verify_frames.py                    # Use custom decoder
  python verify_frames.py --decoder=pymodes  # Use pyModeS
        """
    )
    parser.add_argument(
        '--decoder',
        choices=['custom', 'pymodes'],
        default='custom',
        help='Decoder to use for frame decoding (default: custom)'
    )
    
    args = parser.parse_args()
    
    # Check if pyModeS is available when requested
    if args.decoder == 'pymodes' and not PYMODES_AVAILABLE:
        print("Error: pyModeS not installed. Install with: pip install pyModeS")
        print("Falling back to custom decoder...")
        args.decoder = 'custom'
    
    # Setup paths
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frames_dir = os.path.join(project_root, "frames_adsb", "frames_adsb")
    output_dirs = [
        os.path.join(project_root, "output", "20260109", "iq_output3"),
        os.path.join(project_root, "output", "20260109", "outputs"),
    ]
    
    if not os.path.exists(frames_dir):
        print(f"Error: Frames directory not found: {frames_dir}")
        return
    
    # Get all frame files
    frame_files = [f for f in os.listdir(frames_dir) if f.endswith('.txt')]
    
    print(f"Found {len(frame_files)} frame files in {frames_dir}")
    print(f"Decoder: {args.decoder.upper()}")
    print("=" * 80)
    
    total_matches = 0
    total_mismatches = 0
    total_files_processed = 0
    
    for frame_file in sorted(frame_files):
        frame_path = os.path.join(frames_dir, frame_file)
        csv_path = find_matching_csv(frame_file, output_dirs)
        
        if not csv_path:
            print(f"\n[SKIP] {frame_file}: No matching CSV found")
            continue
        
        print(f"\n[PROCESSING] {frame_file}")
        print(f"  Frame file: {frame_path}")
        print(f"  CSV file:   {csv_path}")
        
        # Parse and decode frames
        frames = parse_frame_file(frame_path)
        print(f"  Parsed {len(frames)} frames")
        
        # Use selected decoder
        if args.decoder == 'pymodes':
            reference_data = decode_frames_pymodes(frames)
        else:
            reference_data = decode_frames(frames)
        print(f"  Decoded {len(reference_data)} position messages")
        
        # Load CSV
        csv_data = load_csv_output(csv_path)
        
        # Compare
        matches, mismatches = compare_positions(reference_data, csv_data)
        
        total_matches += len(matches)
        total_mismatches += len(mismatches)
        total_files_processed += 1
        
        print(f"\n  RESULTS:")
        print(f"    Matches:    {len(matches)}")
        print(f"    Mismatches: {len(mismatches)}")
        
        if len(matches) + len(mismatches) > 0:
            match_rate = len(matches) / (len(matches) + len(mismatches)) * 100
            print(f"    Match Rate: {match_rate:.1f}%")
        
        # Show first few mismatches
        if mismatches and len(mismatches) <= 3:
            print(f"\n  Mismatch Details:")
            for mm in mismatches[:3]:
                ref = mm['ref']
                print(f"    REF: ICAO={ref['icao']}, Lat={ref['lat']:.5f}, Lon={ref['lon']:.5f}, Alt={ref['alt']}")
                if mm['best_match']:
                    csv = mm['best_match']['csv_pos']
                    diff = mm['best_match']
                    print(f"    CSV: ICAO={csv['icao']}, Lat={csv['lat']:.5f}, Lon={csv['lon']:.5f}, Alt={csv['alt']}")
                    print(f"    DIFF: ΔLat={diff['d_lat']:.5f}, ΔLon={diff['d_lon']:.5f}, ΔAlt={diff['d_alt']}")
                else:
                    print(f"    CSV: No match found")
    
    # Summary
    print("\n" + "=" * 80)
    print("OVERALL SUMMARY")
    print("=" * 80)
    print(f"Files processed: {total_files_processed}")
    print(f"Total matches:   {total_matches}")
    print(f"Total mismatches: {total_mismatches}")
    
    if total_matches + total_mismatches > 0:
        overall_rate = total_matches / (total_matches + total_mismatches) * 100
        print(f"Overall match rate: {overall_rate:.1f}%")

if __name__ == "__main__":
    main()
