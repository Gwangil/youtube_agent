#!/bin/bash

# GPU 모드 시작 스크립트
# Whisper Large-v3 + BGE-M3 GPU 서버 사용

echo "🚀 YouTube Agent GPU 모드 시작"
echo "================================================"

# 환경 변수 로드
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# GPU 확인
if ! nvidia-smi &> /dev/null; then
    echo "❌ GPU를 찾을 수 없습니다!"
    echo "CPU 모드를 사용하려면 ./start_cpu.sh를 실행하세요."
    exit 1
fi

echo "🎮 GPU 정보:"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv

# 기존 컨테이너 정리
echo ""
echo "🧹 기존 처리 서비스 정리 중..."
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down 2>/dev/null
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml down 2>/dev/null

# 네트워크 생성 또는 확인
echo ""
echo "🌐 Docker 네트워크 확인..."
if ! docker network inspect youtube_network >/dev/null 2>&1; then
    echo "  생성 중..."
    docker network create youtube_network
else
    echo "  ✅ 기존 네트워크 사용"
fi

# 기본 서비스 시작
echo ""
echo "📦 기본 인프라 서비스 시작..."
docker-compose -f docker-compose.base.yml up -d postgres redis qdrant

# 데이터베이스 준비 대기
echo ""
echo "⏳ 데이터베이스 준비 대기 중..."
sleep 10

# 모니터링 및 관리 서비스
echo ""
echo "📊 모니터링 서비스 시작..."
docker-compose -f docker-compose.base.yml up -d stt-cost-api monitoring-dashboard admin-dashboard

# GPU 처리 서비스 시작
echo ""
echo "🎮 GPU 처리 서비스 시작..."
echo "  - Whisper Large-v3 서버 시작 중..."
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml up -d whisper-server

# Whisper 서버 준비 대기
echo ""
echo "⏳ Whisper GPU 서버 준비 대기 중 (최대 5분)..."
MAX_RETRIES=60
for i in $(seq 1 $MAX_RETRIES); do
    if docker exec youtube_whisper_server curl -f -s http://localhost:8082/health > /dev/null 2>&1; then
        echo "✅ Whisper 서버 준비 완료!"
        break
    fi
    echo -n "."
    sleep 5
done

# 임베딩 서버 시작
echo ""
echo "🧠 BGE-M3 임베딩 서버 시작..."
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml up -d embedding-server

# 데이터 수집 서비스
echo ""
echo "📥 데이터 수집 서비스 시작..."
docker-compose -f docker-compose.base.yml up -d data-collector

# 처리 워커 시작
echo ""
echo "⚙️ 처리 워커 시작..."
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml up -d data-processor
sleep 5
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml up -d stt-worker-1 stt-worker-2 stt-worker-3
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml up -d vectorize-worker-1 vectorize-worker-2 vectorize-worker-3

# Agent 및 UI 서비스
echo ""
echo "🤖 Agent 및 UI 서비스 시작..."
docker-compose -f docker-compose.base.yml up -d agent-service ui-service

# 상태 확인
echo ""
echo "================================================"
echo "📊 서비스 상태:"
echo ""
docker ps --format "table {{.Names}}\t{{.Status}}" | head -1
docker ps --format "table {{.Names}}\t{{.Status}}" | grep youtube | sort

echo ""
echo "✅ GPU 모드 시작 완료!"
echo ""
echo "📌 서비스 접속 정보:"
echo "  - OpenWebUI: http://localhost:3000"
echo "  - Admin Dashboard: http://localhost:8090"
echo "  - API Docs: http://localhost:8000/docs"
echo "  - Monitoring: http://localhost:8081"
echo "  - STT Cost Management: http://localhost:8084"
echo ""
echo "🎮 GPU 사용률:"
nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv

echo ""
echo "💡 팁:"
echo "  - 로그 확인: docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml logs -f [서비스명]"
echo "  - 서비스 중지: docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down"
echo "  - GPU 모니터링: watch -n 1 nvidia-smi"