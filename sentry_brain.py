"""
On-Device LLM Module for Sentry-Bot
====================================
Provides local AI reasoning capabilities using Ollama with lightweight models
optimized for Raspberry Pi 5.

Recommended models for Pi 5 (8GB RAM):
- phi3:mini (3.8B) - Best balance of capability and speed
- llama3.2:1b (1B) - Fastest, good for simple tasks
- llama3.2:3b (3B) - Better reasoning, still fast
- gemma2:2b (2B) - Good efficiency
- qwen2.5:1.5b (1.5B) - Multilingual capable

Features:
- Conversational AI for handling questions
- Contextual reasoning about detections
- Troubleshooting assistance
- Dynamic response generation
- System status interpretation
"""

import json
import logging
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Generator
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """A single message in a conversation."""
    role: str  # 'system', 'user', 'assistant'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {'role': self.role, 'content': self.content}


@dataclass
class LLMConfig:
    """Configuration for the on-device LLM."""
    model: str = "phi3:mini"
    base_url: str = "http://localhost:11434"
    context_length: int = 4096
    temperature: float = 0.7
    max_tokens: int = 512
    timeout: int = 60
    system_prompt: str = ""

    # Pi 5 optimizations
    num_threads: int = 4
    num_gpu_layers: int = 0  # Set > 0 if using GPU acceleration


class OllamaLLM:
    """
    Interface to Ollama for running local LLMs on Raspberry Pi 5.

    Ollama provides an easy way to run quantized models locally with
    good performance on ARM64 devices.
    """

    # Default system prompt for sentry bot
    DEFAULT_SYSTEM_PROMPT = """You are JARVIS, an AI assistant integrated into a home security sentry bot system running on a Raspberry Pi 5.

Your capabilities:
- Monitor and interpret security events (motion detection, person identification, face recognition)
- Answer questions about system status, recent activity, and security events
- Help troubleshoot issues with sensors, cameras, and other hardware
- Provide contextual responses based on detected threats
- Control system functions (arm/disarm, adjust settings)

Your personality:
- Professional but friendly, like a helpful security consultant
- Concise and clear in responses (this runs on limited hardware)
- Proactive about security concerns
- Calm during alerts, reassuring to authorized users

Current system context will be provided with each query. Use it to give relevant, accurate responses.
Keep responses brief (2-3 sentences) unless asked for details."""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        if not self.config.system_prompt:
            self.config.system_prompt = self.DEFAULT_SYSTEM_PROMPT

        self.base_url = self.config.base_url
        self.conversation_history: List[ConversationMessage] = []
        self._initialized = False
        self._available_models: List[str] = []

        # For async generation
        self._generation_queue = queue.Queue()
        self._generating = False

    def initialize(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            # Check if Ollama is running
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )

            if response.status_code != 200:
                logger.error("Ollama is not responding properly")
                return False

            # Get available models
            data = response.json()
            self._available_models = [m['name'] for m in data.get('models', [])]

            logger.info(f"Available Ollama models: {self._available_models}")

            # Check if our model is available
            model_name = self.config.model.split(':')[0]
            if not any(model_name in m for m in self._available_models):
                logger.warning(f"Model {self.config.model} not found. Will attempt to pull.")
                if not self._pull_model():
                    return False

            self._initialized = True
            logger.info(f"Ollama LLM initialized with model: {self.config.model}")
            return True

        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to Ollama. Is it running? Try: ollama serve")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Ollama: {e}")
            return False

    def _pull_model(self) -> bool:
        """Pull the model from Ollama registry."""
        try:
            logger.info(f"Pulling model {self.config.model}... (this may take a while)")

            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": self.config.model},
                timeout=600,  # 10 minutes for download
                stream=True
            )

            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    status = data.get('status', '')
                    if 'pulling' in status or 'downloading' in status:
                        completed = data.get('completed', 0)
                        total = data.get('total', 0)
                        if total > 0:
                            pct = (completed / total) * 100
                            print(f"\rDownloading: {pct:.1f}%", end='', flush=True)

            print()  # New line after progress
            logger.info(f"Model {self.config.model} pulled successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to pull model: {e}")
            return False

    @property
    def is_ready(self) -> bool:
        return self._initialized

    def generate(
        self,
        prompt: str,
        system_context: Optional[str] = None,
        stream: bool = False
    ) -> str:
        """
        Generate a response from the LLM.

        Args:
            prompt: User's input/question
            system_context: Additional context about current system state
            stream: If True, yield tokens as they're generated

        Returns:
            Generated response text
        """
        if not self.is_ready:
            return "AI system is not initialized. Please wait or check Ollama status."

        try:
            # Build messages
            messages = []

            # System prompt with optional context
            system_content = self.config.system_prompt
            if system_context:
                system_content += f"\n\nCurrent System Context:\n{system_context}"

            messages.append({"role": "system", "content": system_content})

            # Add conversation history (last 10 exchanges to save context)
            for msg in self.conversation_history[-20:]:
                messages.append(msg.to_dict())

            # Add current prompt
            messages.append({"role": "user", "content": prompt})

            # Make request
            payload = {
                "model": self.config.model,
                "messages": messages,
                "stream": stream,
                "options": {
                    "temperature": self.config.temperature,
                    "num_predict": self.config.max_tokens,
                    "num_thread": self.config.num_threads,
                }
            }

            if stream:
                return self._stream_generate(payload, prompt)
            else:
                response = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.config.timeout
                )

                if response.status_code != 200:
                    logger.error(f"Ollama error: {response.text}")
                    return "I encountered an error processing your request."

                result = response.json()
                assistant_message = result.get('message', {}).get('content', '')

                # Update conversation history
                self.conversation_history.append(
                    ConversationMessage(role="user", content=prompt)
                )
                self.conversation_history.append(
                    ConversationMessage(role="assistant", content=assistant_message)
                )

                return assistant_message

        except requests.exceptions.Timeout:
            logger.error("LLM request timed out")
            return "Request timed out. The model may be overloaded."
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return f"I encountered an error: {str(e)}"

    def _stream_generate(self, payload: Dict, prompt: str) -> Generator[str, None, None]:
        """Stream tokens as they're generated."""
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.config.timeout,
                stream=True
            )

            full_response = ""
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if 'message' in data:
                        token = data['message'].get('content', '')
                        full_response += token
                        yield token

            # Update history after complete
            self.conversation_history.append(
                ConversationMessage(role="user", content=prompt)
            )
            self.conversation_history.append(
                ConversationMessage(role="assistant", content=full_response)
            )

        except Exception as e:
            logger.error(f"Stream generation failed: {e}")
            yield f"Error: {str(e)}"

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []

    def get_context_summary(self) -> str:
        """Get a summary of recent conversation context."""
        if not self.conversation_history:
            return "No conversation history."

        recent = self.conversation_history[-6:]  # Last 3 exchanges
        summary = []
        for msg in recent:
            role = "You" if msg.role == "user" else "AI"
            summary.append(f"{role}: {msg.content[:100]}...")
        return "\n".join(summary)


class SentryBrain:
    """
    High-level AI brain for the Sentry Bot.
    Combines the LLM with system awareness for intelligent responses.
    """

    # Predefined quick responses for common situations (saves LLM calls)
    QUICK_RESPONSES = {
        "status": "System is {status}. {detections} detections in the last hour. All sensors operational.",
        "armed": "Security system is now armed and monitoring all zones.",
        "disarmed": "Security system disarmed. Have a great day!",
        "person_detected": "Alert: Person detected in monitored area. Analyzing...",
        "authorized": "Welcome back, {name}. I've recognized you and suspended the alert.",
        "pet": "Motion was from a pet. No security concern. Standing down.",
        "false_alarm": "Motion detected but no threat identified. Likely environmental.",
    }

    def __init__(
        self,
        config_path: str = "local_ai_config.json",
        llm_config: Optional[LLMConfig] = None
    ):
        self.config_path = config_path
        self.config = self._load_config()

        # Initialize LLM
        llm_settings = self.config.get('llm', {})
        if llm_config:
            self.llm_config = llm_config
        else:
            self.llm_config = LLMConfig(
                model=llm_settings.get('model', 'phi3:mini'),
                temperature=llm_settings.get('temperature', 0.7),
                max_tokens=llm_settings.get('max_tokens', 256),
                system_prompt=llm_settings.get('system_prompt', ''),
            )

        self.llm = OllamaLLM(self.llm_config)

        # System state tracking
        self.system_state = {
            'armed': True,
            'last_detection': None,
            'detection_count_1h': 0,
            'authorized_bypasses': 0,
            'current_alert_level': 'none',
            'sensors': {'pir': 'ok', 'camera': 'ok', 'mic': 'ok'},
        }

        # Event log for context
        self.event_log: List[Dict] = []

        self._initialized = False

    def _load_config(self) -> Dict:
        """Load configuration."""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except:
            return {}

    def initialize(self) -> bool:
        """Initialize the brain."""
        logger.info("Initializing Sentry Brain...")

        if self.llm.initialize():
            self._initialized = True
            logger.info("Sentry Brain initialized successfully")
            return True
        else:
            logger.warning("LLM initialization failed. Brain will use fallback responses.")
            self._initialized = True  # Can still work with quick responses
            return True

    @property
    def is_ready(self) -> bool:
        return self._initialized

    def update_state(self, **kwargs):
        """Update system state."""
        self.system_state.update(kwargs)

    def log_event(self, event_type: str, details: Dict = None):
        """Log a system event for context."""
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'details': details or {}
        }
        self.event_log.append(event)
        # Keep last 50 events
        self.event_log = self.event_log[-50:]

    def _get_system_context(self) -> str:
        """Build current system context string for LLM."""
        context_parts = [
            f"System Status: {'ARMED' if self.system_state['armed'] else 'DISARMED'}",
            f"Alert Level: {self.system_state['current_alert_level']}",
            f"Detections (last hour): {self.system_state['detection_count_1h']}",
            f"Authorized Bypasses: {self.system_state['authorized_bypasses']}",
        ]

        if self.system_state['last_detection']:
            context_parts.append(f"Last Detection: {self.system_state['last_detection']}")

        # Add recent events
        if self.event_log:
            context_parts.append("\nRecent Events:")
            for event in self.event_log[-5:]:
                context_parts.append(f"  - {event['type']}: {event['details']}")

        return "\n".join(context_parts)

    def quick_response(self, response_type: str, **kwargs) -> str:
        """Get a quick predefined response without LLM."""
        template = self.QUICK_RESPONSES.get(response_type, "")
        if template:
            return template.format(**{**self.system_state, **kwargs})
        return ""

    def think(self, prompt: str, use_llm: bool = True) -> str:
        """
        Process a prompt and generate an intelligent response.

        Args:
            prompt: User input or system event to process
            use_llm: If False, only use quick responses

        Returns:
            AI-generated response
        """
        if not self.is_ready:
            return "AI brain is initializing. Please wait."

        # Check for quick response patterns first
        prompt_lower = prompt.lower()

        if any(word in prompt_lower for word in ['status', 'report', 'how are']):
            quick = self.quick_response('status',
                status='armed' if self.system_state['armed'] else 'disarmed',
                detections=self.system_state['detection_count_1h']
            )
            if quick and not use_llm:
                return quick

        # Use LLM for complex queries
        if use_llm and self.llm.is_ready:
            context = self._get_system_context()
            return self.llm.generate(prompt, system_context=context)
        else:
            return "I'm operating in basic mode. For detailed responses, ensure Ollama is running."

    def analyze_detection(self, detection_data: Dict) -> Dict[str, Any]:
        """
        Analyze a detection event and provide AI reasoning.

        Returns:
            {
                'threat_level': str,  # 'none', 'low', 'medium', 'high', 'critical'
                'recommendation': str,  # What action to take
                'explanation': str,  # Why this assessment
                'should_alert': bool,
            }
        """
        # Log the event
        self.log_event('detection', detection_data)
        self.system_state['detection_count_1h'] += 1
        self.system_state['last_detection'] = datetime.now().isoformat()

        # Quick analysis for common cases
        detection_type = detection_data.get('type', 'unknown')
        confidence = detection_data.get('confidence', 0)
        is_authorized = detection_data.get('authorized', False)

        if is_authorized:
            self.system_state['authorized_bypasses'] += 1
            return {
                'threat_level': 'none',
                'recommendation': 'allow',
                'explanation': f"Authorized person detected: {detection_data.get('identity', 'Unknown')}",
                'should_alert': False
            }

        if detection_type in ['cat', 'dog', 'bird']:
            return {
                'threat_level': 'none',
                'recommendation': 'ignore',
                'explanation': f"Pet detected ({detection_type}). No security concern.",
                'should_alert': False
            }

        if detection_type == 'person' and confidence > 0.7:
            # Use LLM for more nuanced analysis if available
            if self.llm.is_ready:
                prompt = f"""Analyze this security detection:
- Type: {detection_type}
- Confidence: {confidence:.1%}
- Time: {datetime.now().strftime('%H:%M')}
- Location: Monitored zone

Provide a brief threat assessment (1-2 sentences) and recommended action."""

                explanation = self.llm.generate(prompt, self._get_system_context())
            else:
                explanation = "Unidentified person detected with high confidence."

            return {
                'threat_level': 'high',
                'recommendation': 'alert',
                'explanation': explanation,
                'should_alert': True
            }

        # Default for unknown/low confidence
        return {
            'threat_level': 'low',
            'recommendation': 'monitor',
            'explanation': f"Motion detected but unclear source ({detection_type}, {confidence:.1%} confidence).",
            'should_alert': confidence > 0.5
        }

    def handle_voice_query(self, transcribed_text: str) -> str:
        """
        Handle a voice query from the user.

        Args:
            transcribed_text: Text from voice recognition

        Returns:
            Response to speak back
        """
        text_lower = transcribed_text.lower()

        # Command detection
        if any(cmd in text_lower for cmd in ['arm', 'enable', 'activate']):
            self.system_state['armed'] = True
            self.log_event('command', {'action': 'arm'})
            return self.quick_response('armed')

        if any(cmd in text_lower for cmd in ['disarm', 'disable', 'deactivate']):
            self.system_state['armed'] = False
            self.log_event('command', {'action': 'disarm'})
            return self.quick_response('disarmed')

        if 'status' in text_lower or 'report' in text_lower:
            return self.quick_response('status',
                status='armed and monitoring' if self.system_state['armed'] else 'disarmed',
                detections=self.system_state['detection_count_1h']
            )

        # For other queries, use the LLM
        return self.think(transcribed_text)

    def troubleshoot(self, issue: str) -> str:
        """
        Provide troubleshooting assistance for system issues.

        Args:
            issue: Description of the problem

        Returns:
            Troubleshooting advice
        """
        if not self.llm.is_ready:
            return "LLM is not available for detailed troubleshooting. Check Ollama status."

        prompt = f"""The user is experiencing an issue with their Raspberry Pi security system:

Issue: {issue}

System components:
- Raspberry Pi 5
- PIR motion sensor (GPIO 27)
- RGB LEDs (GPIO 17, 22, 24)
- Camera (PiCamera2)
- USB microphone (for voice commands)
- Speaker (for audio output)

Provide brief, practical troubleshooting steps (3-5 points max)."""

        return self.llm.generate(prompt, self._get_system_context())

    def cleanup(self):
        """Cleanup resources."""
        self.llm.clear_history()
        self._initialized = False


# =============================================================================
# OLLAMA INSTALLATION HELPER
# =============================================================================

def install_ollama() -> bool:
    """
    Install Ollama on Raspberry Pi 5.
    """
    print("Installing Ollama for Raspberry Pi 5...")

    try:
        # Download and run Ollama installer
        result = subprocess.run(
            ["curl", "-fsSL", "https://ollama.com/install.sh"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"Failed to download installer: {result.stderr}")
            return False

        # Run the installer
        result = subprocess.run(
            ["sh", "-c", result.stdout],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            print(f"Installation failed: {result.stderr}")
            return False

        print("Ollama installed successfully!")
        return True

    except Exception as e:
        print(f"Installation error: {e}")
        return False


def check_ollama_status() -> Dict[str, Any]:
    """Check if Ollama is installed and running."""
    status = {
        'installed': False,
        'running': False,
        'models': [],
        'version': None
    }

    # Check if installed
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            status['installed'] = True
            status['version'] = result.stdout.strip()
    except:
        pass

    # Check if running
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            status['running'] = True
            data = response.json()
            status['models'] = [m['name'] for m in data.get('models', [])]
    except:
        pass

    return status


# =============================================================================
# MAIN ENTRY POINT FOR TESTING
# =============================================================================

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("Sentry-Bot On-Device LLM Test")
    print("=" * 60)

    # Check Ollama status
    print("\nChecking Ollama status...")
    status = check_ollama_status()
    print(f"  Installed: {status['installed']}")
    print(f"  Running: {status['running']}")
    print(f"  Version: {status['version']}")
    print(f"  Models: {status['models']}")

    if not status['running']:
        print("\nOllama is not running. Start it with: ollama serve")
        print("Or install with: curl -fsSL https://ollama.com/install.sh | sh")
        exit(1)

    # Initialize brain
    print("\nInitializing Sentry Brain...")
    brain = SentryBrain()

    if brain.initialize():
        print("Sentry Brain initialized!")
        print(f"Using model: {brain.llm_config.model}")

        # Interactive test
        print("\n" + "=" * 60)
        print("Interactive Test Mode")
        print("Type 'quit' to exit, 'clear' to clear history")
        print("=" * 60 + "\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if not user_input:
                    continue

                if user_input.lower() == 'quit':
                    break

                if user_input.lower() == 'clear':
                    brain.llm.clear_history()
                    print("Conversation cleared.\n")
                    continue

                # Get response
                print("AI: ", end='', flush=True)
                response = brain.think(user_input)
                print(response)
                print()

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}\n")

        brain.cleanup()
        print("\nGoodbye!")
    else:
        print("Failed to initialize Sentry Brain")
