#!/usr/bin/env python3
"""
SentryBot - Raspberry Pi 5 Intrusion Detection System
A modular, configurable security system with motion detection,
audio alerts, and LED indicators.
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
from typing import Optional, Tuple, List


class SystemState(Enum):
    """System operational states"""
    STANDBY = 1
    INITIALIZING = 2
    POWERING_ON = 3
    UNAUTHORIZED = 4
    WARNING = 5
    ALARM = 6
    POWERING_DOWN = 7


class LEDController:
    """Abstraction layer for LED control - supports both single and RGB LEDs"""

    def __init__(self, config: dict):
        self.led_type = config.get('led_type', 'single')  # 'single' or 'rgb'
        self.pwm_frequency = config.get('pwm_frequency', 100)

        if self.led_type == 'single':
            self.led_pin = config['led_pin']
            GPIO.setup(self.led_pin, GPIO.OUT)
            self.led_pwm = GPIO.PWM(self.led_pin, self.pwm_frequency)
            self.led_pwm.start(0)
        elif self.led_type == 'rgb':
            self.red_pin = config.get('red_pin', 17)
            self.green_pin = config.get('green_pin', 22)
            self.blue_pin = config.get('blue_pin', 24)
            GPIO.setup(self.red_pin, GPIO.OUT)
            GPIO.setup(self.green_pin, GPIO.OUT)
            GPIO.setup(self.blue_pin, GPIO.OUT)
            self.red_pwm = GPIO.PWM(self.red_pin, self.pwm_frequency)
            self.green_pwm = GPIO.PWM(self.green_pin, self.pwm_frequency)
            self.blue_pwm = GPIO.PWM(self.blue_pin, self.pwm_frequency)
            self.red_pwm.start(0)
            self.green_pwm.start(0)
            self.blue_pwm.start(0)

    def set_brightness(self, brightness: int):
        """Set LED brightness (0-100) for single LED"""
        if self.led_type == 'single':
            self.led_pwm.ChangeDutyCycle(brightness)

    def set_color(self, red: int, green: int, blue: int):
        """Set RGB LED color (0-100 per channel)"""
        if self.led_type == 'rgb':
            self.red_pwm.ChangeDutyCycle(red)
            self.green_pwm.ChangeDutyCycle(green)
            self.blue_pwm.ChangeDutyCycle(blue)
        else:
            # For single LED, use maximum of RGB values
            brightness = max(red, green, blue)
            self.set_brightness(brightness)

    def flicker(self, duration: float, color: Tuple[int, int, int] = (100, 0, 0)):
        """Flicker LED for specified duration"""
        start_time = time.time()
        while time.time() - start_time < duration:
            on_time = random.uniform(0.01, 0.1)
            off_time = random.uniform(0.01, 0.1)
            self.set_color(*color)
            time.sleep(on_time)
            self.set_color(0, 0, 0)
            time.sleep(off_time)
        self.set_color(*color)

    def fade_out(self, duration: float, from_color: Tuple[int, int, int] = (100, 0, 0)):
        """Fade out LED over specified duration"""
        start_time = time.time()
        while time.time() - start_time < duration:
            elapsed = time.time() - start_time
            progress = 1 - (elapsed / duration)
            r, g, b = from_color
            self.set_color(int(r * progress), int(g * progress), int(b * progress))
            time.sleep(0.1)
        self.set_color(0, 0, 0)

    def cleanup(self):
        """Stop PWM and cleanup"""
        if self.led_type == 'single':
            self.led_pwm.stop()
        elif self.led_type == 'rgb':
            self.red_pwm.stop()
            self.green_pwm.stop()
            self.blue_pwm.stop()


class AudioManager:
    """Manages audio playback"""

    def __init__(self, sounds_config: dict):
        self.sounds = sounds_config
        pygame.mixer.init()

    def play(self, sound_key: str, random_choice: bool = False) -> Optional[float]:
        """
        Play a sound by key from config
        Returns duration of sound played
        """
        try:
            sound_path = self.sounds.get(sound_key)
            if not sound_path:
                logging.warning(f"Sound key '{sound_key}' not found in config")
                return None

            if random_choice and isinstance(sound_path, list):
                sound_path = random.choice(sound_path)

            sound = pygame.mixer.Sound(sound_path)
            duration = MP3(sound_path).info.length
            sound.play()
            while pygame.mixer.get_busy():
                pygame.time.delay(100)
            return duration
        except Exception as e:
            logging.error(f"Failed to play sound '{sound_key}': {e}")
            return None

    def cleanup(self):
        """Cleanup mixer"""
        pygame.mixer.quit()


class VoiceController:
    """Optional voice command recognition"""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        if enabled:
            try:
                import speech_recognition as sr
                self.recognizer = sr.Recognizer()
                self.sr = sr
            except ImportError:
                logging.warning("speech_recognition not installed, voice control disabled")
                self.enabled = False

    def listen_for_activation(self, phrase: str = "enable sentry mode", timeout: int = 10) -> bool:
        """Listen for activation phrase"""
        if not self.enabled:
            return True  # If disabled, always return True (auto-activate)

        try:
            with self.sr.Microphone() as source:
                logging.info("Listening for voice activation...")
                print(f"Say '{phrase}' to activate...")
                audio = self.recognizer.listen(source, timeout=timeout)
                command = self.recognizer.recognize_google(audio).lower()
                return phrase.lower() in command
        except self.sr.UnknownValueError:
            logging.warning("Could not understand audio")
            return False
        except self.sr.RequestError as e:
            logging.error(f"Speech recognition error: {e}")
            return False
        except Exception as e:
            logging.error(f"Voice control error: {e}")
            return False


class SentryBot:
    """Main intrusion detection system"""

    def __init__(self, config_file: str = 'config.json'):
        # Load configuration
        with open(config_file, 'r') as f:
            self.config = json.load(f)

        # Setup logging
        log_handler = RotatingFileHandler(
            'intrusion_log.log',
            maxBytes=1e6,
            backupCount=5
        )
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s:%(levelname)s:%(message)s',
            handlers=[log_handler, logging.StreamHandler()]
        )

        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)
        self.pir_pin = self.config['pir_pin']
        GPIO.setup(self.pir_pin, GPIO.IN)

        # Initialize components
        self.led = LEDController(self.config)
        self.audio = AudioManager(self.config['sounds'])
        self.voice = VoiceController(self.config.get('voice_enabled', False))

        # Timing parameters
        self.unauthorized_pause = tuple(self.config.get('unauthorized_pause', [0.5, 1]))
        self.warning_delay = self.config.get('warning_delay', 3)
        self.alarm_delay = self.config.get('alarm_delay', 5)

        # State management
        self.state = SystemState.STANDBY
        self.state_lock = threading.Lock()
        self.running = True

        # Web server (optional)
        self.web_server = None
        if self.config.get('web_server', {}).get('enabled', False):
            try:
                from web_server import WebServer
                web_config = self.config['web_server']
                self.web_server = WebServer(self, web_config)
                self.web_server.start()
            except ImportError:
                logging.warning("Flask not installed, web server disabled")
            except Exception as e:
                logging.error(f"Failed to start web server: {e}")

        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        logging.info("SentryBot initialized")

    def get_state(self) -> dict:
        """Get current system state (for web API)"""
        with self.state_lock:
            return {
                'state': self.state.name,
                'timestamp': time.time(),
                'motion_detected': bool(GPIO.input(self.pir_pin))
            }

    def set_state(self, new_state: SystemState):
        """Safely update state"""
        with self.state_lock:
            old_state = self.state
            self.state = new_state
            logging.info(f"State transition: {old_state.name} -> {new_state.name}")

    def handle_standby(self):
        """Handle standby state - monitor for motion"""
        if GPIO.input(self.pir_pin):
            self.set_state(SystemState.INITIALIZING)
        else:
            time.sleep(1)

    def handle_initializing(self):
        """Handle initialization - voice activation if enabled"""
        if self.config.get('voice_enabled', False):
            self.led.set_color(100, 100, 0)  # Yellow - waiting for voice
            if self.voice.listen_for_activation():
                logging.info("Voice activation successful")
                self.set_state(SystemState.POWERING_ON)
            else:
                logging.info("Voice activation failed, returning to standby")
                self.set_state(SystemState.STANDBY)
        else:
            # Auto-activate without voice
            self.set_state(SystemState.POWERING_ON)

    def handle_powering_on(self):
        """Handle power-on sequence"""
        logging.info('Motion detected, system powering on')
        print("Status: Motion detected, system powering on")

        # Flicker LED and play power-on sound
        flicker_thread = threading.Thread(
            target=self.led.flicker,
            args=(2, (100, 0, 0))
        )
        flicker_thread.start()
        self.audio.play('power_on')
        flicker_thread.join()

        self.set_state(SystemState.UNAUTHORIZED)

    def handle_unauthorized(self):
        """Handle unauthorized access detection"""
        # Random pause before playing unauthorized sound
        pause = random.uniform(*self.unauthorized_pause)
        time.sleep(pause)

        self.audio.play('unauthorized', random_choice=True)
        time.sleep(self.warning_delay)

        if GPIO.input(self.pir_pin):
            self.set_state(SystemState.WARNING)
        else:
            self.set_state(SystemState.POWERING_DOWN)

    def handle_warning(self):
        """Handle warning state"""
        logging.info('Movement still detected, playing warning')
        print("Status: Movement still detected, playing warning")

        self.audio.play('warning', random_choice=True)
        time.sleep(self.alarm_delay)

        if GPIO.input(self.pir_pin):
            self.set_state(SystemState.ALARM)
        else:
            self.set_state(SystemState.POWERING_DOWN)

    def handle_alarm(self):
        """Handle alarm state"""
        logging.info('Intruder refuses to leave, triggering alarm')
        print("Status: Intruder refuses to leave, triggering alarm")

        self.audio.play('alarm')
        self.set_state(SystemState.POWERING_DOWN)

    def handle_powering_down(self):
        """Handle power-down sequence"""
        logging.info('No movement detected, powering down')
        print("Status: No movement detected, powering down")

        # Get power-down sound duration
        duration = self.audio.play('power_down')
        if duration:
            # Fade out LED during power-down sound
            fade_thread = threading.Thread(
                target=self.led.fade_out,
                args=(duration, (100, 0, 0))
            )
            fade_thread.start()
            fade_thread.join()
        else:
            self.led.set_color(0, 0, 0)

        self.set_state(SystemState.STANDBY)

    def run(self):
        """Main event loop"""
        logging.info("SentryBot starting main loop")
        print("SentryBot active - monitoring for motion...")

        try:
            while self.running:
                if self.state == SystemState.STANDBY:
                    self.handle_standby()
                elif self.state == SystemState.INITIALIZING:
                    self.handle_initializing()
                elif self.state == SystemState.POWERING_ON:
                    self.handle_powering_on()
                elif self.state == SystemState.UNAUTHORIZED:
                    self.handle_unauthorized()
                elif self.state == SystemState.WARNING:
                    self.handle_warning()
                elif self.state == SystemState.ALARM:
                    self.handle_alarm()
                elif self.state == SystemState.POWERING_DOWN:
                    self.handle_powering_down()
        except Exception as e:
            logging.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            self.shutdown()

    def shutdown(self, signum=None, frame=None):
        """Graceful shutdown"""
        if not self.running:
            return

        self.running = False
        logging.info("Shutting down gracefully...")
        print("\nShutting down SentryBot...")

        try:
            self.led.set_color(0, 0, 0)
            self.led.cleanup()
            self.audio.cleanup()
            GPIO.cleanup()
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")

        logging.info("Shutdown complete")
        sys.exit(0)


def main():
    """Entry point"""
    try:
        bot = SentryBot('config.json')
        bot.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
