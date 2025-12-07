"""
Sentry-Bot AI-Enhanced Intrusion Detection System
=================================================
Combines the original intrusion detection with local AI features:
- Smart person/pet detection to reduce false alarms
- Face recognition for authorized users
- Local voice commands
- Dynamic text-to-speech announcements

Optimized for Raspberry Pi 5.
"""

import RPi.GPIO as GPIO
import time
import random
import logging
from logging.handlers import RotatingFileHandler
from mutagen.mp3 import MP3
import pygame
import threading
import json
import signal
import sys
from enum import Enum
from typing import Optional, Dict, Any

# Import local AI module
try:
    from local_ai import SentryAI, AlertLevel
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("Warning: local_ai module not available. Running in basic mode.")


class SystemState(Enum):
    STANDBY = 1
    POWERING_ON = 2
    UNAUTHORIZED = 3
    WARNING = 4
    ALARM = 5
    POWERING_DOWN = 6


class RGBLed:
    """RGB LED controller with PWM."""

    def __init__(self, red_pin: int, green_pin: int, blue_pin: int):
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.blue_pin = blue_pin

        GPIO.setup(red_pin, GPIO.OUT)
        GPIO.setup(green_pin, GPIO.OUT)
        GPIO.setup(blue_pin, GPIO.OUT)

        self.red_pwm = GPIO.PWM(red_pin, 100)
        self.green_pwm = GPIO.PWM(green_pin, 100)
        self.blue_pwm = GPIO.PWM(blue_pin, 100)

        self.red_pwm.start(0)
        self.green_pwm.start(0)
        self.blue_pwm.start(0)

    def set_color(self, r: int, g: int, b: int):
        """Set RGB values (0-100 for each channel)."""
        self.red_pwm.ChangeDutyCycle(r)
        self.green_pwm.ChangeDutyCycle(g)
        self.blue_pwm.ChangeDutyCycle(b)

    def off(self):
        self.set_color(0, 0, 0)

    def red(self, brightness: int = 100):
        self.set_color(brightness, 0, 0)

    def green(self, brightness: int = 100):
        self.set_color(0, brightness, 0)

    def blue(self, brightness: int = 100):
        self.set_color(0, 0, brightness)

    def yellow(self, brightness: int = 100):
        self.set_color(brightness, brightness, 0)

    def cyan(self, brightness: int = 100):
        self.set_color(0, brightness, brightness)

    def magenta(self, brightness: int = 100):
        self.set_color(brightness, 0, brightness)

    def white(self, brightness: int = 100):
        self.set_color(brightness, brightness, brightness)

    def cleanup(self):
        self.red_pwm.stop()
        self.green_pwm.stop()
        self.blue_pwm.stop()


class SentryBotAI:
    """
    AI-Enhanced Sentry Bot Intrusion Detection System.

    Features:
    - PIR motion detection with AI-powered verification
    - Face recognition for authorized users
    - Voice command control
    - Dynamic TTS announcements
    - RGB LED status indicators
    """

    # LED Colors for different states
    COLOR_STANDBY = (0, 20, 0)       # Dim green - monitoring
    COLOR_ANALYZING = (50, 50, 0)    # Yellow - analyzing
    COLOR_ALERT = (100, 0, 0)        # Red - threat detected
    COLOR_AUTHORIZED = (0, 0, 100)   # Blue - authorized person
    COLOR_WARNING = (100, 50, 0)     # Orange - warning
    COLOR_POWERING = (100, 100, 100) # White - power on/off

    def __init__(self, config_file: str = 'config.json', ai_config_file: str = 'local_ai_config.json'):
        # Load configuration
        with open(config_file, 'r') as f:
            self.config = json.load(f)

        # Setup logging
        log_handler = RotatingFileHandler(
            'sentry_ai.log',
            maxBytes=1e6,
            backupCount=5
        )
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s:%(levelname)s:%(message)s',
            handlers=[log_handler]
        )
        self.logger = logging.getLogger(__name__)

        # GPIO setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # PIR sensor
        self.PIR_PIN = self.config['pir_pin']
        GPIO.setup(self.PIR_PIN, GPIO.IN)

        # LED setup - support both single LED and RGB
        self.led_mode = self.config.get('led_mode', 'single')
        if self.led_mode == 'rgb':
            rgb_pins = self.config.get('rgb_pins', {'red': 17, 'green': 22, 'blue': 24})
            self.rgb_led = RGBLed(rgb_pins['red'], rgb_pins['green'], rgb_pins['blue'])
            self.led_pwm = None
        else:
            self.LED_PIN = self.config['led_pin']
            GPIO.setup(self.LED_PIN, GPIO.OUT)
            self.led_pwm = GPIO.PWM(self.LED_PIN, 100)
            self.led_pwm.start(0)
            self.rgb_led = None

        # Sound configuration
        self.sounds = self.config['sounds']
        self.unauthorized_pause = self.config.get('unauthorized_pause', (0.5, 1))
        self.warning_delay = self.config.get('warning_delay', 3)
        self.alarm_delay = self.config.get('alarm_delay', 5)

        # Initialize Pygame mixer
        pygame.mixer.init()

        # State machine
        self.state = SystemState.STANDBY
        self._armed = True
        self._silenced = False

        # Initialize AI if available
        self.ai: Optional[SentryAI] = None
        self.ai_enabled = False
        if AI_AVAILABLE:
            try:
                self.ai = SentryAI(ai_config_file)
                if self.ai.initialize():
                    self.ai_enabled = True
                    self._setup_ai_callbacks()
                    self.logger.info("AI features initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize AI: {e}")

        # Statistics
        self.stats = {
            'total_detections': 0,
            'false_alarms_prevented': 0,
            'authorized_bypasses': 0,
            'voice_commands': 0
        }

        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        self.logger.info("Sentry-Bot AI System initialized")

    def _setup_ai_callbacks(self):
        """Register callbacks for AI voice commands."""
        if self.ai:
            self.ai.register_callback('activate', self.arm)
            self.ai.register_callback('deactivate', self.disarm)
            self.ai.register_callback('silence', self.silence_alarm)

    def set_led_color(self, r: int, g: int, b: int):
        """Set LED color (works for both RGB and single LED)."""
        if self.rgb_led:
            self.rgb_led.set_color(r, g, b)
        elif self.led_pwm:
            # For single LED, use average brightness
            brightness = (r + g + b) // 3
            self.led_pwm.ChangeDutyCycle(brightness)

    def flicker_led(self, duration: float, color: tuple = (100, 100, 100)):
        """Flicker LED effect during power on."""
        start_time = time.time()
        while time.time() - start_time < duration:
            on_time = random.uniform(0.01, 0.1)
            off_time = random.uniform(0.01, 0.1)
            self.set_led_color(*color)
            time.sleep(on_time)
            self.set_led_color(0, 0, 0)
            time.sleep(off_time)
        self.set_led_color(*color)

    def play_sound(self, file_path: str):
        """Play an audio file."""
        if self._silenced:
            return
        try:
            sound = pygame.mixer.Sound(file_path)
            sound.play()
            while pygame.mixer.get_busy():
                pygame.time.delay(100)
        except pygame.error as e:
            self.logger.error(f"Failed to play sound {file_path}: {e}")

    def speak(self, text: str, block: bool = True):
        """Use AI TTS to speak, fallback to print."""
        if self._silenced:
            return
        if self.ai_enabled and self.ai.tts.is_ready:
            self.ai.speak(text, block)
        else:
            print(f"[SENTRY]: {text}")

    def speak_dynamic(self, response_type: str, **kwargs):
        """Speak a dynamic AI-generated response."""
        if self._silenced:
            return
        if self.ai_enabled and self.ai.tts.is_ready:
            self.ai.speak_dynamic(response_type, **kwargs)

    def arm(self):
        """Arm the security system."""
        self._armed = True
        self._silenced = False
        self.logger.info("System ARMED")
        self.speak_dynamic('system_armed')
        self.stats['voice_commands'] += 1

    def disarm(self):
        """Disarm the security system."""
        self._armed = False
        self.state = SystemState.STANDBY
        self.logger.info("System DISARMED")
        self.speak_dynamic('system_disarmed')
        self.set_led_color(0, 0, 50)  # Blue for disarmed
        self.stats['voice_commands'] += 1

    def silence_alarm(self):
        """Silence current alarm."""
        self._silenced = True
        pygame.mixer.stop()
        self.logger.info("Alarm silenced")
        self.stats['voice_commands'] += 1

    def analyze_with_ai(self) -> Dict[str, Any]:
        """
        Use AI to analyze the current situation.
        Returns analysis results.
        """
        if not self.ai_enabled:
            return {
                'should_alert': True,
                'alert_level': AlertLevel.MEDIUM,
                'authorized_person': None,
                'announcement': None
            }

        # Set LED to yellow while analyzing
        self.set_led_color(*self.COLOR_ANALYZING)

        # Run AI analysis
        result = self.ai.analyze_motion(pir_triggered=True)

        return result

    def handle_standby(self):
        """Handle standby state - monitoring for motion."""
        # Show green standby LED
        self.set_led_color(*self.COLOR_STANDBY)

        if GPIO.input(self.PIR_PIN) and self._armed:
            self.stats['total_detections'] += 1
            self.logger.info("Motion detected - analyzing...")

            # Use AI to analyze before escalating
            if self.ai_enabled:
                analysis = self.analyze_with_ai()

                if not analysis['should_alert']:
                    # AI determined this is not a threat
                    self.stats['false_alarms_prevented'] += 1

                    if analysis.get('authorized_person'):
                        # Recognized authorized person
                        self.stats['authorized_bypasses'] += 1
                        self.set_led_color(*self.COLOR_AUTHORIZED)
                        name = analysis['authorized_person']
                        self.logger.info(f"Authorized person detected: {name}")

                        if analysis.get('announcement'):
                            self.speak(analysis['announcement'])

                        time.sleep(3)
                        return  # Don't escalate

                    elif analysis.get('announcement'):
                        # Pet or other non-threat
                        self.speak(analysis['announcement'])
                        time.sleep(2)
                        return

                # AI says we should alert
                if analysis.get('announcement'):
                    self.speak(analysis['announcement'])

            self.state = SystemState.POWERING_ON
        else:
            time.sleep(0.5)  # Reduce CPU usage in standby

    def handle_powering_on(self):
        """Handle power-on sequence."""
        self.logger.info("Motion confirmed - system powering on")
        print("Status: Motion detected, system powering on")

        # Flicker LED during power up
        flicker_thread = threading.Thread(
            target=self.flicker_led,
            args=(2, self.COLOR_POWERING)
        )
        flicker_thread.start()
        self.play_sound(self.sounds['power_on'])
        flicker_thread.join()

        self.set_led_color(*self.COLOR_ALERT)
        self.state = SystemState.UNAUTHORIZED

    def handle_unauthorized(self):
        """Handle unauthorized access detection."""
        self._silenced = False  # Reset silence for new detection

        pause_duration = random.uniform(*self.unauthorized_pause)
        time.sleep(pause_duration)

        # Play unauthorized sound
        self.play_sound(random.choice(self.sounds['unauthorized']))

        time.sleep(self.warning_delay)

        # Check if motion persists
        if GPIO.input(self.PIR_PIN):
            # Re-analyze with AI
            if self.ai_enabled:
                analysis = self.analyze_with_ai()
                if not analysis['should_alert']:
                    self.logger.info("AI cleared threat during warning phase")
                    self.state = SystemState.POWERING_DOWN
                    return

            self.state = SystemState.WARNING
        else:
            self.state = SystemState.POWERING_DOWN

    def handle_warning(self):
        """Handle warning state."""
        self.logger.info("Movement persists - issuing warning")
        print("Status: Movement still detected, playing warning")

        self.set_led_color(*self.COLOR_WARNING)
        self.play_sound(random.choice(self.sounds['warning']))

        time.sleep(self.alarm_delay)

        if GPIO.input(self.PIR_PIN):
            self.state = SystemState.ALARM
        else:
            self.state = SystemState.POWERING_DOWN

    def handle_alarm(self):
        """Handle full alarm state."""
        self.logger.info("ALARM: Intruder refuses to leave")
        print("Status: Intruder refuses to leave, triggering alarm")

        # Flash red rapidly
        for _ in range(10):
            self.set_led_color(100, 0, 0)
            time.sleep(0.1)
            self.set_led_color(0, 0, 0)
            time.sleep(0.1)

        self.set_led_color(100, 0, 0)
        self.play_sound(self.sounds['alarm'])

        self.state = SystemState.POWERING_DOWN

    def power_down_sequence(self):
        """Execute power down sequence with LED fade."""
        self.logger.info("Powering down")
        print("Status: No movement detected, powering down")

        power_down_duration = MP3(self.sounds['power_down']).info.length

        def fade_out_led():
            start_time = time.time()
            while time.time() - start_time < power_down_duration:
                elapsed = time.time() - start_time
                brightness = int(100 * (1 - elapsed / power_down_duration))
                self.set_led_color(brightness, brightness, brightness)
                time.sleep(0.1)
            self.set_led_color(0, 0, 0)

        fade_thread = threading.Thread(target=fade_out_led)
        fade_thread.start()
        self.play_sound(self.sounds['power_down'])
        fade_thread.join()

        self._silenced = False

    def run(self):
        """Main run loop."""
        self.logger.info("Sentry-Bot AI System starting...")
        print("\n" + "=" * 50)
        print("SENTRY-BOT AI SYSTEM")
        print("=" * 50)
        print(f"AI Features: {'Enabled' if self.ai_enabled else 'Disabled'}")
        if self.ai_enabled:
            print(f"  - Object Detection: {'Ready' if self.ai.object_detector.is_ready else 'N/A'}")
            print(f"  - Face Recognition: {'Ready' if self.ai.face_recognizer.is_ready else 'N/A'}")
            print(f"  - Voice Commands: {'Ready' if self.ai.voice_recognizer.is_ready else 'N/A'}")
            print(f"  - Text-to-Speech: {'Ready' if self.ai.tts.is_ready else 'N/A'}")
        print("=" * 50 + "\n")

        # Start AI services
        if self.ai_enabled:
            self.ai.start()
            self.speak("Sentry Bot AI system online and monitoring.")

        try:
            while True:
                if self.state == SystemState.STANDBY:
                    self.handle_standby()
                elif self.state == SystemState.POWERING_ON:
                    self.handle_powering_on()
                elif self.state == SystemState.UNAUTHORIZED:
                    self.handle_unauthorized()
                elif self.state == SystemState.WARNING:
                    self.handle_warning()
                elif self.state == SystemState.ALARM:
                    self.handle_alarm()
                elif self.state == SystemState.POWERING_DOWN:
                    self.power_down_sequence()
                    self.state = SystemState.STANDBY

        except Exception as e:
            self.logger.error(f"Runtime error: {e}")
            raise
        finally:
            self.shutdown()

    def print_stats(self):
        """Print session statistics."""
        print("\n" + "=" * 50)
        print("SESSION STATISTICS")
        print("=" * 50)
        print(f"Total Detections: {self.stats['total_detections']}")
        print(f"False Alarms Prevented: {self.stats['false_alarms_prevented']}")
        print(f"Authorized Bypasses: {self.stats['authorized_bypasses']}")
        print(f"Voice Commands: {self.stats['voice_commands']}")
        if self.stats['total_detections'] > 0:
            prevention_rate = (self.stats['false_alarms_prevented'] / self.stats['total_detections']) * 100
            print(f"False Alarm Prevention Rate: {prevention_rate:.1f}%")
        print("=" * 50)

    def shutdown(self, signum=None, frame=None):
        """Graceful shutdown."""
        self.logger.info("Shutting down...")
        print("\nShutting down Sentry-Bot...")

        self.print_stats()

        # Stop AI services
        if self.ai_enabled and self.ai:
            self.ai.cleanup()

        # Power down
        self.power_down_sequence()

        # Cleanup GPIO
        if self.led_pwm:
            self.led_pwm.stop()
        if self.rgb_led:
            self.rgb_led.cleanup()

        GPIO.cleanup()
        pygame.mixer.quit()

        self.logger.info("Shutdown complete")
        sys.exit(0)


if __name__ == "__main__":
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Sentry-Bot AI Security System')
    parser.add_argument('--config', default='config.json', help='Main config file')
    parser.add_argument('--ai-config', default='local_ai_config.json', help='AI config file')
    parser.add_argument('--no-ai', action='store_true', help='Disable AI features')
    args = parser.parse_args()

    if args.no_ai:
        AI_AVAILABLE = False

    system = SentryBotAI(args.config, args.ai_config)
    system.run()
