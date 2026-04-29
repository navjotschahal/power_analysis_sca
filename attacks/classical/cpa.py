"""
CPA (Correlation Power Analysis) — AES-128

Proposal notation  (Brier et al., CHES 2004):

         Σ_d (t_{d,i} - t̄_i)(h_{d,j} - h̄_j)
r_{i,j} = ─────────────────────────────────────────────────────
           sqrt( Σ_d(t_{d,i} - t̄_i)² · Σ_d(h_{d,j} - h̄_j)² )

  d ∈ [1..D]  — trace index          (D = total traces)
  i           — time-sample index
  j ∈ [0..255]— key-byte hypothesis
  t_{d,i}     — measured power at sample i in trace d
  h_{d,j}     — hypothetical power consumption (see attack round)
  t̄_i         — mean of t_{d,i} over d
  h̄_j         — mean of h_{d,j} over d

Attack rounds
─────────────
first-round : h_{d,j} = HW( SBOX[ plaintext_d[b] ⊕ j ] ⊕ const )
last-round  : h_{d,j} = HW( INV_SBOX[ ciphertext_d[b] ⊕ j ] ⊕ const )
              const swept 0→255; stops at first const that verifies the full key.
"""

import sys
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from helper import (
    SBOX, INV_SBOX, HW,
    backward_key_schedule, verify_key, key_rank,
    load_dataset, plots_dir, apply_dark_style, STYLE,
)

# ── Core CPA ──────────────────────────────────────────────────────────────────

def _precompute_trace_stats(traces):
    """Compute t̄_i and centered traces once — reused across all bytes and consts."""
    t_bar_i     = np.mean(traces, axis=0)        # t̄_i  : (T,)
    t_di_center = traces - t_bar_i               # t_{d,i} - t̄_i : (D, T)
    sum_t_sq    = np.sum(t_di_center**2, axis=0) # Σ_d(t_{d,i} - t̄_i)² : (T,)
    return t_di_center, sum_t_sq


def cpa_byte(data, target_byte, sbox_table, t_di_center, sum_t_sq, const):
    """
    Compute the max |r_{i,j}| score for each hypothesis j (one key byte).
    Returns correlation_on_guess: (256,) — used in the attack loop.

    h_{d,j} = HW( sbox_table[ data_d[b] ⊕ j ] ⊕ const )
    """
    scores = np.zeros(256, dtype=np.float32)

    for j in range(256):
        h_dj        = HW[sbox_table[data[:, target_byte] ^ j] ^ const]  # (D,)
        h_bar_j     = np.mean(h_dj)                                      # h̄_j
        h_dj_center = h_dj - h_bar_j                                     # (D,)

        # numerator:   Σ_d (t_{d,i} - t̄_i)(h_{d,j} - h̄_j)
        numerator   = h_dj_center @ t_di_center                          # (T,)
        # denominator: sqrt( Σ_d(t_{d,i}-t̄_i)² · Σ_d(h_{d,j}-h̄_j)² )
        denominator = np.sqrt(np.sum(h_dj_center**2) * sum_t_sq)
        r_ij        = np.where(denominator > 0, numerator / denominator, 0.0)
        scores[j]   = np.max(np.abs(r_ij))

    return scores


def cpa_byte_full(data, target_byte, sbox_table, t_di_center, sum_t_sq, const):
    """
    Compute the full r_{i,j} matrix for one key byte.
    Returns correlation_on_trace: (256, T) — used for visualisation.
    """
    T = t_di_center.shape[1]
    corr = np.zeros((256, T), dtype=np.float32)

    for j in range(256):
        h_dj        = HW[sbox_table[data[:, target_byte] ^ j] ^ const]
        h_bar_j     = np.mean(h_dj)
        h_dj_center = h_dj - h_bar_j

        numerator   = h_dj_center @ t_di_center
        denominator = np.sqrt(np.sum(h_dj_center**2) * sum_t_sq)
        corr[j]     = np.where(denominator > 0, numerator / denominator, 0.0)

    return corr

# ── Plots ──────────────────────────────────────────────────────────────────────

def plot_cpa(corr_matrix, correct_j, byte_idx, dataset_label, out_dir):
    """
    Three-panel CPA diagnostic for one key byte.

    Panel 1 — Correlation trace over time: correct hypothesis vs a wrong one.
               Mirrors notebook cells 22 & 24.
    Panel 2 — Score bar chart: max|r_{i,j}| for all 256 hypotheses.
               Correct hypothesis bar highlighted in green.
    Panel 3 — Heatmap of full r_{i,j} matrix (256 × T).
               The correct hypothesis row should be the brightest band.
    """
    wrong_j  = int(np.argsort(np.max(np.abs(corr_matrix), axis=1))[0])   # lowest-scoring guess
    scores   = np.max(np.abs(corr_matrix), axis=1)

    fig = plt.figure(figsize=(16, 12))
    fig.suptitle(
        f'CPA — Byte {byte_idx:02d}  |  Correct hypothesis: 0x{correct_j:02X}  |  {dataset_label}',
        color=STYLE['text'], fontsize=13, fontweight='bold'
    )
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

    ax_trace  = fig.add_subplot(gs[0, :])   # full-width top
    ax_bar    = fig.add_subplot(gs[1, 0])
    ax_heatmap = fig.add_subplot(gs[1, 1])

    apply_dark_style(fig, [ax_trace, ax_bar, ax_heatmap])

    # ── Panel 1: correlation traces ───────────────────────────────────────────
    T = corr_matrix.shape[1]
    x = np.arange(T)
    ax_trace.plot(x, corr_matrix[wrong_j],   color=STYLE['wrong'],   lw=0.8,
                  alpha=0.85, label=f'Wrong   (j=0x{wrong_j:02X})')
    ax_trace.plot(x, corr_matrix[correct_j], color=STYLE['correct'], lw=1.2,
                  label=f'Correct (j=0x{correct_j:02X})')
    ax_trace.axhline(0, color=STYLE['text'], lw=0.4, alpha=0.4)
    ax_trace.set_xlabel('Time sample  i')
    ax_trace.set_ylabel('r_{i,j}  (Pearson correlation)')
    ax_trace.set_title('Correlation trace — correct vs wrong hypothesis')
    ax_trace.legend(facecolor=STYLE['bg'], labelcolor=STYLE['text'], fontsize=9)

    # ── Panel 2: score bar chart ──────────────────────────────────────────────
    colors = [STYLE['correct'] if j == correct_j else STYLE['neutral'] for j in range(256)]
    ax_bar.bar(range(256), scores, color=colors, width=1.0, alpha=0.85)
    ax_bar.set_xlabel('Key hypothesis  j')
    ax_bar.set_ylabel('max|r_{i,j}|  over i')
    ax_bar.set_title('Hypothesis scores — correct highlighted')
    ax_bar.set_xlim(-1, 256)

    # ── Panel 3: heatmap ──────────────────────────────────────────────────────
    downsample = max(1, T // 1000)   # cap at 1000 columns for rendering speed
    hm_data    = np.abs(corr_matrix[:, ::downsample])
    im = ax_heatmap.imshow(hm_data, aspect='auto', cmap='inferno',
                           origin='lower', interpolation='nearest')
    ax_heatmap.axhline(correct_j, color=STYLE['correct'], lw=1.2, alpha=0.9,
                       label=f'Correct j=0x{correct_j:02X}')
    ax_heatmap.set_xlabel(f'Time sample  i  (1:{downsample} downsampled)')
    ax_heatmap.set_ylabel('Key hypothesis  j')
    ax_heatmap.set_title('|r_{i,j}| heatmap')
    ax_heatmap.legend(facecolor=STYLE['bg'], labelcolor=STYLE['text'], fontsize=8)
    plt.colorbar(im, ax=ax_heatmap, fraction=0.046, pad=0.04).ax.yaxis.set_tick_params(color=STYLE['text'])

    out_path = os.path.join(out_dir, f'cpa_byte{byte_idx:02d}.png')
    fig.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=STYLE['bg'])
    plt.close(fig)
    print(f"  → {out_path}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='CPA attack on AES-128')
    parser.add_argument('--data',     default='data/set_001_pico_real')
    parser.add_argument('--round',    choices=['first', 'last'], default='first',
                        help='first=plaintext+SBOX; last=ciphertext+INV_SBOX (sweeps const)')
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

    t_di_center, sum_t_sq = _precompute_trace_stats(traces)

    winning_const          = None
    winning_round_key_10   = None

    for const in range(256):
        print(f"Const {const}: ")
        print(f"    Recovered round-10 key: ", end="", flush=True)

        recovered_round_key_10 = []
        for b in range(16):
            scores         = cpa_byte(data, b, sbox_table, t_di_center, sum_t_sq, const)
            predicted_byte = int(np.argmax(scores))
            print(f"{predicted_byte:02X} ", end="", flush=True)
            recovered_round_key_10.append(predicted_byte)

        if args.round == 'last' and known_key is not None:
            if verify_key(recovered_round_key_10, known_key):
                print("---> Correct")
                winning_const        = const
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
                winning_const        = const
                winning_round_key_10 = recovered_round_key_10
                break

    # ── Plots ─────────────────────────────────────────────────────────────────
    if winning_round_key_10 is None:
        print("\nAttack did not converge — skipping plots.")
        return

    b          = args.plot_byte
    correct_j  = winning_round_key_10[b]   # correct round-10 key byte for visualisation
    used_const = winning_const

    print(f"\nGenerating CPA plots for byte {b} (j=0x{correct_j:02X}, const={used_const})...")
    corr_matrix = cpa_byte_full(data, b, sbox_table, t_di_center, sum_t_sq, used_const)

    pdir = plots_dir(args.data)
    plot_cpa(corr_matrix, correct_j, b, label, pdir)
    print("Done.")


if __name__ == '__main__':
    main()
