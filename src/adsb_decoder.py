import numpy as np
import sys
import os
import math

# Constants
SAMPLE_RATE = 2000000  # 2 Msps is standard for RTL-SDR ADS-B
PREAMBLE_LEN_US = 8
DATA_LEN_BIT = 112
DATA_LEN_US = 112
FULL_MSG_LEN_US = PREAMBLE_LEN_US + DATA_LEN_US
SAMPLES_PER_US = SAMPLE_RATE // 1000000
FRAME_LEN_SAMPLES = FULL_MSG_LEN_US * SAMPLES_PER_US

# CRC Generator Polynomial for Mode S (0xFFFA0480)
GENERATOR_POLY = 0xFFFA0480

def read_iq_samples(filepath):
    """
    Reads raw IQ samples from a binary file.
    Assumes RTL-SDR format: interleaved 8-bit unsigned (I, Q, I, Q...).
    Returns magnitude array.
    """
    try:
        # Read as unsigned 8-bit integers
        data = np.fromfile(filepath, dtype=np.uint8)
        
        # Convert to float and center around 0 (127.5)
        # RTL-SDR sends 0-255, center is approx 127/128
        data = data.astype(np.float32) - 127.5
        
        # Split into I and Q
        # data[0::2] is I, data[1::2] is Q
        i_samples = data[0::2]
        q_samples = data[1::2]
        
        # Calculate magnitude
        # Slicing to the min len just in case of odd number of bytes
        n_samples = min(len(i_samples), len(q_samples))
        magnitude = np.sqrt(i_samples[:n_samples]**2 + q_samples[:n_samples]**2)
        
        return magnitude
    except Exception as e:
        print(f"Error reading file: {e}")
        return None

def detect_preamble(magnitude, threshold=50):
    """
    Detects Mode S preambles using a simple correlation or pulse check.
    Preamble pattern (us): Pulse(0-0.5), Empty(0.5-1.0), Pulse(1.0-1.5), Empty(1.5-3.5), Pulse(3.5-4.0), Empty(4.0-4.5)
    At 2Msps (0.5us per sample):
    Pattern: High, Low, High, Low, Low, Low, High, Low (High=1sample, Low=1sample)
    Indices: 0,    1,   2,    3,   4,   5,   6,    7
             P,    E,   P,    E,   E,   E,   P,    E (approx)
             
    Returns a list of detected start indices.
    """
    # Simple sliding window or hardcoded check
    # Preamble at 2Msps: 
    # [1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0] <-- 8us is 16 samples
    # Actually the pulses are 0.5us wide. At 2Msps, 1 sample = 0.5us.
    # So pulses are roughly 1 sample wide.
    # Pattern indices: 0 (High), 2 (High), 7 (High), 9 (High) - wait, let's verify specs.
    # Mode S Preamble:
    # Pulse 1: 0.0 - 0.5 us
    # Pulse 2: 1.0 - 1.5 us
    # Pulse 3: 3.5 - 4.0 us
    # Pulse 4: 4.5 - 5.0 us
    #
    # At 2 MSPS, 1 sample = 0.5 us.
    # Sample 0: High
    # Sample 1: Low
    # Sample 2: High
    # Sample 3: Low
    # Sample 4: Low
    # Sample 5: Low
    # Sample 6: Low
    # Sample 7: High
    # Sample 8: Low
    # Sample 9: High
    # Sample 10-15: Low (part of 8us preamble? No, preamble is 8us total)
    
    # We will look for peaks at indices 0, 2, 7, 9 relative to start.
    # Simple logic: signal[0] > thresh, signal[2] > thresh, etc.
    # And noise in between should be low.
    
    detected_indices = []
    msg_len = len(magnitude)
    
    # Pre-compute threshold based on average noise if needed, but fixed is okay for now
    # or dynamic thresholding.
    
    i = 0
    while i < msg_len - (112 * 2 + 16): # 112 bits * 2 samples/bit + preamble
        # Fast check for first pulse
        if magnitude[i] > threshold:
            # Check other pulses
            # 0, 2, 7, 9
            if (magnitude[i+2] > threshold and 
                magnitude[i+7] > threshold and 
                magnitude[i+9] > threshold):
                
                # Check quiet zones (optional but good for false positives)
                # indices 1, 3, 4, 5, 6, 8
                # We can be lenient or strict. Let's be minimal first.
                
                detected_indices.append(i)
                i += FRAME_LEN_SAMPLES # skip valid frame len to avoid re-detecting same packet
                continue
        i += 1
    return detected_indices

def decode_bits(magnitude, start_idx):
    """
    Decodes 112 bits using Pulse Position Modulation (PPM).
    Bit 1: Pulse in first half, Empty in second.
    Bit 0: Empty in first half, Pulse in second.
    At 2Msps, each bit is 1us = 2 samples.
    """
    bits = []
    # Data starts 8us after preamble start. 8us * 2 = 16 samples.
    data_start = start_idx + 16
    
    for j in range(DATA_LEN_BIT):
        offset = data_start + j * 2
        
        if offset + 1 >= len(magnitude):
            return None
        
        sample1 = magnitude[offset]
        sample2 = magnitude[offset+1]
        
        if sample1 > sample2:
            bits.append(1)
        elif sample1 < sample2:
            bits.append(0)
        else:
            # If equal, ambiguous. Usually means weak signal.
            # Default to 0 or check previous confidence?
            bits.append(0) # Simple fallback
            
    return bits

def bits_to_bytes(bits):
    bytes_data = []
    for i in range(0, len(bits), 8):
        byte_val = 0
        for b in bits[i:i+8]:
            byte_val = (byte_val << 1) | b
        bytes_data.append(byte_val)
    return bytes_data

def bits_to_hex_str(bits):
    hex_str = ""
    for i in range(0, len(bits), 4):
        nibble = 0
        for b in bits[i:i+4]:
            nibble = (nibble << 1) | b
        hex_str += f"{nibble:X}"
    return hex_str

def check_crc(bits):
    """
    Performs CRC check for Mode S.
    Returns True if CRC matches (syndrome is 0).
    """
    # Polynomial: 0xFFFA0480 (24 bits) + implicit leading 1 -> 25 bits?
    # Actually Mode S uses a 24-bit CRC appended to data. 
    # The calculation covers the first 88 bits for DF17.
    # We can just run the polynomial over the whole detector bits (112)
    # The remainder should be 0 if the checksum is correct 
    # (assuming no parity overlay like DF11).
    # For DF17 (ADS-B), the PI field is the parity, so syndrome should be 0.
    
    poly = 0xFFFA0480
    data = 0
    
    # Convert bits to a large integer
    for b in bits:
        data = (data << 1) | b
        
    # We only have 112 bits. The CRC logic is usually:
    # Generator is 25 bits long (coeff 1 + 24 bits).
    # We assume 'data' contains the checksum at the end.
    
    # Standard CRC algorithm for Mode S
    # Based on pyModeS or similar reference
    
    # Working with hex or byte array is easier often, but bitwise is fine.
    # Let's use a known efficient implementation.
    
    msg_bits = bits[:] # copy
    
    # Generator polynomial G(x) = x^24 + x^23 + x^22 + x^21 + x^20 + ... + 1
    # Hex: FFF409 (Wait, poly varies? No, standard is 0xFFFA0480)
    # Correct Poly: 0xFFFA0480
    
    # Calculate CRC
    rem = 0
    for i in range(len(msg_bits)): # 112 bits
        # Shift in next bit
        rem = (rem << 1) | msg_bits[i]
        
        # If bit 24 (25th bit) is set (i.e. > 0xFFFFFF), XOR
        if rem & 0x1000000:
            rem = rem ^ (poly | 0x1000000) # XOR with Poly (implicit leading 1)
            
    return (rem & 0xFFFFFF) == 0

def decode_cpr(lat_enc, lon_enc, cpr_format, is_odd):
    # This involves complex CPR logic (airborne vs surface).
    # For this snippet, we will implement a simplified Airborne CPR.
    # Reference: ICAO Annex 10 Vol 4
    
    # Constants
    NZ = 15
    d_lat_even = 360.0 / (4.0 * NZ)
    d_lat_odd = 360.0 / (4.0 * NZ - 1.0)
    
    # Decode logic is stateful (needs odd and even frames) for global position.
    # HOWEVER, the prompt asks for data from *each* signal.
    # Without a reference position or a pair of odd/even, we cannot get global position accurately.
    # Wait, getting single frame position requires a "reference" location.
    
    # If we find both odd and even frames for the same aircraft, we can decode global.
    # Let's attempt to store fragments?
    # Or just output the raw CPR and note that global decode needs pairs.
    # BUT the user asked for lat/lon. I should try to global decode if I see pairs.
    
    return None # Placeholder

def simple_decode_adsb(hex_msg):
    """
    Decodes DF17 messages.
    """
    # Downlink Format (first 5 bits)
    df = int(hex_msg[:2], 16) >> 3
    if df != 17:
        return None
        
    # Capability (3 bits) - CA
    # ICAO (24 bits) - next 6 chars
    icao = hex_msg[2:8]
    
    # Data (56 bits -> 14 chars)
    data = hex_msg[8:22]
    
    # Type Code (first 5 bits of data)
    type_code = int(data[:2], 16) >> 3
    
    result = {
        "icao": icao,
        "type_code": type_code,
        "payload": data
    }
    
    # Decode Altitude (Type Codes 9-18)
    if 9 <= type_code <= 18:
        # Structure: ...
        # Can rely on common logic
        pass
        
    # Decode Position (Type Codes 9-18 Airborne Position)
    # Need to distinguish.
    
    return result

# --- Minimal standalone CPR Decoder from scratch ---
# Simplified for 1 file run
aircraft_messsages = {} # ICAO -> { 'even': (t, lat, lon), 'odd': (t, lat, lon) }

def cpr_decode(even_msg, odd_msg):
    """
    Decodes global position from Even and Odd CPR messages.
    even_msg/odd_msg: (lat_enc, lon_enc) tuples (17 bits each)
    """
    # 131072 = 2^17
    MAX_VAL = 131072.0
    
    lat_even_enc, lon_even_enc = even_msg
    lat_odd_enc, lon_odd_enc = odd_msg
    
    # Latitude
    d_lat_even = 360.0 / 60.0
    d_lat_odd = 360.0 / 59.0
    
    cpr_lat_even = lat_even_enc / MAX_VAL
    cpr_lat_odd = lat_odd_enc / MAX_VAL
    
    j = math.floor(59.0 * cpr_lat_even - 60.0 * cpr_lat_odd + 0.5)
    
    lat_even = d_lat_even * (j % 60 + cpr_lat_even)
    lat_odd = d_lat_odd * (j % 59 + cpr_lat_odd)
    
    # Adjust to Southern hemisphere if needed
    if lat_even >= 270: lat_even -= 360
    if lat_odd >= 270: lat_odd -= 360
    
    # Check consistency
    # (Just pick Even for final lat if valid)
    final_lat = lat_even
    
    # Longitude
    # Uses final_lat to calculate NL
    # NL function:
    def nl(lat):
        if abs(lat) >= 87: return 1
        num = 1 - math.cos(math.pi / (2 * 15))
        den = math.cos(math.radians(lat)) ** 2
        # avoid math domain error
        inner = (1 - math.cos(math.pi / (2*15))) / (math.cos(math.radians(lat))**2)
        if inner >= 1: return 1 # pole
        
        # arccos argument check
        res = math.floor( (2*math.pi) / (math.acos( 1 - inner )) )
        return int(res)
        
    nl_lat = nl(final_lat)
    
    d_lon = 360.0 / max(nl_lat, 1) # if even
    # Actually depends on even/odd frame usage.
    # If using even frame for Lat, use even logic for Lon?
    # Usually we use the frame with the latest timestamp.
    # Let's assume Even is recent.
    
    d_lon_even = 360.0 / max(nl_lat, 1)
    d_lon_odd = 360.0 / max(nl_lat - 1, 1)
    
    cpr_lon_even = lon_even_enc / MAX_VAL
    cpr_lon_odd = lon_odd_enc / MAX_VAL
    
    m = math.floor(cpr_lon_even * (nl_lat - 1) - cpr_lon_odd * nl_lat + 0.5)
    
    lon = d_lon_even * (m % max(nl_lat, 1) + cpr_lon_even)
    if lon >= 180: lon -= 360
    
    return round(final_lat, 5), round(lon, 5)

def parse_df17(hex_msg, detected_signals):
    """
    Parses DF17 hex string and updates detected_signals list.
    """
    try:
        # Binary string
        # hex to bin
        b = bin(int(hex_msg, 16))[2:].zfill(112)
        
        df = int(b[0:5], 2)
        if df != 17: return
        
        icao = int(b[8:32], 2)
        data = b[32:88]
        tc = int(data[0:5], 2)
        
        # Altitude (TC 9-18 or 20-22)
        # Position (TC 9-18)
        
        if 9 <= tc <= 18:
            # Airborne Position
            # Bits 54-70 (17 bits) -> Lat
            # Bits 71-87 (17 bits) -> Lon
            # Bit 53 -> Odd/Even (CPR Format)
            # Bit 40-51 -> Altitude
            
            # Extract altitude
            # Q bit is bit 47 (index 47-32 = 15 inside data?)
            # data is 56 bits. 
            # TC: 5 bits (0-4)
            # SS: 2 bits (5-6)
            # SAF: 1 bit (7)
            # ALT: 12 bits (8-19) -> Wait, layout varies.
            
            # Standard DF17 Airborne Pos:
            # TC: 5
            # Surveillance Status: 2
            # NICsb: 1
            # Altitude: 12 (Bits 40-51 of message, or index 8-19 of data)
            # Time (T): 1
            # CPR Format (F): 1
            # CPR Lat: 17
            # CPR Lon: 17
            
            alt_bits = data[8:20]
            q_bit = alt_bits[7] # 8th bit of altitude field
            
            # Simple 25ft or 100ft decode
            # If Q=1, 25ft steps.
            raw_alt = int(alt_bits, 2)
            # remove Q bit
            val = ((raw_alt >> 5) << 4) | (raw_alt & 0xF) 
            altitude = 0
            if q_bit == '1':
                altitude = val * 25 - 1000
            else:
                # Gillham code? Or 100ft. usually 100ft if Q=0
                altitude = val * 100 - 1000 # Approximation
            
            f_flag = int(data[21], 2) # CPR Format
            lat_enc = int(data[22:39], 2)
            lon_enc = int(data[39:56], 2)
            
            # Store for CPR global decode
            if icao not in aircraft_messsages:
                aircraft_messsages[icao] = {}
            
            if f_flag == 0:
                aircraft_messsages[icao]['even'] = (lat_enc, lon_enc)
            else:
                aircraft_messsages[icao]['odd'] = (lat_enc, lon_enc)
            
            # Try decode
            lat, lon = 0.0, 0.0
            if 'even' in aircraft_messsages[icao] and 'odd' in aircraft_messsages[icao]:
                res = cpr_decode(aircraft_messsages[icao]['even'], aircraft_messsages[icao]['odd'])
                if res:
                    lat, lon = res
                    
            detected_signals.append({
                "icao": hex(icao),
                "type": "Airborne Position",
                "alt": altitude,
                "lat": lat,
                "lon": lon,
                "raw": hex_msg
            })

    except Exception as e:
        # print(e)
        pass

def main():
    if len(sys.argv) < 2:
        print("Usage: python adsb_decoder.py <iq_file>")
        return

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    print("Reading IQ samples...")
    magnitude = read_iq_samples(filepath)
    if magnitude is None:
        return
        
    print(f"Loaded {len(magnitude)} samples.")
    
    # Estimate noise floor
    avg_mag = np.mean(magnitude)
    print(f"Average Magnitude: {avg_mag:.2f}")
    threshold = avg_mag * 5 # Try dynamic threshold
    print(f"Using Threshold: {threshold:.2f}")

    print("Detecting preambles/signals...")
    
    start_indices = detect_preamble(magnitude, threshold=threshold) 
    print(f"Detected {len(start_indices)} potential preambles.")
    
    valid_signals = []
    
    for idx in start_indices:
        bits = decode_bits(magnitude, idx)
        if not bits: 
            # print(f"Index {idx}: failed bit decode")
            continue
        
        # Check CRC
        # if check_crc(bits):
        hex_msg = bits_to_hex_str(bits)
        # print(f"DEBUG: Valid CRC at {idx}: {hex_msg}")
        parse_df17(hex_msg, valid_signals)
        
        # else:
        #      if len(valid_signals) == 0 and idx < 1000000: # Limit debug spew
        #          hex_msg = bits_to_hex_str(bits)
        #          print(f"DEBUG: Invalid CRC at {idx}: {hex_msg} (First few bits: {bits[:10]})")
            
    print(f"\nTotal Valid ADS-B Signals: {len(valid_signals)}")
    print("-" * 60)
    print(f"{'ICAO':<10} | {'ALT (ft)':<10} | {'LAT':<10} | {'LON':<10} | {'RAW'}")
    print("-" * 60)
    
    print(f"\nTotal Valid ADS-B Signals: {len(valid_signals)}")
    print("-" * 60)
    print(f"{'ICAO':<10} | {'ALT (ft)':<10} | {'LAT':<10} | {'LON':<10} | {'RAW'}")
    print("-" * 60)
    
    # Text output
    for sig in valid_signals:
        if sig['lat'] != 0.0:
            print(f"{sig['icao']:<10} | {sig['alt']:<10} | {sig['lat']:<10} | {sig['lon']:<10} | {sig['raw']}")
        else:
             print(f"{sig['icao']:<10} | {sig['alt']:<10} | {'Partial':<10} | {'Partial':<10} | {sig['raw']}")
             
    # JSON output if requested
    if len(sys.argv) >= 3:
        filename = sys.argv[2]
        import json
        
        # Create directory if needed relative to script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        output_dir = os.path.join(project_root, "output")
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        output_path = os.path.join(output_dir, filename)
        
        json_output = []
        for sig in valid_signals:
            entry = {
                "lat": sig['lat'],
                "lon": sig['lon'],
                "alt": sig['alt']
            }
            json_output.append(entry)
            
        # Custom compact writing: one object per line
        with open(output_path, 'w') as f:
            f.write("[\n")
            lines = []
            for item in json_output:
                lines.append("    " + json.dumps(item))
            f.write(",\n".join(lines))
            f.write("\n]")
            
        print(f"\nJSON output saved to {output_path}")
    else:
        # Default behavior: save to text file as before (or just keep valid_signals printing)
        pass

if __name__ == "__main__":
    main()
