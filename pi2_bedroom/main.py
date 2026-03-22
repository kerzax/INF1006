#!/usr/bin/env python3
"""
Pi 2 — Bedroom
Role    : Sensor node + appliance control
Sensors : PIR (GPIO 17), Ultrasonic TRIG/ECHO (GPIO 23/24),
          DHT22 (GPIO 4), IR TX (GPIO 18), IR RX (GPIO 25),
          LED (GPIO 27/22), Lamp relay (GPIO 6)
"""

import json
import os
import sys
import threading
import time
from datetime import datetime

import Adafruit_DHT
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    DHT_READ_INTERVAL, MANUAL_OVERRIDE_SEC, MQTT_BROKER_IP, MQTT_PORT,
    NIGHT_END_HOUR, NIGHT_END_MIN, NIGHT_START_HOUR, NIGHT_START_MIN,
    PIR_TIMEOUT_SEC, SENSOR_PUBLISH_INTERVAL, TEMP_AC_THRESHOLD,
    TEMP_FAN_THRESHOLD, TOPICS, ULTRASONIC_PRESENCE_CM,
)

# ── Runtime config ─────────────────────────────────────────────────────────────

config_lock = threading.Lock()

RUNTIME_CONFIG = {
    "temp_ac_threshold":   TEMP_AC_THRESHOLD,
    "pir_timeout_sec":     PIR_TIMEOUT_SEC,
    "manual_override_sec": MANUAL_OVERRIDE_SEC,
    "night_start":         f"{NIGHT_START_HOUR:02d}:{NIGHT_START_MIN:02d}",
    "night_end":           f"{NIGHT_END_HOUR:02d}:{NIGHT_END_MIN:02d}",
}

# ── GPIO ──────────────────────────────────────────────────────────────────────

PIR_PIN   = 17
TRIG_PIN  = 23
ECHO_PIN  = 24
DHT_PIN   = 4
IR_TX_PIN = 18
IR_RX_PIN = 25
LED_RED   = 27
LED_GREEN = 22
LAMP_PIN  = 6

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(PIR_PIN,   GPIO.IN)
GPIO.setup(TRIG_PIN,  GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(ECHO_PIN,  GPIO.IN)
GPIO.setup(LED_RED,   GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(LED_GREEN, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(LAMP_PIN,  GPIO.OUT, initial=GPIO.LOW)

# ── State ─────────────────────────────────────────────────────────────────────

state_lock = threading.Lock()
STATE = {
    "occupied":    False,
    "last_motion": 0,
    "away_mode":   False,
    "temp":        None,
    "humidity":    None,
    "appliances":  {"ac": False, "lamp": False},
    "overrides":   {},    # appliance_id -> expiry timestamp
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_nighttime() -> bool:
    now = datetime.now()
    current = now.hour * 60 + now.minute
    with config_lock:
        sh, sm = map(int, RUNTIME_CONFIG["night_start"].split(":"))
        eh, em = map(int, RUNTIME_CONFIG["night_end"].split(":"))
    start = sh * 60 + sm
    end   = eh * 60 + em
    return current >= start or current < end

def _apply_gpio(appliance_id: str, on: bool):
    if appliance_id == "lamp":
        GPIO.output(LAMP_PIN, GPIO.HIGH if on else GPIO.LOW)

def set_appliance(appliance_id: str, on: bool, manual: bool = False):
    """Update state + hardware. Must be called while state_lock is held."""
    if manual:
        with config_lock:
            override_sec = RUNTIME_CONFIG["manual_override_sec"]
        STATE["overrides"][appliance_id] = time.time() + override_sec
    else:
        exp = STATE["overrides"].get(appliance_id, 0)
        if time.time() < exp:
            return   # still in manual override window
    STATE["appliances"][appliance_id] = on
    _apply_gpio(appliance_id, on)
    if appliance_id == "ac":
        send_ir(appliance_id, on)

# ── LED ───────────────────────────────────────────────────────────────────────

def set_led(occupied: bool):
    if occupied:
        GPIO.output(LED_RED,   GPIO.LOW)
        GPIO.output(LED_GREEN, GPIO.HIGH)
    else:
        GPIO.output(LED_RED,   GPIO.HIGH)
        GPIO.output(LED_GREEN, GPIO.LOW)

# ── Sensors ───────────────────────────────────────────────────────────────────

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

# ── IR ────────────────────────────────────────────────────────────────────────

def send_ir(appliance: str, on: bool):
    try:
        from ir_controller import send_code
        send_code(f"bedroom_{appliance}_{'on' if on else 'off'}", tx_gpio=IR_TX_PIN)
    except Exception as e:
        print(f"[IR] {e}")

# ── MQTT callbacks ────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected (rc={rc})")
    client.subscribe(TOPICS["bedroom"]["command"])
    client.subscribe(TOPICS["config"])

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    # Config update from Pi 1 (only process bedroom payloads)
    if msg.topic == TOPICS["config"]:
        if payload.get("room_id") == "bedroom":
            with config_lock:
                for key in RUNTIME_CONFIG:
                    if key in payload:
                        RUNTIME_CONFIG[key] = payload[key]
        return

    # Away mode
    if "away" in payload:
        with state_lock:
            STATE["away_mode"] = payload["away"]
            if payload["away"]:
                for k in list(STATE["appliances"].keys()):
                    STATE["appliances"][k] = False
                    _apply_gpio(k, False)
        set_led(False)
        return

    # Appliance toggle from dashboard
    appliance = payload.get("appliance")
    on        = payload.get("on", False)
    manual    = payload.get("manual", False)
    if appliance and appliance in STATE["appliances"]:
        with state_lock:
            set_appliance(appliance, on, manual=manual)

# ── Automation loop ───────────────────────────────────────────────────────────

def automation_loop(client: mqtt.Client):
    """
    Bedroom automation (same rules as living room, minus TV/fan):
      - Temp ≥ 35 + occupied → AC ON
      - Temp < 35 → AC OFF
      - Nighttime + occupied → Lamp ON
      - Vacant → all appliances OFF
    """
    while True:
        time.sleep(10)
        with state_lock:
            if STATE["away_mode"]:
                continue

            occupied = STATE["occupied"]
            temp     = STATE["temp"]
            now      = time.time()

            # Vacancy shutoff
            if not occupied:
                for app_id in list(STATE["appliances"].keys()):
                    exp = STATE["overrides"].get(app_id, 0)
                    if now >= exp:
                        set_appliance(app_id, False)
                # Notify Pi 1 of appliance state change
                client.publish(
                    TOPICS["bedroom"]["appliances"],
                    json.dumps(STATE["appliances"]),
                )
                continue

            changed = False

            # Temperature — bedroom only has AC
            if temp is not None:
                with config_lock:
                    t_ac = RUNTIME_CONFIG["temp_ac_threshold"]
                target_ac = temp >= t_ac
                if STATE["appliances"]["ac"] != target_ac:
                    set_appliance("ac", target_ac)
                    changed = True

            # Nighttime lamp
            target_lamp = is_nighttime()
            if STATE["appliances"]["lamp"] != target_lamp:
                set_appliance("lamp", target_lamp)
                changed = True

            if changed:
                client.publish(
                    TOPICS["bedroom"]["appliances"],
                    json.dumps(STATE["appliances"]),
                )

# ── Sensor + publish loop ─────────────────────────────────────────────────────

def sensor_loop(client: mqtt.Client):
    dht_sensor = Adafruit_DHT.DHT22
    last_dht   = 0

    while True:
        distance = read_ultrasonic()
        pir      = GPIO.input(PIR_PIN)

        with state_lock:
            present = pir or (distance is not None and distance < ULTRASONIC_PRESENCE_CM)
            if present:
                STATE["last_motion"] = time.time()
                STATE["occupied"]    = True
            else:
                with config_lock:
                    pir_timeout = RUNTIME_CONFIG["pir_timeout_sec"]
                if time.time() - STATE["last_motion"] > pir_timeout:
                    STATE["occupied"] = False
            occupied  = STATE["occupied"]
            away_mode = STATE["away_mode"]

        set_led(occupied and not away_mode)

        # Publish ultrasonic
        if distance is not None:
            client.publish(
                TOPICS["bedroom"]["ultrasonic"],
                json.dumps({"distance_cm": distance}),
            )

        # Publish PIR
        client.publish(
            TOPICS["bedroom"]["pir"],
            json.dumps({"motion": bool(pir)}),
        )

        # DHT22 (less frequent)
        if time.time() - last_dht >= DHT_READ_INTERVAL:
            humidity, temp = Adafruit_DHT.read_retry(dht_sensor, DHT_PIN)
            if temp is not None and humidity is not None:
                with state_lock:
                    STATE["temp"]     = round(temp, 1)
                    STATE["humidity"] = round(humidity, 1)
                client.publish(
                    TOPICS["bedroom"]["dht"],
                    json.dumps({"temp": round(temp, 1), "humidity": round(humidity, 1)}),
                )
                print(f"[DHT22] {temp:.1f}°C  {humidity:.1f}%")
            last_dht = time.time()

        time.sleep(SENSOR_PUBLISH_INTERVAL)

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[Pi 2] Starting Bedroom node")

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER_IP, MQTT_PORT, keepalive=60)
    client.loop_start()

    threading.Thread(target=automation_loop, args=(client,), daemon=True).start()

    try:
        sensor_loop(client)
    finally:
        GPIO.cleanup()
