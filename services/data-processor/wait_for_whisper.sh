#!/bin/bash

# Whisper 서버가 완전히 준비될 때까지 대기하는 스크립트
# GPU 서버가 모델을 로드하고 준비되었는지 확인

WHISPER_SERVER_URL=${WHISPER_SERVER_URL:-http://whisper-server:8082}
MAX_RETRIES=60
RETRY_INTERVAL=5

echo "🚀 Whisper 서버 연결 대기중... ($WHISPER_SERVER_URL)"

for i in $(seq 1 $MAX_RETRIES); do
    echo "연결 시도 $i/$MAX_RETRIES..."

    # 헬스체크 엔드포인트 확인
    if curl -f -s -o /dev/null -w "%{http_code}" "${WHISPER_SERVER_URL}/health" | grep -q "200"; then
        echo "✅ Whisper 서버 헬스체크 성공!"

        # 실제 transcribe 테스트 (짧은 무음 파일로)
        # 임시 무음 파일 생성
        TMP_AUDIO="/tmp/test_audio_${RANDOM}.wav"
        ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 1 -acodec pcm_s16le -ar 16000 -ac 1 "$TMP_AUDIO" 2>/dev/null

        if [ -f "$TMP_AUDIO" ]; then
            echo "테스트 오디오로 실제 transcribe 확인 중..."
            RESPONSE=$(curl -s -X POST \
                -F "audio=@${TMP_AUDIO}" \
                -F "language=ko" \
                "${WHISPER_SERVER_URL}/transcribe" 2>/dev/null)

            rm -f "$TMP_AUDIO"

            if echo "$RESPONSE" | grep -q "text"; then
                echo "✅ Whisper 서버가 완전히 준비되었습니다!"
                echo "서버 응답: $RESPONSE"
                exit 0
            else
                echo "⚠️ Transcribe 테스트 실패. 응답: $RESPONSE"
            fi
        fi
    else
        echo "⏳ Whisper 서버 아직 준비중..."
    fi

    sleep $RETRY_INTERVAL
done

echo "❌ Whisper 서버 연결 실패! $MAX_RETRIES 회 시도 후 포기"
exit 1