#!/usr/bin/env python3
"""
작업 자동 복구 시스템
실패하거나 멈춘 작업을 자동으로 감지하고 복구
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import redis
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobRecoveryManager:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL", "postgresql://youtube_user:youtube_pass@postgres:5432/youtube_agent")
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)

        self.redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True
        )

        # 복구 설정
        self.max_retry_count = 3
        self.stuck_job_timeout = timedelta(minutes=30)
        self.failed_job_grace_period = timedelta(hours=24)

    def recover_jobs(self) -> Dict:
        """작업 복구 실행"""
        logger.info(f"작업 복구 시작: {datetime.now()}")

        results = {
            'timestamp': datetime.now().isoformat(),
            'recovered': {
                'stuck': 0,
                'failed': 0,
                'orphaned': 0
            },
            'cleaned': {
                'duplicates': 0,
                'expired': 0
            }
        }

        # 1. 멈춘 작업 복구
        stuck_count = self._recover_stuck_jobs()
        results['recovered']['stuck'] = stuck_count

        # 2. 실패한 작업 재시도
        failed_count = self._retry_failed_jobs()
        results['recovered']['failed'] = failed_count

        # 3. 고아 작업 처리
        orphaned_count = self._handle_orphaned_jobs()
        results['recovered']['orphaned'] = orphaned_count

        # 4. 중복 작업 제거
        duplicate_count = self._remove_duplicate_jobs()
        results['cleaned']['duplicates'] = duplicate_count

        # 5. 만료된 작업 정리
        expired_count = self._clean_expired_jobs()
        results['cleaned']['expired'] = expired_count

        # 결과 저장
        self._save_recovery_results(results)

        total_recovered = sum(results['recovered'].values())
        total_cleaned = sum(results['cleaned'].values())

        logger.info(f"작업 복구 완료: {total_recovered}개 복구, {total_cleaned}개 정리")

        return results

    def _recover_stuck_jobs(self) -> int:
        """멈춘 작업 복구"""
        session = self.SessionLocal()
        recovered = 0

        try:
            # processing 상태에서 멈춘 작업 찾기
            query = text("""
                UPDATE processing_jobs
                SET status = 'pending',
                    retry_count = COALESCE(retry_count, 0) + 1,
                    error_message = 'Recovered from stuck state'
                WHERE status = 'processing'
                AND created_at < :timeout_time
                AND COALESCE(retry_count, 0) < :max_retry
                RETURNING id, job_type, content_id
            """)

            timeout_time = datetime.now() - self.stuck_job_timeout
            result = session.execute(query, {
                'timeout_time': timeout_time,
                'max_retry': self.max_retry_count
            })

            recovered_jobs = result.fetchall()
            recovered = len(recovered_jobs)

            if recovered > 0:
                logger.info(f"  멈춘 작업 {recovered}개 복구됨")
                for job in recovered_jobs:
                    logger.debug(f"    - Job {job[0]}: {job[1]} (content_id: {job[2]})")

            session.commit()

        except Exception as e:
            logger.error(f"멈춘 작업 복구 실패: {e}")
            session.rollback()
        finally:
            session.close()

        return recovered

    def _retry_failed_jobs(self) -> int:
        """실패한 작업 재시도"""
        session = self.SessionLocal()
        retried = 0

        try:
            # 재시도 가능한 실패 작업 찾기
            query = text("""
                UPDATE processing_jobs
                SET status = 'pending',
                    retry_count = COALESCE(retry_count, 0) + 1,
                    error_message = NULL
                WHERE status = 'failed'
                AND COALESCE(retry_count, 0) < :max_retry
                AND created_at > :grace_period
                AND error_message NOT LIKE '%permanent%'
                AND error_message NOT LIKE '%deleted%'
                RETURNING id, job_type, retry_count
            """)

            grace_period = datetime.now() - self.failed_job_grace_period
            result = session.execute(query, {
                'max_retry': self.max_retry_count,
                'grace_period': grace_period
            })

            retried_jobs = result.fetchall()
            retried = len(retried_jobs)

            if retried > 0:
                logger.info(f"  실패한 작업 {retried}개 재시도 설정")
                for job in retried_jobs:
                    logger.debug(f"    - Job {job[0]}: {job[1]} (재시도 횟수: {job[2]})")

            session.commit()

        except Exception as e:
            logger.error(f"실패 작업 재시도 설정 실패: {e}")
            session.rollback()
        finally:
            session.close()

        return retried

    def _handle_orphaned_jobs(self) -> int:
        """고아 작업 처리"""
        session = self.SessionLocal()
        handled = 0

        try:
            # 콘텐츠가 삭제된 작업들
            query = text("""
                UPDATE processing_jobs j
                SET status = 'cancelled',
                    error_message = 'Content deleted'
                WHERE NOT EXISTS (
                    SELECT 1 FROM content c
                    WHERE c.id = j.content_id
                )
                AND status IN ('pending', 'processing')
                RETURNING id
            """)

            result = session.execute(query)
            orphaned = result.fetchall()
            handled = len(orphaned)

            if handled > 0:
                logger.info(f"  고아 작업 {handled}개 취소됨")

            session.commit()

        except Exception as e:
            logger.error(f"고아 작업 처리 실패: {e}")
            session.rollback()
        finally:
            session.close()

        return handled

    def _remove_duplicate_jobs(self) -> int:
        """중복 작업 제거"""
        session = self.SessionLocal()
        removed = 0

        try:
            # 동일한 content_id와 job_type의 중복 제거
            query = text("""
                DELETE FROM processing_jobs
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY content_id, job_type
                                   ORDER BY
                                       CASE status
                                           WHEN 'processing' THEN 1
                                           WHEN 'pending' THEN 2
                                           WHEN 'failed' THEN 3
                                           ELSE 4
                                       END,
                                       created_at DESC
                               ) as rn
                        FROM processing_jobs
                        WHERE status IN ('pending', 'failed')
                    ) t
                    WHERE rn > 1
                )
                RETURNING id
            """)

            result = session.execute(query)
            duplicates = result.fetchall()
            removed = len(duplicates)

            if removed > 0:
                logger.info(f"  중복 작업 {removed}개 제거됨")

            session.commit()

        except Exception as e:
            logger.error(f"중복 작업 제거 실패: {e}")
            session.rollback()
        finally:
            session.close()

        return removed

    def _clean_expired_jobs(self) -> int:
        """만료된 작업 정리"""
        session = self.SessionLocal()
        cleaned = 0

        try:
            # 오래된 완료/취소 작업 제거
            query = text("""
                DELETE FROM processing_jobs
                WHERE status IN ('completed', 'cancelled')
                AND created_at < NOW() - INTERVAL '7 days'
                RETURNING id
            """)

            result = session.execute(query)
            expired = result.fetchall()

            # 오래된 실패 작업 제거
            query = text("""
                DELETE FROM processing_jobs
                WHERE status = 'failed'
                AND retry_count >= :max_retry
                AND created_at < NOW() - INTERVAL '30 days'
                RETURNING id
            """)

            result = session.execute(query, {'max_retry': self.max_retry_count})
            expired.extend(result.fetchall())

            cleaned = len(expired)

            if cleaned > 0:
                logger.info(f"  만료된 작업 {cleaned}개 정리됨")

            session.commit()

        except Exception as e:
            logger.error(f"만료 작업 정리 실패: {e}")
            session.rollback()
        finally:
            session.close()

        return cleaned

    def _save_recovery_results(self, results: Dict):
        """복구 결과 저장"""
        try:
            # Redis에 저장
            key = f"job_recovery:latest"
            self.redis_client.setex(key, 86400, json.dumps(results))

            # 통계 업데이트
            stats_key = "job_recovery:stats"
            stats = self.redis_client.get(stats_key)
            if stats:
                stats = json.loads(stats)
            else:
                stats = {
                    'total_recovered': 0,
                    'total_cleaned': 0,
                    'last_run': None
                }

            stats['total_recovered'] += sum(results['recovered'].values())
            stats['total_cleaned'] += sum(results['cleaned'].values())
            stats['last_run'] = results['timestamp']

            self.redis_client.set(stats_key, json.dumps(stats))

        except Exception as e:
            logger.error(f"복구 결과 저장 실패: {e}")

    def get_job_statistics(self) -> Dict:
        """작업 통계 조회"""
        session = self.SessionLocal()
        stats = {}

        try:
            # 상태별 작업 수
            query = text("""
                SELECT status, COUNT(*) as count
                FROM processing_jobs
                GROUP BY status
            """)
            result = session.execute(query)

            stats['by_status'] = {row[0]: row[1] for row in result}

            # 작업 타입별 통계
            query = text("""
                SELECT job_type, status, COUNT(*) as count
                FROM processing_jobs
                GROUP BY job_type, status
            """)
            result = session.execute(query)

            stats['by_type'] = {}
            for job_type, status, count in result:
                if job_type not in stats['by_type']:
                    stats['by_type'][job_type] = {}
                stats['by_type'][job_type][status] = count

            # 최근 실패 작업
            query = text("""
                SELECT id, job_type, content_id, error_message, retry_count
                FROM processing_jobs
                WHERE status = 'failed'
                ORDER BY created_at DESC
                LIMIT 10
            """)
            result = session.execute(query)

            stats['recent_failures'] = [
                {
                    'id': row[0],
                    'type': row[1],
                    'content_id': row[2],
                    'error': row[3],
                    'retries': row[4]
                }
                for row in result
            ]

        except Exception as e:
            logger.error(f"통계 조회 실패: {e}")
        finally:
            session.close()

        return stats

def run_recovery_service(interval_seconds: int = 300):
    """복구 서비스 실행"""
    manager = JobRecoveryManager()

    logger.info(f"작업 복구 서비스 시작 (간격: {interval_seconds}초)")

    while True:
        try:
            # 복구 실행
            results = manager.recover_jobs()

            # 통계 출력
            if results['recovered']['stuck'] > 0 or results['recovered']['failed'] > 0:
                stats = manager.get_job_statistics()
                logger.info(f"현재 작업 상태: {stats.get('by_status', {})}")

            # 대기
            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("작업 복구 서비스 종료")
            break
        except Exception as e:
            logger.error(f"복구 서비스 오류: {e}")
            time.sleep(30)  # 오류 시 30초 후 재시도

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "once":
            # 한 번만 실행
            manager = JobRecoveryManager()
            results = manager.recover_jobs()
            print(json.dumps(results, indent=2))
        elif sys.argv[1] == "stats":
            # 통계만 조회
            manager = JobRecoveryManager()
            stats = manager.get_job_statistics()
            print(json.dumps(stats, indent=2))
    else:
        # 서비스 모드
        run_recovery_service()