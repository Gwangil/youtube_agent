#!/bin/bash

# Docker 네트워크 문제 해결 스크립트

echo "🔧 Docker 네트워크 문제 해결 중..."
echo "================================================"

# 현재 실행 중인 컨테이너 확인
RUNNING_CONTAINERS=$(docker ps --filter "network=youtube_network" -q | wc -l)

if [ "$RUNNING_CONTAINERS" -gt 0 ]; then
    echo "⚠️  youtube_network를 사용하는 컨테이너가 $RUNNING_CONTAINERS개 실행 중입니다."
    echo ""
    docker ps --filter "network=youtube_network" --format "table {{.Names}}\t{{.Status}}"
    echo ""
    echo "컨테이너를 중지하고 네트워크를 재생성하시겠습니까? (y/n)"
    read -r response

    if [ "$response" != "y" ]; then
        echo "❌ 작업 취소됨"
        exit 1
    fi

    echo "🛑 컨테이너 중지 중..."
    docker stop $(docker ps --filter "network=youtube_network" -q)
fi

echo ""
echo "🗑️  기존 youtube_network 삭제 중..."
docker network rm youtube_network 2>/dev/null || true

echo "✨ 새 youtube_network 생성 중..."
docker network create youtube_network

echo ""
echo "✅ 네트워크 재생성 완료!"
echo ""
echo "📝 다음 명령으로 서비스를 시작하세요:"
echo "  GPU 모드: ./start_gpu.sh"
echo "  CPU 모드: ./start_cpu.sh"