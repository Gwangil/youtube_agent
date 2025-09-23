#!/usr/bin/env python3
"""
데이터 정합성 관리 서비스
- RDB와 Qdrant 간 동기화 보장
- 트랜잭션 롤백 처리
- 데이터 품질 모니터링
"""

import os
import sys
import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import redis
from dataclasses import dataclass
from enum import Enum

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataStatus(Enum):
    """데이터 상태 정의"""
    CONSISTENT = "consistent"      # 정합성 일치
    ORPHANED = "orphaned"          # 고아 데이터
    INCOMPLETE = "incomplete"      # 불완전 데이터
    DUPLICATED = "duplicated"      # 중복 데이터
    MISSING = "missing"            # 누락 데이터

@dataclass
class IntegrityCheck:
    """정합성 체크 결과"""
    content_id: int
    status: DataStatus
    db_status: Dict
    vector_status: Dict
    issues: List[str]
    recommendations: List[str]

class DataIntegrityManager:
    def __init__(self):
        # 데이터베이스 연결
        self.db_url = os.getenv("DATABASE_URL", "postgresql://youtube_user:youtube_pass@postgres:5432/youtube_agent")
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Qdrant 연결
        self.qdrant = QdrantClient(
            host=os.getenv("QDRANT_HOST", "qdrant"),
            port=int(os.getenv("QDRANT_PORT", 6333))
        )

        # Redis 연결
        self.redis = redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True
        )

        # 컬렉션 이름들
        self.collections = ["youtube_content", "youtube_summaries"]

    def check_content_integrity(self, content_id: int) -> IntegrityCheck:
        """개별 콘텐츠의 정합성 체크"""
        issues = []
        recommendations = []

        with self.SessionLocal() as db:
            # 1. DB 상태 확인
            db_status = self._get_db_status(db, content_id)

            # 2. Vector DB 상태 확인
            vector_status = self._get_vector_status(content_id)

            # 3. 정합성 검증
            status = DataStatus.CONSISTENT

            # 트랜스크립트 체크
            if db_status['has_transcript'] and not db_status['transcript_exists']:
                issues.append("DB에 transcript_available=True이나 실제 트랜스크립트 없음")
                recommendations.append("transcript_available 플래그 수정 필요")
                status = DataStatus.INCOMPLETE

            # 벡터 체크
            if db_status['has_vectors'] and vector_status['total_vectors'] == 0:
                issues.append("DB에 vector_stored=True이나 Qdrant에 벡터 없음")
                recommendations.append("벡터 재생성 또는 vector_stored 플래그 수정 필요")
                status = DataStatus.INCOMPLETE
            elif not db_status['has_vectors'] and vector_status['total_vectors'] > 0:
                issues.append("DB에 vector_stored=False이나 Qdrant에 벡터 존재")
                recommendations.append("고아 벡터 삭제 필요")
                status = DataStatus.ORPHANED

            # 중복 체크
            if vector_status['duplicate_vectors'] > 0:
                issues.append(f"{vector_status['duplicate_vectors']}개의 중복 벡터 발견")
                recommendations.append("중복 벡터 제거 필요")
                status = DataStatus.DUPLICATED

            # 처리 작업 체크
            if db_status['pending_jobs'] > 0 and db_status['stuck_jobs'] > 0:
                issues.append(f"{db_status['stuck_jobs']}개의 멈춘 작업 발견")
                recommendations.append("작업 재시작 또는 정리 필요")

            return IntegrityCheck(
                content_id=content_id,
                status=status,
                db_status=db_status,
                vector_status=vector_status,
                issues=issues,
                recommendations=recommendations
            )

    def _get_db_status(self, db: Session, content_id: int) -> Dict:
        """데이터베이스 상태 조회"""
        # 콘텐츠 정보
        content = db.execute(
            text("""
                SELECT
                    id, title, transcript_available, vector_stored,
                    created_at, updated_at
                FROM content
                WHERE id = :content_id
            """),
            {"content_id": content_id}
        ).fetchone()

        if not content:
            return {"exists": False}

        # 트랜스크립트 확인
        transcript = db.execute(
            text("SELECT COUNT(*) FROM transcripts WHERE content_id = :content_id"),
            {"content_id": content_id}
        ).scalar()

        # 벡터 매핑 확인
        vectors = db.execute(
            text("SELECT COUNT(*) FROM vector_mappings WHERE content_id = :content_id"),
            {"content_id": content_id}
        ).scalar()

        # 처리 작업 확인
        jobs = db.execute(
            text("""
                SELECT
                    job_type, status, COUNT(*) as count,
                    MIN(created_at) as oldest_job
                FROM processing_jobs
                WHERE content_id = :content_id
                GROUP BY job_type, status
            """),
            {"content_id": content_id}
        ).fetchall()

        pending_jobs = sum(j.count for j in jobs if j.status == 'pending')
        processing_jobs = sum(j.count for j in jobs if j.status == 'processing')

        # 30분 이상 processing 상태인 작업 확인
        stuck_jobs = 0
        for job in jobs:
            if job.status == 'processing' and job.oldest_job:
                if datetime.utcnow() - job.oldest_job > timedelta(minutes=30):
                    stuck_jobs += job.count

        return {
            "exists": True,
            "id": content.id,
            "title": content.title,
            "has_transcript": content.transcript_available,
            "has_vectors": content.vector_stored,
            "transcript_exists": transcript > 0,
            "vector_mappings": vectors,
            "pending_jobs": pending_jobs,
            "processing_jobs": processing_jobs,
            "stuck_jobs": stuck_jobs,
            "created_at": content.created_at,
            "updated_at": content.updated_at
        }

    def _get_vector_status(self, content_id: int) -> Dict:
        """Qdrant 벡터 상태 조회"""
        total_vectors = 0
        duplicate_vectors = 0
        vector_details = {}

        for collection in self.collections:
            try:
                # 해당 content_id의 벡터 검색
                response = self.qdrant.scroll(
                    collection_name=collection,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="content_id",
                                match=MatchValue(value=content_id)
                            )
                        ]
                    ),
                    limit=1000
                )

                points = response[0]
                vector_details[collection] = len(points)
                total_vectors += len(points)

                # 중복 체크 (동일한 chunk_id가 여러 개 있는지)
                chunk_ids = [p.payload.get('chunk_id') for p in points if p.payload.get('chunk_id')]
                if chunk_ids:
                    duplicate_vectors += len(chunk_ids) - len(set(chunk_ids))

            except Exception as e:
                logger.warning(f"Qdrant 조회 실패 ({collection}): {e}")
                vector_details[collection] = 0

        return {
            "total_vectors": total_vectors,
            "duplicate_vectors": duplicate_vectors,
            "details": vector_details
        }

    def fix_integrity_issues(self, check: IntegrityCheck) -> bool:
        """정합성 문제 자동 수정"""
        try:
            with self.SessionLocal() as db:
                fixed = False

                # 1. 고아 벡터 삭제
                if check.status == DataStatus.ORPHANED:
                    self._remove_orphan_vectors(check.content_id)
                    fixed = True

                # 2. 플래그 불일치 수정
                if check.status == DataStatus.INCOMPLETE:
                    if "transcript_available" in str(check.issues):
                        db.execute(
                            text("UPDATE content SET transcript_available = FALSE WHERE id = :id"),
                            {"id": check.content_id}
                        )
                    if "vector_stored" in str(check.issues):
                        if check.vector_status['total_vectors'] > 0:
                            db.execute(
                                text("UPDATE content SET vector_stored = TRUE WHERE id = :id"),
                                {"id": check.content_id}
                            )
                        else:
                            db.execute(
                                text("UPDATE content SET vector_stored = FALSE WHERE id = :id"),
                                {"id": check.content_id}
                            )
                    db.commit()
                    fixed = True

                # 3. 중복 벡터 제거
                if check.status == DataStatus.DUPLICATED:
                    self._remove_duplicate_vectors(check.content_id)
                    fixed = True

                # 4. 멈춘 작업 재시작
                if check.db_status.get('stuck_jobs', 0) > 0:
                    db.execute(
                        text("""
                            UPDATE processing_jobs
                            SET status = 'pending', updated_at = NOW()
                            WHERE content_id = :id
                            AND status = 'processing'
                            AND created_at < NOW() - INTERVAL '30 minutes'
                        """),
                        {"id": check.content_id}
                    )
                    db.commit()
                    fixed = True

                if fixed:
                    logger.info(f"콘텐츠 {check.content_id} 정합성 문제 수정 완료")

                return fixed

        except Exception as e:
            logger.error(f"정합성 문제 수정 실패: {e}")
            return False

    def _remove_orphan_vectors(self, content_id: int):
        """고아 벡터 삭제"""
        for collection in self.collections:
            try:
                self.qdrant.delete(
                    collection_name=collection,
                    points_selector=Filter(
                        must=[
                            FieldCondition(
                                key="content_id",
                                match=MatchValue(value=content_id)
                            )
                        ]
                    )
                )
                logger.info(f"{collection}에서 content_id={content_id} 벡터 삭제")
            except Exception as e:
                logger.error(f"벡터 삭제 실패: {e}")

    def _remove_duplicate_vectors(self, content_id: int):
        """중복 벡터 제거"""
        for collection in self.collections:
            try:
                # 모든 포인트 조회
                response = self.qdrant.scroll(
                    collection_name=collection,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="content_id",
                                match=MatchValue(value=content_id)
                            )
                        ]
                    ),
                    limit=1000
                )

                points = response[0]

                # chunk_id별로 그룹화
                chunk_groups = {}
                for point in points:
                    chunk_id = point.payload.get('chunk_id', point.id)
                    if chunk_id not in chunk_groups:
                        chunk_groups[chunk_id] = []
                    chunk_groups[chunk_id].append(point.id)

                # 중복 제거 (첫 번째만 남기고 삭제)
                points_to_delete = []
                for chunk_id, point_ids in chunk_groups.items():
                    if len(point_ids) > 1:
                        points_to_delete.extend(point_ids[1:])

                if points_to_delete:
                    self.qdrant.delete(
                        collection_name=collection,
                        points_selector=points_to_delete
                    )
                    logger.info(f"{collection}에서 {len(points_to_delete)}개 중복 벡터 삭제")

            except Exception as e:
                logger.error(f"중복 벡터 제거 실패: {e}")

    def run_full_scan(self) -> Dict:
        """전체 데이터 정합성 스캔"""
        logger.info("전체 데이터 정합성 스캔 시작")

        results = {
            "scan_time": datetime.utcnow().isoformat(),
            "total_content": 0,
            "issues_found": 0,
            "issues_fixed": 0,
            "details": []
        }

        with self.SessionLocal() as db:
            # 모든 콘텐츠 조회
            contents = db.execute(
                text("SELECT id FROM content ORDER BY id")
            ).fetchall()

            results["total_content"] = len(contents)

            for content in contents:
                check = self.check_content_integrity(content.id)

                if check.status != DataStatus.CONSISTENT:
                    results["issues_found"] += 1

                    # 자동 수정 시도
                    if self.fix_integrity_issues(check):
                        results["issues_fixed"] += 1

                    results["details"].append({
                        "content_id": content.id,
                        "status": check.status.value,
                        "issues": check.issues,
                        "fixed": results["issues_fixed"] > results["issues_found"] - 1
                    })

        # 결과를 Redis에 저장
        self.redis.set(
            "data_integrity:last_scan",
            json.dumps(results),
            ex=3600  # 1시간 유지
        )

        logger.info(f"스캔 완료: {results['issues_found']}개 문제 발견, {results['issues_fixed']}개 수정")

        return results

    async def start_monitoring(self, interval_minutes: int = 30):
        """주기적 모니터링 시작"""
        logger.info(f"데이터 정합성 모니터링 시작 (주기: {interval_minutes}분)")

        while True:
            try:
                # 정합성 스캔 실행
                results = self.run_full_scan()

                # 알림 발송 (문제 발견 시)
                if results["issues_found"] > results["issues_fixed"]:
                    unfixed = results["issues_found"] - results["issues_fixed"]
                    self._send_alert(
                        f"⚠️ 데이터 정합성 문제: {unfixed}개 미해결",
                        results
                    )

                # 대기
                await asyncio.sleep(interval_minutes * 60)

            except Exception as e:
                logger.error(f"모니터링 오류: {e}")
                await asyncio.sleep(60)  # 1분 후 재시도

    def _send_alert(self, message: str, details: Dict):
        """알림 발송"""
        alert = {
            "timestamp": datetime.utcnow().isoformat(),
            "message": message,
            "details": details
        }

        # Redis에 알림 저장
        self.redis.lpush("data_integrity:alerts", json.dumps(alert))
        self.redis.ltrim("data_integrity:alerts", 0, 99)  # 최근 100개만 유지

        logger.warning(f"알림: {message}")

    def get_integrity_report(self) -> Dict:
        """정합성 보고서 생성"""
        with self.SessionLocal() as db:
            report = {
                "timestamp": datetime.utcnow().isoformat(),
                "database": {},
                "vectors": {},
                "consistency": {}
            }

            # DB 통계
            db_stats = db.execute(
                text("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN transcript_available THEN 1 ELSE 0 END) as transcripts,
                        SUM(CASE WHEN vector_stored THEN 1 ELSE 0 END) as vectors
                    FROM content
                """)
            ).fetchone()

            report["database"] = {
                "total_content": db_stats.total,
                "with_transcript": db_stats.transcripts,
                "with_vectors": db_stats.vectors
            }

            # Qdrant 통계
            for collection in self.collections:
                try:
                    info = self.qdrant.get_collection(collection)
                    report["vectors"][collection] = {
                        "points_count": info.points_count,
                        "vectors_count": info.vectors_count
                    }
                except:
                    report["vectors"][collection] = {"error": "조회 실패"}

            # 최근 스캔 결과
            last_scan = self.redis.get("data_integrity:last_scan")
            if last_scan:
                report["last_scan"] = json.loads(last_scan)

            # 최근 알림
            alerts = self.redis.lrange("data_integrity:alerts", 0, 10)
            report["recent_alerts"] = [json.loads(a) for a in alerts]

            return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="데이터 정합성 관리")
    parser.add_argument("--scan", action="store_true", help="전체 스캔 실행")
    parser.add_argument("--monitor", action="store_true", help="모니터링 시작")
    parser.add_argument("--report", action="store_true", help="보고서 생성")
    parser.add_argument("--fix", type=int, help="특정 콘텐츠 수정")

    args = parser.parse_args()

    manager = DataIntegrityManager()

    if args.scan:
        results = manager.run_full_scan()
        print(json.dumps(results, indent=2, ensure_ascii=False))

    elif args.monitor:
        asyncio.run(manager.start_monitoring())

    elif args.report:
        report = manager.get_integrity_report()
        print(json.dumps(report, indent=2, ensure_ascii=False))

    elif args.fix:
        check = manager.check_content_integrity(args.fix)
        print(f"콘텐츠 {args.fix} 상태: {check.status.value}")
        if check.issues:
            print("발견된 문제:")
            for issue in check.issues:
                print(f"  - {issue}")
        if check.recommendations:
            print("권장 조치:")
            for rec in check.recommendations:
                print(f"  - {rec}")

        if check.status != DataStatus.CONSISTENT:
            if manager.fix_integrity_issues(check):
                print("✅ 문제 수정 완료")
            else:
                print("❌ 수정 실패")