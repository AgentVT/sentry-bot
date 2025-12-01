"""
Pytest configuration and fixtures
"""
import pytest
import json
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch


@pytest.fixture
def mock_gpio():
    """Mock RPi.GPIO module"""
    with patch('RPi.GPIO') as mock:
        mock.BCM = 'BCM'
        mock.IN = 'IN'
        mock.OUT = 'OUT'
        mock.setmode = Mock()
        mock.setup = Mock()
        mock.input = Mock(return_value=False)
        mock.cleanup = Mock()
        mock.PWM = Mock(return_value=Mock(
            start=Mock(),
            stop=Mock(),
            ChangeDutyCycle=Mock()
        ))
        yield mock


@pytest.fixture
def mock_pygame():
    """Mock pygame module"""
    with patch('pygame.mixer') as mock:
        mock.init = Mock()
        mock.quit = Mock()
        mock.Sound = Mock(return_value=Mock(play=Mock()))
        mock.get_busy = Mock(return_value=False)
        yield mock


@pytest.fixture
def mock_mutagen():
    """Mock mutagen module for MP3 reading"""
    with patch('mutagen.mp3.MP3') as mock:
        mock_instance = Mock()
        mock_instance.info.length = 2.5
        mock.return_value = mock_instance
        yield mock


@pytest.fixture
def test_config():
    """Provide test configuration"""
    return {
        "pir_pin": 27,
        "led_type": "single",
        "led_pin": 17,
        "red_pin": 17,
        "green_pin": 22,
        "blue_pin": 24,
        "pwm_frequency": 100,
        "voice_enabled": False,
        "sounds": {
            "power_on": "/tmp/powerup.mp3",
            "unauthorized": ["/tmp/unauthorized.mp3"],
            "warning": ["/tmp/warning.mp3"],
            "alarm": "/tmp/alarm.mp3",
            "power_down": "/tmp/powerdown.mp3"
        },
        "unauthorized_pause": [0.5, 1],
        "warning_delay": 3,
        "alarm_delay": 5,
        "web_server": {
            "enabled": False,
            "host": "127.0.0.1",
            "port": 5001
        }
    }


@pytest.fixture
def config_file(test_config):
    """Create temporary config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_config, f)
        config_path = f.name

    yield config_path

    # Cleanup
    if os.path.exists(config_path):
        os.remove(config_path)


@pytest.fixture
def mock_speech_recognition():
    """Mock speech recognition module"""
    with patch('speech_recognition.Recognizer') as mock:
        recognizer = Mock()
        recognizer.listen = Mock()
        recognizer.recognize_google = Mock(return_value="enable sentry mode")
        mock.return_value = recognizer
        yield mock
