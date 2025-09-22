#!/bin/bash

# 통합 시작 스크립트
# 자동으로 환경을 감지하고 적절한 모드로 시작

echo "🚀 YouTube Agent 시작"
echo "================================================"

# 환경 감지 실행
./scripts/detect_environment.sh

# 감지된 모드 확인
if [ ! -f .detected_mode ]; then
    echo "❌ 환경 감지 실패"
    exit 1
fi

MODE=$(cat .detected_mode)

echo ""
echo "🎯 감지된 모드: $MODE"
echo ""

# 모드에 따라 적절한 스크립트 실행
case "$MODE" in
    gpu)
        echo "GPU 모드로 시작합니다..."
        ./start_gpu.sh
        ;;
    cpu)
        echo "CPU 모드(OpenAI API)로 시작합니다..."
        ./start_cpu.sh
        ;;
    *)
        echo "❌ 알 수 없는 모드: $MODE"
        exit 1
        ;;
esac