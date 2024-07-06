import RPi.GPIO as GPIO
import time
import random
import logging
from mutagen.mp3 import MP3
import pygame
import threading

class IntrusionDetectionSystem:
    def __init__(self, pir_pin, led_pin, sounds):
        # Setup logging
        logging.basicConfig(filename='intrusion_log.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

        # Define GPIO pins
        self.PIR_PIN = pir_pin
        self.LED_PIN = led_pin

        # GPIO setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.PIR_PIN, GPIO.IN)
        GPIO.setup(self.LED_PIN, GPIO.OUT)

        # Setup PWM on the LED pin
        self.led_pwm = GPIO.PWM(self.LED_PIN, 100)  # Frequency set to 100 Hz
        self.led_pwm.start(0)  # Start with the LED off

        # Sound file paths
        self.power_on_sound = sounds['power_on']
        self.unauthorized_sounds = sounds['unauthorized']
        self.warning_sounds = sounds['warning']
        self.alarm_sound = sounds['alarm']
        self.power_down_sound = sounds['power_down']

        # Initialize Pygame mixer
        pygame.mixer.init()

    def flicker_led(self, duration, intensity=100):
        """
        Flickers the LED for a given duration using PWM for intensity control.
        """
        start_time = time.time()
        while time.time() - start_time < duration:
            on_time = random.uniform(0.01, 0.1)  # Shortened flicker times
            off_time = random.uniform(0.01, 0.1)
            self.led_pwm.ChangeDutyCycle(intensity)  # Set PWM duty cycle for brightness
            time.sleep(on_time)
            self.led_pwm.ChangeDutyCycle(0)  # Turn off LED
            time.sleep(off_time)
        self.led_pwm.ChangeDutyCycle(intensity)  # Keep the LED on after flickering

    def play_sound(self, file_path):
        """
        Plays a sound file using Pygame mixer.
        """
        sound = pygame.mixer.Sound(file_path)
        sound.play()
        while pygame.mixer.get_busy():
            pygame.time.delay(100)  # Wait until the sound finishes playing

    def power_down_sequence(self):
        """
        Performs the power-down sequence, including LED fade-out and sound playback.
        """
        logging.info('No movement detected, powering down')
        print("Status: No movement detected, powering down")
        power_down_duration = MP3(self.power_down_sound).info.length

        def fade_out_led():
            start_time = time.time()
            while time.time() - start_time < power_down_duration:
                elapsed_time = time.time() - start_time
                brightness = int(100 * (1 - elapsed_time / power_down_duration))
                self.led_pwm.ChangeDutyCycle(brightness)
                time.sleep(0.1)
            self.led_pwm.ChangeDutyCycle(0)  # Ensure LED is fully off

        fade_out_thread = threading.Thread(target=fade_out_led)
        fade_out_thread.start()
        self.play_sound(self.power_down_sound)
        fade_out_thread.join()

    def run(self):
        try:
            standby_message_printed = False  # Flag to indicate if standby message has been printed
            while True:
                if GPIO.input(self.PIR_PIN):
                    logging.info('Motion detected, system powering on')
                    print("Status: Motion detected, system powering on")
                    flicker_thread = threading.Thread(target=self.flicker_led, args=(2, 100))
                    flicker_thread.start()
                    self.play_sound(self.power_on_sound)
                    flicker_thread.join()

                    # Pause for 1-3 seconds before playing the unauthorized sound
                    pause_duration = random.uniform(0.5, 1)
                    time.sleep(pause_duration)
                    self.play_sound(random.choice(self.unauthorized_sounds))

                    # Wait for 5 seconds after the unauthorized sound finishes
                    time.sleep(3)

                    if GPIO.input(self.PIR_PIN):
                        logging.info('Movement still detected, playing warning')
                        print("Status: Movement still detected, playing warning")
                        self.play_sound(random.choice(self.warning_sounds))

                        # Wait for 5 seconds after the warning finishes
                        time.sleep(5)

                        if GPIO.input(self.PIR_PIN):
                            logging.info('Intruder refuses to leave, triggering alarm')
                            print("Status: Intruder refuses to leave, triggering alarm")
                            self.play_sound(self.alarm_sound)
                            logging.info('Alarm sound played, initiating power-down sequence')
                            self.power_down_sequence()
                        else:
                            logging.info('Intruder left after warning, powering down')
                            print("Status: Intruder left after warning, powering down")
                            self.power_down_sequence()
                    else:
                        logging.info('Intruder left after unauthorized sound, powering down')
                        print("Status: Intruder left after unauthorized sound, powering down")
                        self.power_down_sequence()
                    standby_message_printed = False  # Reset the standby message flag
                else:
                    if not standby_message_printed:
                        logging.info('No movement detected, system in standby')
                        print("Status: No movement detected, system in standby")
                        standby_message_printed = True  # Set the standby message flag
                    time.sleep(3)  # Delay to prevent immediate re-triggering

        finally:
            self.led_pwm.stop()  # Stop the PWM
            GPIO.cleanup()  # Clean up at the end
            pygame.mixer.quit()  # Quit Pygame mixer

if __name__ == "__main__":
    sounds = {
        'power_on': '/home/domin/JARVIS/sounds/powerup1.mp3',
        'unauthorized': [
            '/home/domin/JARVIS/sounds/unauthorized.mp3',
            '/home/domin/JARVIS/sounds/Unauthorized1.mp3',
            '/home/domin/JARVIS/sounds/Unauthorized2.mp3',
            '/home/domin/JARVIS/sounds/Unauthorized3.mp3'
        ],
        'warning': [
            '/home/domin/JARVIS/sounds/2ndrequest.mp3',
            '/home/domin/JARVIS/sounds/2ndrequest1.mp3',
            '/home/domin/JARVIS/sounds/alert1.mp3',
            '/home/domin/JARVIS/sounds/Alert2.mp3',
            '/home/domin/JARVIS/sounds/alert3.mp3',
            '/home/domin/JARVIS/sounds/DrEtli.mp3'
        ],
        'alarm': '/home/domin/JARVIS/sounds/alarm.mp3',
        'power_down': '/home/domin/JARVIS/sounds/powerdown.mp3'
    }

    system = IntrusionDetectionSystem(pir_pin=27, led_pin=17, sounds=sounds)
    system.run()
