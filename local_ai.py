"""
Local AI Module for Sentry-Bot
==============================
100% offline AI features for Raspberry Pi 5:
- Object/Person Detection (TensorFlow Lite)
- Face Recognition (dlib/face_recognition)
- Voice Commands (Vosk)
- Text-to-Speech (Piper)
- Smart Alert Management

Optimized for Raspberry Pi 5 with optional GPU acceleration.
"""

import json
import logging
import os
import queue
import random
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any

import numpy as np

# Configure logging
logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Classification of detection alert levels."""
    IGNORE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Detection:
    """Represents a single detection event."""
    timestamp: datetime
    detection_type: str  # 'person', 'pet', 'vehicle', 'motion', 'face', 'voice'
    confidence: float
    alert_level: AlertLevel
    bounding_box: Optional[Tuple[int, int, int, int]] = None  # x, y, w, h
    identity: Optional[str] = None  # For face recognition
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'detection_type': self.detection_type,
            'confidence': self.confidence,
            'alert_level': self.alert_level.name,
            'bounding_box': self.bounding_box,
            'identity': self.identity,
            'metadata': self.metadata
        }


class BaseAIModule(ABC):
    """Base class for all AI modules."""

    def __init__(self, config: Dict):
        self.config = config
        self.enabled = config.get('enabled', False)
        self._initialized = False

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the module. Returns True if successful."""
        pass

    @abstractmethod
    def cleanup(self):
        """Clean up resources."""
        pass

    @property
    def is_ready(self) -> bool:
        return self.enabled and self._initialized


# =============================================================================
# OBJECT DETECTION MODULE (TensorFlow Lite)
# =============================================================================

class ObjectDetector(BaseAIModule):
    """
    Person/Object detection using TensorFlow Lite.
    Optimized for Raspberry Pi 5 with optional EdgeTPU support.
    """

    COCO_LABELS = {
        0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane',
        5: 'bus', 6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light',
        14: 'bird', 15: 'cat', 16: 'dog', 17: 'horse', 18: 'sheep',
        19: 'cow', 20: 'elephant', 21: 'bear', 22: 'zebra', 23: 'giraffe'
    }

    def __init__(self, config: Dict):
        super().__init__(config)
        self.model_path = config.get('model_path', 'models/detect.tflite')
        self.labels_path = config.get('labels_path', 'models/labelmap.txt')
        self.confidence_threshold = config.get('confidence_threshold', 0.5)
        self.detection_classes = config.get('detection_classes', {})
        self.resolution = tuple(config.get('resolution', [640, 480]))

        self.interpreter = None
        self.input_details = None
        self.output_details = None
        self.labels = {}
        self.camera = None
        self._capture_thread = None
        self._running = False
        self._frame_queue = queue.Queue(maxsize=2)

    def initialize(self) -> bool:
        """Initialize TFLite interpreter and camera."""
        try:
            # Try importing TensorFlow Lite
            try:
                from tflite_runtime.interpreter import Interpreter
            except ImportError:
                try:
                    from tensorflow.lite.python.interpreter import Interpreter
                except ImportError:
                    logger.warning("TensorFlow Lite not available. Object detection disabled.")
                    return False

            # Check if model exists
            if not os.path.exists(self.model_path):
                logger.warning(f"Model not found at {self.model_path}. Run setup_models.sh first.")
                return False

            # Load the model
            self.interpreter = Interpreter(model_path=self.model_path, num_threads=4)
            self.interpreter.allocate_tensors()

            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()

            # Load labels
            self._load_labels()

            # Initialize camera
            if not self._init_camera():
                logger.warning("Camera initialization failed. Object detection disabled.")
                return False

            self._initialized = True
            logger.info("Object detector initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize object detector: {e}")
            return False

    def _load_labels(self):
        """Load label map from file or use defaults."""
        if os.path.exists(self.labels_path):
            with open(self.labels_path, 'r') as f:
                self.labels = {i: line.strip() for i, line in enumerate(f.readlines())}
        else:
            self.labels = self.COCO_LABELS

    def _init_camera(self) -> bool:
        """Initialize PiCamera2 for Raspberry Pi 5."""
        try:
            from picamera2 import Picamera2
            self.camera = Picamera2()
            camera_config = self.camera.create_preview_configuration(
                main={"size": self.resolution, "format": "RGB888"}
            )
            self.camera.configure(camera_config)
            self.camera.start()
            time.sleep(0.5)  # Allow camera to warm up
            return True
        except Exception as e:
            logger.error(f"PiCamera2 init failed: {e}")
            # Fallback to OpenCV
            try:
                import cv2
                self.camera = cv2.VideoCapture(0)
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
                return self.camera.isOpened()
            except Exception as e2:
                logger.error(f"OpenCV camera init failed: {e2}")
                return False

    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame from the camera."""
        if not self.is_ready:
            return None

        try:
            if hasattr(self.camera, 'capture_array'):
                # PiCamera2
                return self.camera.capture_array()
            else:
                # OpenCV
                ret, frame = self.camera.read()
                if ret:
                    import cv2
                    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return None
        except Exception as e:
            logger.error(f"Frame capture failed: {e}")
            return None

    def detect(self, frame: Optional[np.ndarray] = None) -> List[Detection]:
        """
        Run object detection on a frame.
        Returns list of Detection objects.
        """
        if not self.is_ready:
            return []

        if frame is None:
            frame = self.capture_frame()
            if frame is None:
                return []

        detections = []

        try:
            # Preprocess frame
            input_shape = self.input_details[0]['shape']
            height, width = input_shape[1], input_shape[2]

            # Resize and normalize
            import cv2
            resized = cv2.resize(frame, (width, height))
            input_data = np.expand_dims(resized, axis=0)

            # Handle quantized models
            if self.input_details[0]['dtype'] == np.uint8:
                input_data = input_data.astype(np.uint8)
            else:
                input_data = (input_data / 255.0).astype(np.float32)

            # Run inference
            self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
            self.interpreter.invoke()

            # Get results (format depends on model)
            boxes = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
            classes = self.interpreter.get_tensor(self.output_details[1]['index'])[0]
            scores = self.interpreter.get_tensor(self.output_details[2]['index'])[0]

            # Process detections
            h, w = frame.shape[:2]
            for i in range(len(scores)):
                if scores[i] >= self.confidence_threshold:
                    class_id = int(classes[i])
                    label = self.labels.get(class_id, 'unknown')

                    # Get alert level from config
                    class_config = self.detection_classes.get(label, {})
                    alert_level_str = class_config.get('alert_level', 'low')
                    alert_level = AlertLevel[alert_level_str.upper()]

                    # Calculate bounding box
                    ymin, xmin, ymax, xmax = boxes[i]
                    bbox = (
                        int(xmin * w),
                        int(ymin * h),
                        int((xmax - xmin) * w),
                        int((ymax - ymin) * h)
                    )

                    detection = Detection(
                        timestamp=datetime.now(),
                        detection_type=label,
                        confidence=float(scores[i]),
                        alert_level=alert_level,
                        bounding_box=bbox,
                        metadata={'class_id': class_id}
                    )
                    detections.append(detection)

        except Exception as e:
            logger.error(f"Detection failed: {e}")

        return detections

    def detect_persons(self) -> Tuple[bool, List[Detection]]:
        """
        Quick check: Is there a person in frame?
        Returns (person_detected, all_detections)
        """
        detections = self.detect()
        person_detections = [d for d in detections if d.detection_type == 'person']
        return len(person_detections) > 0, detections

    def cleanup(self):
        """Release camera resources."""
        self._running = False
        if self.camera is not None:
            try:
                if hasattr(self.camera, 'stop'):
                    self.camera.stop()
                elif hasattr(self.camera, 'release'):
                    self.camera.release()
            except:
                pass
        self._initialized = False


# =============================================================================
# FACE RECOGNITION MODULE
# =============================================================================

class FaceRecognizer(BaseAIModule):
    """
    Face recognition for identifying authorized users.
    Uses face_recognition library (dlib-based) or MediaPipe as fallback.
    """

    def __init__(self, config: Dict):
        super().__init__(config)
        self.authorized_faces_dir = Path(config.get('authorized_faces_dir', 'authorized_faces'))
        self.recognition_threshold = config.get('recognition_threshold', 0.6)
        self.captures_dir = Path(config.get('unknown_face_captures_dir', 'captured_faces'))
        self.announce_recognized = config.get('announce_recognized', True)

        self.known_encodings = []
        self.known_names = []
        self._face_recognition = None

    def initialize(self) -> bool:
        """Load face_recognition library and authorized face encodings."""
        try:
            import face_recognition
            self._face_recognition = face_recognition

            # Create directories if needed
            self.authorized_faces_dir.mkdir(parents=True, exist_ok=True)
            self.captures_dir.mkdir(parents=True, exist_ok=True)

            # Load known faces
            self._load_authorized_faces()

            self._initialized = True
            logger.info(f"Face recognizer initialized with {len(self.known_names)} known faces")
            return True

        except ImportError:
            logger.warning("face_recognition library not available. Face recognition disabled.")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize face recognizer: {e}")
            return False

    def _load_authorized_faces(self):
        """Load and encode all authorized faces from the directory."""
        self.known_encodings = []
        self.known_names = []

        for img_path in self.authorized_faces_dir.glob('*.jpg'):
            try:
                image = self._face_recognition.load_image_file(str(img_path))
                encodings = self._face_recognition.face_encodings(image)
                if encodings:
                    self.known_encodings.append(encodings[0])
                    # Use filename (without extension) as person name
                    name = img_path.stem.replace('_', ' ').title()
                    self.known_names.append(name)
                    logger.info(f"Loaded face encoding for: {name}")
            except Exception as e:
                logger.error(f"Failed to load face from {img_path}: {e}")

        # Also check for PNG files
        for img_path in self.authorized_faces_dir.glob('*.png'):
            try:
                image = self._face_recognition.load_image_file(str(img_path))
                encodings = self._face_recognition.face_encodings(image)
                if encodings:
                    self.known_encodings.append(encodings[0])
                    name = img_path.stem.replace('_', ' ').title()
                    self.known_names.append(name)
                    logger.info(f"Loaded face encoding for: {name}")
            except Exception as e:
                logger.error(f"Failed to load face from {img_path}: {e}")

    def recognize(self, frame: np.ndarray) -> List[Detection]:
        """
        Detect and recognize faces in a frame.
        Returns list of face Detection objects with identity if recognized.
        """
        if not self.is_ready:
            return []

        detections = []

        try:
            # Resize for faster processing
            small_frame = frame[::2, ::2]  # Downsample by 2x

            # Find faces
            face_locations = self._face_recognition.face_locations(small_frame, model='hog')
            face_encodings = self._face_recognition.face_encodings(small_frame, face_locations)

            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                # Scale back up
                top *= 2
                right *= 2
                bottom *= 2
                left *= 2

                # Check against known faces
                identity = None
                confidence = 0.0
                alert_level = AlertLevel.HIGH

                if self.known_encodings:
                    face_distances = self._face_recognition.face_distance(
                        self.known_encodings, face_encoding
                    )
                    best_match_idx = np.argmin(face_distances)
                    best_distance = face_distances[best_match_idx]

                    if best_distance < self.recognition_threshold:
                        identity = self.known_names[best_match_idx]
                        confidence = 1.0 - best_distance
                        alert_level = AlertLevel.IGNORE  # Authorized person
                    else:
                        confidence = 1.0 - best_distance
                        # Capture unknown face
                        self._save_unknown_face(frame, (left, top, right - left, bottom - top))

                detection = Detection(
                    timestamp=datetime.now(),
                    detection_type='face',
                    confidence=confidence,
                    alert_level=alert_level,
                    bounding_box=(left, top, right - left, bottom - top),
                    identity=identity,
                    metadata={'authorized': identity is not None}
                )
                detections.append(detection)

        except Exception as e:
            logger.error(f"Face recognition failed: {e}")

        return detections

    def is_authorized(self, frame: np.ndarray) -> Tuple[bool, Optional[str]]:
        """
        Quick check: Is there an authorized person in the frame?
        Returns (is_authorized, person_name)
        """
        faces = self.recognize(frame)
        for face in faces:
            if face.identity is not None:
                return True, face.identity
        return False, None

    def enroll_face(self, frame: np.ndarray, name: str) -> bool:
        """
        Enroll a new authorized face.
        Saves the face image and reloads encodings.
        """
        if not self.is_ready:
            return False

        try:
            face_locations = self._face_recognition.face_locations(frame)
            if not face_locations:
                logger.warning("No face found in frame for enrollment")
                return False

            # Save image
            import cv2
            filename = name.lower().replace(' ', '_') + '.jpg'
            filepath = self.authorized_faces_dir / filename
            cv2.imwrite(str(filepath), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

            # Reload encodings
            self._load_authorized_faces()
            logger.info(f"Enrolled new face: {name}")
            return True

        except Exception as e:
            logger.error(f"Face enrollment failed: {e}")
            return False

    def _save_unknown_face(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]):
        """Save captured unknown face for review."""
        try:
            import cv2
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = self.captures_dir / f'unknown_{timestamp}.jpg'
            cv2.imwrite(str(filepath), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        except Exception as e:
            logger.error(f"Failed to save unknown face: {e}")

    def cleanup(self):
        self._initialized = False


# =============================================================================
# VOICE RECOGNITION MODULE (Vosk)
# =============================================================================

class VoiceRecognizer(BaseAIModule):
    """
    Local voice command recognition using Vosk.
    100% offline, optimized for Raspberry Pi 5.
    """

    def __init__(self, config: Dict):
        super().__init__(config)
        self.model_path = config.get('model_path', 'models/vosk-model-small-en-us')
        self.sample_rate = config.get('sample_rate', 16000)
        self.wake_words = [w.lower() for w in config.get('wake_words', ['sentry'])]
        self.commands = {k.lower(): v for k, v in config.get('commands', {}).items()}
        self.command_timeout = config.get('command_timeout', 5)

        self._model = None
        self._recognizer = None
        self._audio = None
        self._stream = None
        self._listening = False
        self._listen_thread = None
        self._command_queue = queue.Queue()
        self._callbacks: Dict[str, Callable] = {}

    def initialize(self) -> bool:
        """Initialize Vosk model and audio stream."""
        try:
            from vosk import Model, KaldiRecognizer
            import pyaudio

            # Check model path
            if not os.path.exists(self.model_path):
                logger.warning(f"Vosk model not found at {self.model_path}. Run setup_models.sh first.")
                return False

            # Load model
            self._model = Model(self.model_path)
            self._recognizer = KaldiRecognizer(self._model, self.sample_rate)

            # Initialize audio
            self._audio = pyaudio.PyAudio()

            # Find input device
            device_index = None
            for i in range(self._audio.get_device_count()):
                dev = self._audio.get_device_info_by_index(i)
                if dev['maxInputChannels'] > 0:
                    device_index = i
                    break

            if device_index is None:
                logger.warning("No audio input device found")
                return False

            self._stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=4000
            )

            self._initialized = True
            logger.info("Voice recognizer initialized successfully")
            return True

        except ImportError as e:
            logger.warning(f"Voice recognition dependencies not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize voice recognizer: {e}")
            return False

    def register_command(self, command_action: str, callback: Callable):
        """Register a callback for a command action."""
        self._callbacks[command_action] = callback

    def start_listening(self):
        """Start continuous listening in background thread."""
        if not self.is_ready or self._listening:
            return

        self._listening = True
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()
        logger.info("Voice recognition started")

    def stop_listening(self):
        """Stop listening."""
        self._listening = False
        if self._listen_thread:
            self._listen_thread.join(timeout=2)

    def _listen_loop(self):
        """Background listening loop."""
        wake_word_active = False
        wake_word_time = None

        while self._listening:
            try:
                data = self._stream.read(4000, exception_on_overflow=False)

                if self._recognizer.AcceptWaveform(data):
                    result = json.loads(self._recognizer.Result())
                    text = result.get('text', '').lower().strip()

                    if not text:
                        continue

                    logger.debug(f"Heard: {text}")

                    # Check for wake word
                    if not wake_word_active:
                        for wake_word in self.wake_words:
                            if wake_word in text:
                                wake_word_active = True
                                wake_word_time = time.time()
                                logger.info(f"Wake word detected: {wake_word}")
                                # Trigger wake word callback if registered
                                if 'wake' in self._callbacks:
                                    self._callbacks['wake']()
                                break
                    else:
                        # Check for command timeout
                        if time.time() - wake_word_time > self.command_timeout:
                            wake_word_active = False
                            continue

                        # Check for commands
                        for phrase, action in self.commands.items():
                            if phrase in text:
                                wake_word_active = False
                                logger.info(f"Command recognized: {phrase} -> {action}")

                                # Execute callback
                                if action in self._callbacks:
                                    self._callbacks[action]()

                                self._command_queue.put({
                                    'phrase': phrase,
                                    'action': action,
                                    'timestamp': datetime.now()
                                })
                                break

            except Exception as e:
                logger.error(f"Voice recognition error: {e}")
                time.sleep(0.1)

    def get_command(self, timeout: float = 0) -> Optional[Dict]:
        """Get next recognized command from queue."""
        try:
            return self._command_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def recognize_once(self, timeout: float = 5.0) -> Optional[str]:
        """Listen for a single utterance and return the text."""
        if not self.is_ready:
            return None

        start_time = time.time()
        self._recognizer.Reset()

        while time.time() - start_time < timeout:
            try:
                data = self._stream.read(4000, exception_on_overflow=False)
                if self._recognizer.AcceptWaveform(data):
                    result = json.loads(self._recognizer.Result())
                    text = result.get('text', '').strip()
                    if text:
                        return text
            except Exception as e:
                logger.error(f"Recognition error: {e}")

        return None

    def cleanup(self):
        """Clean up audio resources."""
        self.stop_listening()

        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except:
                pass

        if self._audio:
            try:
                self._audio.terminate()
            except:
                pass

        self._initialized = False


# =============================================================================
# TEXT-TO-SPEECH MODULE (Piper)
# =============================================================================

class TextToSpeech(BaseAIModule):
    """
    Local text-to-speech using Piper TTS.
    High quality, fast, 100% offline.
    """

    def __init__(self, config: Dict):
        super().__init__(config)
        self.model_path = config.get('model_path', 'models/en_US-lessac-medium.onnx')
        self.voice_config = config.get('voice_config', 'models/en_US-lessac-medium.onnx.json')
        self.speed = config.get('speed', 1.0)
        self.output_dir = Path(config.get('output_dir', 'tts_cache'))
        self.cache_enabled = config.get('cache_enabled', True)
        self.dynamic_responses = config.get('dynamic_responses', {})

        self._piper_path = None
        self._cache = {}

    def initialize(self) -> bool:
        """Initialize Piper TTS."""
        try:
            # Create cache directory
            self.output_dir.mkdir(parents=True, exist_ok=True)

            # Check for piper binary
            piper_locations = [
                '/usr/local/bin/piper',
                '/usr/bin/piper',
                os.path.expanduser('~/.local/bin/piper'),
                'piper'
            ]

            for loc in piper_locations:
                try:
                    result = subprocess.run(
                        [loc, '--version'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        self._piper_path = loc
                        break
                except:
                    continue

            if not self._piper_path:
                # Try Python piper-tts package
                try:
                    import piper
                    self._piper_path = 'python'
                    logger.info("Using Python piper-tts package")
                except ImportError:
                    logger.warning("Piper TTS not found. Run setup_models.sh to install.")
                    return False

            # Check model exists
            if not os.path.exists(self.model_path):
                logger.warning(f"Piper model not found at {self.model_path}")
                return False

            self._initialized = True
            logger.info("Text-to-speech initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize TTS: {e}")
            return False

    def speak(self, text: str, block: bool = True) -> bool:
        """
        Convert text to speech and play it.

        Args:
            text: Text to speak
            block: If True, wait for speech to complete

        Returns:
            True if successful
        """
        if not self.is_ready:
            logger.warning("TTS not ready, falling back to print")
            print(f"[TTS]: {text}")
            return False

        try:
            # Check cache
            cache_key = hash(text)
            if self.cache_enabled and cache_key in self._cache:
                audio_file = self._cache[cache_key]
                if os.path.exists(audio_file):
                    return self._play_audio(audio_file, block)

            # Generate speech
            audio_file = self.output_dir / f'speech_{cache_key}.wav'

            if self._piper_path == 'python':
                # Use Python piper package
                import piper
                voice = piper.PiperVoice.load(self.model_path)
                with open(audio_file, 'wb') as f:
                    voice.synthesize(text, f)
            else:
                # Use piper binary
                cmd = [
                    self._piper_path,
                    '--model', self.model_path,
                    '--output_file', str(audio_file)
                ]

                if os.path.exists(self.voice_config):
                    cmd.extend(['--config', self.voice_config])

                result = subprocess.run(
                    cmd,
                    input=text,
                    text=True,
                    capture_output=True,
                    timeout=30
                )

                if result.returncode != 0:
                    logger.error(f"Piper failed: {result.stderr}")
                    return False

            # Cache and play
            if self.cache_enabled:
                self._cache[cache_key] = str(audio_file)

            return self._play_audio(str(audio_file), block)

        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return False

    def _play_audio(self, file_path: str, block: bool = True) -> bool:
        """Play an audio file."""
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            sound = pygame.mixer.Sound(file_path)
            sound.play()

            if block:
                while pygame.mixer.get_busy():
                    pygame.time.delay(100)

            return True
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")
            # Fallback to aplay
            try:
                subprocess.run(
                    ['aplay', file_path],
                    capture_output=True,
                    timeout=30
                )
                return True
            except:
                return False

    def get_dynamic_response(self, response_type: str, **kwargs) -> Optional[str]:
        """
        Get a random dynamic response of the given type.
        Supports variable substitution with kwargs.
        """
        responses = self.dynamic_responses.get(response_type, [])
        if not responses:
            return None

        response = random.choice(responses)

        # Substitute variables
        for key, value in kwargs.items():
            response = response.replace(f'{{{key}}}', str(value))

        return response

    def speak_dynamic(self, response_type: str, block: bool = True, **kwargs) -> bool:
        """Speak a dynamic response of the given type."""
        response = self.get_dynamic_response(response_type, **kwargs)
        if response:
            return self.speak(response, block)
        return False

    def cleanup(self):
        self._initialized = False


# =============================================================================
# SMART ALERT MANAGER
# =============================================================================

class SmartAlertManager:
    """
    Intelligent alert management with:
    - Cooldown periods to prevent alert fatigue
    - Quiet hours
    - Activity logging and patterns
    - Alert prioritization
    """

    def __init__(self, config: Dict):
        self.config = config
        self.enabled = config.get('enabled', True)
        self.cooldown_seconds = config.get('cooldown_seconds', 30)
        self.activity_log_path = Path(config.get('activity_log_path', 'activity_log.json'))

        quiet_config = config.get('quiet_hours', {})
        self.quiet_hours_enabled = quiet_config.get('enabled', False)
        self.quiet_start = quiet_config.get('start', '23:00')
        self.quiet_end = quiet_config.get('end', '07:00')
        self.quiet_threshold = AlertLevel[quiet_config.get('alert_level_threshold', 'high').upper()]

        self._last_alert_time: Dict[str, datetime] = {}
        self._activity_log: List[Dict] = []
        self._load_activity_log()

    def _load_activity_log(self):
        """Load activity log from file."""
        try:
            if self.activity_log_path.exists():
                with open(self.activity_log_path, 'r') as f:
                    self._activity_log = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load activity log: {e}")
            self._activity_log = []

    def _save_activity_log(self):
        """Save activity log to file."""
        try:
            # Keep only last 1000 entries
            self._activity_log = self._activity_log[-1000:]
            with open(self.activity_log_path, 'w') as f:
                json.dump(self._activity_log, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save activity log: {e}")

    def should_alert(self, detection: Detection) -> bool:
        """
        Determine if an alert should be triggered based on:
        - Alert level
        - Cooldown period
        - Quiet hours
        """
        if not self.enabled:
            return detection.alert_level.value >= AlertLevel.LOW.value

        # Check quiet hours
        if self.quiet_hours_enabled and self._is_quiet_hours():
            if detection.alert_level.value < self.quiet_threshold.value:
                return False

        # Check cooldown
        detection_key = f"{detection.detection_type}:{detection.identity or 'unknown'}"
        last_alert = self._last_alert_time.get(detection_key)

        if last_alert:
            elapsed = (datetime.now() - last_alert).total_seconds()
            if elapsed < self.cooldown_seconds:
                return False

        # Update last alert time
        self._last_alert_time[detection_key] = datetime.now()

        return detection.alert_level.value >= AlertLevel.LOW.value

    def _is_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours."""
        now = datetime.now().time()
        start = datetime.strptime(self.quiet_start, '%H:%M').time()
        end = datetime.strptime(self.quiet_end, '%H:%M').time()

        if start <= end:
            return start <= now <= end
        else:  # Spans midnight
            return now >= start or now <= end

    def log_detection(self, detection: Detection):
        """Log a detection event."""
        self._activity_log.append(detection.to_dict())
        self._save_activity_log()

    def get_recent_activity(self, hours: int = 1) -> List[Dict]:
        """Get activity from the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            entry for entry in self._activity_log
            if datetime.fromisoformat(entry['timestamp']) > cutoff
        ]

    def get_detection_count(self, hours: int = 1) -> int:
        """Get number of detections in the last N hours."""
        return len(self.get_recent_activity(hours))


# =============================================================================
# UNIFIED SENTRY AI CLASS
# =============================================================================

class SentryAI:
    """
    Unified AI system for Sentry-Bot.
    Integrates all AI modules with the existing intrusion detection system.
    """

    def __init__(self, config_path: str = 'local_ai_config.json'):
        self.config_path = config_path
        self.config = self._load_config()

        # Initialize modules
        vision_config = self.config.get('vision', {})
        face_config = self.config.get('face_recognition', {})
        voice_config = self.config.get('voice_recognition', {})
        tts_config = self.config.get('text_to_speech', {})
        alert_config = self.config.get('smart_alerts', {})

        self.object_detector = ObjectDetector(vision_config)
        self.face_recognizer = FaceRecognizer(face_config)
        self.voice_recognizer = VoiceRecognizer(voice_config)
        self.tts = TextToSpeech(tts_config)
        self.alert_manager = SmartAlertManager(alert_config)

        self._initialized = False
        self._callbacks: Dict[str, Callable] = {}

    def _load_config(self) -> Dict:
        """Load AI configuration."""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load AI config: {e}")
            return {}

    def initialize(self) -> bool:
        """Initialize all AI modules."""
        logger.info("Initializing Sentry AI...")

        results = {}

        # Initialize each module
        if self.config.get('vision', {}).get('enabled', False):
            results['vision'] = self.object_detector.initialize()

        if self.config.get('face_recognition', {}).get('enabled', False):
            results['face'] = self.face_recognizer.initialize()

        if self.config.get('voice_recognition', {}).get('enabled', False):
            results['voice'] = self.voice_recognizer.initialize()
            if results['voice']:
                self._setup_voice_commands()

        if self.config.get('text_to_speech', {}).get('enabled', False):
            results['tts'] = self.tts.initialize()

        self._initialized = any(results.values())

        # Log results
        for module, success in results.items():
            status = "OK" if success else "FAILED"
            logger.info(f"  {module}: {status}")

        return self._initialized

    def _setup_voice_commands(self):
        """Setup voice command callbacks."""
        self.voice_recognizer.register_command('activate', self._on_activate)
        self.voice_recognizer.register_command('deactivate', self._on_deactivate)
        self.voice_recognizer.register_command('status', self._on_status)
        self.voice_recognizer.register_command('identify', self._on_identify)
        self.voice_recognizer.register_command('silence', self._on_silence)

    def _on_activate(self):
        if 'activate' in self._callbacks:
            self._callbacks['activate']()
        self.speak_dynamic('system_armed')

    def _on_deactivate(self):
        if 'deactivate' in self._callbacks:
            self._callbacks['deactivate']()
        self.speak_dynamic('system_disarmed')

    def _on_status(self):
        count = self.alert_manager.get_detection_count()
        self.tts.speak_dynamic('status_report', state='monitoring', detections=count)

    def _on_identify(self):
        if self.object_detector.is_ready:
            _, detections = self.object_detector.detect_persons()
            for det in detections:
                self.tts.speak(f"Detected {det.detection_type} with {det.confidence:.0%} confidence")

    def _on_silence(self):
        if 'silence' in self._callbacks:
            self._callbacks['silence']()

    def register_callback(self, event: str, callback: Callable):
        """Register a callback for system events."""
        self._callbacks[event] = callback

    def start(self):
        """Start all AI services."""
        if self.voice_recognizer.is_ready:
            self.voice_recognizer.start_listening()
        logger.info("Sentry AI started")

    def stop(self):
        """Stop all AI services."""
        self.voice_recognizer.stop_listening()
        logger.info("Sentry AI stopped")

    def analyze_motion(self, pir_triggered: bool = True) -> Dict[str, Any]:
        """
        Analyze motion event with AI.
        Returns analysis results including:
        - should_alert: Whether to trigger an alert
        - alert_level: Severity of the alert
        - detections: List of detected objects/faces
        - authorized_person: Name if an authorized person is detected
        """
        result = {
            'should_alert': pir_triggered,
            'alert_level': AlertLevel.MEDIUM if pir_triggered else AlertLevel.IGNORE,
            'detections': [],
            'authorized_person': None,
            'announcement': None
        }

        if not pir_triggered:
            return result

        # Run object detection
        if self.object_detector.is_ready:
            has_person, detections = self.object_detector.detect_persons()
            result['detections'].extend(detections)

            if not has_person:
                # Motion but no person - likely pet or false alarm
                pet_detections = [d for d in detections if d.detection_type in ['cat', 'dog']]
                if pet_detections:
                    result['should_alert'] = False
                    result['alert_level'] = AlertLevel.IGNORE
                    result['announcement'] = self.tts.get_dynamic_response('pet_detected')
                else:
                    result['alert_level'] = AlertLevel.LOW
            else:
                result['alert_level'] = AlertLevel.HIGH

                # Check for authorized faces
                if self.face_recognizer.is_ready:
                    frame = self.object_detector.capture_frame()
                    if frame is not None:
                        is_auth, name = self.face_recognizer.is_authorized(frame)
                        if is_auth:
                            result['should_alert'] = False
                            result['alert_level'] = AlertLevel.IGNORE
                            result['authorized_person'] = name
                            result['announcement'] = self.tts.get_dynamic_response(
                                'authorized_person', name=name
                            )
                        else:
                            result['announcement'] = self.tts.get_dynamic_response('unknown_person')

        # Log detection if alerting
        if result['should_alert'] and result['detections']:
            for det in result['detections']:
                if self.alert_manager.should_alert(det):
                    self.alert_manager.log_detection(det)

        return result

    def speak(self, text: str, block: bool = True) -> bool:
        """Speak text using TTS."""
        return self.tts.speak(text, block)

    def speak_dynamic(self, response_type: str, block: bool = True, **kwargs) -> bool:
        """Speak a dynamic response."""
        return self.tts.speak_dynamic(response_type, block, **kwargs)

    def cleanup(self):
        """Clean up all resources."""
        self.stop()
        self.object_detector.cleanup()
        self.face_recognizer.cleanup()
        self.voice_recognizer.cleanup()
        self.tts.cleanup()
        logger.info("Sentry AI cleaned up")

    @property
    def is_ready(self) -> bool:
        return self._initialized


# =============================================================================
# MAIN ENTRY POINT FOR TESTING
# =============================================================================

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("Sentry-Bot Local AI Module Test")
    print("=" * 60)

    # Initialize
    sentry_ai = SentryAI()

    if sentry_ai.initialize():
        print("\nSentry AI initialized successfully!")
        print("\nModule Status:")
        print(f"  Object Detection: {'Ready' if sentry_ai.object_detector.is_ready else 'Not Available'}")
        print(f"  Face Recognition: {'Ready' if sentry_ai.face_recognizer.is_ready else 'Not Available'}")
        print(f"  Voice Recognition: {'Ready' if sentry_ai.voice_recognizer.is_ready else 'Not Available'}")
        print(f"  Text-to-Speech: {'Ready' if sentry_ai.tts.is_ready else 'Not Available'}")

        # Test TTS if available
        if sentry_ai.tts.is_ready:
            print("\nTesting TTS...")
            sentry_ai.speak("Sentry AI system initialized and ready.")

        # Start listening if voice is ready
        if sentry_ai.voice_recognizer.is_ready:
            print("\nVoice recognition active. Say 'Sentry' followed by a command.")
            sentry_ai.start()

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nShutting down...")

        sentry_ai.cleanup()
    else:
        print("\nFailed to initialize Sentry AI")
        print("Run setup_models.sh to download required models")
