# Power Analysis SCA — ESE5370 Hardware Security

Side-channel analysis (SCA) test bench targeting AES-128.  
Firmware, capture, image encoding, and deep learning attack pipeline.

---

## Data

Captured power traces (Adafruit Pro Trinket 5V, 50 000 traces × 30 000 samples):

**[Google Drive — dataset download](https://drive.google.com/file/d/1Itl82UCQEDyk6cYDD33kB-gKtlXIQBZe/view?usp=sharing)**

---

## Target Hardware

### Adafruit Pro Trinket 5V 16 MHz — ATmega328P **[WORKING]**

The Pro Trinket uses the Atmel **ATmega328P** microcontroller running at 5 V / 16 MHz.
Power is supplied directly to the AVR core with no internal switching regulator between the supply rail and the chip, making the power consumption directly observable with a shunt resistor on the 5 V line.

- Shunt: 10 Ω on 5 V supply rail
- Oscilloscope: Keysight DSOX1204G, CHANnel1, 30 000 points/trace
- Trigger: GPIO output toggled around `AES_ECB_encrypt` first round
- CPA breaks AES byte 0 in under 100 traces at 20 833 samples/trace

### Raspberry Pi Pico W — RP2040 **[FAILED — power regulator]**

The Pico W includes an internal switch-mode power supply (RT6154A) that converts the
5 V USB input to **1.1 V** for the RP2040 core.  This switching regulator dominates
the current draw seen at the supply rail, masking the AES-correlated signal entirely.
The regulator switching noise (≈ MHz ripple) overwhelms the µA-level cryptographic
leakage, making power analysis from the 5 V rail impractical without desoldering the
regulator and injecting a clean LDO supply directly — which was out of scope.

> Firmware and capture infrastructure for the Pico remain in `firmware/` for reference,
> but all training data and attack results use the Pro Trinket.

---

## Repository Structure

```
power_analysis_sca/
├── firmware/               — RP2040 / AVR firmware (AES + UART protocol)
├── capture/
│   ├── capture.py          — Unified capture script (USB & Ethernet scope)
│   └── examples.txt        — Ready-to-run capture commands
├── attacks/
│   ├── helper.py           — SBOX, HW, load_dataset, key_rank utilities
│   ├── cpa/
│   │   └── cpa_attack.py   — Correlation Power Analysis
│   └── deep_learning/
│       ├── hettwer_sca.py  — Hettwer et al. 2020 CNN (Table II exact)
│       ├── ascad_loader.py — ASCADv1 loader for benchmark training
│       ├── image_encode.py — GASF / GADF / RP / MTF encoding
│       └── device.py       — GPU/MPS device detection
└── plot_traces.py          — Dataset visualisation (Fig. 2 style)
```

---

## Quick Start

### 1. Capture (Pro Trinket, Ethernet scope)

```bash
cd capture
python capture.py --board adafruit_trinket_pro_5v16mhz \
                  --port /dev/tty.usbmodem101 \
                  --num-traces 50000 \
                  --scope-ip 169.254.161.197 \
                  --scope-points 30000 \
                  --notes "shunt 10 Ohm on 5 V"
```

See `capture/examples.txt` for USB scope and VXI-11 variants.

### 2. CPA Attack

```bash
python attacks/cpa/cpa_attack.py --data data/set_001_adafruit_trinket_pro_5v16mhz
```

### 3. Deep Learning Attack (Hettwer CNN)

```bash
# Train on captured data (GASF+GADF, paper's best channel combo)
python attacks/deep_learning/hettwer_sca.py \
    --data data/set_001_adafruit_trinket_pro_5v16mhz \
    --channels gasf+gadf --byte 0

# Train on ASCADv1 benchmark dataset
python attacks/deep_learning/hettwer_sca.py \
    --ascad-h5 /path/to/ASCAD.h5 --channels gasf+gadf
```

### 4. Visualise Dataset

```bash
python plot_traces.py --data data/set_001_adafruit_trinket_pro_5v16mhz
```

---

## Dependencies

```bash
pip install numpy scipy h5py matplotlib tqdm pyserial pyvisa pyvisa-py tensorflow
```

---

## References

- Hettwer et al. "Encoding Power Traces as Images for Efficient Side-Channel Analysis", HOST 2020 — [arXiv:2004.11015](https://arxiv.org/abs/2004.11015)
- Benadjila et al. "ASCAD: ANSSI SCA Database", 2019 — [github.com/ANSSI-FR/ASCAD](https://github.com/ANSSI-FR/ASCAD)
