"""
guessing_entropy.py — GE(N) curves for DPA and CPA.

GE(N) = average rank of the correct key byte when the attack uses N traces,
        averaged over n_trials random subsamples.  GE=1 means full convergence.

Usage
-----
  python attacks/classical/guessing_entropy.py \\
      --data data/set_002_reference --byte 0 --trials 20 --steps 20
"""

import argparse
import os
import sys

import numpy as np
import matplotlib.pyplot as plt

try:
    from tqdm import tqdm as _tqdm
except ImportError:
    def _tqdm(iterable, **kw):
        desc  = kw.get('desc', '')
        total = kw.get('total', None) or len(iterable)
        for i, item in enumerate(iterable, 1):
            print(f"\r  {desc}: {i}/{total}", end='', flush=True)
            yield item
        print()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from helper import (
    SBOX, INV_SBOX,
    extract_round_key,
    key_rank,
    load_dataset, plots_dir,
    apply_dark_style, STYLE,
)
from classical.cpa import cpa_byte, _precompute_trace_stats
from classical.dpa import dpa_byte

# ── GE functions ──────────────────────────────────────────────────────────────

def ge_cpa(traces, data, target_byte, sbox_table, correct_rk_byte,
           n_traces_list, n_trials=20, rng=None, const=0):
    """GE(N) curve for CPA. const=0 → HW model; const=2 → HD model (this device)."""
    rng     = rng or np.random.default_rng(42)
    N_total = len(traces)
    ge      = np.zeros(len(n_traces_list))
    bar     = _tqdm(enumerate(n_traces_list), total=len(n_traces_list),
                    desc=f'CPA GE (const={const})', unit='pt', ncols=80, leave=True)
    for k, N in bar:
        ranks = []
        for _ in range(n_trials):
            idx = rng.choice(N_total, size=int(N), replace=False)
            t_c, s_t_sq = _precompute_trace_stats(traces[idx])
            scores = cpa_byte(data[idx], target_byte, sbox_table, t_c, s_t_sq, const=const)
            ranks.append(key_rank(scores, correct_rk_byte))
        ge[k] = float(np.mean(ranks))
        if hasattr(bar, 'set_postfix'):
            bar.set_postfix(N=int(N), GE=f'{ge[k]:.1f}')
    return ge


def ge_dpa(traces, data, target_byte, sbox_table, correct_rk_byte,
           n_traces_list, n_trials=20, rng=None):
    """GE(N) curve for DPA (best score across all 8 bit positions)."""
    rng     = rng or np.random.default_rng(42)
    N_total = len(traces)
    ge      = np.zeros(len(n_traces_list))
    bar     = _tqdm(enumerate(n_traces_list), total=len(n_traces_list),
                    desc='DPA GE', unit='pt', ncols=80, leave=True)
    for k, N in bar:
        ranks = []
        for _ in range(n_trials):
            idx = rng.choice(N_total, size=int(N), replace=False)
            best_scores = None
            for bit in range(8):
                scores = dpa_byte(traces[idx], data[idx], target_byte, sbox_table, bit)
                if best_scores is None or scores.max() > best_scores.max():
                    best_scores = scores
            ranks.append(key_rank(best_scores, correct_rk_byte))
        ge[k] = float(np.mean(ranks))
        if hasattr(bar, 'set_postfix'):
            bar.set_postfix(N=int(N), GE=f'{ge[k]:.1f}')
    return ge


def trace_complexity(ge_curve, n_traces_list, threshold=1.5):
    for N, ge in zip(n_traces_list, ge_curve):
        if ge <= threshold:
            return int(N)
    return None

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Guessing Entropy: DPA vs CPA')
    ap.add_argument('--data',   required=True,  help='Dataset directory')
    ap.add_argument('--byte',   type=int, default=0)
    ap.add_argument('--round',  choices=['first', 'last'], default='last')
    ap.add_argument('--trials', type=int, default=20)
    ap.add_argument('--steps',  type=int, default=20)
    ap.add_argument('--const',  type=int, default=None,
                    help='CPA leakage const (0=HW model). If omitted, runs both 0 and 2.')
    args = ap.parse_args()

    traces, plaintexts, ciphertexts, known_key, label = load_dataset(args.data)
    N_total = len(traces)
    print(f"Dataset      : {label}  ({N_total} traces)")

    if known_key is None:
        print("ERROR: meta.json must contain 'key'.")
        sys.exit(1)

    if args.round == 'last':
        rk         = extract_round_key(bytes(known_key), 10)
        sbox_table = INV_SBOX
        data       = ciphertexts
    else:
        rk         = known_key
        sbox_table = SBOX
        data       = plaintexts

    correct_rk_byte = int(rk[args.byte])
    print(f"Target byte  : {args.byte}  correct = 0x{correct_rk_byte:02X}")

    n_min = max(10, N_total // args.steps)
    ns    = np.unique(np.linspace(n_min, N_total, args.steps, dtype=int)).tolist()
    rng   = np.random.default_rng(42)

    # Decide which const values to run
    consts = [args.const] if args.const is not None else [0, 2]

    print(f"\n{args.trials} trials × {len(ns)} points each")
    cpa_results = {}
    for c in consts:
        cpa_results[c] = ge_cpa(traces, data, args.byte, sbox_table,
                                correct_rk_byte, ns, args.trials, rng, const=c)
    ge_dpa_vals = ge_dpa(traces, data, args.byte, sbox_table,
                         correct_rk_byte, ns, args.trials, rng)

    # ── Table ─────────────────────────────────────────────────────────────────
    cpa_headers = '  '.join(f'CPA(c={c})' for c in consts)
    print(f"\n{'N':>8}  {cpa_headers}  {'GE_DPA':>8}")
    print("-" * (8 + 12 * len(consts) + 10))
    for k, N in enumerate(ns):
        cpa_cols = '  '.join(f"{cpa_results[c][k]:>9.2f}" for c in consts)
        print(f"{N:>8}  {cpa_cols}  {ge_dpa_vals[k]:>8.2f}")

    print(f"\nTrace complexity (GE ≤ 1.5):")
    for c in consts:
        tc = trace_complexity(cpa_results[c], ns)
        model = 'HW' if c == 0 else f'HD(const={c})'
        print(f"  CPA {model}: {tc or f'>{ns[-1]}'} traces")
    tc_dpa = trace_complexity(ge_dpa_vals, ns)
    print(f"  DPA        : {tc_dpa or f'>{ns[-1]}'} traces")

    # ── Plot ──────────────────────────────────────────────────────────────────
    out = plots_dir(args.data)
    fig, ax = plt.subplots(figsize=(10, 5))
    apply_dark_style(fig, ax)

    cpa_colors = [STYLE['correct'], STYLE['neutral']]
    cpa_markers = ['o', '^']
    for i, c in enumerate(consts):
        model = 'HW model' if c == 0 else f'HD model (const={c})'
        ax.plot(ns, cpa_results[c], color=cpa_colors[i % 2], lw=2,
                marker=cpa_markers[i], markersize=4, label=f'CPA — {model}')

    ax.plot(ns, ge_dpa_vals, color=STYLE['wrong'], lw=2,
            marker='s', markersize=4, label='DPA (model-free)')
    ax.axhline(1.5, color='white', ls='--', lw=0.8, alpha=0.5, label='GE = 1.5')
    ax.set_xlabel('Number of Traces (N)')
    ax.set_ylabel('Guessing Entropy')
    ax.set_title(f'Guessing Entropy — HW vs HD vs DPA | byte {args.byte} | {label}',
                 color=STYLE['text'])
    ax.legend(facecolor=STYLE['bg'], labelcolor=STYLE['text'])
    ax.set_ylim(bottom=0)
    plt.tight_layout()
    path = os.path.join(out, f'ge_comparison_b{args.byte:02d}.png')
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=STYLE['bg'])
    print(f"\nPlot saved: {path}")


if __name__ == '__main__':
    main()
