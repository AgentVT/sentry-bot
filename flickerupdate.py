import RPi.GPIO as GPIO
import time
import random
import logging
from mutagen.mp3 import MP3
import pygame
import speech_recognition as sr  # For voice commands

# Setup logging
logging.basicConfig(filename='intrusion_log.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

# Define GPIO pins for RGB LED
RED_PIN = 17
GREEN_PIN = 22
BLUE_PIN = 24
PIR_PIN = 27

# GPIO setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)
GPIO.setup(RED_PIN, GPIO.OUT)
GPIO.setup(GREEN_PIN, GPIO.OUT)
GPIO.setup(BLUE_PIN, GPIO.OUT)

# Setup PWM on the RGB pins
red_pwm = GPIO.PWM(RED_PIN, 100)    # Frequency set to 100 Hz
green_pwm = GPIO.PWM(GREEN_PIN, 100)
blue_pwm = GPIO.PWM(BLUE_PIN, 100)

# Start all PWM channels off
red_pwm.start(0)
green_pwm.start(0)
blue_pwm.start(0)

# Define sound file paths
greeting_sound = '/home/domin/JARVIS/sounds/greeting.mp3'
sentry_enabled_sound = '/home/domin/JARVIS/sounds/sentry_enabled.mp3'
power_down_sound = '/home/domin/JARVIS/sounds/powerdown.mp3'

# Initialize Pygame mixer
pygame.mixer.init()

def play_sound(file_path):
    """
    Plays a sound file using Pygame mixer.
    """
    sound = pygame.mixer.Sound(file_path)
    sound.play()
    while pygame.mixer.get_busy():
        pygame.time.delay(100)  # Wait until the sound finishes playing

def set_led_color(red, green, blue):
    """
    Sets the RGB LED color by adjusting the PWM duty cycles.
    :param red: Brightness of red channel (0-100)
    :param green: Brightness of green channel (0-100)
    :param blue: Brightness of blue channel (0-100)
    """
    red_pwm.ChangeDutyCycle(red)
    green_pwm.ChangeDutyCycle(green)
    blue_pwm.ChangeDutyCycle(blue)

def flicker_led(duration, color=(100, 0, 0)):
    """
    Flickers the RGB LED for a given duration using random on/off intervals.
    :param duration: Duration of the flickering effect in seconds.
    :param color: Tuple (red, green, blue) for the LED color during flickering.
    """
    start_time = time.time()
    while time.time() - start_time < duration:
        on_time = random.uniform(0.05, 0.2)  # Random on-time duration
        off_time = random.uniform(0.05, 0.2)  # Random off-time duration
        set_led_color(*color)
        time.sleep(on_time)
        set_led_color(0, 0, 0)
        time.sleep(off_time)
    set_led_color(*color)  # Ensure LED stays on after flickering

def listen_for_command():
    """
    Listens for voice commands and returns the detected phrase.
    """
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening for the activation command...")
        try:
            audio = recognizer.listen(source, timeout=10)  # Listen for 10 seconds max
            command = recognizer.recognize_google(audio)
            return command.lower()
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            logging.error(f"Speech recognition error: {e}")
            return None

def initialize_system():
    """
    Plays the greeting sound and waits for the "Enable Sentry Mode" command.
    """
    play_sound(greeting_sound)
    flicker_led(2, color=(100, 100, 0))  # Flicker yellow LED
    while True:
        command = listen_for_command()
        if command and "enable sentry mode" in command:
            logging.info("Sentry mode enabled")
            play_sound(sentry_enabled_sound)
            flicker_led(2, color=(100, 0, 0))  # Flicker red LED
            return

def power_down_sequence():
    """
    Performs the power-down sequence, including LED flickering and sound playback.
    """
    logging.info('No movement detected, powering down')
    power_down_duration = MP3(power_down_sound).info.length
    flicker_led(2, color=(100, 0, 0))  # Flicker red LED before power-down
    play_sound(power_down_sound)
    # Gradually fade out LED during power-down sound
   
