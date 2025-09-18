#!/bin/bash

echo "🚀 Whisper 서버 시작 준비 중..."

# Whisper 캐시 초기화
echo "📦 Whisper 캐시 초기화..."
python /app/services/data-processor/init_whisper_cache.py

# Whisper 서버 시작
echo "🎙️ Whisper STT 서버 시작..."
python /app/services/data-processor/whisper_server.py