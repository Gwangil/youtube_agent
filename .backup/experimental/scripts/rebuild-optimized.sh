#!/bin/bash

echo "🚀 최적화된 Docker 이미지 빌드 시작..."
echo "================================================"

# 기존 이미지 백업 태그
echo "📦 기존 이미지 백업 중..."
docker tag youtube_agent-data-processor:latest youtube_agent-data-processor:backup 2>/dev/null || true

# 빌드 캐시 정리 (선택사항)
read -p "빌드 캐시를 정리하시겠습니까? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker builder prune -f
fi

# 최적화된 이미지 빌드
echo "🔨 data-processor 최적화 이미지 빌드..."
docker-compose build --no-cache data-processor

echo "🔨 whisper-server 최적화 이미지 빌드..."
docker-compose build --no-cache whisper-server

echo "🔨 embedding-server 최적화 이미지 빌드..."
docker-compose build --no-cache embedding-server

echo "🔨 STT worker 최적화 이미지 빌드..."
docker-compose build --no-cache stt-worker-1

echo "🔨 Vectorize worker 최적화 이미지 빌드..."
docker-compose build --no-cache vectorize-worker-1

# 이미지 크기 비교
echo ""
echo "📊 이미지 크기 비교:"
echo "================================================"
echo "이전 이미지:"
docker images | grep youtube_agent | grep backup || echo "백업 이미지 없음"
echo ""
echo "최적화된 이미지:"
docker images | grep youtube_agent | grep latest

# 불필요한 이미지 정리
echo ""
read -p "이전 이미지를 삭제하시겠습니까? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker rmi $(docker images -q youtube_agent-*:backup) 2>/dev/null || true
    docker image prune -f
fi

echo ""
echo "✅ 최적화 완료!"
echo "================================================"
echo ""
echo "모델 파일은 이제 볼륨으로 마운트됩니다:"
echo "  - Whisper 모델: ./models/whisper/"
echo "  - BGE-M3 모델: ./models/models--BAAI--bge-m3/"
echo ""
echo "서비스 재시작:"
echo "  docker-compose down"
echo "  docker-compose up -d"