# 🛡️ SentryBot - Raspberry Pi 5 Intrusion Detection System

SentryBot is an intelligent motion-detection security system for Raspberry Pi 5. It provides multi-stage escalating alerts through audio warnings and LED indicators, with optional voice activation and web-based monitoring.

## ✨ Features

- **Motion Detection**: PIR sensor-based intrusion detection
- **3-Stage Alert System**: Escalating responses (Unauthorized → Warning → Alarm)
- **Flexible LED Control**: Supports both single and RGB LEDs with PWM control
- **Audio Alerts**: Randomized sound playback to avoid predictability
- **Voice Activation** (Optional): Enable sentry mode via voice command
- **Web Dashboard**: Real-time status monitoring via web interface
- **Modular Architecture**: Clean, maintainable code with proper separation of concerns
- **Comprehensive Logging**: Rotating log files with detailed event tracking
- **Graceful Shutdown**: Proper cleanup of GPIO and resources

## 📋 Requirements

### Hardware
- Raspberry Pi 5 (or compatible model with GPIO)
- PIR Motion Sensor (connected to GPIO 27)
- LED (single or RGB) with appropriate resistors
- Speaker or audio output device
- Optional: Microphone (for voice activation)

### Software
- Python 3.10+
- Dependencies listed in `requirements.txt`

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/AgentVT/sentry-bot.git
   cd sentry-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure audio files**
   - Update `config.json` with paths to your audio files
   - Ensure MP3 files exist at the specified locations

4. **Configure hardware pins** (if different from defaults)
   - Edit `config.json` to match your GPIO pin configuration

## ⚙️ Configuration

Edit `config.json` to customize your setup:

```json
{
    "pir_pin": 27,              // PIR sensor GPIO pin
    "led_type": "single",       // "single" or "rgb"
    "led_pin": 17,              // Single LED pin or Red pin for RGB
    "red_pin": 17,              // RGB red pin
    "green_pin": 22,            // RGB green pin
    "blue_pin": 24,             // RGB blue pin
    "voice_enabled": false,     // Enable voice activation
    "web_server": {
        "enabled": true,        // Enable web dashboard
        "host": "0.0.0.0",      // Web server host
        "port": 5000            // Web server port
    }
}
```

### LED Configuration
- **Single LED**: Set `"led_type": "single"` and configure `led_pin`
- **RGB LED**: Set `"led_type": "rgb"` and configure `red_pin`, `green_pin`, `blue_pin`

### Voice Activation
1. Set `"voice_enabled": true` in config.json
2. Install speech recognition: `pip install SpeechRecognition`
3. Connect a microphone to your Raspberry Pi
4. Say "Enable Sentry Mode" to activate the system

## 🎮 Usage

### Basic Usage
```bash
python3 sentrybot.py
```

### With Web Dashboard
1. Enable web server in `config.json`
2. Run the application
3. Open browser to `http://<raspberry-pi-ip>:5000`

### Run Tests
```bash
pytest
```

### Run with Coverage
```bash
pytest --cov=. --cov-report=html
```

## 🌐 Web Dashboard

The web dashboard provides:
- Real-time system state monitoring
- Motion detection status
- Color-coded state indicators
- Auto-refreshing every 2 seconds

Access at: `http://<raspberry-pi-ip>:5000`

### API Endpoints
- `GET /api/status` - Get current system status
- `GET /api/config` - Get configuration (sanitized)

## 📊 System States

1. **STANDBY** 🟢 - Monitoring for motion
2. **INITIALIZING** 🟡 - Voice activation (if enabled)
3. **POWERING_ON** 🟠 - Motion detected, starting up
4. **UNAUTHORIZED** 🔴 - Playing unauthorized access alert
5. **WARNING** ⚠️ - Second-stage warning
6. **ALARM** 🚨 - Final alarm stage
7. **POWERING_DOWN** ⬇️ - Shutting down after motion ceases

## 🔧 Development

### Project Structure
```
sentry-bot/
├── sentrybot.py           # Main application (consolidated)
├── web_server.py          # Web dashboard and API
├── config.json            # Configuration file
├── requirements.txt       # Python dependencies
├── pytest.ini            # Test configuration
├── tests/                # Unit tests
│   ├── __init__.py
│   ├── conftest.py       # Test fixtures
│   └── test_sentrybot.py # Test suite
├── intrusiondetectionclass.py  # Legacy (reference)
├── errorhandling.py              # Legacy (reference)
├── newfeaturesRGB.py            # Legacy (reference)
└── flickerupdate.py             # Legacy (reference)
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_sentrybot.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=. --cov-report=html
```

## 🛠️ Troubleshooting

### GPIO Permission Errors
Run with sudo or add your user to the `gpio` group:
```bash
sudo usermod -a -G gpio $USER
```

### Audio Not Playing
- Check ALSA/PulseAudio configuration
- Verify audio file paths in config.json
- Test audio output: `speaker-test -t wav`

### Web Server Not Accessible
- Check firewall settings
- Verify port 5000 is not in use
- Ensure Flask is installed: `pip install Flask`

### PIR Sensor False Positives
- Adjust sensor sensitivity (hardware adjustment)
- Increase `warning_delay` and `alarm_delay` in config.json
- Keep sensor away from heat sources and moving objects

## 📝 Logging

Logs are stored in `intrusion_log.log` with automatic rotation:
- Maximum file size: 1 MB
- Backup files: 5
- Format: `timestamp:level:message`

## 🔒 Security Notes

- The web dashboard runs on `0.0.0.0` by default (accessible from network)
- For production use, consider adding authentication
- Audio file paths are not exposed via the API
- Use HTTPS for remote access (configure reverse proxy)

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Write tests for new features
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Original concept and development by AgentVT
- Built for Raspberry Pi 5
- Uses RPi.GPIO, pygame, and Flask

## 📞 Support

For issues and questions:
- Open an issue on GitHub
- Check existing issues for solutions
- Review the troubleshooting section above

---

**Made with ❤️ for Raspberry Pi enthusiasts**
