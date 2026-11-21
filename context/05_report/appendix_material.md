## 9. Appendix Material

### A. Hardware Specifications

**Adafruit Pro Tinkrer 5V @ 16 MHz**
- MCU: ATmega328P (same as Arduino Uno)
- Clock: 16 MHz crystal
- Supply: 5V USB (via MBR0520 schottky from USB or BAT pin)
- Flash: 28 KB usable (bootloader uses 4 KB)
- UART: hardware UART on pins 0 (RX) / 1 (TX)
- Trigger GPIO: configurable (any digital output pin)
- Firmware: AES-128 ECB via mbedTLS or tiny-AES-c
- Shunt placement: 10 Ω in series with 5V supply rail to VCC pin

**Arduino Uno R4 Minima**
- MCU: Renesas RA4M1 (ARM Cortex-M4, 48 MHz)
- Supply: USB 5V via onboard regulator
- Captured: 2000 traces × 4807 samples (shunt on GND rail)
- Serial: USB CDC (resets on DTR — use `--serial-delay 2` in capture)

**Raspberry Pi Pico**
- MCU: RP2040 (dual Arm Cortex-M0+, 125 MHz)
- Core voltage: 1.1V DVDD via internal SMPS
- Captured: 100 traces × 4000 samples (shunt on GND rail)
- **Note:** internal SMPS makes power SCA very difficult without hardware modification

**Keysight Oscilloscope**
- VISA: `USB0::0x2A8D::0x17B6::MY65060127::INSTR`
- Backend: pyvisa-py (USBTMC, no proprietary driver)
- Sample rate: ≥ 250 MS/s
- Waveform format: BYTE (uint8 ADC counts, 8-bit resolution)

### B. Neural Network Architecture Detail

See §6.4 above for full architecture.  
**TODO-NN-TABLE:** Insert Table II from Hettwer et al. 2020 reproduced in LaTeX tabular format in the report appendix. Include parameter counts per layer.

| Layer | Output shape | Parameters |
|---|---|---|
| Input | (64, 64, C) | 0 |
| Conv2D(8, 5×5) | (64, 64, 8) | 8×(5×5×C+1) |
| BatchNorm | (64, 64, 8) | 32 |
| MaxPool(2×2) | (32, 32, 8) | 0 |
| Dropout(0.5) | (32, 32, 8) | 0 |
| Conv2D(16, 3×3) | (32, 32, 16) | 16×(3×3×8+1) = 1,168 |
| BatchNorm | (32, 32, 16) | 64 |
| MaxPool(2×2) | (16, 16, 16) | 0 |
| Dropout(0.5) | (16, 16, 16) | 0 |
| Flatten | (4096,) | 0 |
| Dense(250) | (250,) | 4096×250+250 = 1,024,250 |
| BatchNorm | (250,) | 1,000 |
| Dropout(0.3) | (250,) | 0 |
| Dense(256, softmax) | (256,) | 250×256+256 = 64,256 |

Total trainable params (C=2, GASF+GADF): ~1,090,000

### C. Video / Image Evidence

**TODO-VIDEO-PATHS:** Add actual file paths or YouTube/Drive links for:
- [ ] Video: oscilloscope trigger firing on GPIO rising edge (Pro Tinkrer )
- [ ] Video: AES power trace visible on scope display
- [ ] Video: Python capture script running in terminal (tqdm progress)
- [ ] Image: representative scope screenshot — Pro Tinkrer 5V power trace
- [ ] Image: representative scope screenshot — Arduino Uno R4 Minima
- [ ] Image: `media/diagnostics/trigger_alignment.png` — variance analysis showing AES window vs noise

### D. GitHub Repository

**TODO-GITHUB-LINK:** Replace placeholder with actual URL.

```
https://github.com/PLACEHOLDER/power-analysis-sca
```

Repository structure:
```
attacks/
  classical/cpa.py         — CPA (Pearson correlation)
  classical/dpa.py         — DPA (differential mean)
  classical/guessing_entropy.py — GE curves
  deep_learning/hettwer_sca.py  — Hettwer 2020 CNN
  deep_learning/image_encode.py — GASF/GADF/RP/MTF encoders
  helper.py                — shared AES tables, key schedule, load_dataset
capture/
  capture.py               — unified capture script (all boards)
  examples.txt             — example commands
data/
  set_001_pico_real/       — RPi Pico (100 traces, failed to converge)
  set_002_reference/       — ChipWhisperer reference (2000 traces, working)
  set_003_arduino_shuntGND/— Arduino Uno R4 (2000 traces)
  DATA_FORMAT.md           — schema documentation
firmware/
  main.cpp                 — Pico firmware (mbedTLS AES, GPIO trigger)
report/                    — LaTeX report source
```

---

