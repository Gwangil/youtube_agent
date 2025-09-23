#!/bin/bash

echo "🔍 데이터 정합성 체크 시작..."

# PostgreSQL과 Qdrant 데이터 비교
echo ""
echo "📊 데이터베이스 상태:"
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
SELECT
    'PostgreSQL' as source,
    COUNT(*) as total_content,
    SUM(CASE WHEN transcript_available THEN 1 ELSE 0 END) as with_transcript,
    SUM(CASE WHEN vector_stored THEN 1 ELSE 0 END) as with_vectors
FROM content;
"

echo ""
echo "📦 Qdrant 벡터 DB 상태:"
for collection in youtube_content youtube_summaries; do
    echo -n "$collection: "
    curl -s "http://localhost:6333/collections/$collection" 2>/dev/null | \
        grep -o '"points_count":[0-9]*' | cut -d: -f2 || echo "0"
done

echo ""
echo "🔄 처리 작업 상태:"
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
SELECT
    job_type,
    status,
    COUNT(*) as count
FROM processing_jobs
GROUP BY job_type, status
ORDER BY job_type, status;
"

echo ""
echo "⚠️  불일치 검사:"

# 1. transcript_available=true이지만 실제 트랜스크립트가 없는 경우
echo ""
echo "1. 트랜스크립트 플래그 불일치:"
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
SELECT c.id, c.title
FROM content c
WHERE c.transcript_available = TRUE
AND NOT EXISTS (
    SELECT 1 FROM transcripts t WHERE t.content_id = c.id
)
LIMIT 5;
"

# 2. vector_stored=true이지만 실제 벡터 매핑이 없는 경우
echo ""
echo "2. 벡터 플래그 불일치:"
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
SELECT c.id, c.title
FROM content c
WHERE c.vector_stored = TRUE
AND NOT EXISTS (
    SELECT 1 FROM vector_mappings v WHERE v.content_id = c.id
)
LIMIT 5;
"

# 3. 30분 이상 processing 상태인 작업
echo ""
echo "3. 멈춘 작업 (30분 이상 processing):"
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
SELECT
    id,
    content_id,
    job_type,
    created_at,
    NOW() - created_at as stuck_time
FROM processing_jobs
WHERE status = 'processing'
AND created_at < NOW() - INTERVAL '30 minutes'
LIMIT 5;
"

# 4. 고아 데이터 체크
echo ""
echo "4. 고아 데이터:"
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
SELECT
    'transcripts' as table_name,
    COUNT(*) as orphan_count
FROM transcripts t
WHERE NOT EXISTS (
    SELECT 1 FROM content c WHERE c.id = t.content_id
)
UNION ALL
SELECT
    'vector_mappings' as table_name,
    COUNT(*) as orphan_count
FROM vector_mappings v
WHERE NOT EXISTS (
    SELECT 1 FROM content c WHERE c.id = v.content_id
);
"

echo ""
echo "✅ 정합성 체크 완료"