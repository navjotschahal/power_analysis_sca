"""
DPA (Differential Power Analysis) — AES-128

Distinguisher  (Kocher et al., CRYPTO 1999):

  Δ_j = max_i | mean( t_{d,i} | bit_l(v_{d,j}) = 1 )
               - mean( t_{d,i} | bit_l(v_{d,j}) = 0 ) |

  d ∈ [1..D]  — trace index
  j ∈ [0..255]— key-byte hypothesis
  l ∈ [0..7]  — target bit position (swept 0→7; first bit that verifies wins)
  v_{d,j}     — INV_SBOX[ ciphertext_d[b] ⊕ j ]  (last-round)
              — SBOX[ plaintext_d[b] ⊕ j ]         (first-round)
"""

import sys
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from helper import (
    SBOX, INV_SBOX,
    backward_key_schedule, verify_key, key_rank,
    load_dataset, plots_dir, apply_dark_style, STYLE,
)

# ── Core DPA ──────────────────────────────────────────────────────────────────

def dpa_byte(traces, data, target_byte, sbox_table, l):
    """
    DPA distinguisher score for one key byte at bit position l.
    Returns delta: (256,) — max Δ_j over all time samples per hypothesis j.

    Fully vectorised: replaces the 256-iteration Python loop with a single
    matrix multiply (T×D) @ (D×256) → (T×256), which is ~100× faster on
    large trace sets.
    """
    t   = traces.astype(np.float32)                                        # (D, T)
    hyp = sbox_table[data[:, target_byte, np.newaxis]
                     ^ np.arange(256, dtype=np.uint8)]                    # (D, 256)
    p1  = ((hyp >> l) & 1).astype(np.float32)                             # (D, 256) — 1 where bit=1
    p0  = 1.0 - p1                                                         # (D, 256) — 1 where bit=0

    c1  = p1.sum(axis=0)                                                   # (256,)
    c0  = p0.sum(axis=0)                                                   # (256,)
    valid = (c1 > 0) & (c0 > 0)                                            # (256,)

    # (T, D) @ (D, 256) = (T, 256)
    sum1  = t.T @ p1
    sum0  = t.T @ p0
    mean1 = sum1 / np.where(c1 > 0, c1, 1.0)
    mean0 = sum0 / np.where(c0 > 0, c0, 1.0)

    delta = np.abs(mean1 - mean0).max(axis=0) * valid                     # (256,)
    return delta.astype(np.float32)


def dpa_byte_full(traces, data, target_byte, sbox_table, l):
    """
    Full Δ_j(i) matrix for one key byte at bit position l.
    Returns (256, T) — used for visualisation.
    Vectorised version of the same computation as dpa_byte.
    """
    t   = traces.astype(np.float32)
    hyp = sbox_table[data[:, target_byte, np.newaxis]
                     ^ np.arange(256, dtype=np.uint8)]
    p1  = ((hyp >> l) & 1).astype(np.float32)
    p0  = 1.0 - p1

    c1  = p1.sum(axis=0)
    c0  = p0.sum(axis=0)

    sum1  = t.T @ p1
    sum0  = t.T @ p0
    mean1 = sum1 / np.where(c1 > 0, c1, 1.0)
    mean0 = sum0 / np.where(c0 > 0, c0, 1.0)

    return np.abs(mean1 - mean0).T.astype(np.float32)   # (256, T)

# ── Plots ──────────────────────────────────────────────────────────────────────

def plot_dpa(accu_matrix, delta_scores, correct_j, byte_idx, bit_l, dataset_label, out_dir):
    """
    Three-panel DPA diagnostic for one key byte.

    Panel 1 — Δ_j(i) over time: correct hypothesis vs a wrong one.
               Mirrors notebook cells 13 & 15.
    Panel 2 — Score bar chart: max Δ_j for all 256 hypotheses.
               Correct hypothesis highlighted in green.
    Panel 3 — Heatmap of full Δ_j(i) matrix (256 × T).
               The correct hypothesis row should be the brightest band.
    """
    wrong_j = int(np.argsort(delta_scores)[0])   # lowest-scoring guess

    fig = plt.figure(figsize=(16, 12))
    fig.suptitle(
        f'DPA — Byte {byte_idx:02d}  |  Bit {bit_l}  |  '
        f'Correct hypothesis: 0x{correct_j:02X}  |  {dataset_label}',
        color=STYLE['text'], fontsize=13, fontweight='bold'
    )
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

    ax_trace   = fig.add_subplot(gs[0, :])
    ax_bar     = fig.add_subplot(gs[1, 0])
    ax_heatmap = fig.add_subplot(gs[1, 1])

    apply_dark_style(fig, [ax_trace, ax_bar, ax_heatmap])

    T = accu_matrix.shape[1]
    x = np.arange(T)

    # ── Panel 1: delta traces ─────────────────────────────────────────────────
    ax_trace.plot(x, accu_matrix[wrong_j],   color=STYLE['wrong'],   lw=0.8,
                  alpha=0.85, label=f'Wrong   (j=0x{wrong_j:02X})')
    ax_trace.plot(x, accu_matrix[correct_j], color=STYLE['correct'], lw=1.2,
                  label=f'Correct (j=0x{correct_j:02X})')
    ax_trace.set_xlabel('Time sample  i')
    ax_trace.set_ylabel('|Δ mean|')
    ax_trace.set_title(f'Differential mean trace — bit {bit_l} — correct vs wrong hypothesis')
    ax_trace.legend(facecolor=STYLE['bg'], labelcolor=STYLE['text'], fontsize=9)

    # ── Panel 2: score bar chart ──────────────────────────────────────────────
    colors = [STYLE['correct'] if j == correct_j else STYLE['neutral'] for j in range(256)]
    ax_bar.bar(range(256), delta_scores, color=colors, width=1.0, alpha=0.85)
    ax_bar.set_xlabel('Key hypothesis  j')
    ax_bar.set_ylabel('max|Δ_j|  over i')
    ax_bar.set_title('Hypothesis scores — correct highlighted')
    ax_bar.set_xlim(-1, 256)

    # ── Panel 3: heatmap ──────────────────────────────────────────────────────
    downsample = max(1, T // 1000)
    hm_data    = accu_matrix[:, ::downsample]
    im = ax_heatmap.imshow(hm_data, aspect='auto', cmap='plasma',
                           origin='lower', interpolation='nearest')
    ax_heatmap.axhline(correct_j, color=STYLE['correct'], lw=1.2, alpha=0.9,
                       label=f'Correct j=0x{correct_j:02X}')
    ax_heatmap.set_xlabel(f'Time sample  i  (1:{downsample} downsampled)')
    ax_heatmap.set_ylabel('Key hypothesis  j')
    ax_heatmap.set_title('|Δ_j(i)| heatmap')
    ax_heatmap.legend(facecolor=STYLE['bg'], labelcolor=STYLE['text'], fontsize=8)
    plt.colorbar(im, ax=ax_heatmap, fraction=0.046, pad=0.04).ax.yaxis.set_tick_params(color=STYLE['text'])

    out_path = os.path.join(out_dir, f'dpa_byte{byte_idx:02d}_bit{bit_l}.png')
    fig.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=STYLE['bg'])
    plt.close(fig)
    print(f"  → {out_path}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='DPA attack on AES-128')
    parser.add_argument('--data',      default='data/set_001_pico_real')
    parser.add_argument('--round',     choices=['first', 'last'], default='first',
                        help='first=plaintext+SBOX; last=ciphertext+INV_SBOX (sweeps bit 0→7)')
    parser.add_argument('--plot-byte', type=int, default=0,
                        help='Key byte index to visualise after the attack (default: 0)')
    args = parser.parse_args()

    traces, plaintexts, ciphertexts, known_key, label = load_dataset(args.data)

    data       = plaintexts if args.round == 'first' else ciphertexts
    sbox_table = SBOX       if args.round == 'first' else INV_SBOX

    D, T = traces.shape
    print(f"Dataset      : {args.data}")
    print(f"Traces       : {D} × {T} samples")
    print(f"Attack round : {args.round}\n")

    winning_bit          = None
    winning_round_key_10 = None

    for l in range(8):
        print(f"Target bit at position {l}: ")
        print(f"    Recovered round-10 key: ", end="", flush=True)

        recovered_round_key_10 = []
        for b in range(16):
            delta          = dpa_byte(traces, data, b, sbox_table, l)
            predicted_byte = int(np.argmax(delta))
            print(f"{predicted_byte:02X} ", end="", flush=True)
            recovered_round_key_10.append(predicted_byte)

        if args.round == 'last' and known_key is not None:
            if verify_key(recovered_round_key_10, known_key):
                print("---> Correct")
                winning_bit          = l
                winning_round_key_10 = recovered_round_key_10
                recovered_key        = backward_key_schedule(bytes(recovered_round_key_10))
                print(f"\nOriginal key : {' '.join(f'{b:02X}' for b in recovered_key)}")
                print(f"Known key    : {' '.join(f'{b:02X}' for b in known_key)}")
                break
            else:
                print("---> False")
        else:
            recovered_key = bytes(recovered_round_key_10)
            if known_key is not None:
                match = "---> Correct" if list(recovered_key) == list(known_key) else "---> False"
            else:
                match = ""
            print(match)
            if match == "---> Correct":
                winning_bit          = l
                winning_round_key_10 = recovered_round_key_10
                break

    # ── Plots ─────────────────────────────────────────────────────────────────
    if winning_round_key_10 is None:
        print("\nAttack did not converge — skipping plots.")
        return

    b         = args.plot_byte
    correct_j = winning_round_key_10[b]
    used_bit  = winning_bit

    print(f"\nGenerating DPA plots for byte {b} (j=0x{correct_j:02X}, bit={used_bit})...")
    accu_matrix  = dpa_byte_full(traces, data, b, sbox_table, used_bit)
    delta_scores = np.max(accu_matrix, axis=1)

    pdir = plots_dir(args.data)
    plot_dpa(accu_matrix, delta_scores, correct_j, b, used_bit, label, pdir)
    print("Done.")


if __name__ == '__main__':
    main()
