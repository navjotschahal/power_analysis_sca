## 7. Datasets in This Project

| Directory | Device | N | T | Attack round | Status |
|---|---|---|---|---|---|
| `data/set_001_pico_real` | RPi Pico RP2040 | 100 | 4000 | first | Captured; attacks did NOT converge (SMPS noise) |
| `data/set_002_reference` | ChipWhisperer (unknown) | 2000 | 29000 | last | **CPA + DPA both converge** |
| `data/set_003_arduino_shuntGND` | Arduino Uno R4 Minima | 2000 | 4807 | first | Captured; attacks did not converge (insufficient traces) |
| `data/set_004_trinket_*` | Pro Tinkrer 5V | 50000 (planned) | 30000 | first | **TODO: capture pending** |

All datasets: `traces.npy` (float32), `plaintexts.npy` (uint8), `ciphertexts.npy` (uint8), `meta.json`  
AES key used in all hardware captures: `2B 7E 15 16 28 AE D2 A6 AB F7 15 88 09 CF 4F 3C`

---

