#!/bin/bash

# CPU 모드 시작 스크립트
# OpenAI API 전용

echo "☁️ YouTube Agent CPU 모드 시작 (OpenAI API)"
echo "================================================"

# 환경 변수 로드
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# OpenAI API 키 확인
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ OpenAI API 키가 설정되지 않았습니다!"
    echo ".env 파일에 OPENAI_API_KEY를 설정하세요."
    exit 1
fi

echo "✅ OpenAI API 키 확인됨"

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

# OpenAI 임베딩 서버 시작
echo ""
echo "☁️ OpenAI 임베딩 서버 시작..."
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml up -d embedding-server-openai

# 데이터 수집 서비스
echo ""
echo "📥 데이터 수집 서비스 시작..."
docker-compose -f docker-compose.base.yml up -d data-collector

# 처리 워커 시작
echo ""
echo "⚙️ OpenAI API 처리 워커 시작..."
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml up -d data-processor

# STT 워커 (더 많은 병렬 처리)
echo ""
echo "🎙️ OpenAI Whisper API 워커 시작 (5개)..."
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml up -d \
    stt-worker-openai-1 \
    stt-worker-openai-2 \
    stt-worker-openai-3 \
    stt-worker-openai-4 \
    stt-worker-openai-5

# 벡터화 워커
echo ""
echo "📐 벡터화 워커 시작..."
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml up -d \
    vectorize-worker-1 \
    vectorize-worker-2 \
    vectorize-worker-3

# Agent 및 UI 서비스
echo ""
echo "🤖 Agent 및 UI 서비스 시작..."
# Agent 서비스에 임베딩 서버 URL 설정
docker-compose -f docker-compose.base.yml up -d agent-service
docker exec youtube_agent_service sh -c "export EMBEDDING_SERVER_URL=http://embedding-server-openai:8083"
docker-compose -f docker-compose.base.yml up -d ui-service

# 상태 확인
echo ""
echo "================================================"
echo "📊 서비스 상태:"
echo ""
docker ps --format "table {{.Names}}\t{{.Status}}" | head -1
docker ps --format "table {{.Names}}\t{{.Status}}" | grep youtube | sort

echo ""
echo "✅ CPU 모드 시작 완료!"
echo ""
echo "📌 서비스 접속 정보:"
echo "  - OpenWebUI: http://localhost:3000"
echo "  - Admin Dashboard: http://localhost:8090"
echo "  - API Docs: http://localhost:8000/docs"
echo "  - Monitoring: http://localhost:8081"
echo "  - STT Cost Management: http://localhost:8084"
echo ""
echo "💰 OpenAI API 비용 정보:"
echo "  - Whisper API: $0.006/분"
echo "  - 일일 한도: $${STT_DAILY_COST_LIMIT:-10.0}"
echo "  - 월별 한도: $${STT_MONTHLY_COST_LIMIT:-100.0}"
echo "  - 자동 승인: $${STT_AUTO_APPROVE_THRESHOLD:-0.10} 이하"
echo ""
echo "💡 팁:"
echo "  - 로그 확인: docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml logs -f [서비스명]"
echo "  - 서비스 중지: docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml down"
echo "  - 비용 승인: http://localhost:8084 접속"