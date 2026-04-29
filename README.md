# DATA https://drive.google.com/file/d/1Itl82UCQEDyk6cYDD33kB-gKtlXIQBZe/view?usp=sharing


# pico_aes_attack — MCU Firmware & Acquisition

Side-Channel Analysis (SCA) test bench targeting AES-128 on the Raspberry Pi Pico (RP2040, ARM Cortex-M0+).

---

## Hardware Requirements

- Raspberry Pi Pico (RP2040)
- Oscilloscope with external trigger input
- Power/EM probe positioned over the RP2040 VDD pin or decoupling capacitor
- **GPIO 22 must be physically wired to the oscilloscope's trigger channel (rising edge)**

---

## Repository Structure

```
power_analysis_sca/
├── firmware/
│   ├── main.c          — RP2040 target firmware
│   └── CMakeLists.txt  — Pico SDK build config
├── test_uart/
│   ├── main.cpp        — UART/USB connectivity test firmware
│   └── CMakeLists.txt  — Pico SDK build config
└── capture.py          — Host-side serial acquisition script
```

---

Install the Prerequisites

You need the compiler for the ARM Cortex-M0+ and the build tools.
Open your terminal and install the following:

Ubuntu/Debian/WSL:

Bash
sudo apt update
sudo apt install cmake gcc-arm-none-eabi libnewlib-arm-none-eabi build-essential git python3
macOS (using Homebrew):

Bash
brew install cmake arm-none-eabi-gcc

Download the Pico SDK

You need the official Raspberry Pi libraries (which include the mbedtls crypto library we are using).

Clone the SDK repository and its submodules to your computer:

Bash
git clone -b master https://github.com/raspberrypi/pico-sdk.git
cd pico-sdk
git submodule update --init
Tell your system where the SDK is located by setting an environment variable:

```bash
export PICO_SDK_PATH=/path/to/pico-sdk
```

## 1. Firmware

### Build

```bash
export PICO_SDK_PATH=/path/to/pico-sdk

mkdir -p firmware/build && cd firmware/build
cmake -DPICO_BOARD=pico_w ..
make -j4
```

Flash `pico_aes_attack.uf2` to the Pico via USB mass storage (hold BOOTSEL on power-up).

### Communication Interface

The Pico supports two interfaces that can be enabled independently or simultaneously:

| Interface | Pico pins | Host port |
|---|---|---|
| USB CDC | native USB | `/dev/tty.usbmodem*` |
| UART | GP0 (TX), GP1 (RX) | `/dev/tty.usbserial-*` |

UART wiring (USB-to-UART adapter):
```
Pico GP0 (TX) --> Adapter RX
Pico GP1 (RX) --> Adapter TX
Pico GND      --> Adapter GND
```

Both the AES firmware (`firmware/`) and the test firmware (`test_uart/`) support the same cmake flags (both ON by default):

```bash
cmake -DPICO_BOARD=pico_w -DUSE_USB=ON -DUSE_UART=ON  ..   # both (default)
cmake -DPICO_BOARD=pico_w -DUSE_USB=ON -DUSE_UART=OFF ..   # USB only
cmake -DPICO_BOARD=pico_w -DUSE_USB=OFF -DUSE_UART=ON ..   # UART only
```

> **Note:** The interface flags must match between firmware and `capture.py --port`. If the firmware is built with `USE_UART=OFF`, `--port uart` will time out waiting for a response.

### Behaviour

- Waits for 16 bytes of plaintext over USB serial (115200 baud)
- Pulls GPIO 22 HIGH immediately before `AES_ECB_encrypt`
- Pulls GPIO 22 LOW immediately after
- Returns 16 bytes of ciphertext

### Secret Key (hardcoded for profiling)

```
00 11 22 33 44 55 66 77 88 99 AA BB CC DD EE FF
```

---

## 2. Data Acquisition

### Dependencies

```bash
pip install pyserial pyvisa pyvisa-py numpy tqdm
```

### Run

```bash
# Use USB CDC (default)
python capture.py --port usb

# Use USB-to-UART adapter
python capture.py --port uart
```

Update `USB_PORT` and `UART_PORT` at the top of `capture.py` to match your system's device paths (`ls /dev/tty.usb*` to find them).

### Output

| File | Contents |
|---|---|
| `plaintexts.npy` | `(N, 16)` uint8 — random plaintexts sent to device |
| `ciphertexts.npy` | `(N, 16)` uint8 — ciphertexts returned by device |
| `traces.npy` | `(N, 5000)` uint8 — raw oscilloscope waveforms |

### Configuration

Edit the constants at the top of `capture.py`:

```python
NUM_TRACES   = 100
USB_PORT     = '/dev/tty.usbmodem2101'    # Pico USB CDC
UART_PORT    = '/dev/tty.usbserial-0001'  # USB-to-UART adapter
SCOPE_ADDRESS = 'USB0::0x2A8D::...'       # pyvisa resource string
```
