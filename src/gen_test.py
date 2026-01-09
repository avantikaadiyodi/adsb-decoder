import numpy as np

# Constants
SAMPLE_RATE = 2000000
# Preamble pattern (16 samples at 2Msps)
# 1 0 1 0 0 0 1 0 1 0 0 0 0 0 0 0
# High is magnitude ~100, Low is ~0 (noise)
# We need I/Q values. 
# Mag = sqrt(I^2 + Q^2)
# If we set Q=0, I=Mag.
# 8-bit unsigned: 127 is 0. 
# High: I=227 (100 amp), Q=127. Mag=100.
# Low: I=127 (0 amp), Q=127. Mag=0.

def create_signal():
    # 2000 samples of noise
    noise = np.random.normal(127.5, 5, 4000).astype(np.uint8) # 2000 I, 2000 Q
    
    # Inject Signal at index 500 (1000 in flat array)
    # Preamble: 1 0 1 0 0 0 1 0 1 0 0 0 0 0 0 0
    pattern = [1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0]
    
    # Create valid frame (just preamble for detection test)
    # interleaved I Q
    # We edit noise array directly
    start_idx = 1000
    
    for i, p in enumerate(pattern):
        val = 227 if p else 127
        # Set I
        noise[start_idx + i*2] = val
        # Set Q (keep at 127 for simple phase)
        noise[start_idx + i*2 + 1] = 127
        
    return noise

data = create_signal()
data.tofile("test_iq.bin")
print("Created test_iq.bin")
