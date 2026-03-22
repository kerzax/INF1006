#!/usr/bin/env python3
"""
Run this script ONCE on Pi 1 to learn IR codes from your remotes.
Make sure `sudo pigpiod` is running first.

Usage:
  python ir_learn.py
"""

from ir_controller import learn_code

CODES = [
    "living_room_tv_on",
    "living_room_tv_off",
    "living_room_ac_on",
    "living_room_ac_off",
    "living_room_fan_on",
    "living_room_fan_off",
]

print("=" * 50)
print("IR Code Learning — Living Room (Pi 1)")
print("Make sure: sudo pigpiod is running")
print("=" * 50)

for code in CODES:
    input(f"\n[Enter] to record:  {code}")
    learn_code(code, rx_gpio=23)

print("\nAll codes saved to ir_codes.json")
