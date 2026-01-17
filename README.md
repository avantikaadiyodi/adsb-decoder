# ADS-B Decoder

A Python-based ADS-B (Automatic Dependent Surveillance-Broadcast) signal decoder that processes raw IQ samples from RTL-SDR devices and extracts aircraft position, altitude, and identification data.

## Overview

This project decodes Mode S ADS-B signals from binary IQ sample files, extracts aircraft telemetry (ICAO address, latitude, longitude, altitude), and provides multiple output formats for analysis and visualization. 

## Features

- **Raw Signal Processing**: Decodes 8-bit unsigned IQ samples at 2 Msps sample rate
- **Preamble Detection**: Dynamic threshold-based Mode S preamble detection
- **PPM Decoding**: Pulse Position Modulation decoder for 112-bit ADS-B messages
- **CPR Decoding**: Global CPR (Compact Position Reporting) decoder using even/odd frame pairs
- **Multiple Output Formats**: CSV, JSON, and KML (Google Earth) support
- **Verification Tools**: Cross-validation against pyModeS reference decoder
- **Visualization**: Generate comparison graphs and 2D flight path plots
- **Batch Processing**: Process multiple IQ files automatically

## Project Structure

```
adsb_decode/
├── src/
│   ├── adsb_decoder.py          # Core decoder (preamble detection, PPM, CPR)
│   ├── verify_frames.py         # Verification tool (compares with pyModeS)
│   ├── visualize_comparison.py  # Graph generation for analysis
│   ├── gen_test.py              # Test data generator
│   └── test_crc.py              # CRC validation utilities
├── iq_samples/                  # Input: Raw IQ binary files
├── frames_adsb/                 # Intermediate: Extracted hex frames
├── output/                      # Output: Decoded CSV/JSON (organized by date)
├── graphs_out/                  # Output: Comparison graphs
└── final_outputs/               # Output: KML files for Google Earth
```

## Installation

### Prerequisites

- Python 3.7+
- NumPy
- Matplotlib (for visualization)
- pyModeS (for verification)

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd adsb_decode

# Install dependencies
pip install numpy matplotlib pyModeS
```

## Usage

### Basic Decoding

Decode a single IQ sample file and output to CSV:

```bash
python src/adsb_decoder.py "iq_samples/iq_samples_20251019_180842.bin" .csv
```

Output to JSON:

```bash
python src/adsb_decoder.py "iq_samples/iq_samples_20251019_180842.bin" .json
```

### Output Format

**CSV Format** (`output/YYYYMMDD/outputHHMM.csv`):
```csv
lat,lon,alt,icao
12.34567,78.91234,35000,0x4b1234
12.34589,78.91256,35025,0x4b1234
```

**JSON Format** (`output/YYYYMMDD/outputHHMM.json`):
```json
[
    {"lat": 12.34567, "lon": 78.91234, "alt": 35000, "icao": "0x4b1234"},
    {"lat": 12.34589, "lon": 78.91256, "alt": 35025, "icao": "0x4b1234"}
]
```

### Verification

Compare custom decoder output against pyModeS reference:

```bash
python src/verify_frames.py
```

This tool:
- Reads raw frames from `frames_adsb/`
- Decodes using both custom CPR decoder and pyModeS
- Compares outputs and generates accuracy statistics
- Outputs verification reports to `verification_custom.txt` and `verification_pymodes.txt`

### Visualization

Generate comparison graphs showing latitude, longitude, altitude, and 2D flight paths:

```bash
python src/visualize_comparison.py
```

Outputs saved to `graphs_out/YYYYMMDD/graph_HHMMSS.png`

## How It Works

### 1. Signal Processing Pipeline

```
IQ Samples → Magnitude Calculation → Preamble Detection → Bit Decoding → Frame Parsing → CPR Decoding
```

### 2. Preamble Detection

Mode S preambles follow a specific pulse pattern at 2 Msps:
- Pulse at 0.0-0.5 μs (sample 0)
- Pulse at 1.0-1.5 μs (sample 2)
- Pulse at 3.5-4.0 μs (sample 7)
- Pulse at 4.5-5.0 μs (sample 9)

The decoder uses dynamic thresholding (5× average magnitude) to identify these patterns.

### 3. PPM Decoding

Each bit is encoded in 1 μs (2 samples at 2 Msps):
- **Bit 1**: Pulse in first half, empty in second
- **Bit 0**: Empty in first half, pulse in second

### 4. CPR Decoding

Compact Position Reporting uses even/odd frame pairs to encode global position:
- Even frames (CPR format = 0)
- Odd frames (CPR format = 1)
- Global position calculated when both frames are available for the same aircraft

### 5. DF17 Message Parsing

Downlink Format 17 (ADS-B) messages contain:
- **ICAO Address** (24 bits): Unique aircraft identifier
- **Type Code** (5 bits): Message type (9-18 for airborne position)
- **Altitude** (12 bits): Encoded altitude (25 ft or 100 ft resolution)
- **CPR Latitude** (17 bits): Encoded latitude
- **CPR Longitude** (17 bits): Encoded longitude

## Configuration

### Output Mode Selection

The decoder supports two output modes in `adsb_decoder.py`:

**Option 1: Auto-Timestamp (Default)**
```python
# Automatically creates: output/YYYYMMDD/outputHHMM.ext
# Enabled by default (lines 492-512)
```

**Option 2: Manual/Batch Path**
```python
# Uses exact path specified in command line
# Uncomment lines 515-522 to enable
```

### Input File Selection

**Option A: Command Line (Default)**
```python
# Usage: python adsb_decoder.py <iq_file> <output_hint>
```

**Option B: Hardcoded Path**
```python
# Uncomment line 569 in adsb_decoder.py
filepath = "./iq_samples/iq_samples_20251019_172049_619.bin"
```

## Performance

- **Sample Rate**: 2 Msps (standard RTL-SDR ADS-B rate)
- **Processing Speed**: Depends on file size and signal density
- **False Positive Rate**: Minimized through preamble pattern matching

## Known Limitations

- **CRC Validation**: CRC check logic exists but is currently disabled for performance (line 452 in `adsb_decoder.py`)
- **Surface Messages**: Only airborne position messages (TC 9-18) are fully supported
- **Aircraft Identification**: Callsign decoding (TC 1-4) not yet implemented
- **Single Frame Decoding**: Requires even/odd frame pairs for position; partial data shown otherwise

## Future Enhancements

- **Real-Time Processing**: Stream data directly from RTL-SDR via `rtl_tcp`
- **Interactive Dashboard**: Web-based UI for live aircraft tracking
- **Flight Database Integration**: Lookup aircraft details via OpenSky API
- **Velocity Decoding**: Extract ground speed, heading, and vertical rate (TC 19)
- **Error Correction**: Single-bit error correction using CRC polynomial
- **Enhanced CRC**: Re-enable CRC validation with optimized performance

## Technical Details

### Constants

```python
SAMPLE_RATE = 2000000        # 2 Msps
PREAMBLE_LEN_US = 8          # 8 microseconds
DATA_LEN_BIT = 112           # 112 bits per message
GENERATOR_POLY = 0xFFFA0480  # Mode S CRC polynomial
```

### CPR Constants

```python
NZ = 15                      # Number of latitude zones
d_lat_even = 360.0 / 60.0   # Even latitude zone width
d_lat_odd = 360.0 / 59.0    # Odd latitude zone width
```

## Troubleshooting

### No Signals Detected

- Check threshold setting (line 587): May need adjustment for weak signals
- Verify IQ file format (8-bit unsigned, interleaved I/Q)
- Ensure sample rate is 2 Msps

### Partial Position Data

- Indicates missing even or odd CPR frame
- Aircraft may be at edge of reception range
- Wait for complete frame pair or use reference position decoding

### Unicode Encoding Errors

- Fixed in current version (uses UTF-8 with error handling)
- Ensure output redirection uses proper encoding on Windows

## Contributing

Contributions are welcome! Areas for improvement:
- Performance optimization
- Additional message type support
- Real-time processing capabilities
- Enhanced visualization options

## Acknowledgments

- pyModeS library for reference implementation
- RTL-SDR community for documentation and tools
- ICAO Annex 10 Volume 4 for ADS-B specifications