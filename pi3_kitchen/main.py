#!/usr/bin/env python3
"""
Pi 3 — Kitchen
Role    : Sensor node
Sensors : Ultrasonic TRIG/ECHO (GPIO 23/24), LED (GPIO 27/22), Lamp relay (GPIO 6)
"""

import json
import os
import sys
import time

import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    MQTT_BROKER_IP, MQTT_PORT,
    PIR_TIMEOUT_SEC, SENSOR_PUBLISH_INTERVAL, TOPICS, ULTRASONIC_PRESENCE_CM,
)

# ── Runtime config ─────────────────────────────────────────────────────────────

RUNTIME_CONFIG = {
    "pir_timeout_sec": PIR_TIMEOUT_SEC,
}

# ── GPIO ──────────────────────────────────────────────────────────────────────

TRIG_PIN  = 23
ECHO_PIN  = 24
LED_RED   = 27
LED_GREEN = 22
LAMP_PIN  = 6

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(TRIG_PIN,  GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(ECHO_PIN,  GPIO.IN)
GPIO.setup(LED_RED,   GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(LED_GREEN, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(LAMP_PIN,  GPIO.OUT, initial=GPIO.LOW)

# ── State ─────────────────────────────────────────────────────────────────────

away_mode      = False
occupied       = False
last_seen_time = 0.0   # timestamp of last detected presence

# ── LED / Lamp ────────────────────────────────────────────────────────────────

def set_led(is_occupied: bool):
    if is_occupied:
        GPIO.output(LED_RED,   GPIO.LOW)
        GPIO.output(LED_GREEN, GPIO.HIGH)
    else:
        GPIO.output(LED_RED,   GPIO.HIGH)
        GPIO.output(LED_GREEN, GPIO.LOW)

def set_lamp(on: bool):
    GPIO.output(LAMP_PIN, GPIO.HIGH if on else GPIO.LOW)

# ── Ultrasonic ────────────────────────────────────────────────────────────────

def read_ultrasonic() -> float | None:
    """Return distance in cm, or None on timeout."""
    GPIO.output(TRIG_PIN, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(TRIG_PIN, GPIO.LOW)

    deadline = time.time() + 0.04
    while GPIO.input(ECHO_PIN) == 0:
        if time.time() > deadline:
            return None
    pulse_start = time.time()

    deadline = time.time() + 0.04
    while GPIO.input(ECHO_PIN) == 1:
        if time.time() > deadline:
            return None
    pulse_end = time.time()

    return round((pulse_end - pulse_start) * 17150, 1)

# ── MQTT ──────────────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected (rc={rc})")
    client.subscribe(TOPICS["kitchen"]["command"])
    client.subscribe(TOPICS["config"])

def on_message(client, userdata, msg):
    global away_mode
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    if msg.topic == TOPICS["config"]:
        if payload.get("room_id") == "kitchen" and "pir_timeout_sec" in payload:
            RUNTIME_CONFIG["pir_timeout_sec"] = payload["pir_timeout_sec"]
        return

    if "away" in payload:
        away_mode = payload["away"]
        if away_mode:
            set_led(False)
            set_lamp(False)

# ── Main loop ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[Pi 3] Starting Kitchen node")

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER_IP, MQTT_PORT, keepalive=60)
    client.loop_start()

    try:
        while True:
            distance = read_ultrasonic()

            if distance is not None:
                person_present = distance < ULTRASONIC_PRESENCE_CM

                if person_present:
                    last_seen_time = time.time()
                    occupied = True
                else:
                    if time.time() - last_seen_time > RUNTIME_CONFIG["pir_timeout_sec"]:
                        occupied = False

                if not away_mode:
                    set_led(occupied)
                    set_lamp(occupied)   # lamp follows presence with PIR_TIMEOUT_SEC delay

                client.publish(
                    TOPICS["kitchen"]["ultrasonic"],
                    json.dumps({"distance_cm": distance}),
                )
                print(f"[Ultrasonic] {distance} cm  occupied={occupied}")

            time.sleep(SENSOR_PUBLISH_INTERVAL)

    finally:
        GPIO.cleanup()
