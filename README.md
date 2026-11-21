# Power Analysis SCA — ESE5370 Hardware Security

Side-channel analysis (SCA) test bench targeting AES-128.  
Firmware, capture, image encoding, and deep learning attack pipeline.

---

## Data

Captured power traces (Adafruit Pro Tinkrer 5V, 50 000 traces × 30 000 samples):

**[Google Drive — dataset download](https://drive.google.com/file/d/1Itl82UCQEDyk6cYDD33kB-gKtlXIQBZe/view?usp=sharing)**

---

## Target Hardware

### Adafruit Pro Tinkrer 5V 16 MHz — ATmega328P **[WORKING]**

The Pro Tinkrer uses the Atmel **ATmega328P** microcontroller running at 5 V / 16 MHz.
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
> but all training data and attack results use the Pro Tinkrer .

---

## Repository Structure

```
power_analysis_sca/
├── firmwares/
│   ├── adafruit_pro_trinket_5v15mhz/ — ATmega328P target (Arduino sketch + bare-metal AES)
│   ├── atmega16u2/                   — ATmega16U2 bare-metal AES
│   ├── picow/                        — RP2040 / Pico W target (needs pico-sdk)
│   └── unarduino_uno/                — Arduino Uno R4 sketches
├── capture/
│   ├── capture.py          — Unified capture script (USB & Ethernet scope)
│   ├── capture_fast.py     — Faster capture variant
│   └── examples.txt        — Ready-to-run capture commands
├── attacks/
│   ├── helper.py           — SBOX, HW, load_dataset, key_rank utilities
│   ├── classical/
│   │   ├── cpa.py          — Correlation Power Analysis
│   │   ├── cpa_paper.py    — CPA variant following the paper notation
│   │   ├── dpa.py          — Differential Power Analysis
│   │   └── guessing_entropy.py — GE vs N curves
│   └── deep_learning/
│       ├── hettwer_sca.py  — Hettwer et al. 2020 CNN (Table II exact)
│       ├── ascad_loader.py — ASCADv1 loader for benchmark training
│       ├── image_encode.py — GASF / GADF / RP / MTF encoding
│       └── device.py       — GPU/MPS device detection
├── report/                 — LaTeX report source and figures
├── context/                — Project knowledge base (see Context Index)
├── plot_traces.py          — Dataset visualisation (Fig. 2 style)
│
│   gitignored, restored from links in context/06_sources/external_sources.md:
├── data/                   — captured + downloaded datasets
├── references/             — downloaded papers, notebooks, reference repos
└── pico-sdk/               — Raspberry Pi Pico SDK 2.2.0
```

---

## External Sources

Downloaded material is not committed. Each item is listed with its link, pinned version
or checksum, and a restore command in
[context/06_sources/external_sources.md](context/06_sources/external_sources.md).

| What | Local path | Link |
|---|---|---|
| Raspberry Pi Pico SDK 2.2.0 | `pico-sdk/` | [raspberrypi/pico-sdk](https://github.com/raspberrypi/pico-sdk) |
| DPA/CPA tutorial + reference traces | `references/dpa-on-aes/` | [nvietsang/dpa-on-aes](https://github.com/nvietsang/dpa-on-aes) |
| ASCAD tooling | `data/ascad2/ASCAD_repo/` | [ANSSI-FR/ASCAD](https://github.com/ANSSI-FR/ASCAD) |
| ASCAD v2 dataset (7.7 GB) | `data/ascad2/ascadv2-extracted.h5` | [data.gouv.fr](https://files.data.gouv.fr/anssi/ascadv2/ascadv2-extracted.h5) |
| Hettwer et al. 2020 paper | `references/power_trace_image_encoding_dnn_sca.pdf` | [arXiv:2004.11015](https://arxiv.org/abs/2004.11015) |
| NCC Group ML104 notebook | `references/NCCGroup_ML104_blog.ipynb` | [NCC Group blog](https://www.nccgroup.com/research/machine-learning-104-breaking-aes-with-power-side-channels/) |
| Own Pro Trinket captures (50k traces) | `data/set_0NN_*` | [Google Drive](https://drive.google.com/file/d/1Itl82UCQEDyk6cYDD33kB-gKtlXIQBZe/view?usp=sharing) |

---

## Context Index

Project knowledge is split into small topic modules under `context/`, grouped by area.
Read the overview first, then only the modules a task needs.

| Area | Module | Contents |
|---|---|---|
| 00 Overview | [00_overview.md](context/00_overview.md) | Course, author, purpose of the context set |
| 01 Project | [narrative.md](context/01_project/narrative.md) | What happened, board progression and outcomes |
| 02 Methods | [cpa_dpa.md](context/02_methods/cpa_dpa.md) | Notation, CPA/DPA formulas, leakage models, metrics |
| 02 Methods | [deep_learning_hettwer.md](context/02_methods/deep_learning_hettwer.md) | Image encodings, CNN architecture, GE attack |
| 03 Hardware | [pico_rp2040_failure.md](context/03_hardware/pico_rp2040_failure.md) | Why the RP2040 SMPS masked leakage |
| 03 Hardware | [trinket_acquisition.md](context/03_hardware/trinket_acquisition.md) | Pro Trinket schematic, oscilloscope, capture command |
| 04 Data | [reference_dataset.md](context/04_data/reference_dataset.md) | dpa-on-aes reference traces and why they work |
| 04 Data | [datasets.md](context/04_data/datasets.md) | Table of all `data/set_*` datasets |
| 05 Report | [todos.md](context/05_report/todos.md) | Open report TODOs |
| 05 Report | [appendix_material.md](context/05_report/appendix_material.md) | Hardware specs, NN table, media evidence, repo layout |
| 06 Sources | [external_sources.md](context/06_sources/external_sources.md) | Every downloaded item: link, version, checksum, restore |
| 06 Sources | [key_references.md](context/06_sources/key_references.md) | Papers and standards cited |

**Adding a module:** put it in the matching numbered folder (or a new `NN_area/`),
start it with a `##` heading, and add one row to this table.

---

## Quick Start

### 1. Capture (Pro Tinkrer , Ethernet scope)

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
python attacks/classical/cpa.py --data data/set_013_adafruit_trinket_pro_5v16mhz --round first
```

### 3. Deep Learning Attack (Hettwer CNN)

```bash
# Train on captured data (GASF+GADF, paper's best channel combo)
python attacks/deep_learning/hettwer_sca.py \
    --data data/set_013_adafruit_trinket_pro_5v16mhz \
    --channels gasf+gadf --byte 0

# Train on ASCADv1 benchmark dataset
python attacks/deep_learning/hettwer_sca.py \
    --ascad-h5 /path/to/ASCAD.h5 --channels gasf+gadf
```

### 4. Visualise Dataset

```bash
python plot_traces.py --data data/set_013_adafruit_trinket_pro_5v16mhz
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
