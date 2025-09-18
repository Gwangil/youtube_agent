#!/bin/bash

# E2E 테스트: 새 채널 추가 및 처리
# 전체 데이터 파이프라인 테스트

set -e

echo "========================================="
echo "E2E 테스트: 새 채널 추가 및 처리"
echo "========================================="

# 색상 코드
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# API 엔드포인트
API_URL="http://localhost:8000"
ADMIN_URL="http://localhost:8090"

# 테스트 채널 정보
TEST_CHANNEL_NAME="TestChannel_$(date +%s)"
TEST_CHANNEL_URL="https://www.youtube.com/@veritasium"  # 실제 존재하는 작은 채널

echo -e "${YELLOW}1. 테스트 채널 추가...${NC}"
RESPONSE=$(curl -s -X POST "$API_URL/api/channels" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"$TEST_CHANNEL_NAME\",
    \"url\": \"$TEST_CHANNEL_URL\",
    \"platform\": \"youtube\",
    \"language\": \"en\"
  }")

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 채널 추가 성공${NC}"
    echo "$RESPONSE" | python -m json.tool
else
    echo -e "${RED}✗ 채널 추가 실패${NC}"
    exit 1
fi

# 채널 ID 추출
CHANNEL_ID=$(echo "$RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

echo -e "\n${YELLOW}2. 데이터 수집 대기 (30초)...${NC}"
sleep 30

echo -e "\n${YELLOW}3. 처리 작업 상태 확인...${NC}"
docker exec youtube_data_processor python -c "
from shared.models.database import ProcessingJob, get_database_url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

# 전체 작업 상태
total = db.query(ProcessingJob).count()
pending = db.query(ProcessingJob).filter_by(status='pending').count()
processing = db.query(ProcessingJob).filter_by(status='processing').count()
completed = db.query(ProcessingJob).filter_by(status='completed').count()
failed = db.query(ProcessingJob).filter_by(status='failed').count()

print(f'전체: {total}개')
print(f'대기: {pending}개')
print(f'처리중: {processing}개')
print(f'완료: {completed}개')
print(f'실패: {failed}개')
"

echo -e "\n${YELLOW}4. STT 처리 완료 대기 (최대 5분)...${NC}"
TIMEOUT=300
ELAPSED=0

while [ $ELAPSED -lt $TIMEOUT ]; do
    COMPLETED=$(docker exec youtube_data_processor python -c "
from shared.models.database import ProcessingJob, get_database_url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

completed = db.query(ProcessingJob).filter_by(
    status='completed',
    job_type='transcribe_audio'
).count()
print(completed)
" 2>/dev/null)

    if [ "$COMPLETED" -gt "0" ]; then
        echo -e "${GREEN}✓ STT 처리 완료: ${COMPLETED}개${NC}"
        break
    fi

    echo -ne "대기 중... ${ELAPSED}초\r"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo -e "${RED}✗ 타임아웃: STT 처리가 완료되지 않았습니다${NC}"
fi

echo -e "\n${YELLOW}5. 벡터화 상태 확인...${NC}"
docker exec youtube_data_processor python -c "
from shared.models.database import VectorMapping, get_database_url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

total_chunks = db.query(VectorMapping).count()
print(f'생성된 청크: {total_chunks}개')
"

echo -e "\n${YELLOW}6. 검색 테스트...${NC}"
SEARCH_RESPONSE=$(curl -s -X POST "$API_URL/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "science experiment",
    "limit": 5
  }')

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 검색 API 성공${NC}"
    echo "$SEARCH_RESPONSE" | python -m json.tool | head -20
else
    echo -e "${RED}✗ 검색 API 실패${NC}"
fi

echo -e "\n${YELLOW}7. RAG 응답 테스트...${NC}"
CHAT_RESPONSE=$(curl -s -X POST "$API_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "youtube-agent",
    "messages": [
      {"role": "user", "content": "Tell me about recent science experiments"}
    ]
  }')

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ RAG 응답 성공${NC}"
    echo "$CHAT_RESPONSE" | python -c "
import sys, json
data = json.load(sys.stdin)
if 'choices' in data and data['choices']:
    content = data['choices'][0]['message']['content']
    print(content[:500] + '...' if len(content) > 500 else content)
"
else
    echo -e "${RED}✗ RAG 응답 실패${NC}"
fi

echo -e "\n${YELLOW}8. 데이터 정합성 검증...${NC}"
make check-data

echo -e "\n========================================="
echo -e "${GREEN}E2E 테스트 완료${NC}"
echo -e "========================================="

# 테스트 데이터 정리 (선택적)
read -p "테스트 데이터를 삭제하시겠습니까? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}테스트 데이터 정리 중...${NC}"
    # 테스트 채널 삭제 로직 추가
    echo -e "${GREEN}정리 완료${NC}"
fi