#!/bin/bash

# YouTube Agent 데이터 복원 스크립트
# 실행: ./.backup/scripts/restore.sh [timestamp]

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 백업 디렉토리 설정
BACKUP_ROOT="$(dirname $(dirname $(realpath $0)))"

# 타임스탬프 파라미터
TIMESTAMP=$1

if [ -z "$TIMESTAMP" ]; then
    echo -e "${RED}사용법: $0 <timestamp>${NC}"
    echo "예시: $0 20250923_120000"
    echo -e "\n사용 가능한 백업:"
    ls -1 $BACKUP_ROOT/backup_metadata_*.json 2>/dev/null | sed 's/.*metadata_/  - /' | sed 's/.json//'
    exit 1
fi

echo -e "${YELLOW}=== YouTube Agent 데이터 복원 시작 ===${NC}"
echo "백업 타임스탬프: $TIMESTAMP"

# 메타데이터 확인
if [ ! -f "$BACKUP_ROOT/backup_metadata_${TIMESTAMP}.json" ]; then
    echo -e "${RED}백업 메타데이터를 찾을 수 없습니다: $TIMESTAMP${NC}"
    exit 1
fi

echo -e "${YELLOW}경고: 기존 데이터가 모두 삭제됩니다!${NC}"
read -p "계속하시겠습니까? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "복원 취소됨"
    exit 0
fi

# 1. PostgreSQL 복원
echo -e "\n${YELLOW}[1/3] PostgreSQL 복원 중...${NC}"
POSTGRES_BACKUP="$BACKUP_ROOT/postgresql/youtube_agent_${TIMESTAMP}.sql.gz"

if [ -f "$POSTGRES_BACKUP" ]; then
    # 기존 연결 종료
    docker exec youtube_postgres psql -U youtube_user -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='youtube_agent' AND pid <> pg_backend_pid();" >/dev/null 2>&1

    # 데이터베이스 재생성
    docker exec youtube_postgres psql -U youtube_user -d postgres -c "DROP DATABASE IF EXISTS youtube_agent;" >/dev/null
    docker exec youtube_postgres psql -U youtube_user -d postgres -c "CREATE DATABASE youtube_agent;" >/dev/null

    # 데이터 복원
    gunzip -c "$POSTGRES_BACKUP" | docker exec -i youtube_postgres psql -U youtube_user -d youtube_agent >/dev/null

    echo -e "${GREEN}✓ PostgreSQL 복원 완료${NC}"
else
    echo -e "${YELLOW}⚠ PostgreSQL 백업 파일을 찾을 수 없습니다${NC}"
fi

# 2. Qdrant 복원
echo -e "\n${YELLOW}[2/3] Qdrant 벡터 DB 복원 중...${NC}"

for collection in youtube_content youtube_summaries; do
    QDRANT_BACKUP="$BACKUP_ROOT/qdrant/${collection}_${TIMESTAMP}.snapshot"

    if [ -f "$QDRANT_BACKUP" ]; then
        echo "  - $collection 컬렉션 복원 중..."

        # 기존 컬렉션 삭제
        curl -X DELETE "http://localhost:6333/collections/${collection}" -s -o /dev/null || true

        # 스냅샷 업로드 및 복원
        curl -X PUT "http://localhost:6333/collections/${collection}/snapshots/upload" \
            -H "Content-Type: application/octet-stream" \
            --data-binary "@${QDRANT_BACKUP}" \
            -s -o /dev/null

        echo "    ✓ $collection 복원 완료"
    else
        echo -e "${YELLOW}  ⚠ $collection 백업 파일을 찾을 수 없습니다${NC}"
    fi
done

# 3. Redis 복원 (선택적)
echo -e "\n${YELLOW}[3/3] Redis 복원 중...${NC}"
REDIS_BACKUP="$BACKUP_ROOT/redis/redis_${TIMESTAMP}.rdb"

if [ -f "$REDIS_BACKUP" ]; then
    # Redis 정지
    docker exec youtube_redis redis-cli FLUSHALL >/dev/null

    # 백업 파일 복사 및 복원
    docker cp "$REDIS_BACKUP" youtube_redis:/data/dump.rdb
    docker restart youtube_redis >/dev/null

    sleep 5
    echo -e "${GREEN}✓ Redis 복원 완료${NC}"
else
    echo -e "${YELLOW}⚠ Redis 백업 파일을 찾을 수 없습니다${NC}"
fi

# 서비스 재시작
echo -e "\n${YELLOW}서비스 재시작 중...${NC}"
docker restart youtube_agent_service youtube_data_processor youtube_admin_dashboard >/dev/null 2>&1

# 복원 확인
echo -e "\n${GREEN}=== 복원 완료 ===${NC}"

# 데이터 확인
echo -e "\n복원된 데이터:"
echo "  - PostgreSQL 콘텐츠: $(docker exec youtube_postgres psql -U youtube_user -d youtube_agent -t -c "SELECT COUNT(*) FROM content;" 2>/dev/null | xargs)"
echo "  - PostgreSQL 채널: $(docker exec youtube_postgres psql -U youtube_user -d youtube_agent -t -c "SELECT COUNT(*) FROM channels;" 2>/dev/null | xargs)"
echo "  - Qdrant 컬렉션: $(curl -s http://localhost:6333/collections | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('result', {}).get('collections', [])))" 2>/dev/null || echo 0)"
echo "  - Redis 키: $(docker exec youtube_redis redis-cli DBSIZE | awk '{print $2}' 2>/dev/null || echo 0)"

echo -e "\n${GREEN}복원이 완료되었습니다!${NC}"