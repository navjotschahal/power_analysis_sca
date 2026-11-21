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

