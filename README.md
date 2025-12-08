# Sentry-Bot: AI-Powered Security System for Raspberry Pi 5

A 100% local, offline AI security system that transforms your Raspberry Pi 5 into an intelligent sentry. Features person detection, face recognition, voice commands, and an on-device LLM brain - all running entirely on your Pi without cloud dependencies.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%205-red.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![AI](https://img.shields.io/badge/AI-100%25%20Local-purple.svg)

## Features

| Feature | Technology | Purpose |
|---------|------------|---------|
| **Motion Detection** | PIR Sensor | Primary intrusion trigger |
| **Person Detection** | TensorFlow Lite | Distinguish humans from pets/objects |
| **Face Recognition** | dlib | Authorize known individuals |
| **Voice Commands** | Vosk | Offline voice control |
| **Text-to-Speech** | Piper | Dynamic announcements |
| **Custom Voice** | XTTS | Clone any voice locally |
| **AI Brain** | Ollama + phi3 | Conversational AI, reasoning |
| **RGB LED Status** | GPIO PWM | Visual feedback |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      SENTRY-BOT AI SYSTEM                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    │
│   │  Vision  │    │  Voice   │    │   TTS    │    │   Face   │    │
│   │ TFLite   │    │  Vosk    │    │  Piper   │    │   dlib   │    │
│   └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘    │
│        │               │               │               │          │
│        └───────────────┴───────┬───────┴───────────────┘          │
│                                │                                   │
│                    ┌───────────▼───────────┐                      │
│                    │     SENTRY BRAIN      │                      │
│                    │   Ollama + phi3:mini  │                      │
│                    │                       │                      │
│                    │  - Reasoning          │                      │
│                    │  - Q&A                │                      │
│                    │  - Troubleshooting    │                      │
│                    └───────────┬───────────┘                      │
│                                │                                   │
│              ┌─────────────────┼─────────────────┐                │
│              │                 │                 │                │
│         ┌────▼────┐      ┌─────▼─────┐    ┌─────▼─────┐          │
│         │   PIR   │      │  Camera   │    │ RGB LEDs  │          │
│         │ Sensor  │      │ PiCamera2 │    │  Status   │          │
│         └─────────┘      └───────────┘    └───────────┘          │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

## Table of Contents

- [Quick Start](#quick-start)
- [Hardware Requirements](#hardware-requirements)
- [Hardware Wiring Guide](#hardware-wiring-guide)
- [Software Installation](#software-installation)
- [Configuration](#configuration)
- [Production Deployment](#production-deployment)
- [Voice Commands](#voice-commands)
- [Custom Voice Setup](#custom-voice-setup)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/AgentVT/sentry-bot.git
cd sentry-bot

# 2. Run the setup script (installs everything)
chmod +x setup_ai.sh
./setup_ai.sh --full

# 3. Add authorized faces (optional)
cp your_photo.jpg authorized_faces/your_name.jpg

# 4. Run the system
python3 sentry_ai_system.py
```

---

## Hardware Requirements

### Minimum Setup
| Component | Model | Purpose |
|-----------|-------|---------|
| Raspberry Pi 5 | 4GB or 8GB RAM | Main computer |
| PIR Sensor | HC-SR501 | Motion detection |
| LED | Any 5mm LED | Status indicator |
| MicroSD Card | 32GB+ Class 10 | Storage |
| Power Supply | 5V 5A USB-C | Power |

### Recommended Setup (Full AI)
| Component | Model | Purpose |
|-----------|-------|---------|
| Raspberry Pi 5 | **8GB RAM** | Required for LLM |
| PIR Sensor | HC-SR501 | Motion detection |
| RGB LED Strip | WS2812B or 3x LEDs | Color status |
| Camera | Pi Camera Module 3 | Person/face detection |
| USB Microphone | Any USB mic | Voice commands |
| Speaker | 3.5mm or USB | Audio output |
| MicroSD Card | 64GB+ A2 | Fast storage |
| NVMe SSD (optional) | 128GB+ | Faster AI inference |
| Cooling | Active cooler | Prevent throttling |

### Storage Requirements
| Component | Size |
|-----------|------|
| Base System | ~500MB |
| TFLite Model | ~5MB |
| Vosk Model | ~50MB |
| Piper Voice | ~60MB |
| Ollama + phi3:mini | ~2.5GB |
| XTTS (voice cloning) | ~2GB |
| **Total** | **~5-6GB** |

---

## Hardware Wiring Guide

### GPIO Pin Configuration

```
Raspberry Pi 5 GPIO Header
─────────────────────────────
           3.3V [1]  [2]  5V
    (SDA) GPIO2 [3]  [4]  5V
    (SCL) GPIO3 [5]  [6]  GND
          GPIO4 [7]  [8]  GPIO14 (TXD)
            GND [9]  [10] GPIO15 (RXD)
  (RED LED) GPIO17 [11] [12] GPIO18
            GPIO27 [13] [14] GND        ← PIR SENSOR GND
(PIR DATA)  GPIO27 [13]                 ← PIR SENSOR DATA
(GRN LED) GPIO22 [15] [16] GPIO23
           3.3V [17] [18] GPIO24       ← BLUE LED
                ...
```

### Wiring Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    RASPBERRY PI 5                            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    GPIO HEADER                       │   │
│  │  [5V]──────────────────────┐                        │   │
│  │  [GND]─────────────────────┼──────────┐             │   │
│  │  [GPIO27]──────────────────┼──────────┼──┐          │   │
│  │  [GPIO17]──────┐           │          │  │          │   │
│  │  [GPIO22]──────┼──┐        │          │  │          │   │
│  │  [GPIO24]──────┼──┼──┐     │          │  │          │   │
│  └────────────────┼──┼──┼─────┼──────────┼──┼──────────┘   │
│                   │  │  │     │          │  │              │
└───────────────────┼──┼──┼─────┼──────────┼──┼──────────────┘
                    │  │  │     │          │  │
                    │  │  │     │          │  │
              ┌─────┴──┴──┴─┐   │    ┌─────┴──┴─────┐
              │  RGB LED    │   │    │  PIR SENSOR  │
              │             │   │    │   HC-SR501   │
              │  R  G  B    │   │    │              │
              │  │  │  │    │   │    │ VCC OUT GND  │
              │  └──┴──┴────┼───┘    │  │   │   │  │
              │     GND     │        │  │   │   │  │
              └─────────────┘        └──┼───┼───┼──┘
                                        │   │   │
                                       5V  GPIO27 GND
```

### PIR Sensor (HC-SR501) Setup

1. **Connect wires:**
   - VCC → Pin 2 (5V)
   - GND → Pin 6 (GND)
   - OUT → Pin 13 (GPIO27)

2. **Adjust potentiometers:**
   - **Sensitivity (left):** Turn clockwise for higher sensitivity
   - **Time delay (right):** Turn counter-clockwise for shorter delay (~3 sec)

3. **Jumper setting:**
   - **H position:** Repeatable trigger (recommended)
   - **L position:** Single trigger

### RGB LED Wiring

**Option A: Common Cathode RGB LED**
```
GPIO17 ──[220Ω]──► RED
GPIO22 ──[220Ω]──► GREEN
GPIO24 ──[220Ω]──► BLUE
GND ─────────────► COMMON (-)
```

**Option B: Three Separate LEDs**
```
GPIO17 ──[220Ω]──► RED LED (+) ──► GND
GPIO22 ──[220Ω]──► GREEN LED (+) ──► GND
GPIO24 ──[220Ω]──► BLUE LED (+) ──► GND
```

### Camera Setup (Pi Camera Module 3)

1. Power off the Pi
2. Lift the camera connector latch
3. Insert ribbon cable (blue side facing USB ports)
4. Press latch down
5. Enable camera: `sudo raspi-config` → Interface Options → Camera

---

## Software Installation

### Prerequisites

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install git if not present
sudo apt install -y git
```

### Installation Options

#### Option 1: Full Installation (Recommended)
Installs everything including the on-device LLM:

```bash
git clone https://github.com/AgentVT/sentry-bot.git
cd sentry-bot
chmod +x setup_ai.sh
./setup_ai.sh --full
```

**Time estimate:** 30-60 minutes (depends on internet speed)

#### Option 2: Minimal Installation
Basic detection without LLM brain:

```bash
./setup_ai.sh --minimal
```

**Time estimate:** 10-15 minutes

#### Option 3: LLM Only
If you already have the base system:

```bash
./setup_ai.sh --llm-only
```

#### Option 4: Manual Installation

```bash
# System dependencies
sudo apt install -y python3-pip python3-venv libportaudio2 \
    portaudio19-dev libatlas-base-dev cmake ffmpeg espeak-ng

# Python packages
pip3 install numpy pygame mutagen RPi.GPIO opencv-python-headless
pip3 install tflite-runtime vosk pyaudio piper-tts

# Face recognition (takes 10-20 min)
pip3 install face_recognition

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama
sudo systemctl start ollama
ollama pull phi3:mini
```

---

## Configuration

### Main Configuration (`config.json`)

```json
{
    "pir_pin": 27,
    "led_pin": 17,
    "led_mode": "rgb",
    "rgb_pins": {
        "red": 17,
        "green": 22,
        "blue": 24
    },
    "sounds": {
        "power_on": "/path/to/powerup.mp3",
        "unauthorized": ["/path/to/alert1.mp3", "/path/to/alert2.mp3"],
        "warning": ["/path/to/warning1.mp3"],
        "alarm": "/path/to/alarm.mp3",
        "power_down": "/path/to/powerdown.mp3"
    },
    "unauthorized_pause": [0.5, 1],
    "warning_delay": 3,
    "alarm_delay": 5
}
```

### AI Configuration (`local_ai_config.json`)

```json
{
    "ai_enabled": true,

    "vision": {
        "enabled": true,
        "confidence_threshold": 0.5,
        "detection_classes": {
            "person": {"alert_level": "high"},
            "cat": {"alert_level": "ignore"},
            "dog": {"alert_level": "ignore"}
        }
    },

    "face_recognition": {
        "enabled": true,
        "recognition_threshold": 0.6
    },

    "voice_recognition": {
        "enabled": true,
        "wake_words": ["sentry", "jarvis"]
    },

    "llm": {
        "enabled": true,
        "model": "phi3:mini"
    }
}
```

### Adding Authorized Faces

```bash
# Create directory if not exists
mkdir -p authorized_faces

# Add photos (use person's name as filename)
cp john_photo.jpg authorized_faces/john_smith.jpg
cp jane_photo.jpg authorized_faces/jane_doe.jpg

# Tips for best recognition:
# - Use clear, well-lit photos
# - Face should be front-facing
# - One person per photo
# - Minimum 200x200 pixels
```

---

## Production Deployment

### Step 1: Prepare the Raspberry Pi 5

```bash
# Use Raspberry Pi Imager to flash Raspberry Pi OS (64-bit)
# Enable SSH during imaging for headless setup

# After first boot, update everything
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

### Step 2: Optimize for Production

```bash
# Disable unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
sudo systemctl disable triggerhappy

# Set GPU memory (minimum needed)
sudo raspi-config
# → Performance Options → GPU Memory → 128

# Enable hardware PWM for LEDs (smoother)
# Add to /boot/config.txt:
echo "dtoverlay=pwm-2chan" | sudo tee -a /boot/config.txt

# Overclock for better AI performance (optional, with cooling)
# Add to /boot/config.txt:
echo "arm_freq=2800" | sudo tee -a /boot/config.txt
echo "gpu_freq=800" | sudo tee -a /boot/config.txt

sudo reboot
```

### Step 3: Install Sentry-Bot

```bash
# Clone to /opt for system-wide installation
sudo git clone https://github.com/AgentVT/sentry-bot.git /opt/sentry-bot
sudo chown -R $USER:$USER /opt/sentry-bot
cd /opt/sentry-bot

# Run full setup
chmod +x setup_ai.sh
./setup_ai.sh --full
```

### Step 4: Create Systemd Service

```bash
# Create service file
sudo tee /etc/systemd/system/sentry-bot.service << 'EOF'
[Unit]
Description=Sentry-Bot AI Security System
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/sentry-bot
ExecStart=/usr/bin/python3 /opt/sentry-bot/sentry_ai_system.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment
Environment="PYTHONUNBUFFERED=1"

# Resource limits
MemoryMax=2G
CPUQuota=80%

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable sentry-bot
sudo systemctl start sentry-bot

# Check status
sudo systemctl status sentry-bot
```

### Step 5: Configure Auto-Start on Boot

```bash
# Ensure Ollama starts first
sudo systemctl enable ollama

# Verify boot order
sudo systemctl list-dependencies sentry-bot.service
```

### Step 6: Set Up Log Rotation

```bash
# Create logrotate config
sudo tee /etc/logrotate.d/sentry-bot << 'EOF'
/opt/sentry-bot/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
EOF
```

### Step 7: Monitor and Manage

```bash
# View real-time logs
sudo journalctl -u sentry-bot -f

# Restart service
sudo systemctl restart sentry-bot

# Stop service
sudo systemctl stop sentry-bot

# Check resource usage
htop
# or
sudo systemctl status sentry-bot --no-pager -l
```

### Step 8: Network Security (Optional)

```bash
# If exposing to network, set up firewall
sudo apt install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable

# For remote monitoring, consider:
# - VPN (WireGuard)
# - SSH tunneling
# - Local network only
```

### Production Checklist

- [ ] Pi 5 with 8GB RAM and active cooling
- [ ] 64GB+ fast SD card or NVMe SSD
- [ ] All hardware connected and tested
- [ ] setup_ai.sh completed successfully
- [ ] Authorized faces added
- [ ] Custom sounds configured
- [ ] Systemd service enabled
- [ ] Log rotation configured
- [ ] Tested full detection cycle
- [ ] Tested voice commands
- [ ] Tested face recognition bypass
- [ ] Monitoring set up

---

## Voice Commands

Say the wake word ("Sentry" or "Jarvis") followed by a command:

| Command | Action |
|---------|--------|
| "Enable sentry" | Arm the system |
| "Arm system" | Arm the system |
| "Disable sentry" | Disarm the system |
| "Disarm system" | Disarm the system |
| "Status report" | Get system status |
| "Who is there" | Identify detected persons |
| "Stop alarm" | Silence current alarm |
| "Add face" | Enter face enrollment mode |

### Natural Language Queries (LLM)

You can also ask the AI brain questions:

- "What was the last detection?"
- "How many alerts today?"
- "Is the camera working?"
- "Help me troubleshoot the PIR sensor"
- "What time did John arrive?"

---

## Custom Voice Setup

### Option 1: Voice Cloning (Easiest)

Clone any voice with just 6-30 seconds of audio:

```bash
# Record a sample
python3 custom_voice.py record my_voice_sample.wav --duration 15

# Clone the voice
python3 custom_voice.py clone jarvis my_voice_sample.wav

# Test it
python3 custom_voice.py test --voice jarvis --text "System armed."

# Enable in config (local_ai_config.json)
# Set: "custom_voice": { "enabled": true, "voice_id": "jarvis" }
```

### Option 2: Pre-trained Voices

```bash
# List available voices
python3 custom_voice.py list

# Download a voice
python3 custom_voice.py download en_US-ryan-medium

# Available voices:
# - en_US-lessac-medium (Female US)
# - en_US-ryan-medium (Male US)
# - en_US-amy-medium (Female US, natural)
# - en_GB-alan-medium (Male British)
# - en_GB-jenny_dioco-medium (Female British)
```

### Option 3: Train Custom Piper Voice

For highest quality, train your own voice model:

```bash
# Show training guide
python3 custom_voice.py guide
```

Requires:
- 1-2 hours of audio recordings
- GPU machine for training (not Pi)
- Export .onnx model for Pi inference

---

## API Reference

### Python Integration

```python
from local_ai import SentryAI
from sentry_brain import SentryBrain
from custom_voice import CustomVoice

# Initialize AI system
ai = SentryAI('local_ai_config.json')
ai.initialize()

# Analyze motion event
result = ai.analyze_motion(pir_triggered=True)
print(f"Should alert: {result['should_alert']}")
print(f"Alert level: {result['alert_level']}")
print(f"Person detected: {'person' in [d.detection_type for d in result['detections']]}")

# Use the LLM brain
brain = SentryBrain()
brain.initialize()
response = brain.think("What should I do if motion is detected at night?")
print(response)

# Custom voice
voice = CustomVoice()
voice.initialize()
voice.speak("Intruder alert!", voice_id="jarvis")

# Cleanup
ai.cleanup()
brain.cleanup()
```

### Running Individual Components

```bash
# Test object detection
python3 -c "from local_ai import ObjectDetector; d = ObjectDetector({}); d.initialize(); print(d.detect())"

# Test voice recognition
python3 -c "from local_ai import VoiceRecognizer; v = VoiceRecognizer({'enabled': True}); v.initialize(); print(v.recognize_once())"

# Test LLM brain
python3 sentry_brain.py

# Test custom voice
python3 custom_voice.py test --text "Hello world"
```

---

## Troubleshooting

### Common Issues

#### PIR Sensor Not Detecting Motion

```bash
# Check GPIO
python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); GPIO.setup(27, GPIO.IN); print('PIR:', GPIO.input(27))"

# Solutions:
# 1. Adjust sensitivity potentiometer (turn clockwise)
# 2. Wait 30-60 seconds for sensor warmup
# 3. Check wiring connections
# 4. Try different GPIO pin
```

#### Camera Not Working

```bash
# Test camera
libcamera-hello --timeout 5000

# Check if camera is detected
vcgencmd get_camera

# Solutions:
# 1. Check ribbon cable connection
# 2. Enable camera in raspi-config
# 3. Update firmware: sudo rpi-update
# 4. Check /boot/config.txt for camera_auto_detect=1
```

#### Ollama/LLM Not Responding

```bash
# Check Ollama status
sudo systemctl status ollama

# Restart Ollama
sudo systemctl restart ollama

# Check if model is loaded
curl http://localhost:11434/api/tags

# Re-pull model if needed
ollama pull phi3:mini

# Check memory usage
free -h
# LLM needs ~2-3GB free RAM
```

#### Voice Recognition Not Working

```bash
# Test microphone
arecord -d 5 test.wav && aplay test.wav

# List audio devices
arecord -l

# Check Vosk model
ls -la models/vosk-model-small-en-us/

# Solutions:
# 1. Check USB microphone connection
# 2. Adjust ALSA settings: alsamixer
# 3. Re-download Vosk model
```

#### Face Recognition Slow/Inaccurate

```bash
# Solutions:
# 1. Use smaller images (resize to 640x480)
# 2. Ensure good lighting
# 3. Re-encode faces with better photos
# 4. Adjust recognition_threshold (lower = more lenient)
```

#### High CPU/Memory Usage

```bash
# Check usage
htop

# Solutions:
# 1. Use smaller LLM model: ollama pull llama3.2:1b
# 2. Disable unused features in local_ai_config.json
# 3. Reduce camera resolution
# 4. Add swap: sudo dphys-swapfile setup
```

### Log Files

```bash
# Application logs
tail -f /opt/sentry-bot/sentry_ai.log

# System logs
sudo journalctl -u sentry-bot -f

# Ollama logs
sudo journalctl -u ollama -f
```

### Factory Reset

```bash
# Stop services
sudo systemctl stop sentry-bot
sudo systemctl stop ollama

# Remove data (keeps code)
rm -rf /opt/sentry-bot/models
rm -rf /opt/sentry-bot/voices
rm -rf /opt/sentry-bot/authorized_faces/*
rm -rf /opt/sentry-bot/captured_faces/*
rm -rf /opt/sentry-bot/*.log

# Re-run setup
cd /opt/sentry-bot
./setup_ai.sh --full
```

---

## File Structure

```
sentry-bot/
├── config.json              # Hardware configuration
├── local_ai_config.json     # AI feature settings
├── sentry_ai_system.py      # Main application (run this)
├── local_ai.py              # AI modules (vision, voice, TTS)
├── sentry_brain.py          # LLM brain integration
├── custom_voice.py          # Voice cloning utilities
├── setup_ai.sh              # Installation script
├── requirements.txt         # Python dependencies
├── errorhandling.py         # Legacy detection system
├── models/                  # AI models (created by setup)
│   ├── detect.tflite
│   ├── vosk-model-small-en-us/
│   └── en_US-lessac-medium.onnx
├── voices/                  # Custom voice profiles
├── authorized_faces/        # Photos of authorized people
├── captured_faces/          # Unknown face captures
└── tts_cache/              # Cached audio files
```

---

## Performance Benchmarks (Pi 5 8GB)

| Operation | Time |
|-----------|------|
| PIR detection | <1ms |
| Object detection (TFLite) | ~100ms |
| Face recognition | ~200ms |
| Voice command recognition | ~500ms |
| LLM response (phi3:mini) | 2-5 seconds |
| TTS generation (Piper) | ~100ms |
| TTS generation (XTTS clone) | 2-3 seconds |

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test on Raspberry Pi 5
5. Submit a pull request

---

## License

MIT License - see [LICENSE](LICENSE) file.

---

## Acknowledgments

- [TensorFlow Lite](https://www.tensorflow.org/lite) - Object detection
- [Vosk](https://alphacephei.com/vosk/) - Offline speech recognition
- [Piper](https://github.com/rhasspy/piper) - Local text-to-speech
- [Coqui TTS](https://github.com/coqui-ai/TTS) - Voice cloning
- [Ollama](https://ollama.ai/) - Local LLM runtime
- [dlib](http://dlib.net/) - Face recognition
