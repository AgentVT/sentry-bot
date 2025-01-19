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
    set_led_color(100, 100, 0)  # Yellow LED for "waiting for command"
    while True:
        command = listen_for_command()
        if command and "enable sentry mode" in command:
            logging.info("Sentry mode enabled")
            play_sound(sentry_enabled_sound)
            set_led_color(100, 0, 0)  # Red LED for sentry mode
            return

def power_down_sequence():
    """
    Performs the power-down sequence, including LED fade-out and sound playback.
    """
    logging.info('No movement detected, powering down')
    power_down_duration = MP3(power_down_sound).info.length
    play_sound(power_down_sound)
    
    start_time = time.time()
    while time.time() - start_time < power_down_duration:
        elapsed_time = time.time() - start_time
        brightness = int(100 * (1 - elapsed_time / power_down_duration))
        set_led_color(brightness, 0, 0)  # Gradually fade red LED
        time.sleep(0.1)
    
    set_led_color(0, 0, 0)  # Turn off LED completely

try:
    # Initial greeting and sentry mode activation
    initialize_system()
    
    # Sentry mode routine
    while True:
        if GPIO.input(PIR_PIN):
            logging.info('Motion detected, activating sentry response')
            set_led_color(100, 0, 0)  # Red LED stays on
            # Add your motion detection routines here (e.g., sounds, more LED effects)
            time.sleep(5)  # Delay to avoid continuous triggers
            
        set_led_color(0, 100, 0)  # Green LED for "all clear" when idle
        time.sleep(1)  # Prevent immediate re-triggering
finally:
    # Stop PWM and cleanup
    red_pwm.stop()
    green_pwm.stop()
    blue_pwm.stop()
    GPIO.cleanup()
    pygame.mixer.quit()
