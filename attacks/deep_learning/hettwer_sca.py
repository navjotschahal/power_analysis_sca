"""
hettwer_sca.py — Exact CNN from Hettwer et al., HOST 2020.

Paper: "Encoding Power Traces as Images for Efficient Side-Channel Analysis"
       Benjamin Hettwer, Tobias Horn, Stefan Gehrer, Tim Güneysu
       IEEE HOST 2020 | arXiv:2004.11015

Architecture (Table II — reproduced exactly)
─────────────────────────────────────────────
  Conv2D(8,  5×5, L2=0.01) → BN → ReLU → MaxPool(2×2, stride=2) → Dropout(0.5)
  Conv2D(16, 3×3, L2=0.01) → BN → ReLU → MaxPool(2×2, stride=2) → Dropout(0.5)
  Flatten
  Dense(250, ReLU) → BN → Dropout(0.3)
  Dense(256, Softmax)   ← 256 key-byte classes

Training setup (Section V-A)
─────────────────────────────
  Optimizer : Adam, lr=0.0002
  Loss      : categorical cross-entropy
  Early stop: patience=20 (val loss)
  Checkpoint: save best val loss weights

Channel combinations tested in paper (Section V-D & V-E)
─────────────────────────────────────────────────────────
  Single  : GASF | GADF | MTF | RP          (1 channel)
  Combined: GASF+GADF | GASF+RP             (2 channels, stacked on z-axis)
  Best result across all datasets: GASF+GADF

Usage
─────
  # Train on custom dataset (GASF+GADF, paper's best combo)
  python attacks/deep_learning/hettwer_sca.py \\
      --data data/set_003_arduino_uno --round first --channels gasf+gadf --byte 0

  # Train on ASCADv1 (benchmark — paper's exact dataset)
  python attacks/deep_learning/hettwer_sca.py \\
      --ascad-h5 /path/to/ASCAD.h5 --channels gasf+gadf

  # ASCADv1 with limited traces (quick smoke test)
  python attacks/deep_learning/hettwer_sca.py \\
      --ascad-h5 /path/to/ASCAD.h5 --ascad-n-prof 5000 --ascad-n-atk 2000

  # Skip training, run GE attack with saved checkpoint
  python attacks/deep_learning/hettwer_sca.py \\
      --data data/set_003_arduino_uno --round first --attack-only \\
      --ckpt data/set_003_arduino_uno/plots/hettwer_gasf+gadf_b00.keras
"""

import argparse
import os
import sys

import h5py
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
from tqdm import tqdm

_kl = tf.keras.layers
_km = tf.keras.models

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from helper import (
    SBOX, INV_SBOX,
    extract_round_key,
    key_rank,
    load_dataset, plots_dir,
    apply_dark_style, STYLE,
)
from deep_learning.device import print_device
from deep_learning.image_encode import encode_multichannel

CHANNEL_PRESETS = {
    'gasf':      [0],
    'gadf':      [1],
    'rp':        [2],
    'mtf':       [3],
    'gasf+gadf': [0, 1],   # paper's best combination
    'gasf+rp':   [0, 2],
    'all':       [0, 1, 2, 3],
}


# ── Image cache ────────────────────────────────────────────────────────────────

def load_or_encode(traces: np.ndarray, data_dir: str, image_size: int,
                   batch_size: int = 500,
                   cache_stem: str = 'images') -> np.ndarray:
    """
    Return (N, S, S, 4) all-channel image tensor.
    Encodes on first run and caches to data_dir/{cache_stem}_S{S}.h5.
    Subsequent runs load from cache — skips re-encoding.
    cache_stem lets ASCAD prof/atk splits share the same data_dir without collision.
    """
    cache_path = os.path.join(data_dir, f'{cache_stem}_S{image_size}.h5')
    N = len(traces)

    if os.path.exists(cache_path):
        with h5py.File(cache_path, 'r') as f:
            if (int(f.attrs.get('image_size', 0)) == image_size and
                    int(f.attrs.get('n_traces',   0)) == N):
                imgs = np.empty((N, image_size, image_size, 4), dtype=np.float32)
                with tqdm(total=N, desc='  Loading cache', unit='img', ncols=72) as pbar:
                    for start in range(0, N, 1000):
                        end = min(start + 1000, N)
                        imgs[start:end] = f['images'][start:end]
                        pbar.update(end - start)
                print(f"  Skipped encoding — loaded from {os.path.basename(cache_path)}")
                return imgs

    imgs = np.empty((N, image_size, image_size, 4), dtype=np.float32)
    with tqdm(total=N, desc='  Encoding traces', unit='trace', ncols=72) as pbar:
        for start in range(0, N, batch_size):
            end = min(start + batch_size, N)
            imgs[start:end] = encode_multichannel(
                traces[start:end].astype(np.float32), image_size=image_size)
            pbar.update(end - start)

    with h5py.File(cache_path, 'w') as f:
        f.attrs['image_size'] = image_size
        f.attrs['n_traces']   = N
        f.create_dataset('images', data=imgs, compression='gzip', compression_opts=4)
    print(f"  Saved image cache → {cache_path}")
    return imgs


# ── Paper architecture (Table II) ─────────────────────────────────────────────

def build_hettwer_model(image_size: int, n_channels: int) -> _km.Model:
    """
    Exact Table II architecture — input (S, S, C), output (256,) softmax.
    """
    reg    = tf.keras.regularizers.l2(0.01)
    inputs = _kl.Input(shape=(image_size, image_size, n_channels), name='image_input')

    # Block 1: Conv(8, 5×5) → BN → ReLU → MaxPool(2×2) → Dropout(0.5)
    x = _kl.Conv2D(8,  kernel_size=5, padding='same', kernel_regularizer=reg, name='conv1')(inputs)
    x = _kl.BatchNormalization(name='bn1')(x)
    x = _kl.Activation('relu', name='relu1')(x)
    x = _kl.MaxPooling2D(pool_size=2, strides=2, name='pool1')(x)
    x = _kl.Dropout(0.5, name='drop1')(x)

    # Block 2: Conv(16, 3×3) → BN → ReLU → MaxPool(2×2) → Dropout(0.5)
    x = _kl.Conv2D(16, kernel_size=3, padding='same', kernel_regularizer=reg, name='conv2')(x)
    x = _kl.BatchNormalization(name='bn2')(x)
    x = _kl.Activation('relu', name='relu2')(x)
    x = _kl.MaxPooling2D(pool_size=2, strides=2, name='pool2')(x)
    x = _kl.Dropout(0.5, name='drop2')(x)

    # Classifier: Flatten → Dense(250) → BN → Dropout(0.3) → Dense(256, softmax)
    x = _kl.Flatten(name='flatten')(x)
    x = _kl.Dense(250, activation='relu', name='fc1')(x)
    x = _kl.BatchNormalization(name='bn3')(x)
    x = _kl.Dropout(0.3, name='drop3')(x)
    x = _kl.Dense(256, activation='softmax', name='sbox_output')(x)

    model = _km.Model(inputs, x, name='HettwertCNN_2020')
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.0002),
        loss='categorical_crossentropy',
        metrics=['accuracy'],
    )
    return model


def paper_callbacks(ckpt_path: str) -> list:
    """EarlyStopping patience=20 + ModelCheckpoint — exact Section V-A setup."""
    return [
        tf.keras.callbacks.EarlyStopping(
            monitor='val_loss', patience=20,
            restore_best_weights=True, verbose=1),
        tf.keras.callbacks.ModelCheckpoint(
            ckpt_path, monitor='val_loss',
            save_best_only=True, verbose=0),
    ]


# ── Data preparation ───────────────────────────────────────────────────────────

def prepare_data(imgs: np.ndarray, labels: np.ndarray,
                 channel_indices: list, val_frac: float = 0.10):
    """Select channels, one-hot encode labels, split train/val."""
    X = imgs[:, :, :, channel_indices]
    y = tf.keras.utils.to_categorical(labels, num_classes=256)
    N       = len(X)
    n_train = int(N * (1 - val_frac))
    idx     = np.random.permutation(N)
    tr, va  = idx[:n_train], idx[n_train:]
    return X[tr], y[tr], X[va], y[va]


# ── GE attack ─────────────────────────────────────────────────────────────────

def ge_attack(model, imgs: np.ndarray, test_data: np.ndarray,
              correct_key_byte: int, sbox_table,
              channel_indices: list,
              target_byte: int = 0,
              n_attack: int = 2000, n_trials: int = 10) -> np.ndarray:
    """
    Key Guessing Entropy — paper Section V-C.
    n_trials independent log-likelihood accumulations, mean key rank per N traces.
    """
    X_atk = imgs[:n_attack, :, :, channel_indices]

    print(f"  Predicting {len(X_atk)} attack traces ...")
    preds = model.predict(X_atk, verbose=0)   # (N, 256)

    ge  = np.zeros(n_attack)
    rng = np.random.default_rng(42)

    for _ in range(n_trials):
        perm   = rng.permutation(n_attack)
        scores = np.zeros(256)
        for i, idx in enumerate(perm):
            data_byte = int(test_data[idx, target_byte])
            for k in range(256):
                scores[k] += np.log(preds[idx, sbox_table[data_byte ^ k]] + 1e-36)
            ge[i] += key_rank(scores, correct_key_byte)

    ge /= n_trials
    return ge


# ── Plots ──────────────────────────────────────────────────────────────────────

def plot_training(hist, channels_label: str, out_path: str):
    h  = hist.history
    ep = range(1, len(h['loss']) + 1)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    apply_dark_style(fig, axes)

    axes[0].plot(ep, h['loss'],     color=STYLE['wrong'],   label='train')
    axes[0].plot(ep, h['val_loss'], color=STYLE['neutral'], label='val', ls='--')
    axes[0].set_title(f'Loss  [{channels_label}]')
    axes[0].set_xlabel('Epoch')
    axes[0].legend(facecolor=STYLE['bg'], labelcolor=STYLE['text'])

    axes[1].plot(ep, h['accuracy'],     color=STYLE['wrong'],   label='train')
    axes[1].plot(ep, h['val_accuracy'], color=STYLE['neutral'], label='val', ls='--')
    axes[1].set_title(f'Accuracy  [{channels_label}]')
    axes[1].set_xlabel('Epoch')
    axes[1].legend(facecolor=STYLE['bg'], labelcolor=STYLE['text'])

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=STYLE['bg'])
    plt.close(fig)
    print(f"  Saved training plot → {out_path}")


def plot_ge(ge: np.ndarray, channels_label: str, out_path: str):
    fig, ax = plt.subplots(figsize=(9, 5))
    apply_dark_style(fig, ax)

    ax.plot(range(1, len(ge) + 1), ge, color=STYLE['correct'], lw=2)
    ax.axhline(1.0, color='white', ls='--', lw=0.8, alpha=0.5, label='KGE = 1')
    ax.set_xlabel('Number of attack traces')
    ax.set_ylabel('Key Guessing Entropy (KGE)')
    ax.set_title(f'KGE — Hettwer CNN [{channels_label}]  (Hettwer et al. 2020)',
                 color=STYLE['text'])
    ax.legend(facecolor=STYLE['bg'], labelcolor=STYLE['text'])
    ax.set_ylim(bottom=0)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=STYLE['bg'])
    plt.close(fig)
    print(f"  Saved KGE plot → {out_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description='Hettwer et al. HOST 2020 — Table II CNN on encoded images',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument('--data',        required=True,
                    help='Dataset directory (traces.npy / plaintexts.npy / meta.json)')
    ap.add_argument('--round',       choices=['first', 'last'], default='first',
                    help='AES round to attack')
    ap.add_argument('--byte',        type=int, default=0,
                    help='Key byte index to attack (0–15)')
    ap.add_argument('--channels',    default='gasf+gadf',
                    choices=list(CHANNEL_PRESETS.keys()),
                    help='Image channel combination')
    ap.add_argument('--image-size',  type=int, default=64,
                    help='S×S image size')
    ap.add_argument('--epochs',      type=int, default=200)
    ap.add_argument('--batch',       type=int, default=256)
    ap.add_argument('--n-attack',    type=int, default=2000)
    ap.add_argument('--trials',      type=int, default=10)
    ap.add_argument('--attack-only', action='store_true',
                    help='Skip training — load checkpoint and run GE attack only')
    ap.add_argument('--ckpt',        default=None,
                    help='Checkpoint path (required with --attack-only)')
    args = ap.parse_args()

    channel_indices = CHANNEL_PRESETS[args.channels]
    n_ch            = len(channel_indices)
    channels_label  = args.channels.upper()

    print_device()

    out_dir = plots_dir(args.data)
    print(f"Dataset    : {args.data}")
    print(f"Round      : {args.round}")
    print(f"Channels   : {channels_label}  ({n_ch} channel{'s' if n_ch > 1 else ''})")
    print(f"Image size : {args.image_size}×{args.image_size}")
    print(f"Target byte: {args.byte}\n")

    # ── Load raw traces ────────────────────────────────────────────────────────
    traces, plaintexts, ciphertexts, known_key, _ = load_dataset(args.data)

    if args.round == 'last':
        sbox_table = INV_SBOX
        data       = ciphertexts
        rk         = list(extract_round_key(bytes(known_key), 10))
    else:
        sbox_table = SBOX
        data       = plaintexts
        rk         = list(known_key)

    correct_key_byte = rk[args.byte]
    print(f"Correct key byte : 0x{correct_key_byte:02X}")

    labels = np.array([sbox_table[int(data[i, args.byte]) ^ correct_key_byte]
                       for i in range(len(traces))], dtype=np.uint8)

    # ── Encode traces → images (cached) ───────────────────────────────────────
    print("\n--- Image encoding ---")
    imgs = load_or_encode(traces, args.data, args.image_size)

    ckpt_path = os.path.join(out_dir, f'hettwer_{args.channels}_b{args.byte:02d}.keras')

    # ── Train ─────────────────────────────────────────────────────────────────
    if args.attack_only:
        if args.ckpt is None:
            print("[ERROR] --attack-only requires --ckpt"); return
        print(f"Loading model from {args.ckpt} ...")
        model = tf.keras.models.load_model(args.ckpt)
    else:
        print("\n--- Preparing data ---")
        X_tr, y_tr, X_va, y_va = prepare_data(imgs, labels, channel_indices)
        print(f"  train={len(X_tr):,}  val={len(X_va):,}")

        print(f"\n--- Building Hettwer CNN ({args.image_size}×{args.image_size}×{n_ch}) ---")
        model = build_hettwer_model(args.image_size, n_ch)
        n_params = sum(np.prod(v.shape) for v in model.trainable_variables)
        print(f"  Trainable parameters: {n_params:,}")

        print(f"\n--- Training (max {args.epochs} epochs, early stop patience=20) ---")
        hist = model.fit(X_tr, y_tr,
                         validation_data=(X_va, y_va),
                         epochs=args.epochs,
                         batch_size=args.batch,
                         callbacks=paper_callbacks(ckpt_path),
                         verbose=1)
        plot_training(hist, channels_label,
                      os.path.join(out_dir, f'hettwer_{args.channels}_training_b{args.byte:02d}.png'))

    # ── GE attack ──────────────────────────────────────────────────────────────
    print(f"\n--- GE Attack ({args.n_attack} traces, {args.trials} trials) ---")
    ge = ge_attack(model, imgs, data, correct_key_byte, sbox_table,
                   channel_indices,
                   target_byte=args.byte,
                   n_attack=min(args.n_attack, len(traces)),
                   n_trials=args.trials)

    converge_n = next((i + 1 for i, v in enumerate(ge) if v <= 1.5), None)
    print(f"  Converged at N = {converge_n or f'>{args.n_attack}'} traces  (KGE ≤ 1.5)")
    print(f"  Final KGE      = {ge[-1]:.2f}")

    plot_ge(ge, channels_label,
            os.path.join(out_dir, f'hettwer_{args.channels}_ge_b{args.byte:02d}.png'))

    print(f"\nDone. Results in {out_dir}/")


if __name__ == '__main__':
    main()
