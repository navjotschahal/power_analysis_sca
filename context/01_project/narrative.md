## 1. Project Narrative & What Actually Happened

The proposal aimed to compare DPA vs CPA on a real embedded target and extend to deep learning.
The project evolved through continuous hardware experiments before producing working results.

### 1.1 Board Progression (chronological)

| Board | Outcome | Root cause |
|---|---|---|
| Raspberry Pi Pico RP2040 | **Failed — attack did not converge** | Internal SMPS (see §3) |
| Arduino Uno R4 Minima (Renesas RA4M1) | Partial — 2000 traces captured, did not converge | Insufficient trace count; noisy baseline |
| **Adafruit Pro Tinkrer 5V @ 16 MHz** | **SUCCESS** — attacks converge | Clean 5V AVR supply; shunt on VDD |
| Reference dataset (dpa-on-aes / ChipWhisperer) | **SUCCESS** — gold standard | Pre-validated, last-round leakage |

---

