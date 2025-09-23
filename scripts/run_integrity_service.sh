#!/bin/bash

echo "🔍 데이터 정합성 체크 서비스 시작..."

# 단일 실행 모드
if [ "$1" == "once" ]; then
    echo "단일 실행 모드..."
    docker exec youtube_data_processor python /app/integrity_checker.py once
    exit 0
fi

# 백그라운드 서비스 모드
if [ "$1" == "background" ]; then
    echo "백그라운드 서비스 시작..."
    docker exec -d youtube_data_processor python /app/integrity_checker.py
    echo "✅ 정합성 체크 서비스가 백그라운드에서 실행 중입니다."
    echo "로그 확인: docker logs youtube_data_processor | grep integrity"
    exit 0
fi

# 서비스 중지
if [ "$1" == "stop" ]; then
    echo "서비스 중지..."
    docker exec youtube_data_processor pkill -f integrity_checker.py
    echo "✅ 정합성 체크 서비스가 중지되었습니다."
    exit 0
fi

# 서비스 상태 확인
if [ "$1" == "status" ]; then
    echo "서비스 상태 확인..."
    if docker exec youtube_data_processor pgrep -f integrity_checker.py > /dev/null; then
        echo "✅ 정합성 체크 서비스 실행 중"

        # 최근 체크 결과 표시
        echo ""
        echo "최근 체크 결과:"
        docker exec youtube_data_processor python -c "
import redis
import json
r = redis.Redis(host='redis', port=6379, decode_responses=True)
result = r.get('integrity_check:latest')
if result:
    data = json.loads(result)
    print(f\"  시간: {data['timestamp']}\")
    print(f\"  발견된 문제: {data['issues_found']}개\")
    print(f\"  수정된 문제: {data['issues_fixed']}개\")
else:
    print('  아직 체크 결과가 없습니다.')
"
    else
        echo "❌ 정합성 체크 서비스가 실행되지 않고 있습니다."
    fi
    exit 0
fi

# 사용법 표시
echo "사용법:"
echo "  $0 once       # 한 번만 실행"
echo "  $0 background # 백그라운드 서비스 시작"
echo "  $0 stop       # 서비스 중지"
echo "  $0 status     # 서비스 상태 확인"