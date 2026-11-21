# Data Format & Directory Structure

## Top-Level Layout

```
data/
├── DATA_FORMAT.md          ← this file
├── set_001_pico_real/      ← real traces from RPi Pico via oscilloscope
├── set_002_simulated/      ← software-generated synthetic traces
└── set_NNN_<label>/        ← future datasets follow the same schema
```

Naming convention: `set_<zero-padded-index>_<short-label>/`
Each dataset is self-contained — add new sets by creating a new numbered folder.

---

## Per-Dataset Schema

Every dataset directory contains exactly these files:

| File | Shape | Dtype | Description |
|---|---|---|---|
| `traces.npy` | `(N, T)` | `float32` | Power waveforms. Row `i` is the trace for encryption `i`. |
| `plaintexts.npy` | `(N, 16)` | `uint8` | Plaintext bytes fed to the device for encryption `i`. |
| `ciphertexts.npy` | `(N, 16)` | `uint8` | Ciphertext bytes returned by the device for encryption `i`. |
| `meta.json` | — | JSON | Dataset metadata (see below). |
| `ge_comparison.png` | — | PNG | Output of `guessing_entropy.py` — written after analysis runs. |

Row alignment is strict: `traces[i]`, `plaintexts[i]`, and `ciphertexts[i]` all correspond to the same AES-128 ECB encryption call.

---

## meta.json Schema

```json
{
  "label":       "Human-readable name shown in plot titles",
  "key":         [0x00, 0x11, ...],   // 16-element uint8 array — the AES-128 secret key
  "device":      "RPi Pico RP2040 | simulated | ...",
  "N":           1000,                // number of traces
  "T":           5000,                // samples per trace
  "snr":         null,                // null for real hardware; float for simulated
  "noise_level": null,                // Gaussian sigma used in simulation (or null)
  "notes":       "Any free-text capture conditions"
}
```

`key` is the ground-truth secret used by the firmware. This is required by `guessing_entropy.py` to compute the rank of the correct byte.

---

## How Attack Scripts Consume This Data

```
attacks/cpa.py  --data data/set_001_pico_real
attacks/dpa.py  --data data/set_001_pico_real
attacks/guessing_entropy.py  --data data/set_001_pico_real  --byte 0  --trials 20
```

All scripts resolve paths relative to the repo root. `meta.json` is optional for `cpa.py`/`dpa.py` (rank reporting is skipped if absent) but **required** for `guessing_entropy.py`.

---

## Data Flow Diagram

```
firmware/main.c  ──(USB serial)──▶  capture.py
                                        │
                            ┌───────────┴───────────┐
                            │                       │
                    traces.npy               plaintexts.npy
                    ciphertexts.npy          meta.json
                            │
                    data/set_NNN_<label>/
                            │
              ┌─────────────┼─────────────┐
              │             │             │
          cpa.py        dpa.py    guessing_entropy.py
                                          │
                                  ge_comparison.png
```

---

## Adding a New Dataset

1. Create `data/set_NNN_<label>/`
2. Save `traces.npy`, `plaintexts.npy`, `ciphertexts.npy` into it
3. Write `meta.json` with the key and capture conditions
4. Run the attack scripts pointing `--data` at the new folder

No changes to any attack script are needed — the key is read from `meta.json` at runtime.

---

## Current Datasets

| Directory | Source | N | T | Attack round | Notes |
|---|---|---|---|---|---|
| `set_001_pico_real` | RPi Pico RP2040 hardware | 100 | 4000 | first | Captured via `capture.py`; shunt on GND rail; trigger GPIO 15 |
| `set_002_reference` | `references/dpa-on-aes` | 2000 | 29000 | last | Converted from per-file .txt; leakage is last-round |
| `set_003_arduino_shuntGND` | Arduino Uno R4 Minima hardware | 2000 | 4807 | first | Captured via `capture_uno.py`; shunt on GND rail |
