#!/usr/bin/env python3
"""
Run this script ONCE on Pi 2 to learn IR codes from your remotes.
Make sure `sudo pigpiod` is running first.

Usage:
  python ir_learn.py
"""

from ir_controller import learn_code

CODES = [
    "bedroom_ac_on",
    "bedroom_ac_off",
    "bedroom_fan_on",
    "bedroom_fan_off",
]

print("=" * 50)
print("IR Code Learning — Bedroom (Pi 2)")
print("Make sure: sudo pigpiod is running")
print("=" * 50)

for code in CODES:
    input(f"\n[Enter] to record:  {code}")
    learn_code(code, rx_gpio=25)

print("\nAll codes saved to ir_codes.json")
