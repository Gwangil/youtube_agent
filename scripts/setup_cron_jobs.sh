#!/bin/bash

echo "⏰ 데이터 품질 관리 Cron 작업 설정..."

# Cron 작업 스크립트 생성
cat > /tmp/data_quality_cron << 'EOF'
# 데이터 품질 관리 자동화 작업

# 30분마다 정합성 체크
*/30 * * * * /mnt/d/workspace/projects/youtube_agent/scripts/check_data_integrity.sh > /var/log/data_integrity_check.log 2>&1

# 1시간마다 자동 수정
0 * * * * /mnt/d/workspace/projects/youtube_agent/scripts/fix_data_integrity.sh > /var/log/data_integrity_fix.log 2>&1

# 6시간마다 Whisper 서버 재시작 (메모리 관리)
0 */6 * * * docker restart youtube_whisper_server > /var/log/whisper_restart.log 2>&1

# 매일 자정에 고아 데이터 전체 정리
0 0 * * * docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "DELETE FROM processing_jobs WHERE status = 'failed' AND created_at < NOW() - INTERVAL '7 days';" > /var/log/cleanup.log 2>&1

# 매일 새벽 3시에 Qdrant 최적화
0 3 * * * curl -X POST http://localhost:6333/collections/youtube_content/points/optimize > /var/log/qdrant_optimize.log 2>&1
EOF

echo ""
echo "📝 Cron 작업 내용:"
cat /tmp/data_quality_cron

echo ""
echo "설정하려면 다음 명령을 실행하세요:"
echo "crontab /tmp/data_quality_cron"
echo ""
echo "현재 cron 작업 확인: crontab -l"
echo "cron 작업 편집: crontab -e"
echo "cron 작업 제거: crontab -r"