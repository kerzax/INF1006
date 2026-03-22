# ── Network ───────────────────────────────────────────────────────────────────
MQTT_BROKER_IP = "192.168.1.100"   # Change to Pi 1's actual IP address
MQTT_PORT      = 1883
FLASK_PORT     = 5000

# ── MQTT Topics ───────────────────────────────────────────────────────────────
TOPICS = {
    "living_room": {
        "pir":        "home/living_room/pir",
        "dht":        "home/living_room/dht",
        "appliances": "home/living_room/appliances",
        "command":    "home/living_room/command",
    },
    "bedroom": {
        "pir":        "home/bedroom/pir",
        "ultrasonic": "home/bedroom/ultrasonic",
        "dht":        "home/bedroom/dht",
        "appliances": "home/bedroom/appliances",
        "command":    "home/bedroom/command",
    },
    "kitchen": {
        "ultrasonic": "home/kitchen/ultrasonic",
        "command":    "home/kitchen/command",
    },
    "config": "home/config",   # broadcast runtime config changes to all nodes
}

# ── Sensor Settings ───────────────────────────────────────────────────────────
ULTRASONIC_PRESENCE_CM  = 150   # person detected if distance < this (cm)
PIR_TIMEOUT_SEC         = 30    # prototype: mark empty after 30 s of no motion (prod = 600)
DHT_READ_INTERVAL       = 10    # seconds between DHT22 reads
SENSOR_PUBLISH_INTERVAL = 5     # seconds between MQTT publishes

# ── Automation ────────────────────────────────────────────────────────────────
MANUAL_OVERRIDE_SEC  = 120   # prototype: respect manual toggle for 2 min (prod = 3600)
TEMP_FAN_THRESHOLD   = 30    # °C — turn fan ON when occupied and temp ≥ this
TEMP_AC_THRESHOLD    = 35    # °C — turn AC ON (fan OFF) when occupied and temp ≥ this
NIGHT_START_HOUR     = 19    # 19:30 → lamp auto-on if occupied
NIGHT_START_MIN      = 30
NIGHT_END_HOUR       = 7     # 07:30 → lamp auto-off
NIGHT_END_MIN        = 30

# ── GPIO (BCM) ────────────────────────────────────────────────────────────────
LED_RED_GPIO   = 27
LED_GREEN_GPIO = 22
