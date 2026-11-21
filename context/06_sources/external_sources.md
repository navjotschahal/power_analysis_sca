## External Sources — Downloaded Material (not committed)

Everything in this file was downloaded or cloned from a public link and is **gitignored**.
The repository records *where it came from and how to restore it* instead of the bytes.
Paths are relative to the repository root.

Last audited: 2026-11-20.

---

### 1. Cloned repositories

| Local path | Upstream | Pinned version | Size | Used for |
|---|---|---|---|---|
| `pico-sdk/` | https://github.com/raspberrypi/pico-sdk | tag `2.2.0` (`a1438df`) | 638 MB | Building `firmwares/picow/` (RP2040 target) |
| `references/dpa-on-aes/` | https://github.com/nvietsang/dpa-on-aes | commit `01dca64` | 811 MB | Tutorial notebook + 2000 raw traces → source of `data/set_002_reference/` |
| `data/ascad2/ASCAD_repo/` | https://github.com/ANSSI-FR/ASCAD | commit `5d00863` | 0.6 MB | ASCAD v1/v2 loaders and dataset documentation |

`pico-sdk` submodules in use: btstack v1.6.2, cyw43-driver v1.1.0, lwip 2.2.1, mbedtls v3.6.2, tinyusb 0.18.0.

Restore:

```bash
git clone --branch 2.2.0 --depth 1 https://github.com/raspberrypi/pico-sdk.git pico-sdk
git -C pico-sdk submodule update --init

git clone https://github.com/nvietsang/dpa-on-aes.git references/dpa-on-aes
git -C references/dpa-on-aes checkout 01dca64

git clone https://github.com/ANSSI-FR/ASCAD.git data/ascad2/ASCAD_repo
git -C data/ascad2/ASCAD_repo checkout 5d00863
```

---

### 2. Downloaded datasets

| Local path | Source | Size | SHA-1 (local copy) |
|---|---|---|---|
| `data/ascad2/ascadv2-extracted.h5` | https://files.data.gouv.fr/anssi/ascadv2/ascadv2-extracted.h5 | 7.7 GB | `8de295c8c18d033b13c03474189c0976a49ca993` |

- Official checksum list: https://files.data.gouv.fr/anssi/ascadv2/sha1.txt
- Dataset paper: https://eprint.iacr.org/2021/592
- Target firmware: https://github.com/ANSSI-FR/SecAESSTM32
- Dataset parameters are recorded in `data/ascad2/meta.json`.

Restore:

```bash
curl -L -o data/ascad2/ascadv2-extracted.h5 https://files.data.gouv.fr/anssi/ascadv2/ascadv2-extracted.h5
shasum -a 1 data/ascad2/ascadv2-extracted.h5   # compare with the table above
```

---

### 3. Downloaded papers and notebooks

| Local path | Work | Link |
|---|---|---|
| `references/power_trace_image_encoding_dnn_sca.pdf` | Hettwer, Horn, Gehrer, Güneysu — "Encoding Power Traces as Images for Efficient Side-Channel Analysis", IEEE HOST 2020 | https://arxiv.org/abs/2004.11015 |
| `references/NCCGroup_ML104_blog.ipynb` | Eric Schorn (NCC Group) — "Machine Learning 104: Breaking AES With Power Side-Channels", June 2023 | Blog: https://www.nccgroup.com/research/machine-learning-104-breaking-aes-with-power-side-channels/ · Notebook: https://nccgroup.github.io/ataraxy/ml104/NCCGroup_ML104_blog.html |

Papers cited only as links (not stored locally) are in [key_references.md](key_references.md) and `report/references.bib`.

---

### 4. Derived data (regenerable, not downloaded)

| Local path | Derived from | Size | How it is produced |
|---|---|---|---|
| `data/set_002_reference/` | `references/dpa-on-aes/traces/` | 309 MB | Per-trace `.txt` converted to `.npy` (see its `meta.json`); `plots/` holds `.keras` checkpoints |
| `data/ascad2/ascadv2_images_S32.h5` | `data/ascad2/ascadv2-extracted.h5` | 4.9 GB | Image encoding at size 32 by the ASCAD2 pipeline (see note below) |

> **Note:** the scripts that produced the ASCAD2 images and ResNet models
> (`ascad2_sca.py`, `image_sca.py`, `resnet_sca.py`, `resnet_body.py`, `cnn_attack.py`)
> exist only as `.pyc` files in `__pycache__/`. Their `.py` sources are missing from disk and from git.

---

### 5. Own captured data (hosted externally)

The `data/set_0NN_*` folders are our own oscilloscope captures. They are gitignored because
of size. The 50 000-trace Pro Trinket dataset is shared here:

- Google Drive: https://drive.google.com/file/d/1Itl82UCQEDyk6cYDD33kB-gKtlXIQBZe/view?usp=sharing

Schema for every set: `data/DATA_FORMAT.md`.

---

### Adding a new external source

1. Put it under `references/` (papers, repos) or `data/` (datasets). Both are gitignored.
2. Add one row to the matching table above: local path, link, version or checksum, size.
3. Add a restore command if it is more than a single download.
