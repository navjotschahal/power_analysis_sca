"""
plot_traces.py — Dataset visualisation (Fig. 2 style, Hettwer et al. 2020).

With image cache present (images_S{N}.h5):
  Row 1 — (a) raw trace overlay  (b) GASF  (c) GADF  (d) MTF  (e) RP  (f) spectrogram
  Row 2 — Pearson correlation of each panel with HW(SBOX[pt ⊕ key]) label

Without image cache:
  Row 1 — raw trace overlay | spectrogram | metadata summary
  Row 2 — trace correlation  | spectrogram correlation  (if key known)

Saves to {data_dir}/data_view/overview.png.

Usage
─────
  python plot_traces.py --data data/set_003_arduino_uno
  python plot_traces.py --data data/set_003_arduino_uno --byte 0 --round first
  python plot_traces.py --data data/set_003_arduino_uno --no-corr
"""

import argparse
import os
import sys
import json

import h5py
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy import signal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'attacks'))
from helper import SBOX, INV_SBOX, HW, extract_round_key, load_dataset, apply_dark_style, STYLE


# ── Signal helpers ─────────────────────────────────────────────────────────────

def _pearson_1d(traces: np.ndarray, hw: np.ndarray) -> np.ndarray:
    """Pearson r between hw and each time sample. Returns (T,)."""
    hw_c  = hw - hw.mean()
    tc    = traces - traces.mean(axis=0)
    return (hw_c[:, None] * tc).mean(0) / ((hw.std() + 1e-8) * (tc.std(0) + 1e-8))


def _pearson_2d(imgs: np.ndarray, hw: np.ndarray) -> np.ndarray:
    """Pearson r between hw and each pixel of a (N, S, S) stack. Returns (S, S)."""
    hw_c = hw - hw.mean()
    ic   = imgs - imgs.mean(axis=0)
    return (hw_c[:, None, None] * ic).mean(0) / ((hw.std() + 1e-8) * (ic.std(0) + 1e-8))


def _make_spectrogram(trace: np.ndarray, nperseg: int = 128):
    """Return (Sxx_norm, freqs, times) for one trace, Sxx rescaled to [0, 1]."""
    freqs, times, Sxx = signal.spectrogram(trace.astype(np.float64), nperseg=nperseg)
    Sxx_norm = (Sxx - Sxx.min()) / (Sxx.max() - Sxx.min() + 1e-8)
    return Sxx_norm.astype(np.float32), freqs, times


def _spectrograms_all(traces: np.ndarray, nperseg: int = 128) -> np.ndarray:
    """Compute spectrogram for every trace. Returns (N, F, T_spec)."""
    _, _, S0 = signal.spectrogram(traces[0].astype(np.float64), nperseg=nperseg)
    out = np.empty((len(traces), *S0.shape), dtype=np.float32)
    for i, tr in enumerate(traces):
        _, _, Sxx = signal.spectrogram(tr.astype(np.float64), nperseg=nperseg)
        out[i] = Sxx.astype(np.float32)
    return out


def _hw_labels(plaintexts, ciphertexts, known_key, round_name: str, byte: int):
    """Return (N,) HW labels for the chosen round and byte."""
    if known_key is None:
        return None
    if round_name == 'last':
        rk   = list(extract_round_key(bytes(known_key), 10))
        data = ciphertexts
        sbox = INV_SBOX
    else:
        rk   = list(known_key)
        data = plaintexts
        sbox = SBOX
    return HW[sbox[data[:, byte].astype(int) ^ rk[byte]]].astype(np.float32)


# ── Main plot ──────────────────────────────────────────────────────────────────

def plot_overview(data_dir: str, byte: int = 0, round_name: str = 'first',
                  image_size: int = 64, n_overlay: int = 5,
                  trace_idx: int = 0, show_corr: bool = True):
    """
    Generate and save the overview figure for a dataset.
    Saves to {data_dir}/data_view/overview.png.
    """
    out_dir = os.path.join(data_dir, 'data_view')
    os.makedirs(out_dir, exist_ok=True)

    # ── Load dataset ──────────────────────────────────────────────────────────
    traces, plaintexts, ciphertexts, known_key, label = load_dataset(data_dir)
    N, T = traces.shape

    meta_path = os.path.join(data_dir, 'meta.json')
    notes = ''
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        notes = meta.get('notes', '')

    hw = _hw_labels(plaintexts, ciphertexts, known_key, round_name, byte)
    corr_ok = (hw is not None) and show_corr

    # ── Load or compute image encodings ──────────────────────────────────────
    cache_path = os.path.join(data_dir, f'images_S{image_size}.h5')
    imgs = None   # (N, S, S, 4) — full dataset (from cache, if present)
    imgs1 = None  # (1, S, S, 4) — single trace for display (always available)

    if os.path.exists(cache_path):
        with h5py.File(cache_path, 'r') as f:
            if (int(f.attrs.get('image_size', 0)) == image_size and
                    int(f.attrs.get('n_traces',   0)) == N):
                imgs = np.array(f['images'], dtype=np.float32)   # (N, S, S, 4)

    # Always compute single-trace encoding for display (fast — one trace only)
    _here = os.path.dirname(os.path.abspath(__file__))
    _attacks_dir = os.path.join(_here, 'attacks')
    if _attacks_dir not in sys.path:
        sys.path.insert(0, _attacks_dir)
    from deep_learning.image_encode import encode_multichannel  # type: ignore[import]
    imgs1 = encode_multichannel(traces[trace_idx:trace_idx+1].astype(np.float32),
                                image_size=image_size)  # (1, S, S, 4)

    nperseg = min(128, max(16, T // 32))
    spec0, freqs, times = _make_spectrogram(traces[trace_idx], nperseg)

    # ── Display config — column order matches Fig. 2 of Hettwer et al. 2020 ──
    # encode_multichannel channel order: 0=GASF 1=GADF 2=RP 3=MTF
    # paper column order:               GASF   GADF   MTF  RP
    DISPLAY_CH   = [0, 1, 3, 2]          # channel indices in paper order
    CH_NAMES     = ['GASF', 'GADF', 'MTF', 'RP']
    IMG_CMAP     = 'viridis'             # row 1 images
    CORR_CMAP    = 'hot'                 # row 2 correlations (paper uses fire palette)
    S            = image_size

    n_cols = 6
    n_rows = 2 if corr_ok else 1

    fig = plt.figure(figsize=(22, 4.0 * n_rows), facecolor=STYLE['bg'])
    fig.suptitle(f'{label}   |   N={N:,}  T={T:,}  byte={byte}  round={round_name}',
                 color=STYLE['text'], fontsize=11, y=1.02)

    gs = gridspec.GridSpec(n_rows, n_cols, figure=fig, hspace=0.55, wspace=0.45)

    def _ax(row, col):
        ax = fig.add_subplot(gs[row, col])
        ax.set_facecolor(STYLE['bg'])
        for sp in ax.spines.values():
            sp.set_edgecolor(STYLE['grid'])
        ax.tick_params(colors=STYLE['text'], labelsize=7)
        return ax

    def _imshow_img(ax, img, cmap, title, xlabel='', ylabel=''):
        """Image panel: axes on, ticks visible, proper labels."""
        im = ax.imshow(img, cmap=cmap, aspect='equal', origin='upper',
                       extent=[0, S, S, 0])
        ax.set_title(title, color=STYLE['text'], fontsize=9, pad=4)
        ax.set_xlabel(xlabel, color=STYLE['text'], fontsize=7)
        ax.set_ylabel(ylabel, color=STYLE['text'], fontsize=7)
        ax.tick_params(colors=STYLE['text'], labelsize=7)
        cb = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cb.ax.tick_params(colors=STYLE['text'], labelsize=6)
        cb.set_label('Correlation' if 'corr' in title.lower() else '',
                     color=STYLE['text'], fontsize=6)

    def _unshift(img, ch_idx):
        """GASF (ch0) and GADF (ch1) are stored in [0,1]; un-shift to [-1,1] for display."""
        if ch_idx in (0, 1):
            return img * 2.0 - 1.0
        return img

    # source for single-trace images
    src     = imgs if imgs is not None else imgs1
    src_idx = trace_idx if imgs is not None else 0

    # ── Row 0 — single trace + encodings ─────────────────────────────────────

    # (a) Single raw trace — all T points
    ax_tr = _ax(0, 0)
    ax_tr.plot(traces[trace_idx], lw=0.8, color=STYLE['correct'])
    ax_tr.set_title('Trace', color=STYLE['text'], fontsize=9, pad=4)
    ax_tr.set_xlabel('Time [Sample Point]', color=STYLE['text'], fontsize=7)
    ax_tr.set_ylabel('Amplitude', color=STYLE['text'], fontsize=7)
    ax_tr.grid(color=STYLE['grid'], lw=0.4)

    # (b)–(e) GASF | GADF | MTF | RP
    for col, (ch, name) in enumerate(zip(DISPLAY_CH, CH_NAMES)):
        img_disp = _unshift(src[src_idx, :, :, ch], ch)
        _imshow_img(_ax(0, col + 1), img_disp, IMG_CMAP, name)

    # (f) Spectrogram
    ax_sp = _ax(0, 5)
    im_sp = ax_sp.imshow(spec0, cmap='viridis', aspect='auto', origin='upper',
                         extent=[times[0], times[-1], freqs[-1], freqs[0]])
    ax_sp.set_title('Spectrogram', color=STYLE['text'], fontsize=9, pad=4)
    ax_sp.set_xlabel('Time [Segment]', color=STYLE['text'], fontsize=7)
    ax_sp.set_ylabel('Frequency [normalized]', color=STYLE['text'], fontsize=7)
    ax_sp.tick_params(colors=STYLE['text'], labelsize=7)
    cb_sp = plt.colorbar(im_sp, ax=ax_sp, fraction=0.046, pad=0.04)
    cb_sp.ax.tick_params(colors=STYLE['text'], labelsize=6)

    # ── Row 1 — correlation plots ─────────────────────────────────────────────
    if corr_ok:
        n_corr = min(N, 500)

        # (a) Trace correlation
        ax_tc = _ax(1, 0)
        corr_tr = _pearson_1d(traces[:n_corr], hw[:n_corr])
        ax_tc.plot(corr_tr, color=STYLE['correct'], lw=0.8)
        ax_tc.axhline(0, color=STYLE['grid'], lw=0.5)
        ax_tc.set_title('Trace', color=STYLE['text'], fontsize=9, pad=4)
        ax_tc.set_xlabel('Time [Sample Point]', color=STYLE['text'], fontsize=7)
        ax_tc.set_ylabel('Correlation', color=STYLE['text'], fontsize=7)
        ax_tc.grid(color=STYLE['grid'], lw=0.4)

        # (b)–(e) GASF | GADF | MTF | RP correlation heatmaps
        if imgs is not None:
            for col, (ch, name) in enumerate(zip(DISPLAY_CH, CH_NAMES)):
                corr_img = _pearson_2d(imgs[:n_corr, :, :, ch], hw[:n_corr])
                _imshow_img(_ax(1, col + 1), corr_img, CORR_CMAP,
                            name, ylabel='Correlation')
        else:
            for col, name in enumerate(CH_NAMES):
                ax_ph = _ax(1, col + 1)
                ax_ph.axis('off')
                ax_ph.text(0.5, 0.5, f'{name} correlation\n(cache not found)',
                           color=STYLE['grid'], fontsize=7,
                           ha='center', va='center', transform=ax_ph.transAxes)

        # (f) Spectrogram correlation
        print(f"  Computing spectrogram correlation ({n_corr} traces) ...")
        specs    = _spectrograms_all(traces[:n_corr], nperseg)
        corr_spec = _pearson_2d(specs, hw[:n_corr])
        ax_sc = _ax(1, 5)
        im_sc = ax_sc.imshow(corr_spec, cmap=CORR_CMAP, aspect='auto', origin='upper',
                              extent=[times[0], times[-1], freqs[-1], freqs[0]])
        ax_sc.set_title('Spectrogram', color=STYLE['text'], fontsize=9, pad=4)
        ax_sc.set_xlabel('Time [Segment]', color=STYLE['text'], fontsize=7)
        ax_sc.set_ylabel('Correlation', color=STYLE['text'], fontsize=7)
        ax_sc.tick_params(colors=STYLE['text'], labelsize=7)
        cb_sc = plt.colorbar(im_sc, ax=ax_sc, fraction=0.046, pad=0.04)
        cb_sc.ax.tick_params(colors=STYLE['text'], labelsize=6)

    # ── Save ──────────────────────────────────────────────────────────────────
    out_path = os.path.join(out_dir, 'overview.png')
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=STYLE['bg'])
    plt.close(fig)
    print(f"  Saved → {out_path}")
    return out_path


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description='Dataset visualisation — Fig. 2 style (Hettwer et al. 2020)',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument('--data',       required=True,
                    help='Dataset directory (traces.npy / meta.json)')
    ap.add_argument('--byte',       type=int, default=0,
                    help='Key byte index for HW correlation (0–15)')
    ap.add_argument('--round',      choices=['first', 'last'], default='first',
                    help='AES round for HW label')
    ap.add_argument('--image-size', type=int, default=64,
                    help='Image size S to look for in cache (images_S{N}.h5)')
    ap.add_argument('--n-overlay',  type=int, default=5,
                    help='Number of traces to overlay in panel (a)')
    ap.add_argument('--trace-idx',  type=int, default=0,
                    help='Trace index to display as encoded images')
    ap.add_argument('--no-corr',    action='store_true',
                    help='Skip correlation row (faster, no key required)')
    args = ap.parse_args()

    print(f"Dataset : {args.data}")
    plot_overview(
        data_dir   = args.data,
        byte       = args.byte,
        round_name = args.round,
        image_size = args.image_size,
        n_overlay  = args.n_overlay,
        trace_idx  = args.trace_idx,
        show_corr  = not args.no_corr,
    )


if __name__ == '__main__':
    main()
