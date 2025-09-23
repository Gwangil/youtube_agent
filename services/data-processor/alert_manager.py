#!/usr/bin/env python3
"""
데이터 품질 모니터링 및 알림 시스템
문제 감지 시 알림을 생성하고 관리
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient
import redis
import json
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AlertType(Enum):
    DATA_INTEGRITY = "data_integrity"
    PROCESSING_FAILURE = "processing_failure"
    SYSTEM_PERFORMANCE = "system_performance"
    RESOURCE_USAGE = "resource_usage"
    STUCK_JOBS = "stuck_jobs"
    DUPLICATE_DATA = "duplicate_data"

class AlertManager:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL", "postgresql://youtube_user:youtube_pass@postgres:5432/youtube_agent")
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)

        self.qdrant = QdrantClient(
            host=os.getenv("QDRANT_HOST", "qdrant"),
            port=int(os.getenv("QDRANT_PORT", 6333))
        )

        self.redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True
        )

        # 알림 임계값
        self.thresholds = {
            'stuck_jobs': 10,  # 10개 이상 멈춘 작업
            'failed_jobs': 20,  # 20개 이상 실패한 작업
            'processing_lag': 100,  # 100개 이상 대기 중인 작업
            'integrity_issues': 5,  # 5개 이상 정합성 문제
            'duplicate_rate': 0.1,  # 10% 이상 중복률
        }

    def check_and_alert(self) -> List[Dict]:
        """전체 시스템 체크 및 알림 생성"""
        logger.info(f"시스템 모니터링 시작: {datetime.now()}")

        alerts = []

        # 1. 데이터 정합성 체크
        integrity_alerts = self._check_data_integrity()
        alerts.extend(integrity_alerts)

        # 2. 처리 작업 상태 체크
        job_alerts = self._check_processing_jobs()
        alerts.extend(job_alerts)

        # 3. 시스템 성능 체크
        performance_alerts = self._check_system_performance()
        alerts.extend(performance_alerts)

        # 4. 중복 데이터 체크
        duplicate_alerts = self._check_duplicate_data()
        alerts.extend(duplicate_alerts)

        # 알림 저장 및 전송
        if alerts:
            self._save_alerts(alerts)
            self._send_notifications(alerts)

        logger.info(f"모니터링 완료: {len(alerts)}개 알림 생성")

        return alerts

    def _check_data_integrity(self) -> List[Dict]:
        """데이터 정합성 체크"""
        alerts = []
        session = self.SessionLocal()

        try:
            # transcript 플래그 불일치
            query = text("""
                SELECT COUNT(*) FROM content c
                WHERE (
                    (transcript_available = TRUE AND NOT EXISTS (
                        SELECT 1 FROM transcripts t WHERE t.content_id = c.id
                    ))
                    OR
                    (transcript_available = FALSE AND EXISTS (
                        SELECT 1 FROM transcripts t WHERE t.content_id = c.id
                    ))
                )
            """)
            result = session.execute(query).scalar()

            if result > self.thresholds['integrity_issues']:
                alerts.append({
                    'type': AlertType.DATA_INTEGRITY.value,
                    'level': AlertLevel.WARNING.value,
                    'title': 'Transcript 플래그 불일치',
                    'message': f'{result}개 콘텐츠의 transcript 플래그가 실제 데이터와 일치하지 않습니다.',
                    'count': result,
                    'timestamp': datetime.now().isoformat()
                })

            # vector 플래그 불일치
            query = text("""
                SELECT COUNT(*) FROM content c
                WHERE (
                    (vector_stored = TRUE AND NOT EXISTS (
                        SELECT 1 FROM vector_mappings v WHERE v.content_id = c.id
                    ))
                    OR
                    (vector_stored = FALSE AND EXISTS (
                        SELECT 1 FROM vector_mappings v WHERE v.content_id = c.id
                    ))
                )
            """)
            result = session.execute(query).scalar()

            if result > self.thresholds['integrity_issues']:
                alerts.append({
                    'type': AlertType.DATA_INTEGRITY.value,
                    'level': AlertLevel.WARNING.value,
                    'title': 'Vector 플래그 불일치',
                    'message': f'{result}개 콘텐츠의 vector 플래그가 실제 데이터와 일치하지 않습니다.',
                    'count': result,
                    'timestamp': datetime.now().isoformat()
                })

            # 고아 데이터
            query = text("""
                SELECT
                    (SELECT COUNT(*) FROM transcripts t
                     WHERE NOT EXISTS (SELECT 1 FROM content c WHERE c.id = t.content_id)) as orphan_transcripts,
                    (SELECT COUNT(*) FROM vector_mappings v
                     WHERE NOT EXISTS (SELECT 1 FROM content c WHERE c.id = v.content_id)) as orphan_vectors
            """)
            result = session.execute(query).first()

            if result[0] > 0 or result[1] > 0:
                alerts.append({
                    'type': AlertType.DATA_INTEGRITY.value,
                    'level': AlertLevel.ERROR.value,
                    'title': '고아 데이터 발견',
                    'message': f'고아 transcript: {result[0]}개, 고아 vector: {result[1]}개',
                    'orphan_transcripts': result[0],
                    'orphan_vectors': result[1],
                    'timestamp': datetime.now().isoformat()
                })

        except Exception as e:
            logger.error(f"정합성 체크 실패: {e}")
        finally:
            session.close()

        return alerts

    def _check_processing_jobs(self) -> List[Dict]:
        """처리 작업 상태 체크"""
        alerts = []
        session = self.SessionLocal()

        try:
            # 멈춘 작업
            query = text("""
                SELECT COUNT(*) FROM processing_jobs
                WHERE status = 'processing'
                AND created_at < NOW() - INTERVAL '30 minutes'
            """)
            stuck_count = session.execute(query).scalar()

            if stuck_count > self.thresholds['stuck_jobs']:
                alerts.append({
                    'type': AlertType.STUCK_JOBS.value,
                    'level': AlertLevel.ERROR.value,
                    'title': '멈춘 작업 과다',
                    'message': f'{stuck_count}개 작업이 30분 이상 processing 상태입니다.',
                    'count': stuck_count,
                    'timestamp': datetime.now().isoformat()
                })

            # 실패한 작업
            query = text("""
                SELECT COUNT(*), job_type
                FROM processing_jobs
                WHERE status = 'failed'
                AND created_at > NOW() - INTERVAL '1 day'
                GROUP BY job_type
            """)
            failures = session.execute(query).fetchall()

            for count, job_type in failures:
                if count > self.thresholds['failed_jobs']:
                    alerts.append({
                        'type': AlertType.PROCESSING_FAILURE.value,
                        'level': AlertLevel.WARNING.value,
                        'title': f'{job_type} 작업 실패 과다',
                        'message': f'최근 24시간 동안 {count}개 {job_type} 작업이 실패했습니다.',
                        'job_type': job_type,
                        'count': count,
                        'timestamp': datetime.now().isoformat()
                    })

            # 대기 중인 작업
            query = text("""
                SELECT COUNT(*), job_type
                FROM processing_jobs
                WHERE status = 'pending'
                GROUP BY job_type
            """)
            pending = session.execute(query).fetchall()

            for count, job_type in pending:
                if count > self.thresholds['processing_lag']:
                    alerts.append({
                        'type': AlertType.PROCESSING_FAILURE.value,
                        'level': AlertLevel.WARNING.value,
                        'title': f'{job_type} 작업 지연',
                        'message': f'{count}개 {job_type} 작업이 대기 중입니다.',
                        'job_type': job_type,
                        'count': count,
                        'timestamp': datetime.now().isoformat()
                    })

        except Exception as e:
            logger.error(f"작업 체크 실패: {e}")
        finally:
            session.close()

        return alerts

    def _check_system_performance(self) -> List[Dict]:
        """시스템 성능 체크"""
        alerts = []
        session = self.SessionLocal()

        try:
            # 처리 속도 체크
            query = text("""
                SELECT
                    AVG(EXTRACT(EPOCH FROM (
                        CASE WHEN status = 'completed' THEN created_at ELSE NOW() END
                        - created_at
                    ))) as avg_processing_time,
                    job_type
                FROM processing_jobs
                WHERE created_at > NOW() - INTERVAL '1 hour'
                GROUP BY job_type
            """)
            results = session.execute(query).fetchall()

            for avg_time, job_type in results:
                if avg_time and avg_time > 1800:  # 30분 이상
                    alerts.append({
                        'type': AlertType.SYSTEM_PERFORMANCE.value,
                        'level': AlertLevel.WARNING.value,
                        'title': f'{job_type} 처리 속도 저하',
                        'message': f'{job_type} 평균 처리 시간: {avg_time/60:.1f}분',
                        'job_type': job_type,
                        'avg_time': avg_time,
                        'timestamp': datetime.now().isoformat()
                    })

            # 에러율 체크
            query = text("""
                SELECT
                    job_type,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    COUNT(*) as total
                FROM processing_jobs
                WHERE created_at > NOW() - INTERVAL '1 hour'
                GROUP BY job_type
            """)
            results = session.execute(query).fetchall()

            for job_type, failed, total in results:
                if total > 0:
                    error_rate = failed / total
                    if error_rate > 0.2:  # 20% 이상 에러율
                        alerts.append({
                            'type': AlertType.SYSTEM_PERFORMANCE.value,
                            'level': AlertLevel.ERROR.value,
                            'title': f'{job_type} 에러율 높음',
                            'message': f'{job_type} 에러율: {error_rate*100:.1f}% ({failed}/{total})',
                            'job_type': job_type,
                            'error_rate': error_rate,
                            'timestamp': datetime.now().isoformat()
                        })

        except Exception as e:
            logger.error(f"성능 체크 실패: {e}")
        finally:
            session.close()

        return alerts

    def _check_duplicate_data(self) -> List[Dict]:
        """중복 데이터 체크"""
        alerts = []

        try:
            collections = ['youtube_content', 'youtube_summaries']

            for collection in collections:
                # 벡터 DB 포인트 수 확인
                try:
                    collection_info = self.qdrant.get_collection(collection)
                    points_count = collection_info.points_count

                    # 예상 포인트 수와 비교
                    session = self.SessionLocal()
                    query = text("""
                        SELECT COUNT(DISTINCT content_id)
                        FROM vector_mappings
                        WHERE collection_name = :collection
                    """)
                    content_count = session.execute(
                        query,
                        {'collection': collection}
                    ).scalar() or 0
                    session.close()

                    if content_count > 0:
                        avg_chunks_per_content = points_count / content_count

                        # 평균 청크 수가 비정상적으로 높은 경우
                        if collection == 'youtube_content' and avg_chunks_per_content > 500:
                            alerts.append({
                                'type': AlertType.DUPLICATE_DATA.value,
                                'level': AlertLevel.WARNING.value,
                                'title': f'{collection} 중복 의심',
                                'message': f'콘텐츠당 평균 {avg_chunks_per_content:.1f}개 벡터 (정상: 100-300개)',
                                'collection': collection,
                                'points_count': points_count,
                                'content_count': content_count,
                                'timestamp': datetime.now().isoformat()
                            })

                except Exception as e:
                    logger.error(f"{collection} 체크 실패: {e}")

        except Exception as e:
            logger.error(f"중복 체크 실패: {e}")

        return alerts

    def _save_alerts(self, alerts: List[Dict]):
        """알림 저장"""
        try:
            # Redis에 저장
            for alert in alerts:
                # 개별 알림 저장
                alert_id = f"alert:{datetime.now().strftime('%Y%m%d%H%M%S')}:{alert['type']}"
                self.redis_client.setex(alert_id, 86400, json.dumps(alert))

                # 타입별 리스트에 추가
                list_key = f"alerts:{alert['type']}"
                self.redis_client.lpush(list_key, json.dumps(alert))
                self.redis_client.ltrim(list_key, 0, 99)  # 최근 100개만 유지

            # 최신 알림 업데이트
            if alerts:
                self.redis_client.setex(
                    "alerts:latest",
                    3600,
                    json.dumps(alerts)
                )

        except Exception as e:
            logger.error(f"알림 저장 실패: {e}")

    def _send_notifications(self, alerts: List[Dict]):
        """알림 전송"""
        for alert in alerts:
            # 로그로 출력
            level = alert.get('level', 'info')
            if level == AlertLevel.CRITICAL.value:
                logger.critical(f"🚨 {alert['title']}: {alert['message']}")
            elif level == AlertLevel.ERROR.value:
                logger.error(f"❌ {alert['title']}: {alert['message']}")
            elif level == AlertLevel.WARNING.value:
                logger.warning(f"⚠️ {alert['title']}: {alert['message']}")
            else:
                logger.info(f"ℹ️ {alert['title']}: {alert['message']}")

            # 여기에 이메일, Slack 등 실제 알림 전송 로직 추가 가능

    def get_recent_alerts(self, limit: int = 10) -> List[Dict]:
        """최근 알림 조회"""
        try:
            alerts_json = self.redis_client.get("alerts:latest")
            if alerts_json:
                alerts = json.loads(alerts_json)
                return alerts[:limit]
        except Exception as e:
            logger.error(f"알림 조회 실패: {e}")

        return []

def run_monitoring_service(interval_seconds: int = 300):
    """모니터링 서비스 실행"""
    manager = AlertManager()

    logger.info(f"모니터링 알림 서비스 시작 (간격: {interval_seconds}초)")

    while True:
        try:
            # 체크 및 알림
            alerts = manager.check_and_alert()

            # 대기
            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("모니터링 서비스 종료")
            break
        except Exception as e:
            logger.error(f"모니터링 서비스 오류: {e}")
            time.sleep(30)

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "once":
        # 한 번만 실행
        manager = AlertManager()
        alerts = manager.check_and_alert()
        print(json.dumps(alerts, indent=2, ensure_ascii=False))
    else:
        # 서비스 모드
        run_monitoring_service()