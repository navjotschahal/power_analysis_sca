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

