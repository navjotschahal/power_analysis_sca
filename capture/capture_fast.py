"""
capture_fast.py — High-speed SCA capture via Keysight Segmented Memory.

Versus the one-by-one capture.py loop, this script arms the oscilloscope
ONCE per batch of N traces, blasts UART without any scope round-trips, then
downloads all N segments in a single sweep.
Typical throughput: 50–200 traces/second vs ~2.5/second.

SCPI flow per batch (N = --batch-size):
  Arm  :  :ACQuire:MODE SEGMented
           :ACQuire:SEGMented:COUNt N
           :RUN                             ← scope captures N segments, then auto-stops
  Blast:  send PT[0]…PT[N-1] over UART, read CT[0]…CT[N-1]
           (scope captures each trigger pulse → segment 1…N, no PC involvement)
  Fetch:  poll :RSTate? until STOP          ← avoids pyvisa-py HiSLIP *OPC? timeout bug
           for i in 1..N:
               :WAVeform:SEGMented:INDex i
               :WAVeform:DATA?              ← download segment i

Alignment guarantee
───────────────────
  ser.read(16) is blocking — PT[j+1] is not sent until CT[j] arrives.
  The firmware only sends CT after AES + trigger GPIO pulse.
  Therefore triggers fire strictly in order, and:
      plaintext[j]  ←→  ciphertext[j]  ←→  scope segment (j+1)  ✓

Output (identical schema to capture.py, compatible with all attack scripts):
  data/set_NNN_<board>/
      traces.npy          (N, T)   uint8   raw ADC values
      plaintexts.npy      (N, 16)  uint8
      ciphertexts.npy     (N, 16)  uint8
      meta.json

Usage examples:
  # USB scope, default 2000 traces in batches of 200
  python capture_fast.py --board trinket_5v --port /dev/tty.usbserial-0001

  # Ethernet (HiSLIP), 10 000 traces in batches of 500
  python capture_fast.py --board trinket_5v --port /dev/tty.usbserial-0001 \\
      --scope-ip 192.168.1.100 --num-traces 10000 --batch-size 500

  # Larger batch → fewer points per segment (scope RAM is shared)
  python capture_fast.py --board trinket_5v --port /dev/tty.usbserial-0001 \\
      --scope-ip 192.168.1.100 --batch-size 1000 --scope-points 2000
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

_PROTOCOL_TEMPLATES = {
    'hislip': 'TCPIP0::{ip}::hislip0::INSTR',
    'vxi11':  'TCPIP0::{ip}::INSTR',
    'socket': 'TCPIP0::{ip}::5025::SOCKET',
}


def build_tcpip_address(ip: str, protocol: str) -> str:
    tmpl = _PROTOCOL_TEMPLATES.get(protocol)
    if tmpl is None:
        raise ValueError(f"Unknown protocol '{protocol}'. Choose: {list(_PROTOCOL_TEMPLATES)}")
    return tmpl.format(ip=ip)


def next_set_dir(board: str) -> str:
    existing = glob.glob('data/set_*/') + glob.glob('data/set_*')
    nums = [
        int(m.group(1))
        for d in existing
        if (m := re.search(r'set_(\d+)', d))
    ]
    n = max(nums, default=0) + 1
    return f'data/set_{n:03d}_{board}'


def open_serial(port: str, baud: int, delay: float) -> serial.Serial:
    s = serial.Serial(port, baud, timeout=2, exclusive=True)
    if delay > 0:
        time.sleep(delay)
    s.reset_input_buffer()
    return s


def scope_setup_waveform(scope, channel: str, points: int) -> None:
    scope.write(f':WAVeform:SOURce {channel}')
    scope.write(':WAVeform:FORMat BYTE')
    scope.write(':WAVeform:POINts:MODE NORMal')
    scope.write(f':WAVeform:POINts {points}')


def scope_abort(scope) -> None:
    """Abort a stuck segmented acquisition and restore realtime mode."""
    for cmd in (':STOP', ':ACQuire:MODE RTIMe', '*CLS'):
        try:
            scope.write(cmd)
        except Exception:
            pass


# ── Core segmented-memory batch ────────────────────────────────────────────────
def capture_batch(
    scope,
    ser: serial.Serial,
    batch_size: int,
    opc_timeout_ms: int,
) -> tuple[list[np.ndarray], list[bytes], list[bytes]]:
    """
    Run one full segmented-memory batch.

    Returns (batch_traces, batch_plaintexts, batch_ciphertexts).
    Raises on any error so the caller can abort+retry the whole batch.
    """
    # ── Phase 1: Arm scope for batch_size hardware triggers ────────────────────
    scope.write(':ACQuire:MODE SEGMented')
    scope.write(f':ACQuire:SEGMented:COUNt {batch_size}')
    scope.write(':RUN')
    # :RUN starts segmented acquisition — scope auto-stops after N segments.
    # :SINGle is NOT used because it only arms for one trigger on Keysight scopes
    # and kills CPA/DPA correlation by preventing hardware-trigger alignment.
    # 100 ms lets the scope reach armed state before the first trigger arrives.
    time.sleep(0.10)

    # ── Phase 2: Blast UART — no scope I/O in this loop ───────────────────────
    batch_pts: list[bytes] = []
    batch_cts: list[bytes] = []

    for _ in range(batch_size):
        pt = os.urandom(16)
        ser.write(pt)
        ser.flush()
        ct = ser.read(16)                   # blocks until firmware sends back CT
        if len(ct) != 16:
            raise ValueError(
                f"Serial underrun at batch offset {len(batch_pts)}: "
                f"expected 16 bytes, got {len(ct)}"
            )
        batch_pts.append(pt)
        batch_cts.append(ct)

    # All CTs received ⇒ all N triggers have fired ⇒ scope should auto-stop soon.

    # ── Phase 3: Poll :RSTate? until the scope auto-stops ─────────────────────
    # In segmented mode with :RUN the scope stops automatically after N segments.
    # Polling :RSTate? avoids the pyvisa-py HiSLIP *OPC? socket-timeout bug.
    deadline = time.monotonic() + opc_timeout_ms / 1000
    while True:
        rstate = scope.query(':RSTate?').strip().upper()
        if rstate == 'STOP':
            break
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Scope did not auto-stop after {opc_timeout_ms/1000:.0f}s "
                f"(last :RSTate? = {rstate!r}). "
                "Check trigger config and that batch_size fits in scope memory."
            )
        time.sleep(0.05)

    # ── Phase 4: Download all N segments (Keysight uses 1-based index) ────────
    batch_traces: list[np.ndarray] = []
    for seg_idx in range(1, batch_size + 1):
        scope.write(f':WAVeform:SEGMented:INDex {seg_idx}')
        wave = scope.query_binary_values(
            ':WAVeform:DATA?', datatype='B', container=np.array
        )
        batch_traces.append(wave)

    # batch_traces[j] ↔ batch_pts[j] ↔ batch_cts[j]  for j in 0..batch_size-1
    return batch_traces, batch_pts, batch_cts


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description='High-speed SCA capture — Keysight Segmented Memory',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument('--board',          required=True,
                    help='Short board label (used in directory name and meta.json). '
                         'Examples: trinket_5v, pico, uno_r4')
    ap.add_argument('--port',           required=True,
                    help='Serial port. Find with: ls /dev/tty.usb*')
    ap.add_argument('--num-traces',     type=int, default=2000,
                    help='Total traces to capture')
    ap.add_argument('--batch-size',     type=int, default=200,
                    help='Segments per segmented-memory batch. '
                         'Larger = faster (fewer arm round-trips) but fewer '
                         'ADC points per segment (scope RAM is fixed). '
                         'Typical range: 100–1000.')
    ap.add_argument('--out-dir',        default=None,
                    help='Output directory (auto-generated as data/set_NNN_<board> if omitted)')
    ap.add_argument('--baud',           type=int, default=115200,
                    help='UART baud rate')
    ap.add_argument('--serial-delay',   type=float, default=0.5,
                    help='Seconds to wait after opening serial port '
                         '(use 2.0 for boards that reset on DTR, e.g. UNO R4)')
    ap.add_argument('--scope-address',  default=SCOPE_ADDRESS,
                    help='PyVISA resource string (ignored when --scope-ip is given)')
    ap.add_argument('--scope-ip',       default=None,
                    help='Scope IP for Ethernet. Constructs TCPIP address automatically. '
                         'Find it: [Utility] → I/O → LAN Settings on the scope.')
    ap.add_argument('--scope-protocol', default='hislip',
                    choices=['hislip', 'vxi11', 'socket'],
                    help='Ethernet transport protocol '
                         '(hislip=fastest/Keysight, vxi11=widest compat, socket=raw port 5025)')
    ap.add_argument('--scope-channel',  default='CHANnel1',
                    help='Oscilloscope channel carrying the power trace')
    ap.add_argument('--scope-points',   type=int, default=5000,
                    help='Requested waveform points per trace. '
                         'Actual points per segment = scope_memory / batch_size — '
                         'reduce batch-size if you need more points.')
    ap.add_argument('--opc-timeout',    type=int, default=60,
                    help='Seconds to wait for scope to auto-stop after the UART blast')
    ap.add_argument('--notes',          default='',
                    help='Free-text notes written into meta.json')
    ap.add_argument('--skip-images',    action='store_true',
                    help='Skip GASF/GADF/RP/MTF encoding after capture')
    ap.add_argument('--no-plot',        action='store_true',
                    help='Skip overview plot generation after capture')
    args = ap.parse_args()

    out_dir = args.out_dir or next_set_dir(args.board)
    os.makedirs(out_dir, exist_ok=True)

    if args.scope_ip:
        scope_visa = build_tcpip_address(args.scope_ip, args.scope_protocol)
        scope_transport = f'ethernet/{args.scope_protocol}'
    else:
        scope_visa = args.scope_address
        scope_transport = 'usb'

    opc_timeout_ms = args.opc_timeout * 1000

    print(f"Board        : {args.board}")
    print(f"Port         : {args.port}  @{args.baud} baud")
    print(f"Traces       : {args.num_traces}  (batch_size={args.batch_size}, "
          f"{-(-args.num_traces // args.batch_size)} batches)")
    print(f"Scope points : {args.scope_points}")
    print(f"Scope VISA   : {scope_visa}")
    print(f"Output       : {out_dir}/\n")

    # ── Connect oscilloscope ───────────────────────────────────────────────────
    print("Connecting to oscilloscope ...")
    rm = pyvisa.ResourceManager('@py')
    try:
        scope = rm.open_resource(scope_visa)
        scope.timeout = 10_000
        if args.scope_ip and args.scope_protocol == 'socket':
            scope.read_termination  = '\n'
            scope.write_termination = '\n'
        print(f"  {scope.query('*IDN?').strip()}\n")
    except Exception as e:
        print(f"  Failed to connect to scope: {e}")
        return

    scope_setup_waveform(scope, args.scope_channel, args.scope_points)

    # ── Connect board ──────────────────────────────────────────────────────────
    print(f"Connecting to {args.board} on {args.port} ...")
    ser = open_serial(args.port, args.baud, args.serial_delay)
    print("  Ready.\n")

    # Accumulated results — plain lists, converted to numpy at save
    all_traces:      list[np.ndarray] = []
    all_plaintexts:  list[bytes]      = []
    all_ciphertexts: list[bytes]      = []

    # Split total work into batches (last batch may be smaller)
    batch_schedule: list[int] = []
    remaining = args.num_traces
    while remaining > 0:
        batch_schedule.append(min(args.batch_size, remaining))
        remaining -= batch_schedule[-1]

    # ── Main capture loop ──────────────────────────────────────────────────────
    print(f"Capturing {args.num_traces} traces ...")
    t_start = time.monotonic()
    pbar = tqdm(total=args.num_traces, unit='trace')

    try:
        for batch_idx, batch_size in enumerate(batch_schedule):
            while True:     # retry loop — whole batch discarded on any error
                try:
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()

                    bt, bpts, bcts = capture_batch(
                        scope, ser, batch_size, opc_timeout_ms
                    )

                    all_traces.extend(bt)
                    all_plaintexts.extend(bpts)
                    all_ciphertexts.extend(bcts)
                    pbar.update(batch_size)
                    break   # success → move to next batch

                except serial.SerialException as e:
                    pbar.write(f"\n[!] Serial error in batch {batch_idx}: {e} — reconnecting ...")
                    scope_abort(scope)
                    try:
                        ser.close()
                    except Exception:
                        pass
                    time.sleep(2)
                    ser = open_serial(args.port, args.baud, args.serial_delay)
                    pbar.write("[+] Reconnected. Retrying batch ...")

                except ValueError as e:
                    pbar.write(f"\n[!] Batch {batch_idx}: {e} — retrying ...")
                    scope_abort(scope)
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    time.sleep(0.5)

                except pyvisa.errors.VisaIOError as e:
                    pbar.write(f"\n[!] Scope VISA error in batch {batch_idx}: {e} — retrying ...")
                    scope_abort(scope)
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    time.sleep(1)

                except Exception as e:
                    pbar.write(f"\n[!] Unexpected error in batch {batch_idx}: {e} — retrying ...")
                    scope_abort(scope)
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    time.sleep(1)

    finally:
        pbar.close()
        ser.close()
        try:
            scope.write(':ACQuire:MODE RTIMe')  # restore normal realtime mode
        except Exception:
            pass

    if not all_traces:
        print("No traces captured.")
        return

    elapsed = time.monotonic() - t_start
    n_captured = len(all_traces)
    print(f"\nCapture complete: {n_captured} traces in {elapsed:.1f}s "
          f"({n_captured / elapsed:.1f} traces/s)")

    # ── Save dataset ───────────────────────────────────────────────────────────
    print("Saving dataset ...")
    t_arr  = np.array(all_traces)
    pt_arr = np.array([list(pt) for pt in all_plaintexts],  dtype=np.uint8)
    ct_arr = np.array([list(ct) for ct in all_ciphertexts], dtype=np.uint8)

    np.save(os.path.join(out_dir, 'traces.npy'),      t_arr)
    np.save(os.path.join(out_dir, 'plaintexts.npy'),  pt_arr)
    np.save(os.path.join(out_dir, 'ciphertexts.npy'), ct_arr)

    meta = {
        'label':        out_dir.split('/')[-1],
        'key':          AES_KEY,
        'key_hex':      ''.join(f'{b:02x}' for b in AES_KEY),
        'device':       args.board,
        'N':            int(t_arr.shape[0]),
        'T':            int(t_arr.shape[1]),
        'snr':          None,
        'noise_level':  None,
        'notes':        (
            args.notes
            + f' | capture=segmented_memory batch_size={args.batch_size}'
            f' port={args.port} baud={args.baud}'
            f' scope_points={args.scope_points}'
            f' scope_transport={scope_transport}'
        ).strip(' |'),
    }
    with open(os.path.join(out_dir, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"Saved {n_captured} traces → {out_dir}/")
    print(f"  traces.npy      {t_arr.shape}  {t_arr.dtype}")
    print(f"  plaintexts.npy  {pt_arr.shape}  {pt_arr.dtype}")
    print(f"  ciphertexts.npy {ct_arr.shape}  {ct_arr.dtype}")
    print(f"  meta.json       written")

    # ── Optional image encodings ───────────────────────────────────────────────
    if not args.skip_images:
        print("\nComputing image encodings (GASF / GADF / RP / MTF) ...")
        _attacks_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'attacks'
        )
        if _attacks_dir not in sys.path:
            sys.path.insert(0, _attacks_dir)
        from deep_learning.hettwer_sca import load_or_encode  # type: ignore[import]
        load_or_encode(t_arr.astype(np.float32), out_dir, image_size=64)

    # ── Optional overview plot ─────────────────────────────────────────────────
    if not args.no_plot:
        print("\nGenerating overview plot ...")
        _root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root_dir not in sys.path:
            sys.path.insert(0, _root_dir)
        from plot_traces import plot_overview
        plot_overview(data_dir=out_dir, byte=0, round_name='first')


if __name__ == '__main__':
    main()
