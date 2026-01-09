def modes_checksum(hex_msg):
    # hex_msg: string of hex digits
    b = bin(int(hex_msg, 16))[2:].zfill(len(hex_msg)*4)
    bits = [int(c) for c in b]
    
    poly = 0xFFFA0480
    rem = 0
    for bit in bits:
        rem = (rem << 1) | bit
        if rem & 0x1000000:
            rem = rem ^ poly
            rem = rem & 0xFFFFFF # Ensure 24 bits
            
    return rem

# Known valid messages
# From pyModeS tests or online examples
# 8D40621D58C382D690C8AC2863A7 (CRC pass?)
# 8D4D24E49908EC91F8548E46668B (My captured one)

msgs = [
    "8D40621D58C382D690C8AC2863A7", 
    "8D75804B580FF2CF7E9BA6F701D0" # Canonical valid
]

for m in msgs:
    res = modes_checksum(m)
    print(f"Msg: {m} -> CRC: {res:06X}")
