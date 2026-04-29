"""
image_encode.py — Convert 1D power traces to 2D images for CNN-based SCA.

Motivation (Proprioceptive Image paper, ICRA 2026):
  Converting time-series sensor data → 2D image lets standard image-CNN
  architectures process the data.  The same idea applies to power traces:
  temporal correlation structure becomes spatial texture that Conv2D filters
  can exploit.

Encoding methods (pure numpy — no pyts dependency):
  gasf  — Gramian Angular Summation Field  : cos(φ_i + φ_j)
  gadf  — Gramian Angular Difference Field : sin(φ_i − φ_j)
  rp    — Recurrence Plot                  : ||x_i − x_j|| < ε
  mtf   — Markov Transition Field          : quantised transition probs

All encoders:
  Input  : (N, W) float32 traces, W = window width
  Output : (N, W, W) float32 images in [0, 1]

Usage
-----
  python attacks/deep_learning/image_encode.py \\
    --data data/set_002_reference --method gasf --image-size 64 --show
"""

import argparse
import os
import sys

import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from helper import (
    INV_SBOX, HW,
    extract_round_key,
    load_dataset, plots_dir,
    apply_dark_style, STYLE,
)

# ── Core encoders ──────────────────────────────────────────────────────────────

def _norm_minmax(traces: np.ndarray) -> np.ndarray:
    """Normalise each trace to [−1, 1] (required for angle-based methods)."""
    mn = traces.min(axis=1, keepdims=True)
    mx = traces.max(axis=1, keepdims=True)
    return 2.0 * (traces - mn) / (mx - mn + 1e-8) - 1.0


def gasf(traces: np.ndarray) -> np.ndarray:
    """
    Gramian Angular Summation Field.
    GASF[n, i, j] = cos(φ_i + φ_j)  where φ_k = arccos(x_k).
    Captures pairwise phase sums — symmetric, diagonal = cos(2φ).
    """
    x   = np.clip(_norm_minmax(traces), -1.0, 1.0)
    phi = np.arccos(x)                                    # (N, W)
    out = np.cos(phi[:, :, None] + phi[:, None, :])       # (N, W, W)
    return ((out + 1.0) / 2.0).astype(np.float32)        # shift to [0,1]


def gadf(traces: np.ndarray) -> np.ndarray:
    """
    Gramian Angular Difference Field.
    GADF[n, i, j] = sin(φ_i − φ_j).
    Captures pairwise phase differences — anti-symmetric, zero diagonal.
    """
    x   = np.clip(_norm_minmax(traces), -1.0, 1.0)
    phi = np.arccos(x)
    out = np.sin(phi[:, :, None] - phi[:, None, :])       # (N, W, W)
    return ((out + 1.0) / 2.0).astype(np.float32)


def rp(traces: np.ndarray, threshold: float = 0.1) -> np.ndarray:
    """
    Recurrence Plot.
    RP[n, i, j] = 1  if |x_i − x_j| < threshold, else 0.
    Encodes self-similarity — diagonal always 1, off-diagonal patterns
    reveal periodicity (AES operates in 16-byte rounds → stripe patterns).
    """
    x   = _norm_minmax(traces)
    diff = np.abs(x[:, :, None] - x[:, None, :])         # (N, W, W)
    return (diff < threshold).astype(np.float32)


def mtf(traces: np.ndarray, n_bins: int = 8) -> np.ndarray:
    """
    Markov Transition Field.
    Quantises each trace into n_bins, builds a transition-probability matrix Q,
    then MTF[n, i, j] = Q[bin(x_i), bin(x_j)].
    Captures state-transition dynamics along the time axis.
    """
    N, W = traces.shape
    x    = _norm_minmax(traces)
    # Quantise to [0, n_bins-1]
    edges = np.linspace(-1.0, 1.0, n_bins + 1)
    bins  = np.digitize(x, edges[1:-1]).astype(int)       # (N, W) values 0..n_bins-1

    out = np.zeros((N, W, W), dtype=np.float32)
    for n in range(N):
        b = bins[n]
        # Build transition count matrix
        Q = np.zeros((n_bins, n_bins), dtype=np.float32)
        for t in range(W - 1):
            Q[b[t], b[t + 1]] += 1.0
        # Normalise rows to probabilities
        row_sum = Q.sum(axis=1, keepdims=True)
        Q = Q / (row_sum + 1e-8)
        # Assign to image: MTF[i,j] = Q[bin_i, bin_j]
        out[n] = Q[b[:, None], b[None, :]]
    return out

# ── Resize helper ──────────────────────────────────────────────────────────────

def resize_traces(traces: np.ndarray, target_w: int) -> np.ndarray:
    """Downsample traces from W to target_w using linear interpolation."""
    N, W = traces.shape
    if W == target_w:
        return traces
    x_old = np.linspace(0, 1, W)
    x_new = np.linspace(0, 1, target_w)
    out   = np.zeros((N, target_w), dtype=np.float32)
    for i in range(N):
        out[i] = np.interp(x_new, x_old, traces[i])
    return out

# ── Encode functions ──────────────────────────────────────────────────────────

ENCODERS = {'gasf': gasf, 'gadf': gadf, 'rp': rp, 'mtf': mtf}
ENCODER_LABELS = {
    'gasf': 'GASF\ncos(φᵢ+φⱼ)',
    'gadf': 'GADF\nsin(φᵢ−φⱼ)',
    'rp':   'RP\n|xᵢ−xⱼ|<ε',
    'mtf':  'MTF\nMarkov transitions',
}


def encode(traces: np.ndarray, method: str = 'gasf',
           image_size: int = 64) -> np.ndarray:
    """
    Single-method encode: (N, W) → (N, S, S, 1).
    Kept for backward compatibility and single-method experiments.
    """
    if method not in ENCODERS:
        raise ValueError(f"Unknown method '{method}'. Choose from {list(ENCODERS)}")
    t_rs   = resize_traces(traces, image_size)
    images = ENCODERS[method](t_rs)
    return images[:, :, :, np.newaxis]                     # (N, S, S, 1)


def encode_multichannel(traces: np.ndarray, image_size: int = 64) -> np.ndarray:
    """
    ICRA-paper style: stack all 4 encodings as channels of a single image.

    Each encoding captures a different aspect of temporal structure:
      Ch 0 — GASF : pairwise phase sums        (symmetric, overall correlation)
      Ch 1 — GADF : pairwise phase differences (anti-symmetric, directionality)
      Ch 2 — RP   : self-similarity / recurrence (periodicity, AES round stripes)
      Ch 3 — MTF  : Markov transition field     (state dynamics along time)

    Parameters
    ----------
    traces     : (N, W) float32 — windowed, normalised traces
    image_size : S — output image size S×S

    Returns
    -------
    images : (N, S, S, 4) float32 — 4-channel image ready for Conv2D
    """
    t_rs     = resize_traces(traces, image_size)           # (N, S)
    channels = [enc(t_rs) for enc in ENCODERS.values()]   # 4 × (N, S, S)
    return np.stack(channels, axis=-1).astype(np.float32) # (N, S, S, 4)

# ── CPA peak + window (shared with resnet_sca) ────────────────────────────────

def find_cpa_peak(traces, data, byte, sbox_table, rk_byte) -> int:
    hw    = HW[sbox_table[data[:, byte] ^ rk_byte]].astype(np.float32)
    hw_c  = hw - hw.mean()
    t_c   = traces - traces.mean(axis=0)
    corr  = (hw_c[:, None] * t_c).mean(axis=0) / \
            ((hw.std() + 1e-8) * (t_c.std(axis=0) + 1e-8))
    peak  = int(np.argmax(np.abs(corr)))
    print(f"  CPA peak: sample {peak}  |r| = {np.abs(corr[peak]):.4f}")
    return peak


def extract_window(traces, center, window):
    _, T  = traces.shape
    half  = window // 2
    start = max(0, center - half)
    end   = min(T, start + window)
    start = max(0, end - window)
    w     = traces[:, start:end].astype(np.float32)
    return (w - w.mean(axis=0)) / (w.std(axis=0) + 1e-8)  # (N, window) — no channel dim

# ── Stage visualisation ───────────────────────────────────────────────────────

def plot_encoding_stages(trace_1d: np.ndarray, image_size: int, out_path: str):
    """
    Full pipeline diagram for one trace — 4 rows:

      Row 0 (Stage 1) : raw 1D trace window
      Row 1 (Stage 2) : 4 individual encodings computed independently
      Row 2 (Stage 3) : the 4 channels of the (S,S,4) tensor that enters Conv2D
      Row 3 (Stage 4) : two composite views of the final tensor —
                          • mean of all 4 channels (per-pixel average)
                          • RGB blend: R=GASF  G=GADF  B=RP  (MTF shown aside)
                        This is the closest single image to "what the model sees".
    """
    sample = trace_1d[np.newaxis, :]                       # (1, W)
    cmaps  = ['viridis', 'plasma', 'binary_r', 'magma']
    ch_names = list(ENCODERS.keys())                       # ['gasf','gadf','rp','mtf']

    fig = plt.figure(figsize=(16, 14))
    fig.patch.set_facecolor(STYLE['bg'])
    fig.suptitle('Image Encoding Pipeline — 1D trace → (64 × 64 × 4) model input',
                 color=STYLE['text'], fontsize=13, y=0.99)

    gs = fig.add_gridspec(4, 4, hspace=0.5, wspace=0.3)

    # ── Row 0: raw 1D trace ───────────────────────────────────────────────────
    ax0 = fig.add_subplot(gs[0, :])
    ax0.set_facecolor(STYLE['bg'])
    ax0.plot(trace_1d, color=STYLE['correct'], linewidth=0.8)
    ax0.set_title('Stage 1 — Raw 1D trace window (normalised, windowed around CPA peak)',
                  color=STYLE['text'], fontsize=9)
    ax0.set_xlabel('Sample index', color=STYLE['text'])
    ax0.set_ylabel('Amplitude',    color=STYLE['text'])
    ax0.tick_params(colors=STYLE['text'])
    for sp in ax0.spines.values():
        sp.set_edgecolor(STYLE['grid'])

    # ── Row 1: individual encodings ───────────────────────────────────────────
    t_rs = resize_traces(sample, image_size)
    for col, (method, enc_fn) in enumerate(ENCODERS.items()):
        img = enc_fn(t_rs)[0]
        ax  = fig.add_subplot(gs[1, col])
        ax.set_facecolor(STYLE['bg'])
        im  = ax.imshow(img, cmap=cmaps[col], aspect='auto')
        ax.set_title(f'Stage 2 — {ENCODER_LABELS[method]}',
                     color=STYLE['text'], fontsize=8)
        ax.axis('off')
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04).ax.tick_params(
            colors=STYLE['text'])

    # ── Row 2: 4 channels of the actual (S,S,4) tensor ────────────────────────
    multi = encode_multichannel(sample, image_size)[0]     # (S, S, 4)
    for col in range(4):
        img = multi[:, :, col]
        ax  = fig.add_subplot(gs[2, col])
        ax.set_facecolor(STYLE['bg'])
        im  = ax.imshow(img, cmap=cmaps[col], aspect='auto')
        ax.set_title(f'Stage 3 — tensor[:,:,{col}]  {ch_names[col].upper()}',
                     color=STYLE['text'], fontsize=8)
        ax.axis('off')
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04).ax.tick_params(
            colors=STYLE['text'])

    # ── Row 3: composite views — what the model actually receives ─────────────

    # Mean composite: average signal across all 4 channels
    mean_img = multi.mean(axis=-1)                         # (S, S)
    ax_mean  = fig.add_subplot(gs[3, :2])
    ax_mean.set_facecolor(STYLE['bg'])
    im = ax_mean.imshow(mean_img, cmap='inferno', aspect='auto')
    ax_mean.set_title(
        'Stage 4a — Mean composite  (avg of 4 channels)\n'
        'Highlights regions of high leakage across all encodings',
        color=STYLE['text'], fontsize=8)
    ax_mean.axis('off')
    plt.colorbar(im, ax=ax_mean, fraction=0.046, pad=0.04).ax.tick_params(
        colors=STYLE['text'])

    # RGB blend: R=GASF, G=GADF, B=RP  (3 channels → human-visible colour image)
    # MTF is the 4th channel — shown as a separate greyscale inset label
    def _norm(x):
        mn, mx = x.min(), x.max()
        return (x - mn) / (mx - mn + 1e-8)

    rgb = np.stack([
        _norm(multi[:, :, 0]),   # R = GASF
        _norm(multi[:, :, 1]),   # G = GADF
        _norm(multi[:, :, 2]),   # B = RP
    ], axis=-1)
    ax_rgb = fig.add_subplot(gs[3, 2:])
    ax_rgb.set_facecolor(STYLE['bg'])
    ax_rgb.imshow(rgb, aspect='auto')
    ax_rgb.set_title(
        'Stage 4b — RGB composite  (R=GASF  G=GADF  B=RP,  Ch3=MTF not shown)\n'
        'Human-readable approximation of the 4-channel tensor input to Conv2D',
        color=STYLE['text'], fontsize=8)
    ax_rgb.axis('off')

    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=STYLE['bg'])
    plt.close(fig)
    print(f"  Saved encoding stages → {out_path}")


# ── Visualisation ──────────────────────────────────────────────────────────────

def plot_encoding_gallery(traces_win: np.ndarray, labels: np.ndarray,
                          image_size: int, out_path: str, n_show: int = 4):
    """
    Plot one sample image per method side-by-side, for HW class 0 and HW class 4.
    Shows what different encoding methods look like on real power traces.
    """
    methods = list(ENCODERS.keys())
    n_cols  = len(methods)
    fig, axes = plt.subplots(2, n_cols, figsize=(n_cols * 3, 6))
    fig.patch.set_facecolor(STYLE['bg'])
    fig.suptitle('Image Encoding Methods — Power Trace → 2D Image',
                 color=STYLE['text'], fontsize=12)

    for row, hw_val in enumerate([0, 4]):
        idxs = np.where(labels == hw_val)[0]
        idx  = idxs[0] if len(idxs) > 0 else 0
        sample = traces_win[idx:idx+1]                     # (1, W)
        for col, method in enumerate(methods):
            img = encode(sample, method=method, image_size=image_size)[0, :, :, 0]
            ax  = axes[row, col]
            ax.imshow(img, cmap='viridis', aspect='auto')
            ax.set_title(f'{method.upper()}\nHW={hw_val}',
                         color=STYLE['text'], fontsize=9)
            ax.axis('off')

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=STYLE['bg'])
    plt.close(fig)
    print(f"  Saved gallery → {out_path}")

# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Encode power traces to 2D images')
    ap.add_argument('--data',       required=True)
    ap.add_argument('--byte',       type=int, default=0)
    ap.add_argument('--window',     type=int, default=512,
                    help='trace window width (samples around CPA peak)')
    ap.add_argument('--image-size', type=int, default=64,
                    help='output image size W×W (default 64)')
    ap.add_argument('--method',     default='gasf',
                    choices=list(ENCODERS), help='encoding method')
    ap.add_argument('--show',       action='store_true',
                    help='save gallery plot of all 4 methods')
    args = ap.parse_args()

    traces, _, ciphertexts, known_key, label = load_dataset(args.data)
    print(f"\nDataset : {label}  ({len(traces)} × {traces.shape[1]})")

    rk10  = extract_round_key(bytes(known_key), 10)
    rk_b  = int(rk10[args.byte])
    N_tr  = int(len(traces) * 0.8)

    print("\n--- CPA peak ---")
    peak = find_cpa_peak(traces[:N_tr], ciphertexts[:N_tr], args.byte, INV_SBOX, rk_b)
    win  = extract_window(traces, peak, args.window)       # (N, window)

    print(f"\n--- Encoding ({args.method}, {args.image_size}×{args.image_size}) ---")
    imgs = encode(win, method=args.method, image_size=args.image_size)
    print(f"  Output shape : {imgs.shape}   dtype: {imgs.dtype}")
    print(f"  Value range  : [{imgs.min():.3f}, {imgs.max():.3f}]")

    if args.show:
        hw_labels = HW[INV_SBOX[ciphertexts[:, args.byte] ^ rk_b]].astype(int)
        out = plots_dir(args.data)
        plot_encoding_gallery(win, hw_labels, args.image_size,
                              os.path.join(out, f'image_encoding_gallery_b{args.byte:02d}.png'))

    print("\nDone.")


if __name__ == '__main__':
    main()
