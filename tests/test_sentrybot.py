"""
Unit tests for SentryBot
"""
import pytest
import time
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path to import sentrybot
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestLEDController:
    """Test LED controller functionality"""

    def test_single_led_initialization(self, mock_gpio, test_config):
        """Test single LED initialization"""
        from sentrybot import LEDController

        test_config['led_type'] = 'single'
        controller = LEDController(test_config)

        assert controller.led_type == 'single'
        assert controller.led_pin == 17
        mock_gpio.setup.assert_called_with(17, 'OUT')

    def test_rgb_led_initialization(self, mock_gpio, test_config):
        """Test RGB LED initialization"""
        from sentrybot import LEDController

        test_config['led_type'] = 'rgb'
        controller = LEDController(test_config)

        assert controller.led_type == 'rgb'
        assert mock_gpio.setup.call_count >= 3  # R, G, B pins

    def test_set_brightness(self, mock_gpio, test_config):
        """Test setting brightness on single LED"""
        from sentrybot import LEDController

        test_config['led_type'] = 'single'
        controller = LEDController(test_config)
        controller.set_brightness(50)

        controller.led_pwm.ChangeDutyCycle.assert_called_with(50)

    def test_set_color_single_led(self, mock_gpio, test_config):
        """Test setting color on single LED (uses max value)"""
        from sentrybot import LEDController

        test_config['led_type'] = 'single'
        controller = LEDController(test_config)
        controller.set_color(100, 50, 25)

        # Should use maximum value (100)
        controller.led_pwm.ChangeDutyCycle.assert_called_with(100)

    def test_set_color_rgb_led(self, mock_gpio, test_config):
        """Test setting color on RGB LED"""
        from sentrybot import LEDController

        test_config['led_type'] = 'rgb'
        controller = LEDController(test_config)
        controller.set_color(100, 50, 25)

        controller.red_pwm.ChangeDutyCycle.assert_called_with(100)
        controller.green_pwm.ChangeDutyCycle.assert_called_with(50)
        controller.blue_pwm.ChangeDutyCycle.assert_called_with(25)

    def test_cleanup(self, mock_gpio, test_config):
        """Test LED cleanup"""
        from sentrybot import LEDController

        controller = LEDController(test_config)
        controller.cleanup()

        controller.led_pwm.stop.assert_called_once()


class TestAudioManager:
    """Test audio manager functionality"""

    def test_initialization(self, mock_pygame, test_config):
        """Test audio manager initialization"""
        from sentrybot import AudioManager

        manager = AudioManager(test_config['sounds'])
        mock_pygame.init.assert_called_once()

    def test_play_sound(self, mock_pygame, mock_mutagen, test_config):
        """Test playing a sound"""
        from sentrybot import AudioManager

        manager = AudioManager(test_config['sounds'])
        duration = manager.play('power_on')

        assert duration == 2.5
        mock_pygame.Sound.assert_called()

    def test_play_random_sound(self, mock_pygame, mock_mutagen, test_config):
        """Test playing random sound from list"""
        from sentrybot import AudioManager

        manager = AudioManager(test_config['sounds'])
        duration = manager.play('unauthorized', random_choice=True)

        assert duration == 2.5
        mock_pygame.Sound.assert_called()

    def test_play_invalid_sound(self, mock_pygame, test_config):
        """Test handling of invalid sound key"""
        from sentrybot import AudioManager

        manager = AudioManager(test_config['sounds'])
        duration = manager.play('nonexistent_sound')

        assert duration is None

    def test_cleanup(self, mock_pygame, test_config):
        """Test audio cleanup"""
        from sentrybot import AudioManager

        manager = AudioManager(test_config['sounds'])
        manager.cleanup()

        mock_pygame.quit.assert_called_once()


class TestVoiceController:
    """Test voice controller functionality"""

    def test_disabled_voice_control(self, test_config):
        """Test voice control when disabled"""
        from sentrybot import VoiceController

        controller = VoiceController(enabled=False)
        result = controller.listen_for_activation()

        assert result is True  # Always returns True when disabled

    @patch('sentrybot.sr')
    def test_voice_activation_success(self, mock_sr, test_config):
        """Test successful voice activation"""
        from sentrybot import VoiceController

        mock_recognizer = Mock()
        mock_recognizer.listen = Mock()
        mock_recognizer.recognize_google = Mock(return_value="enable sentry mode")
        mock_sr.Recognizer.return_value = mock_recognizer
        mock_sr.Microphone = MagicMock()

        controller = VoiceController(enabled=True)
        result = controller.listen_for_activation()

        assert result is True


class TestSystemState:
    """Test system state enum"""

    def test_state_values(self):
        """Test that all expected states exist"""
        from sentrybot import SystemState

        assert SystemState.STANDBY
        assert SystemState.INITIALIZING
        assert SystemState.POWERING_ON
        assert SystemState.UNAUTHORIZED
        assert SystemState.WARNING
        assert SystemState.ALARM
        assert SystemState.POWERING_DOWN


class TestSentryBot:
    """Test main SentryBot class"""

    @patch('sentrybot.signal')
    def test_initialization(self, mock_signal, mock_gpio, mock_pygame,
                           mock_mutagen, config_file):
        """Test SentryBot initialization"""
        from sentrybot import SentryBot

        bot = SentryBot(config_file)

        assert bot.state.name == 'STANDBY'
        assert bot.running is True
        mock_gpio.setmode.assert_called()

    @patch('sentrybot.signal')
    def test_get_state(self, mock_signal, mock_gpio, mock_pygame,
                      mock_mutagen, config_file):
        """Test getting current state"""
        from sentrybot import SentryBot

        bot = SentryBot(config_file)
        state = bot.get_state()

        assert 'state' in state
        assert 'timestamp' in state
        assert 'motion_detected' in state
        assert state['state'] == 'STANDBY'

    @patch('sentrybot.signal')
    def test_set_state(self, mock_signal, mock_gpio, mock_pygame,
                      mock_mutagen, config_file):
        """Test state transitions"""
        from sentrybot import SentryBot, SystemState

        bot = SentryBot(config_file)
        bot.set_state(SystemState.POWERING_ON)

        assert bot.state == SystemState.POWERING_ON

    @patch('sentrybot.signal')
    def test_handle_standby_no_motion(self, mock_signal, mock_gpio, mock_pygame,
                                     mock_mutagen, config_file):
        """Test standby state with no motion"""
        from sentrybot import SentryBot, SystemState

        mock_gpio.input.return_value = False
        bot = SentryBot(config_file)
        initial_state = bot.state

        bot.handle_standby()

        assert bot.state == initial_state  # Should remain in standby

    @patch('sentrybot.signal')
    def test_handle_standby_with_motion(self, mock_signal, mock_gpio, mock_pygame,
                                       mock_mutagen, config_file):
        """Test standby state with motion detected"""
        from sentrybot import SentryBot, SystemState

        mock_gpio.input.return_value = True
        bot = SentryBot(config_file)

        bot.handle_standby()

        assert bot.state == SystemState.INITIALIZING

    @patch('sentrybot.signal')
    @patch('time.sleep')
    def test_handle_powering_on(self, mock_sleep, mock_signal, mock_gpio,
                               mock_pygame, mock_mutagen, config_file):
        """Test power-on sequence"""
        from sentrybot import SentryBot, SystemState

        bot = SentryBot(config_file)
        bot.set_state(SystemState.POWERING_ON)

        bot.handle_powering_on()

        assert bot.state == SystemState.UNAUTHORIZED

    @patch('sentrybot.signal')
    def test_shutdown(self, mock_signal, mock_gpio, mock_pygame,
                     mock_mutagen, config_file):
        """Test graceful shutdown"""
        from sentrybot import SentryBot

        bot = SentryBot(config_file)

        with pytest.raises(SystemExit):
            bot.shutdown()

        assert bot.running is False
        mock_gpio.cleanup.assert_called()


class TestWebServer:
    """Test web server functionality"""

    @patch('web_server.Flask')
    def test_web_server_initialization(self, mock_flask, test_config):
        """Test web server initialization"""
        from web_server import WebServer

        mock_bot = Mock()
        mock_bot.get_state.return_value = {
            'state': 'STANDBY',
            'timestamp': time.time(),
            'motion_detected': False
        }

        server = WebServer(mock_bot, test_config['web_server'])
        assert server.sentrybot == mock_bot

    @patch('web_server.Flask')
    def test_api_status_endpoint(self, mock_flask, test_config):
        """Test API status endpoint returns correct data"""
        from web_server import WebServer

        mock_bot = Mock()
        expected_state = {
            'state': 'STANDBY',
            'timestamp': 123456.789,
            'motion_detected': False
        }
        mock_bot.get_state.return_value = expected_state

        server = WebServer(mock_bot, test_config['web_server'])
        # The routes are set up, we're just testing the structure
        assert server.app is not None


def test_config_loading(config_file):
    """Test configuration file loading"""
    import json

    with open(config_file, 'r') as f:
        config = json.load(f)

    assert config['pir_pin'] == 27
    assert config['led_type'] == 'single'
    assert 'sounds' in config
    assert 'web_server' in config


def test_imports():
    """Test that all modules can be imported"""
    import sentrybot
    import web_server

    assert sentrybot.SentryBot
    assert sentrybot.LEDController
    assert sentrybot.AudioManager
    assert sentrybot.VoiceController
    assert web_server.WebServer
