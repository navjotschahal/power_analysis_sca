"""
cpa_paper.py — CPA exactly as specified in Brier et al., CHES 2004.

Paper: "Correlation Power Analysis with a Leakage Model"
       Eric Brier, Christophe Clavier, Francis Olivier
       CHES 2004, LNCS 3156, pp. 16-29.

Equation (1) from the paper:
─────────────────────────────────────────────────────────────────────────────

         Σ_d  (t_{d,i} − t̄_i)(h_{d,j} − h̄_j)
r_{i,j} = ──────────────────────────────────────────────────────────────
           √[ Σ_d(t_{d,i}−t̄_i)² · Σ_d(h_{d,j}−h̄_j)² ]

─────────────────────────────────────────────────────────────────────────────

Variables (paper notation preserved exactly):
  d ∈ {1..D}   — trace index
  i            — time sample index
  j ∈ {0..255} — key-byte hypothesis
  t_{d,i}      — measured power at sample i in trace d
  h_{d,j}      — hypothetical power: HW( INV_SBOX[ ciphertext_d[b] ⊕ j ] )
  t̄_i          — mean of t_{d,i} over d (all traces)
  h̄_j          — mean of h_{d,j} over d

NO const, NO sweep — pure HW model exactly as written in the paper.

Key differences from cpa.py
────────────────────────────
  cpa.py        : h = HW(v ^ const), sweeps const 0-255 (HD model workaround)
  cpa_paper.py  : h = HW(v)          (paper equation, const implicitly = 0)

  cpa.py        : loops over 256 hypotheses one at a time
  cpa_paper.py  : fully vectorised — computes all 256 × T correlations at once
                  using matrix multiply (D×256)ᵀ @ (D×T) = (256×T)

Usage
─────
  python attacks/classical/cpa_paper.py --data data/set_002_reference --round last
"""

import argparse
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from helper import (
    SBOX, INV_SBOX, HW,
    backward_key_schedule, verify_key, key_rank,
    load_dataset, plots_dir, apply_dark_style, STYLE,
)

# ── Paper equation — fully vectorised ─────────────────────────────────────────

def cpa_all_hypotheses(traces: np.ndarray, data: np.ndarray,
                       target_byte: int, sbox_table) -> np.ndarray:
    """
    Compute r_{i,j} for ALL 256 hypotheses simultaneously.

    Paper equation, vectorised form:
      H : (D, 256)  — hypothetical power for every trace × every hypothesis
      T : (D, T)    — measured traces, mean-centred

      r = (H_c.T @ T_c) / outer(||H_c||_col, ||T_c||_col)

    Returns
    -------
    r_matrix : (256, T)  — full Pearson correlation matrix
    """
    D = len(traces)
    T = traces.shape[1]

    # ── H matrix: hypothetical power for all hypotheses ───────────────────────
    # data[:, b] : (D,)  — one ciphertext/plaintext byte per trace
    # np.arange(256)     — all key hypotheses at once
    intermediates = sbox_table[
        data[:, target_byte, np.newaxis] ^ np.arange(256, dtype=np.uint8)
    ]                                           # (D, 256)
    H = np.array([HW[v] for v in intermediates.ravel()],
                 dtype=np.float32).reshape(D, 256)   # (D, 256)

    # ── Mean-centre both matrices (paper: subtract mean over d) ───────────────
    H_c = H - H.mean(axis=0)                   # (D, 256)  — h_{d,j} − h̄_j
    T_c = traces.astype(np.float32) - traces.astype(np.float32).mean(axis=0)
                                                # (D, T)    — t_{d,i} − t̄_i

    # ── Numerator: Σ_d (t_{d,i}−t̄_i)(h_{d,j}−h̄_j) ─────────────────────────
    # (256, D) @ (D, T) = (256, T)
    numerator = H_c.T @ T_c                    # (256, T)

    # ── Denominator: √[Σ_d(t−t̄)² · Σ_d(h−h̄)²] ──────────────────────────────
    denom_H = np.sqrt(np.sum(H_c ** 2, axis=0))   # (256,)  — one per hypothesis
    denom_T = np.sqrt(np.sum(T_c ** 2, axis=0))   # (T,)    — one per time sample

    denom = np.outer(denom_H, denom_T)         # (256, T)
    r_matrix = np.where(denom > 0, numerator / denom, 0.0)

    return r_matrix.astype(np.float32)         # (256, T)


def attack_byte(traces, data, target_byte, sbox_table) -> tuple[int, np.ndarray]:
    """
    Attack one key byte.
    Returns (predicted_key_byte, r_matrix (256, T)).
    """
    r_matrix = cpa_all_hypotheses(traces, data, target_byte, sbox_table)
    scores   = np.max(np.abs(r_matrix), axis=1)   # (256,) — max|r| over time
    return int(np.argmax(scores)), r_matrix


# ── Plots ──────────────────────────────────────────────────────────────────────

def plot_cpa_paper(r_matrix, correct_j, byte_idx, dataset_label, out_dir):
    """
    Three-panel CPA diagnostic — mirrors Figure 1 & 2 of Brier et al. 2004.

    Panel 1 — r_{i,j} over time: correct hypothesis (bright peak) vs wrong (flat noise)
    Panel 2 — max|r_{i,j}| bar chart: one bar per hypothesis, correct = green
    Panel 3 — |r_{i,j}| heatmap: 256 rows × T cols, correct row = bright stripe
    """
    scores  = np.max(np.abs(r_matrix), axis=1)   # (256,)
    wrong_j = int(np.argsort(scores)[0])          # lowest-scoring hypothesis

    fig = plt.figure(figsize=(16, 12))
    fig.suptitle(
        f'CPA (Brier 2004) — Byte {byte_idx:02d}  |  '
        f'Correct: 0x{correct_j:02X}  |  {dataset_label}',
        color=STYLE['text'], fontsize=13, fontweight='bold'
    )
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

    ax_trace   = fig.add_subplot(gs[0, :])
    ax_bar     = fig.add_subplot(gs[1, 0])
    ax_heatmap = fig.add_subplot(gs[1, 1])
    apply_dark_style(fig, [ax_trace, ax_bar, ax_heatmap])

    T = r_matrix.shape[1]
    x = np.arange(T)

    # Panel 1 — correlation traces
    ax_trace.plot(x, r_matrix[wrong_j],   color=STYLE['wrong'],   lw=0.8,
                  alpha=0.85, label=f'Wrong   j=0x{wrong_j:02X}')
    ax_trace.plot(x, r_matrix[correct_j], color=STYLE['correct'], lw=1.2,
                  label=f'Correct j=0x{correct_j:02X}')
    ax_trace.axhline(0, color=STYLE['text'], lw=0.4, alpha=0.4)
    ax_trace.set_xlabel('Time sample  i')
    ax_trace.set_ylabel('r_{i,j}  (Pearson correlation)')
    ax_trace.set_title('Correlation trace — paper eq.(1), HW model, no const')
    ax_trace.legend(facecolor=STYLE['bg'], labelcolor=STYLE['text'], fontsize=9)

    # Panel 2 — score bar chart
    colors = [STYLE['correct'] if j == correct_j else STYLE['neutral']
              for j in range(256)]
    ax_bar.bar(range(256), scores, color=colors, width=1.0, alpha=0.85)
    ax_bar.set_xlabel('Key hypothesis  j')
    ax_bar.set_ylabel('max|r_{i,j}|  over i')
    ax_bar.set_title('Hypothesis scores — correct highlighted')
    ax_bar.set_xlim(-1, 256)

    # Panel 3 — heatmap
    downsample = max(1, T // 1000)
    hm_data    = np.abs(r_matrix[:, ::downsample])
    im = ax_heatmap.imshow(hm_data, aspect='auto', cmap='inferno',
                           origin='lower', interpolation='nearest')
    ax_heatmap.axhline(correct_j, color=STYLE['correct'], lw=1.2,
                       label=f'Correct j=0x{correct_j:02X}')
    ax_heatmap.set_xlabel(f'Time sample  i  (1:{downsample} downsampled)')
    ax_heatmap.set_ylabel('Key hypothesis  j')
    ax_heatmap.set_title('|r_{i,j}| heatmap — eq.(1)')
    ax_heatmap.legend(facecolor=STYLE['bg'], labelcolor=STYLE['text'], fontsize=8)
    plt.colorbar(im, ax=ax_heatmap, fraction=0.046, pad=0.04)

    out_path = os.path.join(out_dir, f'cpa_paper_byte{byte_idx:02d}.png')
    fig.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=STYLE['bg'])
    plt.close(fig)
    print(f"  → {out_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='CPA — exact Brier et al. 2004 equation, no const sweep')
    parser.add_argument('--data',       default='data/set_001_pico_real')
    parser.add_argument('--round',      choices=['first', 'last'], default='first',
                        help='first=plaintext+SBOX  last=ciphertext+INV_SBOX')
    parser.add_argument('--plot-byte',  type=int, default=0)
    args = parser.parse_args()

    traces, plaintexts, ciphertexts, known_key, label = load_dataset(args.data)
    data       = plaintexts if args.round == 'first' else ciphertexts
    sbox_table = SBOX       if args.round == 'first' else INV_SBOX

    D, T = traces.shape
    print(f"Dataset      : {label}")
    print(f"Traces       : {D} × {T} samples")
    print(f"Attack round : {args.round}")
    print(f"Model        : HW( sbox[data[b] ⊕ j] )  — paper equation, no const\n")

    recovered = []
    print("Recovered round key: ", end="", flush=True)
    for b in range(16):
        pred, _ = attack_byte(traces, data, b, sbox_table)
        recovered.append(pred)
        print(f"{pred:02X} ", end="", flush=True)
    print()

    if known_key is not None:
        if args.round == 'last':
            from helper import extract_round_key
            rk = list(extract_round_key(bytes(known_key), 10))
        else:
            rk = list(known_key)

        match = recovered == rk
        print(f"Known key    : {' '.join(f'{b:02X}' for b in rk)}")
        print(f"Result       : {'CORRECT ✓' if match else 'WRONG ✗'}")

        if not match:
            wrong_bytes = [i for i in range(16) if recovered[i] != rk[i]]
            print(f"Wrong bytes  : {wrong_bytes}  "
                  f"(HW model mismatch — device uses HD leakage)")

        if args.round == 'last' and not match:
            # Try backward key schedule on what we got anyway
            try:
                orig = backward_key_schedule(bytes(recovered))
                print(f"Attempted key: {' '.join(f'{b:02X}' for b in orig)}")
            except Exception:
                pass

    # Plot for the requested byte
    b = args.plot_byte
    if known_key is not None:
        correct_j = rk[b]
    else:
        correct_j = recovered[b]

    print(f"\nGenerating plot for byte {b} (correct j=0x{correct_j:02X}) ...")
    _, r_matrix = attack_byte(traces, data, b, sbox_table)
    pdir = plots_dir(args.data)
    plot_cpa_paper(r_matrix, correct_j, b, label, pdir)
    print("Done.")


if __name__ == '__main__':
    main()
