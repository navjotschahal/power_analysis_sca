## 4. Data Acquisition Hardware — Pro Tinkrer (Only Board That Worked)

### 4.1 Hardware Schematic (Pro Tinkrer 5V @ 16 MHz)

```
USB 5V ──┬── [10 Ω shunt] ──┬── Pro Tinkrer VCC pin
         │                  │
         │              [scope CH1+]  ← Keysight oscilloscope
         │              [scope CH1-] ── GND
         │
         └── GND ──────────────────── Trinket GND pin

Trigger wiring:
  Trinket GPIO pin ──────── [scope CH2] / EXT TRIG BNC
  (GPIO goes HIGH before AES, LOW after AES)

Host connection:
  USB-UART adapter (FTDI) ── /dev/tty.usbserial-0001
  Trinket TX/RX ──────────── adapter RX/TX
  Baud: 115200

Oscilloscope settings:
  Ch1: power trace (differential across shunt)
  Ch2/EXT: trigger (GPIO)
  Trigger: rising edge, Ch2
  Sample rate: ≥ 250 MS/s
  Points per acquisition: 30,000 (scope_points in capture.py)
  Format: BYTE transfer (binary, fast)
```

### 4.2 Oscilloscope

**Model:** Keysight/Agilent (VISA address: `USB0::0x2A8D::0x17B6::MY65060127::INSTR`)  
**Control:** PyVISA with pyvisa-py backend (USBTMC, no proprietary driver needed on macOS)  
**Key SCPI commands:**
- `:WAVeform:SOURce CHANnel1` — read power trace from Ch1
- `:WAVeform:FORMat BYTE` — binary uint8 transfer
- `:WAVeform:POINts:MODE NORMal`
- `:WAVeform:POINts 30000` — 30k samples for Trinket
- `:SINGle` — arm single-shot trigger
- `*OPC?` — synchronise (wait for acquisition complete)
- `:WAVeform:DATA?` — download waveform

### 4.3 Capture Command (Pro Tinkrer , 50k traces)

```bash
python capture/capture.py --board adafruit_trinket_pro_5v16mhz \
                          --port /dev/tty.usbmodem101 \
                          --num-traces 50000 \
                          --baud 115200 \
                          --serial-delay 0.5 \
                          --scope-address USB0::0x2A8D::0x17B6::MY65060127::INSTR \
                          --scope-channel CHANnel1 \
                          --scope-points 30000 \
                          --notes "shunt on 5 V using 10 Ohm"
```

---

