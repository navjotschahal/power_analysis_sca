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

