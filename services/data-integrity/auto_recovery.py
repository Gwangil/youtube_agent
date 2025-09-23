#!/usr/bin/env python3
"""
자동 복구 및 재처리 시스템
- 실패한 작업 자동 재시도
- 데이터 불일치 자동 복구
- 스마트 재처리 스케줄링
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import redis
import json

logger = logging.getLogger(__name__)

class AutoRecoveryService:
    """자동 복구 서비스"""

    def __init__(self):
        # DB 연결
        self.db_url = "postgresql://youtube_user:youtube_pass@postgres:5432/youtube_agent"
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Redis 연결
        self.redis = redis.Redis(
            host="redis",
            port=6379,
            decode_responses=True
        )

        # 복구 설정
        self.config = {
            "max_retries": 3,
            "retry_delay_minutes": 5,
            "stuck_job_timeout_minutes": 30,
            "orphan_data_retention_days": 7,
            "health_check_interval_minutes": 10
        }

    async def run_recovery_cycle(self):
        """복구 사이클 실행"""
        logger.info("자동 복구 사이클 시작")

        tasks = [
            self._recover_stuck_jobs(),
            self._retry_failed_jobs(),
            self._clean_orphan_data(),
            self._reprocess_incomplete_content(),
            self._fix_data_inconsistencies()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 집계
        recovery_report = {
            "timestamp": datetime.utcnow().isoformat(),
            "stuck_jobs": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
            "failed_jobs": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
            "orphan_cleanup": results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])},
            "incomplete_reprocess": results[3] if not isinstance(results[3], Exception) else {"error": str(results[3])},
            "inconsistency_fixes": results[4] if not isinstance(results[4], Exception) else {"error": str(results[4])}
        }

        # Redis에 보고서 저장
        self.redis.set(
            "recovery:last_report",
            json.dumps(recovery_report, ensure_ascii=False),
            ex=3600
        )

        logger.info(f"복구 사이클 완료: {recovery_report}")
        return recovery_report

    async def _recover_stuck_jobs(self) -> Dict:
        """멈춘 작업 복구"""
        recovered = 0
        failed = 0

        with self.SessionLocal() as db:
            # 30분 이상 processing 상태인 작업 조회
            stuck_threshold = datetime.utcnow() - timedelta(minutes=self.config["stuck_job_timeout_minutes"])

            stuck_jobs = db.execute(
                text("""
                    SELECT id, content_id, job_type, retry_count
                    FROM processing_jobs
                    WHERE status = 'processing'
                    AND updated_at < :threshold
                """),
                {"threshold": stuck_threshold}
            ).fetchall()

            for job in stuck_jobs:
                try:
                    if job.retry_count < self.config["max_retries"]:
                        # 재시도
                        db.execute(
                            text("""
                                UPDATE processing_jobs
                                SET status = 'pending',
                                    retry_count = retry_count + 1,
                                    updated_at = NOW()
                                WHERE id = :id
                            """),
                            {"id": job.id}
                        )
                        recovered += 1
                        logger.info(f"작업 복구: Job {job.id} (재시도 {job.retry_count + 1}/{self.config['max_retries']})")
                    else:
                        # 최대 재시도 초과 - 실패 처리
                        db.execute(
                            text("""
                                UPDATE processing_jobs
                                SET status = 'failed',
                                    error_message = 'Max retries exceeded',
                                    updated_at = NOW()
                                WHERE id = :id
                            """),
                            {"id": job.id}
                        )
                        failed += 1
                        logger.warning(f"작업 실패 처리: Job {job.id} (최대 재시도 초과)")

                except Exception as e:
                    logger.error(f"작업 복구 실패 (Job {job.id}): {e}")
                    failed += 1

            db.commit()

        return {"recovered": recovered, "failed": failed, "total": len(stuck_jobs)}

    async def _retry_failed_jobs(self) -> Dict:
        """실패한 작업 재시도"""
        retried = 0
        permanent_fail = 0

        with self.SessionLocal() as db:
            # 재시도 가능한 실패 작업 조회
            retry_threshold = datetime.utcnow() - timedelta(minutes=self.config["retry_delay_minutes"])

            failed_jobs = db.execute(
                text("""
                    SELECT id, content_id, job_type, retry_count, error_message
                    FROM processing_jobs
                    WHERE status = 'failed'
                    AND retry_count < :max_retries
                    AND updated_at < :threshold
                """),
                {
                    "max_retries": self.config["max_retries"],
                    "threshold": retry_threshold
                }
            ).fetchall()

            for job in failed_jobs:
                try:
                    # 에러 유형 분석
                    if self._is_retryable_error(job.error_message):
                        db.execute(
                            text("""
                                UPDATE processing_jobs
                                SET status = 'pending',
                                    retry_count = retry_count + 1,
                                    updated_at = NOW()
                                WHERE id = :id
                            """),
                            {"id": job.id}
                        )
                        retried += 1
                        logger.info(f"실패 작업 재시도: Job {job.id}")
                    else:
                        # 재시도 불가능한 에러
                        db.execute(
                            text("""
                                UPDATE processing_jobs
                                SET status = 'permanent_failure',
                                    updated_at = NOW()
                                WHERE id = :id
                            """),
                            {"id": job.id}
                        )
                        permanent_fail += 1

                except Exception as e:
                    logger.error(f"작업 재시도 실패 (Job {job.id}): {e}")

            db.commit()

        return {"retried": retried, "permanent_failures": permanent_fail}

    async def _clean_orphan_data(self) -> Dict:
        """고아 데이터 정리"""
        cleaned = {
            "vectors": 0,
            "transcripts": 0,
            "redis_keys": 0
        }

        with self.SessionLocal() as db:
            # 1. 콘텐츠가 삭제된 트랜스크립트 정리
            orphan_transcripts = db.execute(
                text("""
                    DELETE FROM transcripts
                    WHERE content_id NOT IN (SELECT id FROM content)
                    RETURNING id
                """)
            ).fetchall()
            cleaned["transcripts"] = len(orphan_transcripts)

            # 2. 콘텐츠가 삭제된 벡터 매핑 정리
            orphan_mappings = db.execute(
                text("""
                    DELETE FROM vector_mappings
                    WHERE content_id NOT IN (SELECT id FROM content)
                    RETURNING id
                """)
            ).fetchall()
            cleaned["vectors"] = len(orphan_mappings)

            db.commit()

        # 3. Redis 고아 키 정리
        orphan_keys = []
        for key in self.redis.keys("content:*:*"):
            content_id = key.split(":")[1]
            if content_id.isdigit():
                # DB에 존재하는지 확인
                with self.SessionLocal() as db:
                    exists = db.execute(
                        text("SELECT 1 FROM content WHERE id = :id"),
                        {"id": int(content_id)}
                    ).fetchone()

                    if not exists:
                        orphan_keys.append(key)

        if orphan_keys:
            self.redis.delete(*orphan_keys)
            cleaned["redis_keys"] = len(orphan_keys)

        logger.info(f"고아 데이터 정리: {cleaned}")
        return cleaned

    async def _reprocess_incomplete_content(self) -> Dict:
        """불완전한 콘텐츠 재처리"""
        reprocessed = 0
        skipped = 0

        with self.SessionLocal() as db:
            # 불완전한 콘텐츠 조회
            incomplete = db.execute(
                text("""
                    SELECT c.id, c.title,
                           c.transcript_available,
                           c.vector_stored,
                           COUNT(DISTINCT t.id) as transcript_count,
                           COUNT(DISTINCT v.id) as vector_count
                    FROM content c
                    LEFT JOIN transcripts t ON c.id = t.content_id
                    LEFT JOIN vector_mappings v ON c.id = v.content_id
                    WHERE c.created_at < NOW() - INTERVAL '1 hour'
                    GROUP BY c.id
                    HAVING
                        (c.transcript_available = TRUE AND COUNT(DISTINCT t.id) = 0)
                        OR (c.vector_stored = TRUE AND COUNT(DISTINCT v.id) = 0)
                """)
            ).fetchall()

            for content in incomplete:
                try:
                    # 재처리 작업 생성
                    if content.transcript_available and content.transcript_count == 0:
                        db.execute(
                            text("""
                                INSERT INTO processing_jobs
                                (content_id, job_type, status, priority)
                                VALUES (:content_id, 'extract_transcript', 'pending', 5)
                                ON CONFLICT (content_id, job_type) DO UPDATE
                                SET status = 'pending', retry_count = 0, updated_at = NOW()
                            """),
                            {"content_id": content.id}
                        )
                        reprocessed += 1

                    if content.vector_stored and content.vector_count == 0:
                        db.execute(
                            text("""
                                INSERT INTO processing_jobs
                                (content_id, job_type, status, priority)
                                VALUES (:content_id, 'vectorize', 'pending', 4)
                                ON CONFLICT (content_id, job_type) DO UPDATE
                                SET status = 'pending', retry_count = 0, updated_at = NOW()
                            """),
                            {"content_id": content.id}
                        )
                        reprocessed += 1

                except Exception as e:
                    logger.error(f"재처리 실패 (Content {content.id}): {e}")
                    skipped += 1

            db.commit()

        return {"reprocessed": reprocessed, "skipped": skipped}

    async def _fix_data_inconsistencies(self) -> Dict:
        """데이터 불일치 수정"""
        fixed = 0
        failed = 0

        with self.SessionLocal() as db:
            # 플래그 불일치 수정
            # 1. transcript_available = True이지만 실제 없는 경우
            db.execute(
                text("""
                    UPDATE content c
                    SET transcript_available = FALSE
                    WHERE transcript_available = TRUE
                    AND NOT EXISTS (
                        SELECT 1 FROM transcripts t
                        WHERE t.content_id = c.id
                    )
                """)
            )
            fixed += db.connection().execute(text("SELECT ROW_COUNT()")).scalar()

            # 2. vector_stored = True이지만 실제 없는 경우
            db.execute(
                text("""
                    UPDATE content c
                    SET vector_stored = FALSE
                    WHERE vector_stored = TRUE
                    AND NOT EXISTS (
                        SELECT 1 FROM vector_mappings v
                        WHERE v.content_id = c.id
                    )
                """)
            )
            fixed += db.connection().execute(text("SELECT ROW_COUNT()")).scalar()

            # 3. 반대 경우 (데이터는 있는데 플래그가 False)
            db.execute(
                text("""
                    UPDATE content c
                    SET transcript_available = TRUE
                    WHERE transcript_available = FALSE
                    AND EXISTS (
                        SELECT 1 FROM transcripts t
                        WHERE t.content_id = c.id
                    )
                """)
            )
            fixed += db.connection().execute(text("SELECT ROW_COUNT()")).scalar()

            db.execute(
                text("""
                    UPDATE content c
                    SET vector_stored = TRUE
                    WHERE vector_stored = FALSE
                    AND EXISTS (
                        SELECT 1 FROM vector_mappings v
                        WHERE v.content_id = c.id
                    )
                """)
            )
            fixed += db.connection().execute(text("SELECT ROW_COUNT()")).scalar()

            db.commit()

        return {"fixed": fixed, "failed": failed}

    def _is_retryable_error(self, error_message: str) -> bool:
        """재시도 가능한 에러인지 판단"""
        if not error_message:
            return True

        # 재시도 불가능한 에러 패턴
        non_retryable = [
            "file not found",
            "invalid format",
            "unsupported",
            "permission denied",
            "quota exceeded"
        ]

        error_lower = error_message.lower()
        for pattern in non_retryable:
            if pattern in error_lower:
                return False

        return True

    async def start_monitoring(self):
        """자동 복구 모니터링 시작"""
        logger.info("자동 복구 서비스 시작")

        while True:
            try:
                await self.run_recovery_cycle()
                await asyncio.sleep(self.config["health_check_interval_minutes"] * 60)

            except Exception as e:
                logger.error(f"복구 사이클 오류: {e}")
                await asyncio.sleep(60)


if __name__ == "__main__":
    service = AutoRecoveryService()
    asyncio.run(service.start_monitoring())