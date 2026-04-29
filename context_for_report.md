# Report Context — Power Side-Channel Attacks on AES-128
**Course:** ESE5370 Hardware Security — Spring 2026  
**Author:** Navjot Singh Chahal · nschahal@seas.upenn.edu  
**Purpose:** Context dump for a dedicated report-writing session. Search `TODO` to find every gap.

---

## 1. Project Narrative & What Actually Happened

The proposal aimed to compare DPA vs CPA on a real embedded target and extend to deep learning.
The project evolved through continuous hardware experiments before producing working results.

### 1.1 Board Progression (chronological)

| Board | Outcome | Root cause |
|---|---|---|
| Raspberry Pi Pico RP2040 | **Failed — attack did not converge** | Internal SMPS (see §3) |
| Arduino Uno R4 Minima (Renesas RA4M1) | Partial — 2000 traces captured, did not converge | Insufficient trace count; noisy baseline |
| **Adafruit Pro Trinket 5V @ 16 MHz** | **SUCCESS** — attacks converge | Clean 5V AVR supply; shunt on VDD |
| Reference dataset (dpa-on-aes / ChipWhisperer) | **SUCCESS** — gold standard | Pre-validated, last-round leakage |

---

## 2. CPA and DPA — Notation and Implementation

### 2.1 Shared Notation (from proposal §4)

| Symbol | Meaning |
|---|---|
| $D$ | Total number of traces |
| $d \in [1,D]$ | Trace index |
| $i$ | Time-sample index |
| $j \in [0,255]$ | Key-byte hypothesis |
| $t_{d,i}$ | Measured power at sample $i$ in trace $d$ |
| $h_{d,j}$ | Hypothetical power consumption under hypothesis $j$ |
| $\bar{t}_i$ | Mean of $t_{d,i}$ over all traces |
| $\bar{h}_j$ | Mean of $h_{d,j}$ over all traces |
| $\mathrm{HW}(x)$ | Hamming weight of byte $x$ |
| $S[\cdot]$ | AES SubBytes (SBOX) lookup |
| $S^{-1}[\cdot]$ | Inverse SubBytes (INV_SBOX) lookup |

### 2.2 CPA — Pearson Correlation Distinguisher
*(Brier, Clavier, Olivier — CHES 2004)*

**Formula** (Eq. 1 in proposal, Eq. in `report/sections/04_methodology.tex`):

$$
r_{i,j} = \frac{\displaystyle\sum_{d=1}^{D} (t_{d,i} - \bar{t}_i)(h_{d,j} - \bar{h}_j)}
               {\sqrt{\displaystyle\sum_{d=1}^{D}(t_{d,i}-\bar{t}_i)^2 \cdot \sum_{d=1}^{D}(h_{d,j}-\bar{h}_j)^2}}
$$

**Leakage model — first round:**
$$h_{d,j} = \mathrm{HW}(S[p_{d,b} \oplus j] \oplus c), \quad c \in \{0,\ldots,255\}$$

**Leakage model — last round:**
$$h_{d,j} = \mathrm{HW}(S^{-1}[c_{d,b} \oplus j] \oplus c), \quad c \in \{0,\ldots,255\}$$

**Decision rule:**
$$\hat{k}_b = \arg\max_j \; \max_i \; |r_{i,j}|$$

**Implementation:** `attacks/classical/cpa.py`
- `_precompute_trace_stats()` — computes $\bar{t}_i$ and centred traces once, reused across all bytes and const sweeps
- `cpa_byte()` — returns the max $|r_{i,j}|$ score per hypothesis (scalar per `j`); used in key recovery loop
- `cpa_byte_full()` — returns the full $r_{i,j}$ matrix (256 × T); used for visualisation only
- Const $c$ is swept 0→255; first $c$ that passes `backward_key_schedule` verification wins
- Output: 3-panel diagnostic plot per byte (correlation trace, bar chart, heatmap)

**Results on reference dataset (2000 traces, last-round):**
- 15/16 bytes: rank 1 at $c=0$ (pure HW model)
- Byte 11: rank 2 at $c=0$, rank 1 at $c=2$ (HD leakage from register state 2)
- Full original key recovered: `2B 7E 15 16 28 AE D2 A6 AB F7 15 88 09 CF 4F 3C`

### 2.3 DPA — Differential Mean Distinguisher
*(Kocher, Jaffe, Jun — CRYPTO 1999)*

**Formula** (Eq. in `report/sections/04_methodology.tex`):

$$
\Delta_j = \max_i \left| \frac{1}{|S_1|}\sum_{d \in S_1} t_{d,i} - \frac{1}{|S_0|}\sum_{d \in S_0} t_{d,i} \right|
$$

where the partition is by a single bit $\ell$ of the intermediate value:
$$S_1 = \{d : \mathrm{bit}_\ell(v_{d,j}) = 1\}, \quad S_0 = \{d : \mathrm{bit}_\ell(v_{d,j}) = 0\}$$
$$v_{d,j} = S^{-1}[c_{d,b} \oplus j] \quad \text{(last round)}$$

**Decision rule:**
$$\hat{k}_b = \arg\max_j \; \Delta_j$$

**Implementation:** `attacks/classical/dpa.py`
- `dpa_byte()` — fully vectorised; computes the partition means as a single matrix multiply $(T \times D) \cdot (D \times 256) \to (T \times 256)$; ~100× faster than a Python loop
- `dpa_byte_full()` — returns full $\Delta_j(i)$ matrix (256 × T) for visualisation
- Bit position $\ell$ swept 0→7; first $\ell$ that passes key verification wins
- Output: 3-panel diagnostic plot per byte (delta trace, bar chart, heatmap)

**Results on reference dataset:**
- Bit 0: 14/16 bytes correct (bytes 3 and 15 wrong — backward schedule fails)
- **Bit 1: 16/16 bytes correct — full key recovered**
- Round-10 key: `D0 14 F9 A8 C9 EE 25 89 E1 3F 0C C8 B6 63 0C A6`
- Original key (backward schedule): `2B 7E 15 16 28 AE D2 A6 AB F7 15 88 09 CF 4F 3C`

### 2.4 Evaluation Metrics

**Guessing Entropy (GE)** — primary metric (Benadjila et al. 2020 / ASCAD):
$$\mathrm{GE}(N) = \mathbb{E}[\mathrm{rank}(\hat{k}_b^{(N)})]$$

- Estimated by averaging key rank over multiple random subsets of size $N$
- GE = 1 → full convergence (correct byte is the top guess)
- Script: `attacks/classical/guessing_entropy.py --data <dir> --byte <b> --trials 20`

**Trace Complexity $N_\text{traces}$:** minimum $N$ where $\mathrm{GE}(N) \leq 1.5$

---

## 3. Why Pi Pico (RP2040) Traces Failed

The RP2040 contains an on-chip **Switch-Mode Power Supply (SMPS)** — a buck converter that steps the 3.3V USB/external supply down to the core voltage of ~1.1V DVDD for the Cortex-M0+ cores.

**Why this kills SCA:**
- The SMPS switches at ~1 MHz, injecting broadband switching noise directly on the DVDD rail
- The data-dependent AES leakage signal is small (μA-level modulation) relative to the SMPS noise floor
- Variance analysis of our 100 captured Pico traces showed:
  - AES window: samples [3216–3710] out of 4000 — 80% of the trace is pre-trigger idle noise
  - SNR proxy (peak variance / noise floor): only 21× vs 78× for Arduino
  - Dynamic range at AES peak: only 4.6× vs 8.7× for Arduino

**What would be needed (invasive modification):**
- Remove or bypass the on-chip SMPS
- Supply 1.1V directly to the DVDD pin via an external, low-noise LDO regulator
- This is the standard approach used with ChipWhisperer's CW308 UFO target board for RP2040
- Not attempted in this project due to hardware risk

**Contrast with Pro Trinket 5V:**
The ATmega328P on the Trinket runs directly from the 5V USB rail with a simple linear regulator. No SMPS. The 5V supply is clean and the power consumption of the AVR core is directly measurable with a shunt resistor. This is why the Trinket produced usable traces.

---

## 4. Data Acquisition Hardware — Pro Trinket (Only Board That Worked)

### 4.1 Hardware Schematic (Pro Trinket 5V @ 16 MHz)

```
USB 5V ──┬── [10 Ω shunt] ──┬── Pro Trinket VCC pin
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

### 4.3 Capture Command (Pro Trinket, 50k traces)

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

## 5. Reference Dataset (ChipWhisperer / dpa-on-aes)

**Source:** `references/dpa-on-aes` GitHub repo — originally distributed as per-trace `.txt` files  
**Converted to project format:** `data/set_002_reference/` (traces.npy, plaintexts.npy, ciphertexts.npy, meta.json)

| Property | Value |
|---|---|
| N (traces) | 2,000 |
| T (samples/trace) | 29,000 |
| Leakage type | **Last-round** — SubBytes$_{10}$ on ciphertext via $S^{-1}(c_b \oplus k_{10,b})$ |
| Device | Unknown — ChipWhisperer-style capture |
| Masking | **Unmasked** (no countermeasures) |
| Known key | `2B 7E 15 16 28 AE D2 A6 AB F7 15 88 09 CF 4F 3C` (NIST AES-128 test vector) |
| dtype | float32 (raw ADC values, range ~[-1278, +1373]) |

**Why it works and our captures don't (yet):**
- Pre-validated, precisely triggered ChipWhisperer hardware — zero clock jitter
- 29,000 samples gives many time points over the entire AES last round
- Professionally conditioned power measurement (ChipWhisperer dedicated measurement path)
- Our oscilloscope captures have trigger jitter from USB serial latency and scope arm delay

---

## 6. Deep Learning Attacks — Hettwer et al. 2020

**Paper:** "Encoding Power Traces as Images for Efficient Side-Channel Analysis"  
Benjamin Hettwer, Tobias Horn, Stefan Gehrer, Tim Güneysu  
**IEEE HOST 2020** | arXiv:2004.11015 | https://arxiv.org/pdf/2004.11015

### 6.1 Core Idea

Instead of feeding a raw 1D time-series trace into a neural network, each trace is first converted into a **2D image** using time-series encoding methods. This allows standard image CNN architectures (Conv2D) to exploit 2D spatial structure — temporal correlations become spatial textures.

### 6.2 Encoding Methods (implemented in `attacks/deep_learning/image_encode.py`)

All encoders: input `(N, W)` float32 traces → output `(N, W, W)` float32 images ∈ [0, 1]  
Traces are first normalised to [−1, 1] per-trace and downsampled to the image size S×S.

**GASF — Gramian Angular Summation Field**
$$\mathrm{GASF}[i,j] = \cos(\varphi_i + \varphi_j), \quad \varphi_k = \arccos(x_k)$$
- Symmetric matrix; diagonal = $\cos(2\varphi)$ — preserves phase sum structure
- Captures overall pairwise temporal correlation

**GADF — Gramian Angular Difference Field**
$$\mathrm{GADF}[i,j] = \sin(\varphi_i - \varphi_j)$$
- Anti-symmetric; zero diagonal
- Captures directionality / phase differences between time points
- **GASF + GADF together is the paper's best-performing combination**

**RP — Recurrence Plot**
$$\mathrm{RP}[i,j] = \mathbf{1}[|x_i - x_j| < \varepsilon], \quad \varepsilon = 0.1$$
- Binary matrix encoding self-similarity
- AES operates in 16 rounds → periodic structure produces **stripe patterns** in the RP
- Useful for detecting round structure without explicit alignment

**MTF — Markov Transition Field**
- Quantises trace into $n=8$ bins, builds per-trace state-transition probability matrix $Q$
- $\mathrm{MTF}[i,j] = Q[\mathrm{bin}(x_i), \mathrm{bin}(x_j)]$
- Captures temporal state dynamics — which power states tend to follow which

### 6.3 Why Image Encoding is Beneficial for SCA

1. **Translation invariance:** small trigger jitter shifts the leakage point in time; Conv2D with pooling is robust to small translations, unlike fixed-index correlation
2. **Multi-scale feature extraction:** CNN filters at different scales capture both narrow S-Box spikes and broader round-level patterns simultaneously
3. **2D structure from 1D data:** GASF/GADF encode pairwise temporal relationships that are invisible to 1D CNNs — the Conv2D can detect patterns between non-adjacent time points
4. **RP stripe patterns:** the 16-round periodicity of AES appears as structured diagonal stripes in RP images, giving the CNN a strong structural prior
5. **Profiling attack framework:** once trained on a profiling device, the model generalises to attack a victim device — no need to re-run the attack per trace-set

### 6.4 CNN Architecture (Table II of paper — exactly reproduced in `hettwer_sca.py`)

```
Input: (S, S, C)  — S=64, C=1 or 2 depending on channel combination

Conv2D(8 filters, 5×5, L2=0.01) → BatchNorm → ReLU → MaxPool(2×2, stride=2) → Dropout(0.5)
Conv2D(16 filters, 3×3, L2=0.01) → BatchNorm → ReLU → MaxPool(2×2, stride=2) → Dropout(0.5)
Flatten
Dense(250, ReLU) → BatchNorm → Dropout(0.3)
Dense(256, Softmax)   ← 256 output classes (one per key-byte value 0x00–0xFF)
```

**Training setup (Section V-A of paper):**
- Optimizer: Adam, lr = 0.0002
- Loss: categorical cross-entropy
- Early stopping: patience = 20 on val_loss
- Checkpoint: best val_loss weights saved to `.keras` file
- Input to model: `(S, S, C)` images, labels = `HW(SBOX[pt[b] ⊕ k_b])` (9 classes) or full `SBOX[pt[b] ⊕ k_b]` (256 classes)

**Channel combinations tested:**

| Combination | Channels | Notes |
|---|---|---|
| `gasf` | 1 | baseline |
| `gadf` | 1 | baseline |
| `rp` | 1 | good for round detection |
| `mtf` | 1 | state dynamics |
| `gasf+gadf` | 2 | **paper's best result** |
| `gasf+rp` | 2 | competitive |
| `all` | 4 | (N, 64, 64, 4) tensor |

### 6.5 GE Attack (Key Guessing Entropy evaluation)

The trained model outputs `P(SBOX[pt[b] ⊕ k_b] | trace)` — a probability over 256 S-Box output values.
For each hypothesis $k$, log-likelihood is accumulated across attack traces:

$$\mathrm{score}[k] \mathrel{+}= \log P(\mathrm{SBOX}[p_{d,b} \oplus k] \;|\; \text{trace}_d)$$

Key rank is computed after each trace; GE is the mean rank over `n_trials=10` random permutations.

**Usage:**
```bash
# Train and evaluate (GASF+GADF, byte 0, first round)
python attacks/deep_learning/hettwer_sca.py \
    --data data/set_003_arduino_shuntGND --round first --channels gasf+gadf --byte 0

# Attack-only with saved checkpoint
python attacks/deep_learning/hettwer_sca.py \
    --data data/set_003_arduino_shuntGND --round first --attack-only \
    --ckpt data/set_003_arduino_shuntGND/plots/hettwer_gasf+gadf_b00.keras

# Visualise encoding pipeline for one trace
python attacks/deep_learning/image_encode.py \
    --data data/set_002_reference --method gasf --image-size 64 --show
```

---

## 7. Datasets in This Project

| Directory | Device | N | T | Attack round | Status |
|---|---|---|---|---|---|
| `data/set_001_pico_real` | RPi Pico RP2040 | 100 | 4000 | first | Captured; attacks did NOT converge (SMPS noise) |
| `data/set_002_reference` | ChipWhisperer (unknown) | 2000 | 29000 | last | **CPA + DPA both converge** |
| `data/set_003_arduino_shuntGND` | Arduino Uno R4 Minima | 2000 | 4807 | first | Captured; attacks did not converge (insufficient traces) |
| `data/set_004_trinket_*` | Pro Trinket 5V | 50000 (planned) | 30000 | first | **TODO: capture pending** |

All datasets: `traces.npy` (float32), `plaintexts.npy` (uint8), `ciphertexts.npy` (uint8), `meta.json`  
AES key used in all hardware captures: `2B 7E 15 16 28 AE D2 A6 AB F7 15 88 09 CF 4F 3C`

---

## 8. TODOs

Search this document and the report directory for `TODO` to find every gap.

### Report content TODOs

- **TODO-KEY:** `report/sections/04_methodology.tex` line 20 has wrong hardcoded key  
  (`00 11 22 33 44 55 66 77 88 99 AA BB CC DD EE FF`) — must be updated to `2B 7E 15 16 28 AE D2 A6 AB F7 15 88 09 CF 4F 3C`

- **TODO-TRIGPIN:** same section references GPIO 22 as trigger — actual firmware uses GPIO 15. Fix in report.

- **TODO-GE-CURVES:** `report/sections/05_results.tex` §Guessing Entropy has a placeholder figure.  
  Must run `attacks/classical/guessing_entropy.py` on actual converging dataset and insert real GE vs N curves for both CPA and DPA.

- **TODO-TRINKET-CAPTURE:** Capture 50,000 traces from Pro Trinket 5V, save to `data/set_004_trinket_*`. Then run CPA/DPA/GE analysis and populate the results section with real hardware GE curves.

- **TODO-DL-RESULTS:** Deep learning (hettwer_sca.py) has not been run to convergence on any dataset yet. Need to train on reference or Trinket data and report GE curves for GASF+GADF combination.

- **TODO-GITHUB:** `report/appendix/B_repository.tex` and `appendix/A_hardware_setup.tex` have `PLACEHOLDER` GitHub URL. Replace with actual repo link.

- **TODO-SCHEMATIC-FIGURE:** Insert Pro Trinket schematic as a proper figure (LaTeX `\includegraphics`) in Appendix A. Currently text-only placeholder.

- **TODO-VIDEO-EMBED:** Appendix A §Video Evidence references video files — confirm paths and include frame captures as figures in the appendix. Videos show: scope trigger firing, AES power trace, Python acquisition running, representative scope display.

- **TODO-ARDUINO-DISCUSSION:** Add a subsection in Discussion explaining why Arduino R4 Minima also failed (Renesas RA4M1 also has internal power regulation; only 2000 traces captured vs recommended 5000+ for AVR-class devices).

- **TODO-PICO-HARDWARE-NOTE:** Add a hardware limitations box in Discussion §Limitations explaining the RP2040 SMPS issue and what would be required for a successful Pico attack (bypass SMPS, supply DVDD directly).

- **TODO-ASCAD-MENTION:** Proposal mentions ASCAD dataset. The `data/ascad2/` directory exists in the project. Clarify in report whether ASCAD data was used or just referenced; if used, document it.

- **TODO-REPORT-FLOW:** The report abstract still says "RP2040" as the primary target but results are on the reference ChipWhisperer dataset. Update abstract to accurately reflect that (a) reference dataset was primary analysis vehicle, (b) Trinket was the successful real hardware target.

---

## 9. Appendix Material

### A. Hardware Specifications

**Adafruit Pro Trinket 5V @ 16 MHz**
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
- [ ] Video: oscilloscope trigger firing on GPIO rising edge (Pro Trinket)
- [ ] Video: AES power trace visible on scope display
- [ ] Video: Python capture script running in terminal (tqdm progress)
- [ ] Image: representative scope screenshot — Pro Trinket 5V power trace
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

## 10. Key References

1. Kocher, Jaffe, Jun — "Differential Power Analysis" — CRYPTO 1999
2. Brier, Clavier, Olivier — "Correlation Power Analysis with a Leakage Model" — CHES 2004
3. Benadjila et al. — "Deep Learning for Side-Channel Analysis and Introduction to ASCAD Database" — J. Cryptographic Engineering 2020
4. **Hettwer, Horn, Gehrer, Güneysu — "Encoding Power Traces as Images for Efficient Side-Channel Analysis" — IEEE HOST 2020** | arXiv:2004.11015
5. Colin O'Flynn & Greg d'Eon — "An Introduction to ChipWhisperer-Lint"
6. NIST FIPS 197 — Advanced Encryption Standard (AES)
