"""
device.py — TensorFlow compute-device detection and configuration.
"""

import platform
import tensorflow as tf


def _configure() -> str:
    """
    Detect the best available device and configure it.
    Priority: CUDA GPU → Apple MPS (Metal) → CPU.

    CUDA:  enables memory_growth so TF allocates VRAM on demand.
    Metal: manages its own unified memory pool — set_memory_growth is unsupported.
    """
    gpus = tf.config.list_physical_devices('GPU')
    if gpus:
        is_metal = any('metal' in g.name.lower() or 'apple' in g.name.lower()
                       for g in gpus) or platform.system() == 'Darwin'
        if is_metal:
            return f"Apple MPS / Metal  ({len(gpus)} device)"
        for g in gpus:
            tf.config.experimental.set_memory_growth(g, True)
        return f"CUDA GPU  ({len(gpus)} device{'s' if len(gpus) > 1 else ''})"
    return "CPU"


ACTIVE_DEVICE = _configure()


def print_device():
    print(f"  [device] {ACTIVE_DEVICE}")
