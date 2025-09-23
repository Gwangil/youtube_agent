#!/bin/bash

# 데이터 품질 관리 서비스 통합 관리 스크립트

SERVICES=("integrity_checker" "job_recovery" "alert_manager")

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function print_header() {
    echo ""
    echo "======================================"
    echo "$1"
    echo "======================================"
}

function start_all_services() {
    print_header "🚀 모든 데이터 품질 서비스 시작"

    for service in "${SERVICES[@]}"; do
        echo -e "${YELLOW}Starting ${service}...${NC}"
        docker exec -d youtube_data_processor python /app/${service}.py
        sleep 1
    done

    echo -e "${GREEN}✅ 모든 서비스가 시작되었습니다.${NC}"
}

function stop_all_services() {
    print_header "🛑 모든 데이터 품질 서비스 중지"

    for service in "${SERVICES[@]}"; do
        echo -e "${YELLOW}Stopping ${service}...${NC}"
        docker exec youtube_data_processor pkill -f ${service}.py
    done

    echo -e "${GREEN}✅ 모든 서비스가 중지되었습니다.${NC}"
}

function status_all_services() {
    print_header "📊 서비스 상태"

    for service in "${SERVICES[@]}"; do
        if docker exec youtube_data_processor pgrep -f ${service}.py > /dev/null; then
            echo -e "  ${service}: ${GREEN}실행 중${NC}"
        else
            echo -e "  ${service}: ${RED}중지됨${NC}"
        fi
    done

    # 최근 체크 결과
    print_header "📈 최근 체크 결과"

    docker exec youtube_data_processor python -c "
import redis
import json
from datetime import datetime

r = redis.Redis(host='redis', port=6379, decode_responses=True)

# 정합성 체크 결과
integrity = r.get('integrity_check:latest')
if integrity:
    data = json.loads(integrity)
    print('🔍 정합성 체크:')
    print(f'  - 시간: {data[\"timestamp\"]}')
    print(f'  - 발견: {data[\"issues_found\"]}개 문제')
    print(f'  - 수정: {data[\"issues_fixed\"]}개')
else:
    print('정합성 체크: 데이터 없음')

print()

# 작업 복구 결과
recovery = r.get('job_recovery:latest')
if recovery:
    data = json.loads(recovery)
    print('🔧 작업 복구:')
    print(f'  - 시간: {data[\"timestamp\"]}')
    print(f'  - 복구: 멈춘({data[\"recovered\"][\"stuck\"]}), 실패({data[\"recovered\"][\"failed\"]})')
    print(f'  - 정리: 중복({data[\"cleaned\"][\"duplicates\"]}), 만료({data[\"cleaned\"][\"expired\"]})')
else:
    print('작업 복구: 데이터 없음')

print()

# 최근 알림
alerts = r.get('alerts:latest')
if alerts:
    data = json.loads(alerts)
    print(f'⚠️ 최근 알림: {len(data)}개')
    for alert in data[:3]:
        print(f'  - [{alert[\"level\"]}] {alert[\"title\"]}')"
}

function run_integrity_check() {
    print_header "🔍 정합성 체크 실행"
    docker exec youtube_data_processor python /app/integrity_checker.py once
}

function run_job_recovery() {
    print_header "🔧 작업 복구 실행"
    docker exec youtube_data_processor python /app/job_recovery.py once
}

function run_alert_check() {
    print_header "⚠️ 알림 체크 실행"
    docker exec youtube_data_processor python /app/alert_manager.py once
}

function run_full_check() {
    print_header "🔄 전체 품질 체크 실행"

    echo -e "${YELLOW}1. 정합성 체크...${NC}"
    run_integrity_check

    echo ""
    echo -e "${YELLOW}2. 작업 복구...${NC}"
    run_job_recovery

    echo ""
    echo -e "${YELLOW}3. 알림 체크...${NC}"
    run_alert_check

    echo ""
    echo -e "${GREEN}✅ 전체 체크 완료${NC}"
}

function show_dashboard() {
    print_header "📊 데이터 품질 대시보드"

    docker exec youtube_data_processor python -c "
import psycopg2
import redis
import json
from qdrant_client import QdrantClient

# DB 연결
conn = psycopg2.connect(
    host='postgres',
    database='youtube_agent',
    user='youtube_user',
    password='youtube_pass'
)
cur = conn.cursor()

print('📈 데이터베이스 상태:')
print('-' * 40)

# 콘텐츠 상태
cur.execute('''
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN transcript_available THEN 1 ELSE 0 END) as with_transcript,
        SUM(CASE WHEN vector_stored THEN 1 ELSE 0 END) as with_vector,
        SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active
    FROM content
''')
total, transcript, vector, active = cur.fetchone()
print(f'  콘텐츠: {total}개 (활성: {active}개)')
print(f'  - Transcript: {transcript}개 ({transcript*100//total if total else 0}%)')
print(f'  - Vector: {vector}개 ({vector*100//total if total else 0}%)')

# 작업 상태
cur.execute('''
    SELECT status, COUNT(*) FROM processing_jobs
    GROUP BY status
''')
jobs = cur.fetchall()
print(f'\\n  처리 작업:')
for status, count in jobs:
    print(f'  - {status}: {count}개')

# Qdrant 상태
print('\\n📦 벡터 데이터베이스 상태:')
print('-' * 40)
try:
    qdrant = QdrantClient(host='qdrant', port=6333)
    for collection in ['youtube_content', 'youtube_summaries']:
        info = qdrant.get_collection(collection)
        print(f'  {collection}: {info.points_count} 포인트')
except Exception as e:
    print(f'  오류: {e}')

# Redis 상태
print('\\n💾 캐시/큐 상태:')
print('-' * 40)
try:
    r = redis.Redis(host='redis', port=6379)
    info = r.info()
    print(f'  메모리 사용: {info[\"used_memory_human\"]}')
    print(f'  연결된 클라이언트: {info[\"connected_clients\"]}')

    # 승인 대기열
    pending = r.llen('stt_cost:pending_approvals')
    if pending > 0:
        print(f'  ⚠️ STT 승인 대기: {pending}개')
except Exception as e:
    print(f'  오류: {e}')

cur.close()
conn.close()
"
}

function show_help() {
    echo "사용법: $0 <명령>"
    echo ""
    echo "명령:"
    echo "  start       - 모든 품질 서비스 시작"
    echo "  stop        - 모든 품질 서비스 중지"
    echo "  restart     - 모든 품질 서비스 재시작"
    echo "  status      - 서비스 상태 확인"
    echo "  check       - 전체 품질 체크 실행 (1회)"
    echo "  integrity   - 정합성 체크만 실행"
    echo "  recovery    - 작업 복구만 실행"
    echo "  alerts      - 알림 체크만 실행"
    echo "  dashboard   - 데이터 품질 대시보드"
    echo "  help        - 도움말 표시"
}

# 메인 로직
case "$1" in
    start)
        start_all_services
        ;;
    stop)
        stop_all_services
        ;;
    restart)
        stop_all_services
        sleep 2
        start_all_services
        ;;
    status)
        status_all_services
        ;;
    check)
        run_full_check
        ;;
    integrity)
        run_integrity_check
        ;;
    recovery)
        run_job_recovery
        ;;
    alerts)
        run_alert_check
        ;;
    dashboard)
        show_dashboard
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}알 수 없는 명령: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac