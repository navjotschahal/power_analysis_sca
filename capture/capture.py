"""
capture.py — Unified SCA capture script for all boards.

All firmwares in this project share the same 16-byte protocol:
  host -> board  : 16-byte random plaintext (UART, 115200 baud)
  board -> scope : trigger pulse on GPIO
  board -> host  : 16-byte ciphertext (UART)

Data is saved to data/set_<NNN>_<board>/ (auto-numbered) with:
  traces.npy, plaintexts.npy, ciphertexts.npy, meta.json

Oscilloscope connection
───────────────────────
  USB (default):
    --scope-address 'USB0::0x2A8D::0x17B6::MY65060127::INSTR'

  Ethernet — three protocol options (all use pyvisa-py, no extra drivers):
    HiSLIP  (fastest, recommended for Keysight):
      --scope-ip 192.168.1.100
      --scope-ip 192.168.1.100 --scope-protocol hislip

    VXI-11  (classic LAN instrument standard, widest compatibility):
      --scope-ip 192.168.1.100 --scope-protocol vxi11

    Raw socket (port 5025, lowest overhead):
      --scope-ip 192.168.1.100 --scope-protocol socket

  Find the scope IP: on the scope front panel →
    [Utility] → I/O → LAN Settings → IP Address

Examples
────────
  # Adafruit Pro Trinket via USB scope
  python capture.py --board trinket_5v --port /dev/tty.usbserial-0001

  # Raspberry Pi Pico, scope over Ethernet (HiSLIP)
  python capture.py --board pico --port /dev/tty.usbmodem101 \\
                    --scope-ip 192.168.1.100 --num-traces 5000

  # Trinket, scope over Ethernet (VXI-11)
  python capture.py --board trinket_5v --port /dev/tty.usbserial-0001 \\
                    --scope-ip 192.168.1.100 --scope-protocol vxi11

  # Override output directory
  python capture.py --board trinket_r1_baremetal --port /dev/tty.usbserial-0001 \\
                    --out-dir data/set_005_trinket_bare_r1 --num-traces 10000

  # Adjust scope points and serial delay (boards that reset on DTR)
  python capture.py --board uno_r4 --port /dev/tty.usbmodem101 \\
                    --serial-delay 2 --scope-points 10000
"""

import argparse
import glob
import json
import os
import re
import sys
import time

import numpy as np
import pyvisa
import serial
from tqdm import tqdm

# ── Fixed across all firmwares ─────────────────────────────────────────────────
AES_KEY = [0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6,
           0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c]

SCOPE_ADDRESS = 'USB0::0x2A8D::0x17B6::MY65060127::INSTR'
SCOPE_ADDRESS_ETH = 'TCPIP0::169.254.161.197::INSTR'   # link-local Ethernet (direct cable)

_PROTOCOL_TEMPLATES = {
    'hislip': 'TCPIP0::{ip}::hislip0::INSTR',
    'vxi11':  'TCPIP0::{ip}::INSTR',        # short form — matches scope's self-reported address
    'socket': 'TCPIP0::{ip}::5025::SOCKET',
}


def build_tcpip_address(ip: str, protocol: str) -> str:
    tmpl = _PROTOCOL_TEMPLATES.get(protocol)
    if tmpl is None:
        raise ValueError(f"Unknown protocol '{protocol}'. Choose: {list(_PROTOCOL_TEMPLATES)}")
    return tmpl.format(ip=ip)


# ── Auto-number next set directory ────────────────────────────────────────────
def next_set_dir(board: str) -> str:
    existing = glob.glob('data/set_*/') + glob.glob('data/set_*')
    nums = [
        int(m.group(1))
        for d in existing
        if (m := re.search(r'set_(\d+)', d))
    ]
    n = max(nums, default=0) + 1
    return f'data/set_{n:03d}_{board}'


# ── Serial helpers ─────────────────────────────────────────────────────────────
def open_serial(port: str, baud: int, delay: float) -> serial.Serial:
    s = serial.Serial(port, baud, timeout=2, exclusive=True)
    if delay > 0:
        time.sleep(delay)
    s.reset_input_buffer()
    return s


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description='Unified SCA capture — all boards',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument('--board',        required=True,
                    help='Short board label (used in directory name and meta.json). '
                         'Examples: trinket_5v, pico, atmega16u2, uno_r4')
    ap.add_argument('--port',         required=True,
                    help='Serial port. Find with: ls /dev/tty.usb*')
    ap.add_argument('--num-traces',   type=int, default=2000,
                    help='Number of traces to capture')
    ap.add_argument('--out-dir',      default=None,
                    help='Output directory. Auto-generated as data/set_NNN_<board> if omitted')
    ap.add_argument('--baud',         type=int, default=115200,
                    help='UART baud rate')
    ap.add_argument('--serial-delay', type=float, default=0.5,
                    help='Seconds to wait after opening serial port '
                         '(use 2.0 for boards that reset on DTR, e.g. UNO R4)')
    ap.add_argument('--scope-address', default=SCOPE_ADDRESS,
                    help='PyVISA resource string for the oscilloscope '
                         '(ignored when --scope-ip is given)')
    ap.add_argument('--scope-ip', default=None,
                    help='Scope IP address for Ethernet connection. '
                         'Constructs TCPIP VISA address automatically. '
                         'Find it: [Utility] → I/O → LAN Settings on the scope.')
    ap.add_argument('--scope-protocol', default='hislip',
                    choices=['hislip', 'vxi11', 'socket'],
                    help='Ethernet transport protocol (default: hislip). '
                         'hislip=fastest (Keysight), vxi11=widest compat, socket=raw port 5025')
    ap.add_argument('--scope-channel', default='CHANnel1',
                    help='Oscilloscope channel carrying the power trace')
    ap.add_argument('--scope-points',  type=int, default=5000,
                    help='Waveform points to download per trace')
    ap.add_argument('--notes',             default='',
                    help='Free-text notes written into meta.json')
    ap.add_argument('--skip-images', action='store_true',
                    help='Skip GASF/GADF/RP/MTF encoding after capture (encoding runs by default)')
    ap.add_argument('--no-plot',           action='store_true',
                    help='Skip overview plot generation after capture')
    args = ap.parse_args()

    out_dir = args.out_dir or next_set_dir(args.board)
    os.makedirs(out_dir, exist_ok=True)

    # Resolve scope VISA address: --scope-ip takes priority over --scope-address
    if args.scope_ip:
        scope_visa = build_tcpip_address(args.scope_ip, args.scope_protocol)
        scope_transport = f'ethernet/{args.scope_protocol}'
    else:
        scope_visa = args.scope_address
        scope_transport = 'usb'

    print(f"Board        : {args.board}")
    print(f"Port         : {args.port}  @{args.baud} baud")
    print(f"Traces       : {args.num_traces}")
    print(f"Scope points : {args.scope_points}")
    print(f"Scope VISA   : {scope_visa}")
    print(f"Output       : {out_dir}/\n")

    # ── Connect oscilloscope ───────────────────────────────────────────────────
    print("Connecting to oscilloscope ...")
    rm = pyvisa.ResourceManager('@py')
    try:
        scope = rm.open_resource(scope_visa)
        scope.timeout = 10000
        # Raw socket mode requires explicit line termination
        if args.scope_ip and args.scope_protocol == 'socket':
            scope.read_termination  = '\n'
            scope.write_termination = '\n'
        print(f"  {scope.query('*IDN?').strip()}\n")
    except Exception as e:
        print(f"  Failed: {e}")
        return

    scope.write(f':WAVeform:SOURce {args.scope_channel}')
    scope.write(':WAVeform:FORMat BYTE')
    scope.write(':WAVeform:POINts:MODE NORMal')
    scope.write(f':WAVeform:POINts {args.scope_points}')

    # ── Connect board ──────────────────────────────────────────────────────────
    print(f"Connecting to {args.board} on {args.port} ...")
    ser = open_serial(args.port, args.baud, args.serial_delay)
    print(f"  Ready.\n")

    traces      = []
    plaintexts  = []
    ciphertexts = []

    # ── Capture loop ───────────────────────────────────────────────────────────
    print(f"Capturing {args.num_traces} traces ...")
    try:
        for i in tqdm(range(args.num_traces)):
            while True:
                try:
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()

                    pt = os.urandom(16)

                    scope.write(':SINGle')
                    time.sleep(0.15)

                    ser.write(pt)
                    ser.flush()

                    ct = ser.read(16)
                    if len(ct) != 16:
                        raise ValueError(f"Expected 16 ciphertext bytes, got {len(ct)}")

                    scope.query('*OPC?')
                    waveform = scope.query_binary_values(
                        ':WAVeform:DATA?', datatype='B', container=np.array)

                    traces.append(waveform)
                    plaintexts.append(list(pt))
                    ciphertexts.append(list(ct))
                    break

                except serial.SerialException as e:
                    tqdm.write(f"\n[!] Serial error on trace {i}: {e} — reconnecting ...")
                    try:
                        ser.close()
                    except Exception:
                        pass
                    time.sleep(2)
                    ser = open_serial(args.port, args.baud, args.serial_delay)
                    tqdm.write("[+] Reconnected.")

                except Exception as e:
                    tqdm.write(f"\n[!] Trace {i} failed: {e} — retrying ...")
                    try:
                        scope.write('*CLS')
                    except Exception:
                        pass
                    time.sleep(1)
    finally:
        ser.close()

    if not traces:
        print("No traces captured.")
        return

    # ── Save dataset ───────────────────────────────────────────────────────────
    print("\nSaving dataset ...")
    t_arr = np.array(traces)
    np.save(os.path.join(out_dir, 'traces.npy'),      t_arr)
    np.save(os.path.join(out_dir, 'plaintexts.npy'),  np.array(plaintexts,  dtype=np.uint8))
    np.save(os.path.join(out_dir, 'ciphertexts.npy'), np.array(ciphertexts, dtype=np.uint8))

    meta = {
        'label':        out_dir.split('/')[-1],
        'key':          AES_KEY,
        'key_hex':      ''.join(f'{b:02x}' for b in AES_KEY),
        'device':       args.board,
        'N':            int(t_arr.shape[0]),
        'T':            int(t_arr.shape[1]),
        'snr':          None,
        'noise_level':  None,
        'notes':        (args.notes + f' | port={args.port} baud={args.baud}'
                         f' scope_points={args.scope_points}'
                         f' scope_transport={scope_transport}').strip(' |'),
    }
    with open(os.path.join(out_dir, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"Saved {len(traces)} traces → {out_dir}/")
    print(f"  traces.npy      {t_arr.shape}  {t_arr.dtype}")
    print(f"  plaintexts.npy  ({len(traces)}, 16)  uint8")
    print(f"  ciphertexts.npy ({len(traces)}, 16)  uint8")
    print(f"  meta.json       written")

    # ── Compute and save image encodings ──────────────────────────────────────
    if not args.skip_images:
        print("\nComputing image encodings (GASF / GADF / RP / MTF) ...")
        _attacks_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'attacks')
        if _attacks_dir not in sys.path:
            sys.path.insert(0, _attacks_dir)
        from deep_learning.hettwer_sca import load_or_encode  # type: ignore[import]
        load_or_encode(t_arr.astype(np.float32), out_dir, image_size=64)

    # ── Overview plot ──────────────────────────────────────────────────────────
    if not args.no_plot:
        print("\nGenerating overview plot ...")
        _root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root_dir not in sys.path:
            sys.path.insert(0, _root_dir)
        from plot_traces import plot_overview
        plot_overview(data_dir=out_dir, byte=0, round_name='first')


if __name__ == '__main__':
    main()
