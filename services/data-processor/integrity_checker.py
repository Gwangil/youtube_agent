#!/usr/bin/env python3
"""
자동 데이터 정합성 체크 서비스
주기적으로 데이터베이스와 벡터 DB의 정합성을 검사하고 자동 복구
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import redis
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataIntegrityChecker:
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

        self.issues_found = []
        self.fixes_applied = []

    def check_and_fix(self) -> Dict:
        """전체 정합성 체크 및 자동 수정"""
        logger.info("=" * 50)
        logger.info(f"데이터 정합성 체크 시작: {datetime.now()}")

        results = {
            'timestamp': datetime.now().isoformat(),
            'issues_found': 0,
            'issues_fixed': 0,
            'details': []
        }

        # 1. 플래그 불일치 수정
        flag_issues = self._fix_flag_mismatches()
        results['details'].append(flag_issues)
        results['issues_found'] += flag_issues['found']
        results['issues_fixed'] += flag_issues['fixed']

        # 2. 고아 데이터 정리
        orphan_issues = self._clean_orphan_data()
        results['details'].append(orphan_issues)
        results['issues_found'] += orphan_issues['found']
        results['issues_fixed'] += orphan_issues['fixed']

        # 3. 멈춘 작업 복구
        stuck_issues = self._recover_stuck_jobs()
        results['details'].append(stuck_issues)
        results['issues_found'] += stuck_issues['found']
        results['issues_fixed'] += stuck_issues['fixed']

        # 4. 중복 벡터 제거
        duplicate_issues = self._remove_duplicate_vectors()
        results['details'].append(duplicate_issues)
        results['issues_found'] += duplicate_issues['found']
        results['issues_fixed'] += duplicate_issues['fixed']

        # 5. 벡터 DB 동기화
        sync_issues = self._sync_vector_db()
        results['details'].append(sync_issues)
        results['issues_found'] += sync_issues['found']
        results['issues_fixed'] += sync_issues['fixed']

        # 결과 저장
        self._save_results(results)

        logger.info(f"정합성 체크 완료: {results['issues_found']}개 문제 발견, {results['issues_fixed']}개 수정")
        logger.info("=" * 50)

        return results

    def _fix_flag_mismatches(self) -> Dict:
        """플래그 불일치 수정"""
        logger.info("플래그 불일치 체크 중...")

        session = self.SessionLocal()
        result = {'type': 'flag_mismatch', 'found': 0, 'fixed': 0}

        try:
            # transcript_available 불일치 수정
            query = text("""
                UPDATE content c
                SET transcript_available = TRUE
                WHERE transcript_available = FALSE
                AND EXISTS (SELECT 1 FROM transcripts t WHERE t.content_id = c.id)
                RETURNING id
            """)
            updated = session.execute(query).fetchall()
            if updated:
                result['found'] += len(updated)
                result['fixed'] += len(updated)
                logger.info(f"  transcript_available: {len(updated)}개 수정")

            query = text("""
                UPDATE content c
                SET transcript_available = FALSE
                WHERE transcript_available = TRUE
                AND NOT EXISTS (SELECT 1 FROM transcripts t WHERE t.content_id = c.id)
                RETURNING id
            """)
            updated = session.execute(query).fetchall()
            if updated:
                result['found'] += len(updated)
                result['fixed'] += len(updated)
                logger.info(f"  transcript_available: {len(updated)}개 수정")

            # vector_stored 불일치 수정
            query = text("""
                UPDATE content c
                SET vector_stored = TRUE
                WHERE vector_stored = FALSE
                AND EXISTS (SELECT 1 FROM vector_mappings v WHERE v.content_id = c.id)
                RETURNING id
            """)
            updated = session.execute(query).fetchall()
            if updated:
                result['found'] += len(updated)
                result['fixed'] += len(updated)
                logger.info(f"  vector_stored: {len(updated)}개 수정")

            query = text("""
                UPDATE content c
                SET vector_stored = FALSE
                WHERE vector_stored = TRUE
                AND NOT EXISTS (SELECT 1 FROM vector_mappings v WHERE v.content_id = c.id)
                RETURNING id
            """)
            updated = session.execute(query).fetchall()
            if updated:
                result['found'] += len(updated)
                result['fixed'] += len(updated)
                logger.info(f"  vector_stored: {len(updated)}개 수정")

            session.commit()

        except Exception as e:
            logger.error(f"플래그 수정 실패: {e}")
            session.rollback()
        finally:
            session.close()

        return result

    def _clean_orphan_data(self) -> Dict:
        """고아 데이터 정리"""
        logger.info("고아 데이터 정리 중...")

        session = self.SessionLocal()
        result = {'type': 'orphan_data', 'found': 0, 'fixed': 0}

        try:
            # 고아 트랜스크립트 삭제
            query = text("""
                DELETE FROM transcripts t
                WHERE NOT EXISTS (SELECT 1 FROM content c WHERE c.id = t.content_id)
                RETURNING id
            """)
            deleted = session.execute(query).fetchall()
            if deleted:
                result['found'] += len(deleted)
                result['fixed'] += len(deleted)
                logger.info(f"  고아 트랜스크립트: {len(deleted)}개 삭제")

            # 고아 벡터 매핑 삭제
            query = text("""
                DELETE FROM vector_mappings v
                WHERE NOT EXISTS (SELECT 1 FROM content c WHERE c.id = v.content_id)
                RETURNING id
            """)
            deleted = session.execute(query).fetchall()
            if deleted:
                result['found'] += len(deleted)
                result['fixed'] += len(deleted)
                logger.info(f"  고아 벡터 매핑: {len(deleted)}개 삭제")

            # 고아 처리 작업 삭제
            query = text("""
                DELETE FROM processing_jobs j
                WHERE NOT EXISTS (SELECT 1 FROM content c WHERE c.id = j.content_id)
                AND j.created_at < NOW() - INTERVAL '1 day'
                RETURNING id
            """)
            deleted = session.execute(query).fetchall()
            if deleted:
                result['found'] += len(deleted)
                result['fixed'] += len(deleted)
                logger.info(f"  고아 처리 작업: {len(deleted)}개 삭제")

            session.commit()

        except Exception as e:
            logger.error(f"고아 데이터 정리 실패: {e}")
            session.rollback()
        finally:
            session.close()

        return result

    def _recover_stuck_jobs(self) -> Dict:
        """멈춘 작업 복구"""
        logger.info("멈춘 작업 복구 중...")

        session = self.SessionLocal()
        result = {'type': 'stuck_jobs', 'found': 0, 'fixed': 0}

        try:
            # 30분 이상 processing 상태인 작업 재설정
            query = text("""
                UPDATE processing_jobs
                SET status = 'pending',
                    retry_count = COALESCE(retry_count, 0) + 1
                WHERE status = 'processing'
                AND created_at < NOW() - INTERVAL '30 minutes'
                RETURNING id
            """)
            updated = session.execute(query).fetchall()
            if updated:
                result['found'] += len(updated)
                result['fixed'] += len(updated)
                logger.info(f"  멈춘 작업: {len(updated)}개 재설정")

            # 실패한 작업 중 재시도 가능한 것 재설정 (3회 미만)
            query = text("""
                UPDATE processing_jobs
                SET status = 'pending',
                    retry_count = COALESCE(retry_count, 0) + 1
                WHERE status = 'failed'
                AND COALESCE(retry_count, 0) < 3
                AND created_at > NOW() - INTERVAL '1 day'
                RETURNING id
            """)
            updated = session.execute(query).fetchall()
            if updated:
                result['found'] += len(updated)
                result['fixed'] += len(updated)
                logger.info(f"  재시도 가능 작업: {len(updated)}개 재설정")

            session.commit()

        except Exception as e:
            logger.error(f"작업 복구 실패: {e}")
            session.rollback()
        finally:
            session.close()

        return result

    def _remove_duplicate_vectors(self) -> Dict:
        """중복 벡터 제거"""
        logger.info("중복 벡터 체크 중...")

        result = {'type': 'duplicate_vectors', 'found': 0, 'fixed': 0}

        collections = ['youtube_content', 'youtube_summaries']

        for collection in collections:
            try:
                # 모든 포인트 조회
                points, _ = self.qdrant.scroll(
                    collection_name=collection,
                    limit=10000,
                    with_payload=True,
                    with_vectors=False
                )

                # content_id와 chunk_id별로 그룹화
                seen = {}
                duplicates = []

                for point in points:
                    content_id = point.payload.get('content_id')
                    chunk_id = point.payload.get('chunk_id', point.id)

                    key = f"{content_id}:{chunk_id}"
                    if key in seen:
                        duplicates.append(point.id)
                    else:
                        seen[key] = point.id

                if duplicates:
                    result['found'] += len(duplicates)
                    # 중복 제거
                    self.qdrant.delete(
                        collection_name=collection,
                        points_selector=duplicates
                    )
                    result['fixed'] += len(duplicates)
                    logger.info(f"  {collection}: {len(duplicates)}개 중복 제거")

            except Exception as e:
                logger.error(f"{collection} 중복 제거 실패: {e}")

        return result

    def _sync_vector_db(self) -> Dict:
        """벡터 DB 동기화"""
        logger.info("벡터 DB 동기화 중...")

        session = self.SessionLocal()
        result = {'type': 'vector_sync', 'found': 0, 'fixed': 0}

        try:
            # 비활성 콘텐츠의 벡터 제거
            query = text("""
                SELECT id FROM content
                WHERE is_active = FALSE
                AND vector_stored = TRUE
            """)
            inactive_contents = session.execute(query).fetchall()

            for content_row in inactive_contents:
                content_id = content_row[0]

                # Qdrant에서 제거
                for collection in ['youtube_content', 'youtube_summaries']:
                    try:
                        self.qdrant.delete(
                            collection_name=collection,
                            points_selector=Filter(
                                must=[
                                    FieldCondition(
                                        key="content_id",
                                        match=MatchValue(value=str(content_id))
                                    )
                                ]
                            )
                        )
                    except:
                        pass

                # 플래그 업데이트
                update_query = text("""
                    UPDATE content
                    SET vector_stored = FALSE
                    WHERE id = :content_id
                """)
                session.execute(update_query, {"content_id": content_id})

                result['found'] += 1
                result['fixed'] += 1

            if inactive_contents:
                logger.info(f"  비활성 콘텐츠: {len(inactive_contents)}개 벡터 제거")

            session.commit()

        except Exception as e:
            logger.error(f"벡터 동기화 실패: {e}")
            session.rollback()
        finally:
            session.close()

        return result

    def _save_results(self, results: Dict):
        """결과 저장"""
        try:
            # Redis에 최근 결과 저장
            self.redis_client.setex(
                "integrity_check:latest",
                86400,  # 1일 유지
                json.dumps(results)
            )

            # 히스토리 추가
            history_key = f"integrity_check:history:{datetime.now().strftime('%Y%m%d')}"
            self.redis_client.lpush(history_key, json.dumps(results))
            self.redis_client.expire(history_key, 604800)  # 7일 유지

        except Exception as e:
            logger.error(f"결과 저장 실패: {e}")

def run_periodic_check():
    """주기적 체크 실행"""
    checker = DataIntegrityChecker()

    while True:
        try:
            # 체크 실행
            results = checker.check_and_fix()

            # 문제가 발견되면 알림
            if results['issues_found'] > 0:
                logger.warning(f"⚠️ {results['issues_found']}개 문제 발견, {results['issues_fixed']}개 수정됨")

            # 30분 대기
            time.sleep(1800)

        except KeyboardInterrupt:
            logger.info("정합성 체크 서비스 종료")
            break
        except Exception as e:
            logger.error(f"체크 중 오류: {e}")
            time.sleep(60)  # 오류 시 1분 후 재시도

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        # 한 번만 실행
        checker = DataIntegrityChecker()
        results = checker.check_and_fix()
        print(json.dumps(results, indent=2))
    else:
        # 주기적 실행
        run_periodic_check()