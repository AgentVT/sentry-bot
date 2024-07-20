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

class SystemState(Enum):
    STANDBY = 1
    POWERING_ON = 2
    UNAUTHORIZED = 3
    WARNING = 4
    ALARM = 5
    POWERING_DOWN = 6

class IntrusionDetectionSystem:
    def __init__(self, config_file):
        # Load configuration
        with open(config_file, 'r') as f:
            config = json.load(f)

        # Setup logging with rotation
        log_handler = RotatingFileHandler('intrusion_log.log', maxBytes=1e6, backupCount=5)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s', handlers=[log_handler])

        # Define GPIO pins from config
        self.PIR_PIN = config['pir_pin']
        self.LED_PIN = config['led_pin']

        # GPIO setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.PIR_PIN, GPIO.IN)
        GPIO.setup(self.LED_PIN, GPIO.OUT)

        # Setup PWM on the LED pin
        self.led_pwm = GPIO.PWM(self.LED_PIN, 100)
        self.led_pwm.start(0)

        # Sound file paths from config
        self.sounds = config['sounds']

        # Timing parameters from config
        self.unauthorized_pause = config.get('unauthorized_pause', (0.5, 1))
        self.warning_delay = config.get('warning_delay', 3)
        self.alarm_delay = config.get('alarm_delay', 5)

        # Initialize Pygame mixer
        pygame.mixer.init()

        # Set initial state
        self.state = SystemState.STANDBY

        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

    def flicker_led(self, duration, intensity=100):
        start_time = time.time()
        while time.time() - start_time < duration:
            on_time = random.uniform(0.01, 0.1)
            off_time = random.uniform(0.01, 0.1)
            self.led_pwm.ChangeDutyCycle(intensity)
            time.sleep(on_time)
            self.led_pwm.ChangeDutyCycle(0)
            time.sleep(off_time)
        self.led_pwm.ChangeDutyCycle(intensity)

    def play_sound(self, file_path):
        try:
            sound = pygame.mixer.Sound(file_path)
            sound.play()
            while pygame.mixer.get_busy():
                pygame.time.delay(100)
        except pygame.error as e:
            logging.error(f"Failed to play sound {file_path}: {e}")

    def power_down_sequence(self):
        logging.info('No movement detected, powering down')
        print("Status: No movement detected, powering down")
        power_down_duration = MP3(self.sounds['power_down']).info.length

        def fade_out_led():
            start_time = time.time()
            while time.time() - start_time < power_down_duration:
                elapsed_time = time.time() - start_time
                brightness = int(100 * (1 - elapsed_time / power_down_duration))
                self.led_pwm.ChangeDutyCycle(brightness)
                time.sleep(0.1)
            self.led_pwm.ChangeDutyCycle(0)

        fade_out_thread = threading.Thread(target=fade_out_led)
        fade_out_thread.start()
        self.play_sound(self.sounds['power_down'])
        fade_out_thread.join()

    def handle_standby(self):
        if GPIO.input(self.PIR_PIN):
            self.state = SystemState.POWERING_ON
        else:
            time.sleep(1)

    def handle_powering_on(self):
        logging.info('Motion detected, system powering on')
        print("Status: Motion detected, system powering on")
        flicker_thread = threading.Thread(target=self.flicker_led, args=(2, 100))
        flicker_thread.start()
        self.play_sound(self.sounds['power_on'])
        flicker_thread.join()
        self.state = SystemState.UNAUTHORIZED

    def handle_unauthorized(self):
        pause_duration = random.uniform(*self.unauthorized_pause)
        time.sleep(pause_duration)
        self.play_sound(random.choice(self.sounds['unauthorized']))
        time.sleep(self.warning_delay)
        if GPIO.input(self.PIR_PIN):
            self.state = SystemState.WARNING
        else:
            self.state = SystemState.POWERING_DOWN

    def handle_warning(self):
        logging.info('Movement still detected, playing warning')
        print("Status: Movement still detected, playing warning")
        self.play_sound(random.choice(self.sounds['warning']))
        time.sleep(self.alarm_delay)
        if GPIO.input(self.PIR_PIN):
            self.state = SystemState.ALARM
        else:
            self.state = SystemState.POWERING_DOWN

    def handle_alarm(self):
        logging.info('Intruder refuses to leave, triggering alarm')
        print("Status: Intruder refuses to leave, triggering alarm")
        self.play_sound(self.sounds['alarm'])
        self.state = SystemState.POWERING_DOWN

    def run(self):
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
        finally:
            self.shutdown()

    def shutdown(self, signum=None, frame=None):
        logging.info("Shutting down gracefully...")
        self.power_down_sequence()
        self.led_pwm.stop()
        GPIO.cleanup()
        pygame.mixer.quit()
        sys.exit(0)

if __name__ == "__main__":
    system = IntrusionDetectionSystem('config.json')
    system.run()
