"""
ascad_loader.py — ASCADv1 data loader for Hettwer DNN benchmarking.

Loads ASCAD.h5 (ATMega8518, first-order Boolean masking x⊕r), selects the
two leakage windows identified by Hettwer et al. 2020 Table I:

  [140:240] — mask register leakage (r_in)
  [450:550] — masked S-Box output  (SBOX[pt⊕k] ⊕ r)

Concatenated → 200-sample segment per trace.  Cross-window GASF/GADF pixels
implicitly capture the second-order interaction between mask and masked value,
allowing the CNN to recover the unmasked intermediate without explicit
second-order pre-processing.

Labels use the *unmasked* target: SBOX[pt[:,byte] ⊕ k[:,byte]]
(256 classes), which is the correct label even though the mask is present,
because the network learns to suppress the mask through the image structure.

Reference
─────────
  Hettwer et al. "Encoding Power Traces as Images…" HOST 2020 / arXiv:2004.11015
  ASCAD: Benadjila et al. 2019  https://github.com/ANSSI-FR/ASCAD
"""

import os
import sys

import h5py
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from helper import SBOX

# ── Leakage window positions (Hettwer et al. Table I) ─────────────────────────
MASK_WIN = slice(140, 240)   # 100 samples — mask (r_in) leakage
SBOX_WIN = slice(450, 550)   # 100 samples — masked S-Box output leakage


def load_ascad(h5_path: str,
               target_byte: int = 2,
               n_prof: int | None = None,
               n_atk:  int | None = None):
    """
    Load ASCADv1 and return windowed traces with unmasked labels.

    Parameters
    ----------
    h5_path     : absolute path to ASCAD.h5
    target_byte : AES key byte index (paper default = 2, the third byte)
    n_prof      : cap on profiling traces (None → all 50 000)
    n_atk       : cap on attack traces    (None → all 10 000)

    Returns
    -------
    X_prof           : (N_prof, 200) float32  windowed profiling traces
    y_prof           : (N_prof,)    uint8     unmasked SBOX labels
    X_atk            : (N_atk,  200) float32  windowed attack traces
    y_atk            : (N_atk,)    uint8     unmasked SBOX labels
    correct_key_byte : int                   true key byte value (fixed in ASCAD)
    pt_atk           : (N_atk, 16) uint8     attack plaintexts for GE scoring
    """
    if not os.path.isfile(h5_path):
        raise FileNotFoundError(f"ASCAD.h5 not found: {h5_path}")

    print(f"  Loading ASCAD.h5 from {h5_path} ...")
    with h5py.File(h5_path, 'r') as f:
        prof_traces = np.array(f['Profiling_traces/traces'],   dtype=np.float32)
        prof_meta   = f['Profiling_traces/metadata']
        prof_pt     = np.array(prof_meta['plaintext'], dtype=np.uint8)
        prof_key    = np.array(prof_meta['key'],       dtype=np.uint8)

        atk_traces  = np.array(f['Attack_traces/traces'],    dtype=np.float32)
        atk_meta    = f['Attack_traces/metadata']
        atk_pt      = np.array(atk_meta['plaintext'], dtype=np.uint8)
        atk_key     = np.array(atk_meta['key'],       dtype=np.uint8)

    # In ASCADv1 the key is fixed; grab it from the first profiling trace
    correct_key_byte = int(prof_key[0, target_byte])

    # Concatenate leakage windows → 200-sample segment
    X_prof = _concat_windows(prof_traces)
    X_atk  = _concat_windows(atk_traces)

    if n_prof is not None:
        X_prof  = X_prof[:n_prof]
        prof_pt = prof_pt[:n_prof]
        prof_key= prof_key[:n_prof]
    if n_atk is not None:
        X_atk  = X_atk[:n_atk]
        atk_pt = atk_pt[:n_atk]
        atk_key= atk_key[:n_atk]

    y_prof = _label(prof_pt, prof_key, target_byte)
    y_atk  = _label(atk_pt,  atk_key,  target_byte)

    print(f"  Profiling : {len(X_prof):,} traces  Attack : {len(X_atk):,} traces")
    print(f"  Target byte {target_byte}  correct key byte 0x{correct_key_byte:02X}")
    print(f"  Window : [{MASK_WIN.start}:{MASK_WIN.stop}] ++ [{SBOX_WIN.start}:{SBOX_WIN.stop}]"
          f"  → {X_prof.shape[1]} samples/trace")

    return X_prof, y_prof, X_atk, y_atk, correct_key_byte, atk_pt


def _concat_windows(traces: np.ndarray) -> np.ndarray:
    """(N, 700) → (N, 200) by concatenating the two leakage windows."""
    return np.concatenate([traces[:, MASK_WIN], traces[:, SBOX_WIN]], axis=1)


def _label(pt: np.ndarray, key: np.ndarray, byte: int) -> np.ndarray:
    """Unmasked label: SBOX[pt[b] ⊕ k[b]] — 256 distinct values."""
    return SBOX[pt[:, byte].astype(np.int32) ^ key[:, byte].astype(np.int32)].astype(np.uint8)
