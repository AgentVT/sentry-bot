#!/bin/bash
#
# Sentry-Bot AI Setup Script for Raspberry Pi 5
# ==============================================
# Downloads and installs all required AI models and dependencies
# for 100% local, offline operation.
#
# Usage: ./setup_ai.sh [--full|--minimal|--models-only|--llm-only]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="${SCRIPT_DIR}/models"
FACES_DIR="${SCRIPT_DIR}/authorized_faces"
CACHE_DIR="${SCRIPT_DIR}/tts_cache"
CAPTURES_DIR="${SCRIPT_DIR}/captured_faces"

# Model URLs
TFLITE_MODEL_URL="https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip"
VOSK_MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
PIPER_VOICE_URL="https://github.com/rhasspy/piper/releases/download/v1.2.0/voice-en_US-lessac-medium.tar.gz"

# LLM Configuration
DEFAULT_LLM_MODEL="phi3:mini"  # Best balance for Pi 5
FALLBACK_LLM_MODEL="llama3.2:1b"  # Faster, less capable

echo -e "${BLUE}"
echo "=========================================="
echo "   Sentry-Bot AI Setup for Raspberry Pi 5"
echo "=========================================="
echo -e "${NC}"

# Parse arguments
INSTALL_TYPE="full"
if [ "$1" == "--minimal" ]; then
    INSTALL_TYPE="minimal"
elif [ "$1" == "--models-only" ]; then
    INSTALL_TYPE="models"
elif [ "$1" == "--llm-only" ]; then
    INSTALL_TYPE="llm-only"
fi

echo -e "${YELLOW}Installation type: ${INSTALL_TYPE}${NC}"
echo ""

# Function to check if running on Raspberry Pi
check_raspberry_pi() {
    if [ -f /proc/device-tree/model ]; then
        model=$(cat /proc/device-tree/model)
        if [[ "$model" == *"Raspberry Pi"* ]]; then
            echo -e "${GREEN}Detected: $model${NC}"
            return 0
        fi
    fi
    echo -e "${YELLOW}Warning: Not running on Raspberry Pi. Some features may not work.${NC}"
    return 0
}

# Function to create directories
create_directories() {
    echo -e "${BLUE}Creating directories...${NC}"
    mkdir -p "$MODELS_DIR"
    mkdir -p "$FACES_DIR"
    mkdir -p "$CACHE_DIR"
    mkdir -p "$CAPTURES_DIR"
    echo -e "${GREEN}Done${NC}"
}

# Function to install system dependencies
install_system_deps() {
    echo -e "${BLUE}Installing system dependencies...${NC}"

    sudo apt-get update

    # Core dependencies
    sudo apt-get install -y \
        python3-pip \
        python3-venv \
        python3-dev \
        libportaudio2 \
        portaudio19-dev \
        libatlas-base-dev \
        libjpeg-dev \
        zlib1g-dev \
        libpng-dev \
        ffmpeg \
        espeak-ng

    # Camera support for Pi 5
    sudo apt-get install -y \
        libcamera-apps \
        python3-picamera2 \
        python3-libcamera

    # Audio support
    sudo apt-get install -y \
        alsa-utils \
        pulseaudio

    # For face recognition (dlib compilation)
    sudo apt-get install -y \
        cmake \
        libopenblas-dev \
        liblapack-dev \
        libx11-dev \
        libgtk-3-dev

    echo -e "${GREEN}System dependencies installed${NC}"
}

# Function to install Python dependencies
install_python_deps() {
    echo -e "${BLUE}Installing Python dependencies...${NC}"

    # Upgrade pip
    pip3 install --upgrade pip

    # Core dependencies
    pip3 install \
        numpy \
        pygame \
        mutagen \
        RPi.GPIO \
        opencv-python-headless

    # TensorFlow Lite Runtime (optimized for Pi)
    pip3 install tflite-runtime

    # Voice recognition
    pip3 install vosk pyaudio

    # Piper TTS
    pip3 install piper-tts

    # Face recognition (this takes a while to compile dlib)
    echo -e "${YELLOW}Installing face_recognition (this may take 10-20 minutes)...${NC}"
    pip3 install face_recognition

    echo -e "${GREEN}Python dependencies installed${NC}"
}

# Function to install minimal Python dependencies
install_minimal_python_deps() {
    echo -e "${BLUE}Installing minimal Python dependencies...${NC}"

    pip3 install --upgrade pip
    pip3 install \
        numpy \
        pygame \
        mutagen \
        RPi.GPIO \
        opencv-python-headless \
        tflite-runtime

    echo -e "${GREEN}Minimal Python dependencies installed${NC}"
}

# Function to download TFLite model
download_tflite_model() {
    echo -e "${BLUE}Downloading TensorFlow Lite object detection model...${NC}"

    cd "$MODELS_DIR"

    if [ ! -f "detect.tflite" ]; then
        wget -q --show-progress "$TFLITE_MODEL_URL" -O coco_ssd.zip
        unzip -q coco_ssd.zip
        mv detect.tflite detect.tflite 2>/dev/null || true

        # Create labelmap
        cat > labelmap.txt << 'EOF'
person
bicycle
car
motorcycle
airplane
bus
train
truck
boat
traffic light
fire hydrant
stop sign
parking meter
bench
bird
cat
dog
horse
sheep
cow
elephant
bear
zebra
giraffe
backpack
umbrella
handbag
tie
suitcase
frisbee
skis
snowboard
sports ball
kite
baseball bat
baseball glove
skateboard
surfboard
tennis racket
bottle
wine glass
cup
fork
knife
spoon
bowl
banana
apple
sandwich
orange
broccoli
carrot
hot dog
pizza
donut
cake
chair
couch
potted plant
bed
dining table
toilet
tv
laptop
mouse
remote
keyboard
cell phone
microwave
oven
toaster
sink
refrigerator
book
clock
vase
scissors
teddy bear
hair drier
toothbrush
EOF

        rm -f coco_ssd.zip
        echo -e "${GREEN}TFLite model downloaded${NC}"
    else
        echo -e "${YELLOW}TFLite model already exists${NC}"
    fi

    cd "$SCRIPT_DIR"
}

# Function to download Vosk model
download_vosk_model() {
    echo -e "${BLUE}Downloading Vosk speech recognition model...${NC}"

    cd "$MODELS_DIR"

    if [ ! -d "vosk-model-small-en-us" ]; then
        wget -q --show-progress "$VOSK_MODEL_URL" -O vosk-model.zip
        unzip -q vosk-model.zip
        mv vosk-model-small-en-us-0.15 vosk-model-small-en-us 2>/dev/null || true
        rm -f vosk-model.zip
        echo -e "${GREEN}Vosk model downloaded${NC}"
    else
        echo -e "${YELLOW}Vosk model already exists${NC}"
    fi

    cd "$SCRIPT_DIR"
}

# Function to download Piper voice
download_piper_voice() {
    echo -e "${BLUE}Downloading Piper TTS voice model...${NC}"

    cd "$MODELS_DIR"

    if [ ! -f "en_US-lessac-medium.onnx" ]; then
        wget -q --show-progress "$PIPER_VOICE_URL" -O piper-voice.tar.gz
        tar -xzf piper-voice.tar.gz
        rm -f piper-voice.tar.gz
        echo -e "${GREEN}Piper voice downloaded${NC}"
    else
        echo -e "${YELLOW}Piper voice already exists${NC}"
    fi

    cd "$SCRIPT_DIR"
}

# Function to configure audio
configure_audio() {
    echo -e "${BLUE}Configuring audio...${NC}"

    # Enable audio
    sudo modprobe snd_bcm2835 2>/dev/null || true

    # Set default audio levels
    amixer sset 'Master' 80% 2>/dev/null || true
    amixer sset 'PCM' 80% 2>/dev/null || true

    # Create ALSA config for better compatibility
    cat > ~/.asoundrc << 'EOF'
pcm.!default {
    type asym
    playback.pcm "plughw:0,0"
    capture.pcm "plughw:1,0"
}
ctl.!default {
    type hw
    card 0
}
EOF

    echo -e "${GREEN}Audio configured${NC}"
}

# Function to enable camera
enable_camera() {
    echo -e "${BLUE}Enabling camera...${NC}"

    # For Pi 5, camera should work via libcamera
    # Just verify it's accessible
    if command -v libcamera-hello &> /dev/null; then
        echo -e "${GREEN}libcamera is available${NC}"
    else
        echo -e "${YELLOW}Warning: libcamera not found. Camera may not work.${NC}"
    fi
}

# Function to install Ollama (local LLM runtime)
install_ollama() {
    echo -e "${BLUE}Installing Ollama (local LLM runtime)...${NC}"

    # Check if already installed
    if command -v ollama &> /dev/null; then
        echo -e "${YELLOW}Ollama is already installed${NC}"
        ollama --version
        return 0
    fi

    # Download and install Ollama
    echo -e "${YELLOW}Downloading Ollama installer...${NC}"
    curl -fsSL https://ollama.com/install.sh | sh

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Ollama installed successfully${NC}"
    else
        echo -e "${RED}Ollama installation failed${NC}"
        return 1
    fi
}

# Function to setup Ollama service
setup_ollama_service() {
    echo -e "${BLUE}Setting up Ollama service...${NC}"

    # Create systemd service for auto-start
    sudo tee /etc/systemd/system/ollama.service > /dev/null << 'EOF'
[Unit]
Description=Ollama Local LLM Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=3
Environment="OLLAMA_HOST=0.0.0.0"

[Install]
WantedBy=multi-user.target
EOF

    # Enable and start service
    sudo systemctl daemon-reload
    sudo systemctl enable ollama
    sudo systemctl start ollama

    # Wait for service to be ready
    echo -e "${YELLOW}Waiting for Ollama service to start...${NC}"
    sleep 5

    # Check if running
    if systemctl is-active --quiet ollama; then
        echo -e "${GREEN}Ollama service is running${NC}"
    else
        echo -e "${RED}Ollama service failed to start${NC}"
        return 1
    fi
}

# Function to download LLM model
download_llm_model() {
    local model="${1:-$DEFAULT_LLM_MODEL}"
    echo -e "${BLUE}Downloading LLM model: ${model}...${NC}"
    echo -e "${YELLOW}This may take 10-30 minutes depending on your connection${NC}"

    # Check if Ollama is running
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${YELLOW}Starting Ollama service...${NC}"
        sudo systemctl start ollama
        sleep 5
    fi

    # Pull the model
    ollama pull "$model"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Model ${model} downloaded successfully${NC}"
    else
        echo -e "${RED}Failed to download model ${model}${NC}"
        if [ "$model" != "$FALLBACK_LLM_MODEL" ]; then
            echo -e "${YELLOW}Trying fallback model: ${FALLBACK_LLM_MODEL}${NC}"
            ollama pull "$FALLBACK_LLM_MODEL"
        fi
    fi
}

# Function to test LLM
test_llm() {
    echo -e "${BLUE}Testing LLM...${NC}"

    # Simple test prompt
    local response=$(curl -s http://localhost:11434/api/generate -d '{
        "model": "'"$DEFAULT_LLM_MODEL"'",
        "prompt": "Say hello in exactly 5 words.",
        "stream": false
    }' | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','ERROR')[:100])" 2>/dev/null)

    if [ -n "$response" ] && [ "$response" != "ERROR" ]; then
        echo -e "${GREEN}LLM Test Response: ${response}${NC}"
        return 0
    else
        echo -e "${YELLOW}LLM test inconclusive. Model may still be loading.${NC}"
        return 1
    fi
}

# Function to test installation
test_installation() {
    echo -e "${BLUE}Testing installation...${NC}"

    python3 << 'EOF'
import sys

def test_import(module, name):
    try:
        __import__(module)
        print(f"  ✓ {name}")
        return True
    except ImportError as e:
        print(f"  ✗ {name}: {e}")
        return False

print("\nTesting imports:")
results = []
results.append(test_import('numpy', 'NumPy'))
results.append(test_import('pygame', 'Pygame'))
results.append(test_import('cv2', 'OpenCV'))
results.append(test_import('tflite_runtime.interpreter', 'TFLite Runtime'))

try:
    results.append(test_import('vosk', 'Vosk'))
except:
    print("  - Vosk (optional)")

try:
    results.append(test_import('piper', 'Piper TTS'))
except:
    print("  - Piper TTS (optional)")

try:
    results.append(test_import('face_recognition', 'Face Recognition'))
except:
    print("  - Face Recognition (optional)")

print(f"\nBasic tests: {sum(results[:4])}/4 passed")
EOF

    echo ""
}

# Function to create example authorized face placeholder
create_example_face() {
    echo -e "${BLUE}Creating example authorized face placeholder...${NC}"

    cat > "${FACES_DIR}/README.txt" << 'EOF'
AUTHORIZED FACES DIRECTORY
==========================

Place photos of authorized individuals here.

File naming:
- Use the person's name as the filename
- Replace spaces with underscores
- Use .jpg or .png format

Examples:
- john_smith.jpg
- jane_doe.png
- admin.jpg

Tips for best recognition:
- Use clear, well-lit photos
- Face should be clearly visible
- One person per photo
- Front-facing photos work best
EOF

    echo -e "${GREEN}Example placeholder created${NC}"
}

# Function to update config
update_config() {
    echo -e "${BLUE}Updating configuration...${NC}"

    # Update local_ai_config.json with correct paths
    if [ -f "${SCRIPT_DIR}/local_ai_config.json" ]; then
        # Update model paths to absolute paths
        sed -i "s|\"models/|\"${MODELS_DIR}/|g" "${SCRIPT_DIR}/local_ai_config.json"
        sed -i "s|\"authorized_faces\"|\"${FACES_DIR}\"|g" "${SCRIPT_DIR}/local_ai_config.json"
        sed -i "s|\"captured_faces\"|\"${CAPTURES_DIR}\"|g" "${SCRIPT_DIR}/local_ai_config.json"
        sed -i "s|\"tts_cache\"|\"${CACHE_DIR}\"|g" "${SCRIPT_DIR}/local_ai_config.json"
    fi

    echo -e "${GREEN}Configuration updated${NC}"
}

# Main installation flow
main() {
    check_raspberry_pi
    create_directories

    case $INSTALL_TYPE in
        "full")
            install_system_deps
            install_python_deps
            download_tflite_model
            download_vosk_model
            download_piper_voice
            configure_audio
            enable_camera
            # Install Ollama and LLM
            install_ollama
            setup_ollama_service
            download_llm_model "$DEFAULT_LLM_MODEL"
            test_llm
            ;;
        "minimal")
            install_system_deps
            install_minimal_python_deps
            download_tflite_model
            ;;
        "models")
            download_tflite_model
            download_vosk_model
            download_piper_voice
            ;;
        "llm-only")
            install_ollama
            setup_ollama_service
            download_llm_model "$DEFAULT_LLM_MODEL"
            test_llm
            ;;
    esac

    create_example_face
    update_config
    test_installation

    echo ""
    echo -e "${GREEN}=========================================="
    echo "   Setup Complete!"
    echo "==========================================${NC}"
    echo ""
    echo -e "${BLUE}AI Components Installed:${NC}"
    echo "  - TensorFlow Lite (Object Detection)"
    echo "  - Vosk (Voice Recognition)"
    echo "  - Piper (Text-to-Speech)"
    echo "  - Ollama + ${DEFAULT_LLM_MODEL} (On-Device LLM)"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo "1. Add photos of authorized people to: ${FACES_DIR}/"
    echo "2. Test the LLM: python3 sentry_brain.py"
    echo "3. Test all AI: python3 local_ai.py"
    echo "4. Run the full system: python3 sentry_ai_system.py"
    echo ""
    echo -e "${BLUE}Voice commands (say 'Sentry' or 'Jarvis' first):${NC}"
    echo "  - 'Enable sentry' / 'Arm system'"
    echo "  - 'Disable sentry' / 'Disarm system'"
    echo "  - 'Status report'"
    echo "  - 'Who is there'"
    echo "  - 'Stop alarm'"
    echo ""
    echo -e "${BLUE}Ask the AI anything:${NC}"
    echo "  - 'What was the last detection?'"
    echo "  - 'How many alerts today?'"
    echo "  - 'Help me troubleshoot the camera'"
    echo ""
}

main "$@"
