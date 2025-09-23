#!/bin/bash

echo "🔧 데이터 정합성 자동 수정 시작..."

# 1. 플래그 불일치 수정
echo ""
echo "📋 플래그 불일치 수정:"

# transcript_available 수정
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
-- transcript_available = true이지만 실제 없는 경우
UPDATE content c
SET transcript_available = FALSE
WHERE transcript_available = TRUE
AND NOT EXISTS (
    SELECT 1 FROM transcripts t WHERE t.content_id = c.id
);
"

docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
-- transcript_available = false이지만 실제 있는 경우
UPDATE content c
SET transcript_available = TRUE
WHERE transcript_available = FALSE
AND EXISTS (
    SELECT 1 FROM transcripts t WHERE t.content_id = c.id
);
"

# vector_stored 수정
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
-- vector_stored = true이지만 실제 없는 경우
UPDATE content c
SET vector_stored = FALSE
WHERE vector_stored = TRUE
AND NOT EXISTS (
    SELECT 1 FROM vector_mappings v WHERE v.content_id = c.id
);
"

docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
-- vector_stored = false이지만 실제 있는 경우
UPDATE content c
SET vector_stored = TRUE
WHERE vector_stored = FALSE
AND EXISTS (
    SELECT 1 FROM vector_mappings v WHERE v.content_id = c.id
);
"

# 2. 멈춘 작업 재시작
echo ""
echo "🔄 멈춘 작업 재시작:"
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
UPDATE processing_jobs
SET status = 'pending',
    retry_count = retry_count + 1,
    updated_at = NOW()
WHERE status = 'processing'
AND created_at < NOW() - INTERVAL '30 minutes';
"

# 3. 고아 데이터 정리
echo ""
echo "🗑️  고아 데이터 정리:"

# 고아 트랜스크립트 정리
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
DELETE FROM transcripts t
WHERE NOT EXISTS (
    SELECT 1 FROM content c WHERE c.id = t.content_id
);
"

# 고아 벡터 매핑 정리
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
DELETE FROM vector_mappings v
WHERE NOT EXISTS (
    SELECT 1 FROM content c WHERE c.id = v.content_id
);
"

# 4. 중복 작업 제거
echo ""
echo "🔁 중복 작업 제거:"
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
DELETE FROM processing_jobs
WHERE id NOT IN (
    SELECT MIN(id)
    FROM processing_jobs
    GROUP BY content_id, job_type
)
AND status = 'pending';
"

# 5. Qdrant 중복 벡터 정리 (Python 스크립트 필요)
echo ""
echo "📦 Qdrant 중복 벡터 정리:"

# Python 스크립트로 Qdrant 정리
docker exec youtube_data_processor python -c "
from qdrant_client import QdrantClient
from collections import Counter

client = QdrantClient(host='qdrant', port=6333)

for collection in ['youtube_content', 'youtube_summaries']:
    try:
        # 모든 포인트 조회
        response = client.scroll(
            collection_name=collection,
            limit=10000
        )
        points = response[0]

        # content_id별 그룹화
        content_ids = {}
        for point in points:
            cid = point.payload.get('content_id')
            if cid:
                if cid not in content_ids:
                    content_ids[cid] = []
                content_ids[cid].append(point.id)

        # 중복 제거 통계
        duplicates = sum(len(ids) - 1 for ids in content_ids.values() if len(ids) > 1)

        if duplicates > 0:
            print(f'{collection}: {duplicates}개 중복 벡터 발견')
            # TODO: 실제 중복 제거 로직 구현
        else:
            print(f'{collection}: 중복 없음')

    except Exception as e:
        print(f'{collection} 오류: {e}')
"

# 6. Redis 캐시 초기화
echo ""
echo "💾 Redis 캐시 초기화:"
docker exec youtube_redis redis-cli FLUSHDB

echo ""
echo "✅ 데이터 정합성 수정 완료"

# 수정 후 상태 재확인
echo ""
echo "📊 수정 후 상태:"
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
SELECT
    COUNT(*) as total_content,
    SUM(CASE WHEN transcript_available THEN 1 ELSE 0 END) as with_transcript,
    SUM(CASE WHEN vector_stored THEN 1 ELSE 0 END) as with_vectors,
    SUM(CASE WHEN transcript_available != EXISTS(SELECT 1 FROM transcripts t WHERE t.content_id = content.id) THEN 1 ELSE 0 END) as transcript_mismatch,
    SUM(CASE WHEN vector_stored != EXISTS(SELECT 1 FROM vector_mappings v WHERE v.content_id = content.id) THEN 1 ELSE 0 END) as vector_mismatch
FROM content;
"