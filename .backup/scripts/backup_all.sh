#!/bin/bash

# YouTube Agent 전체 데이터 백업 스크립트
# 실행: ./.backup/scripts/backup_all.sh

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 백업 디렉토리 설정
BACKUP_ROOT="$(dirname $(dirname $(realpath $0)))"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo -e "${GREEN}=== YouTube Agent 데이터 백업 시작 ===${NC}"
echo "백업 디렉토리: $BACKUP_ROOT"
echo "타임스탬프: $TIMESTAMP"

# 1. PostgreSQL 백업
echo -e "\n${YELLOW}[1/4] PostgreSQL 백업 중...${NC}"
POSTGRES_BACKUP_DIR="$BACKUP_ROOT/postgresql"
mkdir -p "$POSTGRES_BACKUP_DIR"

# 전체 데이터베이스 덤프
docker exec youtube_postgres pg_dump -U youtube_user -d youtube_agent \
    > "$POSTGRES_BACKUP_DIR/youtube_agent_${TIMESTAMP}.sql" 2>/dev/null

# 테이블별 백업
docker exec youtube_postgres pg_dump -U youtube_user -d youtube_agent -t channels \
    > "$POSTGRES_BACKUP_DIR/channels_${TIMESTAMP}.sql" 2>/dev/null
docker exec youtube_postgres pg_dump -U youtube_user -d youtube_agent -t content \
    > "$POSTGRES_BACKUP_DIR/content_${TIMESTAMP}.sql" 2>/dev/null
docker exec youtube_postgres pg_dump -U youtube_user -d youtube_agent -t transcripts \
    > "$POSTGRES_BACKUP_DIR/transcripts_${TIMESTAMP}.sql" 2>/dev/null

# 압축
gzip "$POSTGRES_BACKUP_DIR"/*_${TIMESTAMP}.sql

echo -e "${GREEN}✓ PostgreSQL 백업 완료${NC}"

# 2. Qdrant 벡터 DB 백업
echo -e "\n${YELLOW}[2/4] Qdrant 벡터 DB 백업 중...${NC}"
QDRANT_BACKUP_DIR="$BACKUP_ROOT/qdrant"
mkdir -p "$QDRANT_BACKUP_DIR"

# Qdrant 스냅샷 생성 및 다운로드
for collection in youtube_content youtube_summaries; do
    echo "  - $collection 컬렉션 백업 중..."

    # 스냅샷 생성
    curl -X POST "http://localhost:6333/collections/${collection}/snapshots" \
        -H "Content-Type: application/json" \
        -s -o /dev/null

    # 스냅샷 목록 가져오기
    SNAPSHOT_NAME=$(curl -s "http://localhost:6333/collections/${collection}/snapshots" | \
        python3 -c "import sys, json; snapshots = json.load(sys.stdin).get('result', []); print(snapshots[-1]['name']) if snapshots else print('')")

    if [ ! -z "$SNAPSHOT_NAME" ]; then
        # 스냅샷 다운로드
        curl -s "http://localhost:6333/collections/${collection}/snapshots/${SNAPSHOT_NAME}" \
            -o "$QDRANT_BACKUP_DIR/${collection}_${TIMESTAMP}.snapshot"
    fi
done

echo -e "${GREEN}✓ Qdrant 백업 완료${NC}"

# 3. Redis 백업
echo -e "\n${YELLOW}[3/4] Redis 백업 중...${NC}"
REDIS_BACKUP_DIR="$BACKUP_ROOT/redis"
mkdir -p "$REDIS_BACKUP_DIR"

# Redis 데이터 덤프
docker exec youtube_redis redis-cli --rdb "$REDIS_BACKUP_DIR/dump_${TIMESTAMP}.rdb" >/dev/null 2>&1 || true
docker cp youtube_redis:/data/dump.rdb "$REDIS_BACKUP_DIR/redis_${TIMESTAMP}.rdb" 2>/dev/null || true

echo -e "${GREEN}✓ Redis 백업 완료${NC}"

# 4. 모델 파일 백업 (선택적)
echo -e "\n${YELLOW}[4/4] 모델 파일 확인 중...${NC}"
MODELS_BACKUP_DIR="$BACKUP_ROOT/models"
mkdir -p "$MODELS_BACKUP_DIR"

# Whisper 모델 체크 (GPU 모드인 경우)
if docker ps | grep -q youtube_whisper_server; then
    echo "  - Whisper 모델 백업 중..."
    docker exec youtube_whisper_server ls /models 2>/dev/null | while read model; do
        if [ ! -z "$model" ]; then
            docker cp youtube_whisper_server:/models/$model "$MODELS_BACKUP_DIR/" 2>/dev/null || true
        fi
    done
fi

# 백업 메타데이터 생성
cat > "$BACKUP_ROOT/backup_metadata_${TIMESTAMP}.json" << EOF
{
    "timestamp": "${TIMESTAMP}",
    "date": "$(date -Iseconds)",
    "services": {
        "postgresql": $(docker exec youtube_postgres psql -U youtube_user -d youtube_agent -t -c "SELECT COUNT(*) FROM content;" 2>/dev/null || echo 0),
        "qdrant": $(curl -s http://localhost:6333/collections | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('result', {}).get('collections', [])))" 2>/dev/null || echo 0),
        "redis": $(docker exec youtube_redis redis-cli DBSIZE | awk '{print $2}' 2>/dev/null || echo 0)
    },
    "backup_files": [
        $(ls -1 $BACKUP_ROOT/*/${TIMESTAMP}* 2>/dev/null | sed 's/^/"/; s/$/",/' | tr '\n' ' ' | sed 's/, $//')
    ]
}
EOF

# 오래된 백업 정리 (7일 이상)
echo -e "\n${YELLOW}오래된 백업 파일 정리 중...${NC}"
find "$BACKUP_ROOT" -type f -name "*.sql.gz" -mtime +7 -delete 2>/dev/null || true
find "$BACKUP_ROOT" -type f -name "*.snapshot" -mtime +7 -delete 2>/dev/null || true
find "$BACKUP_ROOT" -type f -name "*.rdb" -mtime +7 -delete 2>/dev/null || true

# 백업 크기 확인
BACKUP_SIZE=$(du -sh "$BACKUP_ROOT" | cut -f1)

echo -e "\n${GREEN}=== 백업 완료 ===${NC}"
echo "백업 위치: $BACKUP_ROOT"
echo "백업 크기: $BACKUP_SIZE"
echo "메타데이터: $BACKUP_ROOT/backup_metadata_${TIMESTAMP}.json"

# 백업 통계
echo -e "\n${GREEN}백업 통계:${NC}"
echo "  - PostgreSQL: $(ls -1 $POSTGRES_BACKUP_DIR/*.sql.gz 2>/dev/null | wc -l) 파일"
echo "  - Qdrant: $(ls -1 $QDRANT_BACKUP_DIR/*.snapshot 2>/dev/null | wc -l) 스냅샷"
echo "  - Redis: $(ls -1 $REDIS_BACKUP_DIR/*.rdb 2>/dev/null | wc -l) 덤프"
echo "  - Models: $(ls -1 $MODELS_BACKUP_DIR 2>/dev/null | wc -l) 파일"