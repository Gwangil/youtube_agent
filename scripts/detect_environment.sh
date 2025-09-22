#!/bin/bash

# 환경 감지 스크립트
# GPU 사용 가능 여부를 확인하고 적절한 모드를 선택

echo "🔍 환경 감지 중..."
echo "================================================"

# GPU 감지 함수
detect_gpu() {
    # nvidia-smi 존재 확인
    if ! command -v nvidia-smi &> /dev/null; then
        return 1
    fi

    # GPU 사용 가능 확인
    if nvidia-smi &> /dev/null; then
        GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader | wc -l)
        if [ "$GPU_COUNT" -gt 0 ]; then
            GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
            GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
            return 0
        fi
    fi
    return 1
}

# OpenAI API 키 확인
check_openai_key() {
    if [ -z "$OPENAI_API_KEY" ]; then
        if [ -f .env ]; then
            set -a
            source .env
            set +a
        fi
    fi

    if [ -z "$OPENAI_API_KEY" ]; then
        return 1
    fi
    return 0
}

# Docker 확인
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker가 설치되지 않았습니다."
        exit 1
    fi

    if ! docker info &> /dev/null; then
        echo "❌ Docker 데몬이 실행되지 않았습니다."
        exit 1
    fi
}

# 메인 감지 로직
main() {
    echo ""
    echo "📋 시스템 정보:"
    echo "  OS: $(uname -s)"
    echo "  Kernel: $(uname -r)"
    echo "  CPU: $(nproc) cores"
    echo "  Memory: $(free -h | grep ^Mem | awk '{print $2}')"

    # Docker 확인
    check_docker
    echo "  ✅ Docker 사용 가능"

    # GPU 감지
    echo ""
    echo "🎮 GPU 감지:"
    if detect_gpu; then
        echo "  ✅ GPU 감지됨: $GPU_NAME"
        echo "  📊 VRAM: ${GPU_MEMORY}MB"
        GPU_MODE=true

        # Whisper Large-v3 모델 실행 가능 여부 확인
        if [ "$GPU_MEMORY" -lt 8000 ]; then
            echo "  ⚠️ VRAM 부족 (8GB 미만) - Whisper Large 모델 실행 불가"
            echo "  💡 OpenAI API 모드를 권장합니다."
            GPU_MODE=false
        fi
    else
        echo "  ❌ GPU 없음 또는 NVIDIA 드라이버 미설치"
        GPU_MODE=false
    fi

    # OpenAI API 키 확인
    echo ""
    echo "🔑 OpenAI API 확인:"
    if check_openai_key; then
        echo "  ✅ OpenAI API 키 설정됨"
        OPENAI_MODE=true
    else
        echo "  ❌ OpenAI API 키 없음"
        OPENAI_MODE=false
    fi

    # 권장 모드 결정
    echo ""
    echo "================================================"
    echo "🎯 권장 실행 모드:"
    echo ""

    if [ "$GPU_MODE" = true ]; then
        echo "  🚀 GPU 모드 (Whisper Large-v3 + BGE-M3)"
        echo ""
        echo "  실행 명령:"
        echo "  ./start_gpu.sh"
        echo ""
        echo "  또는:"
        echo "  docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml up -d"
        MODE="gpu"
    elif [ "$OPENAI_MODE" = true ]; then
        echo "  ☁️ CPU 모드 (OpenAI API)"
        echo ""
        echo "  실행 명령:"
        echo "  ./start_cpu.sh"
        echo ""
        echo "  또는:"
        echo "  docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml up -d"
        MODE="cpu"
    else
        echo "  ❌ 실행 불가"
        echo ""
        echo "  GPU가 없고 OpenAI API 키도 설정되지 않았습니다."
        echo "  다음 중 하나를 수행하세요:"
        echo "  1. NVIDIA GPU 드라이버 설치"
        echo "  2. .env 파일에 OPENAI_API_KEY 설정"
        MODE="none"
        exit 1
    fi

    # 모드를 파일에 저장
    echo "$MODE" > .detected_mode
    echo ""
    echo "📝 감지된 모드가 .detected_mode 파일에 저장되었습니다."
}

# 스크립트 실행
main