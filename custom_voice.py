"""
Custom Voice Module for Sentry-Bot
===================================
100% local voice cloning and custom TTS for Raspberry Pi 5.

Supported Engines:
1. Piper TTS - Pre-trained or custom trained voices (fastest)
2. Coqui XTTS - Voice cloning with ~6-30 seconds of audio
3. OpenVoice - Voice cloning with style transfer

Usage:
    # Clone a voice from a sample
    voice = CustomVoice()
    voice.clone_voice("my_voice", "path/to/sample.wav")
    voice.speak("Hello, this is my cloned voice!", voice_id="my_voice")

    # Or use a pre-configured Piper voice
    voice.speak("Hello!", engine="piper", voice="en_US-lessac-medium")
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VoiceProfile:
    """A custom voice profile."""
    name: str
    engine: str  # 'piper', 'xtts', 'openvoice'
    model_path: Optional[str] = None
    sample_paths: List[str] = field(default_factory=list)
    speaker_embedding: Optional[np.ndarray] = None
    settings: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'engine': self.engine,
            'model_path': self.model_path,
            'sample_paths': self.sample_paths,
            'settings': self.settings,
            'created_at': self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'VoiceProfile':
        data['created_at'] = datetime.fromisoformat(data.get('created_at', datetime.now().isoformat()))
        data.pop('speaker_embedding', None)  # Don't load embedding from JSON
        return cls(**data)


class PiperVoiceEngine:
    """
    Piper TTS Engine - Fast, high-quality, runs great on Pi 5.

    Pre-trained voices: https://github.com/rhasspy/piper/blob/master/VOICES.md

    Custom voice training requires:
    1. 1-2 hours of clean audio recordings
    2. Training on a GPU machine (not Pi)
    3. Export .onnx model for Pi inference
    """

    # Popular pre-trained voices for download
    VOICE_CATALOG = {
        'en_US-lessac-medium': {
            'url': 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx',
            'config_url': 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json',
            'description': 'US English, female, medium quality'
        },
        'en_US-amy-medium': {
            'url': 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx',
            'config_url': 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json',
            'description': 'US English, female, natural'
        },
        'en_US-ryan-medium': {
            'url': 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx',
            'config_url': 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json',
            'description': 'US English, male, medium quality'
        },
        'en_GB-alan-medium': {
            'url': 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx',
            'config_url': 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json',
            'description': 'British English, male'
        },
        'en_GB-jenny_dioco-medium': {
            'url': 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium.onnx',
            'config_url': 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium.onnx.json',
            'description': 'British English, female'
        }
    }

    def __init__(self, models_dir: str = 'models/voices'):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._piper_path = self._find_piper()

    def _find_piper(self) -> Optional[str]:
        """Find piper executable."""
        locations = [
            '/usr/local/bin/piper',
            '/usr/bin/piper',
            os.path.expanduser('~/.local/bin/piper'),
            'piper'
        ]
        for loc in locations:
            try:
                result = subprocess.run([loc, '--version'], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return loc
            except:
                continue
        return None

    def list_available_voices(self) -> List[Dict]:
        """List available pre-trained voices."""
        voices = []
        for name, info in self.VOICE_CATALOG.items():
            model_path = self.models_dir / f"{name}.onnx"
            voices.append({
                'name': name,
                'description': info['description'],
                'installed': model_path.exists()
            })
        return voices

    def download_voice(self, voice_name: str) -> bool:
        """Download a pre-trained voice."""
        if voice_name not in self.VOICE_CATALOG:
            logger.error(f"Unknown voice: {voice_name}")
            return False

        info = self.VOICE_CATALOG[voice_name]
        model_path = self.models_dir / f"{voice_name}.onnx"
        config_path = self.models_dir / f"{voice_name}.onnx.json"

        try:
            import requests

            # Download model
            if not model_path.exists():
                logger.info(f"Downloading {voice_name} model...")
                response = requests.get(info['url'], stream=True)
                with open(model_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

            # Download config
            if not config_path.exists():
                response = requests.get(info['config_url'])
                with open(config_path, 'w') as f:
                    f.write(response.text)

            logger.info(f"Voice {voice_name} downloaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to download voice: {e}")
            return False

    def synthesize(
        self,
        text: str,
        voice_name: str = 'en_US-lessac-medium',
        output_path: Optional[str] = None,
        speed: float = 1.0
    ) -> Optional[str]:
        """Synthesize speech using Piper."""
        if not self._piper_path:
            logger.error("Piper not found")
            return None

        model_path = self.models_dir / f"{voice_name}.onnx"
        if not model_path.exists():
            logger.info(f"Voice {voice_name} not installed, downloading...")
            if not self.download_voice(voice_name):
                return None

        if output_path is None:
            output_path = tempfile.mktemp(suffix='.wav')

        try:
            cmd = [
                self._piper_path,
                '--model', str(model_path),
                '--output_file', output_path,
                '--length_scale', str(1.0 / speed)
            ]

            result = subprocess.run(
                cmd,
                input=text,
                text=True,
                capture_output=True,
                timeout=60
            )

            if result.returncode == 0 and os.path.exists(output_path):
                return output_path
            else:
                logger.error(f"Piper synthesis failed: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            return None


class CoquiXTTSEngine:
    """
    Coqui XTTS Engine - Voice cloning with minimal samples.

    Features:
    - Clone any voice with 6-30 seconds of audio
    - Multi-language support
    - Runs locally on Pi 5 (slower than Piper, but more flexible)

    Requirements:
    - pip install TTS
    - ~4GB RAM for inference
    """

    def __init__(self, models_dir: str = 'models/xtts'):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._tts = None
        self._loaded_speaker = None
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize XTTS model."""
        try:
            from TTS.api import TTS

            logger.info("Loading XTTS model (this may take a minute)...")

            # Use XTTS v2 for best quality voice cloning
            self._tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

            # Move to CPU for Pi 5 (no CUDA)
            self._tts.to('cpu')

            self._initialized = True
            logger.info("XTTS initialized successfully")
            return True

        except ImportError:
            logger.warning("Coqui TTS not installed. Run: pip install TTS")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize XTTS: {e}")
            return False

    def clone_voice(
        self,
        voice_name: str,
        sample_paths: Union[str, List[str]],
        description: str = ""
    ) -> Optional[VoiceProfile]:
        """
        Clone a voice from audio sample(s).

        Args:
            voice_name: Name for the cloned voice
            sample_paths: Path(s) to audio sample(s) - WAV format, 6-30 seconds
            description: Optional description

        Returns:
            VoiceProfile if successful
        """
        if not self._initialized:
            if not self.initialize():
                return None

        if isinstance(sample_paths, str):
            sample_paths = [sample_paths]

        # Validate samples
        valid_samples = []
        for path in sample_paths:
            if os.path.exists(path):
                valid_samples.append(path)
            else:
                logger.warning(f"Sample not found: {path}")

        if not valid_samples:
            logger.error("No valid audio samples provided")
            return None

        # Copy samples to voice directory
        voice_dir = self.models_dir / voice_name
        voice_dir.mkdir(parents=True, exist_ok=True)

        stored_samples = []
        for i, sample in enumerate(valid_samples):
            dest = voice_dir / f"sample_{i}.wav"
            shutil.copy(sample, dest)
            stored_samples.append(str(dest))

        # Create voice profile
        profile = VoiceProfile(
            name=voice_name,
            engine='xtts',
            model_path=str(voice_dir),
            sample_paths=stored_samples,
            settings={'description': description}
        )

        # Save profile
        profile_path = voice_dir / 'profile.json'
        with open(profile_path, 'w') as f:
            json.dump(profile.to_dict(), f, indent=2)

        logger.info(f"Voice '{voice_name}' cloned from {len(stored_samples)} sample(s)")
        return profile

    def synthesize(
        self,
        text: str,
        voice_profile: VoiceProfile,
        output_path: Optional[str] = None,
        language: str = 'en'
    ) -> Optional[str]:
        """
        Synthesize speech using a cloned voice.

        Args:
            text: Text to speak
            voice_profile: Voice profile to use
            output_path: Output WAV path (generated if None)
            language: Language code ('en', 'es', 'fr', etc.)

        Returns:
            Path to output audio file
        """
        if not self._initialized:
            if not self.initialize():
                return None

        if not voice_profile.sample_paths:
            logger.error("Voice profile has no samples")
            return None

        if output_path is None:
            output_path = tempfile.mktemp(suffix='.wav')

        try:
            # Use first sample as speaker reference
            speaker_wav = voice_profile.sample_paths[0]

            self._tts.tts_to_file(
                text=text,
                file_path=output_path,
                speaker_wav=speaker_wav,
                language=language
            )

            if os.path.exists(output_path):
                return output_path
            return None

        except Exception as e:
            logger.error(f"XTTS synthesis failed: {e}")
            return None

    def list_cloned_voices(self) -> List[VoiceProfile]:
        """List all cloned voices."""
        voices = []
        for voice_dir in self.models_dir.iterdir():
            if voice_dir.is_dir():
                profile_path = voice_dir / 'profile.json'
                if profile_path.exists():
                    try:
                        with open(profile_path, 'r') as f:
                            data = json.load(f)
                            voices.append(VoiceProfile.from_dict(data))
                    except:
                        pass
        return voices


class CustomVoice:
    """
    Unified custom voice interface for Sentry-Bot.

    Supports multiple TTS engines with automatic fallback:
    1. Piper (fastest, pre-trained or custom trained)
    2. XTTS (voice cloning with minimal samples)

    Example:
        voice = CustomVoice()
        voice.initialize()

        # Use pre-trained voice
        voice.speak("Hello!", voice_id="en_US-ryan-medium")

        # Clone a custom voice
        voice.clone_voice("jarvis", "samples/jarvis_sample.wav")
        voice.speak("System armed.", voice_id="jarvis")
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.voices_dir = Path(self.config.get('voices_dir', 'voices'))
        self.cache_dir = Path(self.config.get('cache_dir', 'tts_cache'))

        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize engines
        self.piper = PiperVoiceEngine(str(self.voices_dir / 'piper'))
        self.xtts = CoquiXTTSEngine(str(self.voices_dir / 'xtts'))

        # Voice profiles
        self._profiles: Dict[str, VoiceProfile] = {}
        self._default_voice = self.config.get('default_voice', 'en_US-lessac-medium')

        # Audio cache
        self._cache_enabled = self.config.get('cache_enabled', True)
        self._cache: Dict[str, str] = {}

        self._initialized = False

    def initialize(self) -> bool:
        """Initialize voice engines."""
        logger.info("Initializing Custom Voice system...")

        # Piper is lightweight, always try to init
        piper_ok = self.piper._piper_path is not None
        if piper_ok:
            logger.info("Piper TTS: Ready")
        else:
            logger.warning("Piper TTS: Not found (install with setup_ai.sh)")

        # XTTS is heavier, init on demand
        logger.info("XTTS: Available (will load on first use)")

        # Load saved profiles
        self._load_profiles()

        self._initialized = piper_ok
        return self._initialized

    def _load_profiles(self):
        """Load saved voice profiles."""
        profiles_file = self.voices_dir / 'profiles.json'
        if profiles_file.exists():
            try:
                with open(profiles_file, 'r') as f:
                    data = json.load(f)
                    for name, profile_data in data.items():
                        self._profiles[name] = VoiceProfile.from_dict(profile_data)
                logger.info(f"Loaded {len(self._profiles)} voice profiles")
            except Exception as e:
                logger.error(f"Failed to load profiles: {e}")

    def _save_profiles(self):
        """Save voice profiles."""
        profiles_file = self.voices_dir / 'profiles.json'
        try:
            data = {name: profile.to_dict() for name, profile in self._profiles.items()}
            with open(profiles_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save profiles: {e}")

    def list_voices(self) -> Dict[str, List]:
        """List all available voices."""
        return {
            'piper_pretrained': self.piper.list_available_voices(),
            'custom_cloned': [p.to_dict() for p in self._profiles.values()]
        }

    def clone_voice(
        self,
        voice_name: str,
        sample_paths: Union[str, List[str]],
        engine: str = 'xtts',
        description: str = ""
    ) -> bool:
        """
        Clone a voice from audio sample(s).

        Args:
            voice_name: Unique name for this voice
            sample_paths: Path(s) to audio samples (WAV, 6-30 seconds each)
            engine: TTS engine to use ('xtts')
            description: Optional description

        Returns:
            True if successful
        """
        if engine == 'xtts':
            profile = self.xtts.clone_voice(voice_name, sample_paths, description)
            if profile:
                self._profiles[voice_name] = profile
                self._save_profiles()
                return True
        else:
            logger.error(f"Voice cloning not supported for engine: {engine}")

        return False

    def speak(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        block: bool = True
    ) -> bool:
        """
        Speak text using a voice.

        Args:
            text: Text to speak
            voice_id: Voice name (default voice if None)
            speed: Speech speed multiplier
            block: Wait for speech to complete

        Returns:
            True if successful
        """
        voice_id = voice_id or self._default_voice

        # Check cache
        if self._cache_enabled:
            cache_key = hashlib.md5(f"{voice_id}:{text}:{speed}".encode()).hexdigest()
            if cache_key in self._cache and os.path.exists(self._cache[cache_key]):
                return self._play_audio(self._cache[cache_key], block)

        # Generate speech
        audio_path = self._synthesize(text, voice_id, speed)
        if audio_path:
            # Cache it
            if self._cache_enabled:
                cached_path = self.cache_dir / f"{cache_key}.wav"
                shutil.copy(audio_path, cached_path)
                self._cache[cache_key] = str(cached_path)

            return self._play_audio(audio_path, block)

        return False

    def _synthesize(
        self,
        text: str,
        voice_id: str,
        speed: float = 1.0
    ) -> Optional[str]:
        """Synthesize speech to audio file."""

        # Check if it's a custom cloned voice
        if voice_id in self._profiles:
            profile = self._profiles[voice_id]

            if profile.engine == 'xtts':
                return self.xtts.synthesize(text, profile)
            else:
                logger.error(f"Unknown engine: {profile.engine}")
                return None

        # Try Piper pre-trained voice
        if self.piper._piper_path:
            return self.piper.synthesize(text, voice_id, speed=speed)

        logger.error(f"No engine available for voice: {voice_id}")
        return None

    def _play_audio(self, file_path: str, block: bool = True) -> bool:
        """Play audio file."""
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
            logger.error(f"Playback failed: {e}")
            # Fallback to aplay
            try:
                cmd = ['aplay', '-q', file_path]
                if not block:
                    subprocess.Popen(cmd)
                else:
                    subprocess.run(cmd, timeout=60)
                return True
            except:
                return False

    def download_voice(self, voice_name: str) -> bool:
        """Download a pre-trained Piper voice."""
        return self.piper.download_voice(voice_name)

    def set_default_voice(self, voice_id: str):
        """Set the default voice."""
        self._default_voice = voice_id

    def record_sample(
        self,
        output_path: str,
        duration: float = 10.0,
        sample_rate: int = 22050
    ) -> bool:
        """
        Record a voice sample from microphone.

        Args:
            output_path: Output WAV file path
            duration: Recording duration in seconds
            sample_rate: Audio sample rate

        Returns:
            True if successful
        """
        try:
            import pyaudio

            print(f"Recording for {duration} seconds... Speak now!")

            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                input=True,
                frames_per_buffer=1024
            )

            frames = []
            for _ in range(int(sample_rate / 1024 * duration)):
                data = stream.read(1024)
                frames.append(data)

            stream.stop_stream()
            stream.close()
            audio.terminate()

            # Save to WAV
            with wave.open(output_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
                wf.setframerate(sample_rate)
                wf.writeframes(b''.join(frames))

            print(f"Recording saved to: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Recording failed: {e}")
            return False


# =============================================================================
# VOICE TRAINING GUIDE
# =============================================================================

TRAINING_GUIDE = """
================================================================================
                    CUSTOM VOICE TRAINING GUIDE
================================================================================

There are TWO ways to get a custom voice for Sentry-Bot:

------------------------------------------------------------------------------
OPTION 1: Voice Cloning with XTTS (Easiest - No Training Required)
------------------------------------------------------------------------------

Requirements:
- 6-30 seconds of clear audio (WAV format)
- pip install TTS

Steps:
1. Record or obtain a clean voice sample:
   - Clear speech, minimal background noise
   - WAV format, 22050 Hz sample rate
   - 6-30 seconds is ideal

2. Clone the voice:
   from custom_voice import CustomVoice

   voice = CustomVoice()
   voice.initialize()
   voice.clone_voice("jarvis", "path/to/sample.wav")
   voice.speak("Hello, I am your new voice!", voice_id="jarvis")

Pros: Quick, easy, no GPU needed
Cons: Quality depends on sample, slower inference on Pi 5

------------------------------------------------------------------------------
OPTION 2: Train a Custom Piper Voice (Best Quality)
------------------------------------------------------------------------------

Requirements:
- 1-2 hours of audio recordings with transcripts
- A PC/server with GPU for training (not on Pi)
- Time: Several hours of training

Steps:

1. PREPARE TRAINING DATA
   - Record 1-2 hours of clear speech
   - Create transcript file matching audio
   - Format: LJSpeech style dataset

   dataset/
   ├── wavs/
   │   ├── audio_001.wav
   │   ├── audio_002.wav
   │   └── ...
   └── metadata.csv  (format: filename|transcript)

2. TRAIN ON GPU MACHINE (not Pi)

   # Install piper-train
   pip install piper-train

   # Preprocess data
   python -m piper_train.preprocess \\
     --language en \\
     --input-dir dataset/ \\
     --output-dir training/

   # Train (takes several hours)
   python -m piper_train \\
     --dataset-dir training/ \\
     --output-dir output/ \\
     --config config.json

3. EXPORT MODEL

   # Convert to ONNX for Pi
   python -m piper_train.export \\
     --checkpoint output/checkpoint.ckpt \\
     --output my_voice.onnx

4. DEPLOY TO PI 5

   # Copy to Pi
   scp my_voice.onnx pi@raspberrypi:~/sentry-bot/voices/piper/

   # Use in code
   voice = CustomVoice()
   voice.speak("Hello!", voice_id="my_voice")

Pros: Best quality, fastest inference
Cons: Requires training setup and time

------------------------------------------------------------------------------
OPTION 3: Download Pre-trained Piper Voices
------------------------------------------------------------------------------

from custom_voice import CustomVoice

voice = CustomVoice()

# List available voices
print(voice.list_voices()['piper_pretrained'])

# Download a voice
voice.download_voice('en_US-ryan-medium')  # Male US English
voice.download_voice('en_GB-alan-medium')  # Male British English

# Use it
voice.speak("Hello there!", voice_id='en_US-ryan-medium')

Available voices: https://rhasspy.github.io/piper-samples/

================================================================================
"""


def print_training_guide():
    """Print the voice training guide."""
    print(TRAINING_GUIDE)


# =============================================================================
# CLI INTERFACE
# =============================================================================

if __name__ == '__main__':
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description='Custom Voice Manager for Sentry-Bot')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # List voices
    subparsers.add_parser('list', help='List available voices')

    # Download voice
    download_parser = subparsers.add_parser('download', help='Download a pre-trained voice')
    download_parser.add_argument('voice_name', help='Voice name to download')

    # Clone voice
    clone_parser = subparsers.add_parser('clone', help='Clone a voice from samples')
    clone_parser.add_argument('voice_name', help='Name for the cloned voice')
    clone_parser.add_argument('samples', nargs='+', help='Path(s) to audio samples')

    # Test voice
    test_parser = subparsers.add_parser('test', help='Test a voice')
    test_parser.add_argument('--voice', '-v', default=None, help='Voice to test')
    test_parser.add_argument('--text', '-t', default='Hello, this is a test of the custom voice system.', help='Text to speak')

    # Record sample
    record_parser = subparsers.add_parser('record', help='Record a voice sample')
    record_parser.add_argument('output', help='Output WAV file path')
    record_parser.add_argument('--duration', '-d', type=float, default=10, help='Duration in seconds')

    # Training guide
    subparsers.add_parser('guide', help='Show voice training guide')

    args = parser.parse_args()

    voice = CustomVoice()
    voice.initialize()

    if args.command == 'list':
        voices = voice.list_voices()
        print("\n=== Pre-trained Piper Voices ===")
        for v in voices['piper_pretrained']:
            status = "✓ Installed" if v['installed'] else "○ Not installed"
            print(f"  {v['name']}: {v['description']} [{status}]")

        print("\n=== Custom Cloned Voices ===")
        if voices['custom_cloned']:
            for v in voices['custom_cloned']:
                print(f"  {v['name']}: {v['engine']} engine")
        else:
            print("  (none)")

    elif args.command == 'download':
        print(f"Downloading voice: {args.voice_name}")
        if voice.download_voice(args.voice_name):
            print("Success!")
        else:
            print("Failed!")

    elif args.command == 'clone':
        print(f"Cloning voice '{args.voice_name}' from {len(args.samples)} sample(s)...")
        if voice.clone_voice(args.voice_name, args.samples):
            print("Success! Voice cloned.")
        else:
            print("Failed to clone voice.")

    elif args.command == 'test':
        print(f"Testing voice: {args.voice or 'default'}")
        print(f"Text: {args.text}")
        if voice.speak(args.text, voice_id=args.voice):
            print("Success!")
        else:
            print("Failed!")

    elif args.command == 'record':
        voice.record_sample(args.output, duration=args.duration)

    elif args.command == 'guide':
        print_training_guide()

    else:
        parser.print_help()
