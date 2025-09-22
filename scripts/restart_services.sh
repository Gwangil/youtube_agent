#!/bin/bash

echo "🔄 YouTube Agent 서비스 재시작 시작..."
echo "================================================"

# 1. STT 워커들 먼저 정지
echo "⏸️ STT 워커 정지 중..."
docker stop youtube_stt_worker_1 youtube_stt_worker_2 youtube_stt_worker_3 2>/dev/null
docker stop youtube_data_processor 2>/dev/null

# 2. Whisper 서버 재시작
echo ""
echo "🔄 Whisper GPU 서버 재시작 중..."
docker restart youtube_whisper_server

# 3. Whisper 서버 준비 대기
echo ""
echo "⏳ Whisper 서버가 완전히 준비될 때까지 대기 중..."
MAX_RETRIES=60
for i in $(seq 1 $MAX_RETRIES); do
    if docker exec youtube_whisper_server curl -f -s http://localhost:8082/health > /dev/null 2>&1; then
        echo "✅ Whisper 서버 준비 완료!"
        break
    fi
    echo -n "."
    sleep 5
done

# 4. 데이터 프로세서 시작
echo ""
echo "🚀 Data Processor 시작..."
docker start youtube_data_processor

# 5. STT 워커들 순차 시작
echo ""
echo "🚀 STT 워커들 시작..."
docker start youtube_stt_worker_1
sleep 2
docker start youtube_stt_worker_2
sleep 2
docker start youtube_stt_worker_3

# 6. 상태 확인
echo ""
echo "================================================"
echo "📊 서비스 상태 확인:"
echo ""

docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(whisper|stt|processor)"

echo ""
echo "✅ 서비스 재시작 완료!"
echo ""
echo "📌 GPU 사용률 확인:"
nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv