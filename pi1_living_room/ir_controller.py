"""
IR Controller — Pi 1 (Living Room)
Uses pigpio for accurate microsecond timing.

Usage:
  1. Run `sudo pigpiod` before starting
  2. Run `python ir_learn.py` to record codes from your remote
  3. Codes are saved to ir_codes.json and replayed via send_code()
"""

import json
import os
import threading
import time

import pigpio

CODES_FILE   = os.path.join(os.path.dirname(__file__), "ir_codes.json")
CARRIER_FREQ = 38000   # Hz — standard IR carrier
GAP_US       = 100_000 # 100 ms silence = end of IR burst

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load() -> dict:
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE) as f:
            return json.load(f)
    return {}

def _save(codes: dict):
    with open(CODES_FILE, "w") as f:
        json.dump(codes, f, indent=2)

# ── Learn ─────────────────────────────────────────────────────────────────────

def learn_code(name: str, rx_gpio: int = 23, timeout_s: int = 10):
    """
    Record an IR signal from a remote control.
    Point the remote at the IR receiver and press the button when prompted.

    name    : unique identifier e.g. "living_room_tv_on"
    rx_gpio : BCM pin connected to IR receiver OUT
    """
    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("pigpio daemon not running — run: sudo pigpiod")

    print(f"[IR Learn] Ready — press remote button for: '{name}'")

    pulses    = []
    last_tick = [None]
    done      = threading.Event()

    def _cb(gpio, level, tick):
        if last_tick[0] is not None:
            gap = pigpio.tickDiff(last_tick[0], tick)
            # Positive = mark (LED on), negative = space (LED off)
            pulses.append(gap if level == 0 else -gap)
            if gap > GAP_US:
                done.set()
        last_tick[0] = tick

    pi.set_mode(rx_gpio, pigpio.INPUT)
    cb = pi.callback(rx_gpio, pigpio.EITHER_EDGE, _cb)

    done.wait(timeout=timeout_s)
    cb.cancel()
    pi.stop()

    if pulses:
        codes = _load()
        codes[name] = pulses
        _save(codes)
        print(f"[IR Learn] Saved '{name}' ({len(pulses)} pulses)")
    else:
        print(f"[IR Learn] No signal received for '{name}'")

# ── Send ──────────────────────────────────────────────────────────────────────

def send_code(name: str, tx_gpio: int = 18):
    """
    Replay a saved IR code.

    name    : key from ir_codes.json e.g. "living_room_tv_on"
    tx_gpio : BCM pin connected to IR LED anode (via 100Ω resistor)
    """
    codes = _load()
    if name not in codes:
        print(f"[IR Send] Code '{name}' not found — run ir_learn.py first")
        return

    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("pigpio daemon not running — run: sudo pigpiod")

    pi.set_mode(tx_gpio, pigpio.OUTPUT)
    half_period = int(500_000 / CARRIER_FREQ)   # µs

    wave_pulses = []
    for duration in codes[name]:
        if duration > 0:
            # Mark — emit carrier
            cycles = max(1, abs(duration) // (half_period * 2))
            for _ in range(cycles):
                wave_pulses.append(pigpio.pulse(1 << tx_gpio, 0,            half_period))
                wave_pulses.append(pigpio.pulse(0,            1 << tx_gpio, half_period))
        else:
            # Space — silence
            wave_pulses.append(pigpio.pulse(0, 0, abs(duration)))

    pi.wave_clear()
    pi.wave_add_generic(wave_pulses)
    wave_id = pi.wave_create()
    pi.wave_send_once(wave_id)

    while pi.wave_tx_busy():
        time.sleep(0.001)

    pi.wave_delete(wave_id)
    pi.stop()
    print(f"[IR Send] Sent '{name}'")
