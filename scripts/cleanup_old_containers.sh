#!/bin/bash

# 이전 구성의 컨테이너 정리 스크립트
# 새로운 base/gpu/cpu 분리 구성으로 마이그레이션

echo "🧹 이전 Docker 구성 정리"
echo "================================================"

# 현재 실행 중인 컨테이너 확인
echo ""
echo "📊 현재 실행 중인 컨테이너:"
docker ps --filter "name=youtube" --format "table {{.Names}}\t{{.Status}}" | head -20

echo ""
echo "⚠️  주의: 이 스크립트는 모든 YouTube Agent 컨테이너를 정리합니다."
echo "데이터는 보존되지만 실행 중인 서비스가 중단됩니다."
echo ""
read -p "계속하시겠습니까? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 취소됨"
    exit 1
fi

echo ""
echo "1️⃣ 기존 docker-compose.yml 구성 정리..."
# 기존 단일 docker-compose.yml 사용 시 정리
if [ -f docker-compose.yml ] && ! grep -q "docker-compose.base.yml" docker-compose.yml 2>/dev/null; then
    echo "  기존 docker-compose.yml 감지됨"
    docker-compose down --remove-orphans
fi

echo ""
echo "2️⃣ 새로운 구성으로 정리..."
# GPU 모드 정리
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down --remove-orphans 2>/dev/null

# CPU 모드 정리
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml down --remove-orphans 2>/dev/null

echo ""
echo "3️⃣ 고아 컨테이너 수동 정리..."
# 특정 이름 패턴의 컨테이너 정리
OLD_CONTAINERS=$(docker ps -aq --filter "name=youtube_whisper_server" --filter "name=youtube_embedding_server" --filter "name=youtube_stt_worker" --filter "name=youtube_vectorize_worker")

if [ ! -z "$OLD_CONTAINERS" ]; then
    echo "  제거할 컨테이너:"
    docker ps -a --filter "name=youtube_whisper_server" --filter "name=youtube_embedding_server" --format "  - {{.Names}}"
    docker stop $OLD_CONTAINERS 2>/dev/null
    docker rm $OLD_CONTAINERS 2>/dev/null
    echo "  ✅ 고아 컨테이너 제거 완료"
else
    echo "  ✅ 고아 컨테이너 없음"
fi

echo ""
echo "4️⃣ Docker 네트워크 확인..."
docker network inspect youtube_network >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "  ✅ youtube_network 존재"
else
    echo "  🔄 youtube_network 생성 중..."
    docker network create youtube_network
fi

echo ""
echo "5️⃣ 데이터 볼륨 상태..."
echo "  보존된 볼륨:"
docker volume ls --filter "name=youtube" --format "  - {{.Name}}"

echo ""
echo "================================================"
echo "✅ 정리 완료!"
echo ""
echo "📝 다음 단계:"
echo "  1. 환경 확인: ./detect_environment.sh"
echo "  2. 서비스 시작:"
echo "     - 자동 모드: ./start.sh"
echo "     - GPU 모드: ./start_gpu.sh"
echo "     - CPU 모드: ./start_cpu.sh"
echo ""
echo "💡 팁: 데이터는 모두 보존되어 있으므로 서비스를 재시작하면"
echo "      이전 상태에서 계속 작업할 수 있습니다."