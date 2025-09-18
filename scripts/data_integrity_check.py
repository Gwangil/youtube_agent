#!/usr/bin/env python3
"""
데이터 정합성 체크 스크립트
PostgreSQL과 Qdrant 간의 데이터 일관성을 검증합니다.
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List, Set, Tuple
import logging

# 프로젝트 경로 추가
sys.path.append('/app')
sys.path.append('/app/shared')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import psycopg2

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataIntegrityChecker:
    """데이터 정합성 검증 클래스"""

    def __init__(self):
        # PostgreSQL 연결
        self.db_url = os.getenv('DATABASE_URL', 'postgresql://youtube_user:youtube_pass@postgres:5432/youtube_agent')
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Qdrant 연결
        self.qdrant_url = os.getenv('QDRANT_URL', 'http://qdrant:6333')
        self.qdrant_client = QdrantClient(url=self.qdrant_url)

        self.issues = []

    def check_database_connection(self) -> bool:
        """데이터베이스 연결 확인"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                logger.info("✅ PostgreSQL 연결 성공")
                return True
        except Exception as e:
            logger.error(f"❌ PostgreSQL 연결 실패: {e}")
            self.issues.append(f"PostgreSQL 연결 실패: {e}")
            return False

    def check_qdrant_connection(self) -> bool:
        """Qdrant 연결 확인"""
        try:
            collections = self.qdrant_client.get_collections()
            logger.info(f"✅ Qdrant 연결 성공 (컬렉션: {len(collections.collections)}개)")
            return True
        except Exception as e:
            logger.error(f"❌ Qdrant 연결 실패: {e}")
            self.issues.append(f"Qdrant 연결 실패: {e}")
            return False

    def check_tables_exist(self) -> Dict[str, bool]:
        """필수 테이블 존재 확인"""
        required_tables = ['channels', 'content', 'processing_jobs', 'transcripts', 'vector_mappings']
        table_status = {}

        with self.SessionLocal() as session:
            for table in required_tables:
                try:
                    result = session.execute(
                        text(f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :table)"),
                        {"table": table}
                    )
                    exists = result.scalar()
                    table_status[table] = exists

                    if exists:
                        # 테이블 레코드 수 확인
                        count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                        logger.info(f"✅ 테이블 '{table}' 존재 (레코드: {count}개)")
                    else:
                        logger.warning(f"⚠️ 테이블 '{table}' 없음")
                        self.issues.append(f"테이블 '{table}' 없음")
                except Exception as e:
                    logger.error(f"❌ 테이블 '{table}' 확인 실패: {e}")
                    table_status[table] = False
                    self.issues.append(f"테이블 '{table}' 확인 실패: {e}")

        return table_status

    def check_qdrant_collections(self) -> Dict[str, int]:
        """Qdrant 컬렉션 확인"""
        collection_status = {}

        try:
            collections = self.qdrant_client.get_collections()

            # youtube_content 컬렉션 확인
            for collection in collections.collections:
                collection_name = collection.name
                collection_info = self.qdrant_client.get_collection(collection_name)
                point_count = collection_info.points_count
                collection_status[collection_name] = point_count
                logger.info(f"✅ Qdrant 컬렉션 '{collection_name}': {point_count}개 벡터")

            if 'youtube_content' not in collection_status:
                logger.warning("⚠️ 'youtube_content' 컬렉션이 없습니다")
                self.issues.append("'youtube_content' 컬렉션 없음")

        except Exception as e:
            logger.error(f"❌ Qdrant 컬렉션 확인 실패: {e}")
            self.issues.append(f"Qdrant 컬렉션 확인 실패: {e}")

        return collection_status

    def check_data_consistency(self) -> Dict[str, any]:
        """PostgreSQL과 Qdrant 간 데이터 일관성 확인"""
        consistency_report = {
            'postgres_contents': 0,
            'postgres_chunks': 0,
            'qdrant_vectors': 0,
            'orphaned_chunks': [],
            'missing_vectors': [],
            'orphaned_vectors': []
        }

        with self.SessionLocal() as session:
            # PostgreSQL 데이터 수집
            try:
                # 콘텐츠 수
                content_count = session.execute(text("SELECT COUNT(*) FROM content")).scalar()
                consistency_report['postgres_contents'] = content_count

                # 벡터 매핑 수
                vector_count = session.execute(text("SELECT COUNT(*) FROM vector_mappings")).scalar()
                consistency_report['postgres_chunks'] = vector_count

                # 벡터 매핑 ID 목록
                vector_mappings = session.execute(
                    text("SELECT chunk_id FROM vector_mappings")
                ).fetchall()
                postgres_chunk_ids = {str(row[0]) for row in vector_mappings}

            except Exception as e:
                logger.error(f"❌ PostgreSQL 데이터 조회 실패: {e}")
                self.issues.append(f"PostgreSQL 데이터 조회 실패: {e}")
                return consistency_report

        # Qdrant 데이터 수집
        try:
            if 'youtube_content' in [c.name for c in self.qdrant_client.get_collections().collections]:
                # 전체 벡터 수
                collection_info = self.qdrant_client.get_collection('youtube_content')
                consistency_report['qdrant_vectors'] = collection_info.points_count

                # Qdrant의 모든 포인트 ID 가져오기 (배치 처리)
                qdrant_point_ids = set()
                offset = 0
                limit = 100

                while True:
                    result = self.qdrant_client.scroll(
                        collection_name='youtube_content',
                        offset=offset,
                        limit=limit,
                        with_payload=False,
                        with_vectors=False
                    )

                    if not result[0]:
                        break

                    for point in result[0]:
                        qdrant_point_ids.add(str(point.id))

                    if len(result[0]) < limit:
                        break
                    offset += limit

                # 정합성 분석
                # PostgreSQL에는 있지만 Qdrant에는 없는 청크
                consistency_report['missing_vectors'] = list(postgres_chunk_ids - qdrant_point_ids)[:10]  # 처음 10개만

                # Qdrant에는 있지만 PostgreSQL에는 없는 벡터
                consistency_report['orphaned_vectors'] = list(qdrant_point_ids - postgres_chunk_ids)[:10]  # 처음 10개만

                if consistency_report['missing_vectors']:
                    logger.warning(f"⚠️ Qdrant에 없는 청크: {len(postgres_chunk_ids - qdrant_point_ids)}개")
                    self.issues.append(f"Qdrant에 없는 청크 {len(postgres_chunk_ids - qdrant_point_ids)}개 발견")

                if consistency_report['orphaned_vectors']:
                    logger.warning(f"⚠️ 고아 벡터: {len(qdrant_point_ids - postgres_chunk_ids)}개")
                    self.issues.append(f"고아 벡터 {len(qdrant_point_ids - postgres_chunk_ids)}개 발견")

        except Exception as e:
            logger.error(f"❌ Qdrant 데이터 조회 실패: {e}")
            self.issues.append(f"Qdrant 데이터 조회 실패: {e}")

        return consistency_report

    def check_processing_jobs(self) -> Dict[str, int]:
        """처리 작업 상태 확인"""
        job_status = {}

        with self.SessionLocal() as session:
            try:
                # 상태별 작업 수
                statuses = ['pending', 'processing', 'completed', 'failed']
                for status in statuses:
                    count = session.execute(
                        text("SELECT COUNT(*) FROM processing_jobs WHERE status = :status"),
                        {"status": status}
                    ).scalar()
                    job_status[status] = count
                    logger.info(f"  작업 상태 '{status}': {count}개")

                # 오래된 processing 작업 확인 (1일 이상)
                stuck_jobs = session.execute(
                    text("""
                        SELECT COUNT(*) FROM processing_jobs
                        WHERE status = 'processing'
                        AND started_at < NOW() - INTERVAL '1 day'
                    """)
                ).scalar()

                if stuck_jobs > 0:
                    logger.warning(f"⚠️ 1일 이상 처리 중인 작업: {stuck_jobs}개")
                    self.issues.append(f"1일 이상 처리 중인 작업 {stuck_jobs}개 발견")
                    job_status['stuck'] = stuck_jobs

            except Exception as e:
                logger.error(f"❌ 작업 상태 확인 실패: {e}")
                self.issues.append(f"작업 상태 확인 실패: {e}")

        return job_status

    def generate_report(self) -> Dict:
        """종합 보고서 생성"""
        logger.info("\n" + "="*50)
        logger.info("데이터 정합성 체크 시작")
        logger.info("="*50 + "\n")

        report = {
            'timestamp': datetime.now().isoformat(),
            'status': 'healthy',
            'connections': {
                'postgresql': self.check_database_connection(),
                'qdrant': self.check_qdrant_connection()
            },
            'tables': self.check_tables_exist(),
            'collections': self.check_qdrant_collections(),
            'consistency': self.check_data_consistency(),
            'jobs': self.check_processing_jobs(),
            'issues': self.issues
        }

        # 상태 결정
        if self.issues:
            if any('실패' in issue for issue in self.issues):
                report['status'] = 'critical'
            else:
                report['status'] = 'warning'

        # 요약
        logger.info("\n" + "="*50)
        logger.info("정합성 체크 요약")
        logger.info("="*50)

        if report['status'] == 'healthy':
            logger.info("✅ 모든 검증 통과: 시스템이 정상입니다.")
        elif report['status'] == 'warning':
            logger.warning(f"⚠️ 경고 사항 {len(self.issues)}개 발견:")
            for issue in self.issues:
                logger.warning(f"  - {issue}")
        else:
            logger.error(f"❌ 심각한 문제 {len(self.issues)}개 발견:")
            for issue in self.issues:
                logger.error(f"  - {issue}")

        return report

    def fix_orphaned_vectors(self):
        """고아 벡터 정리"""
        logger.info("\n고아 벡터 정리 시작...")

        consistency = self.check_data_consistency()
        orphaned = consistency.get('orphaned_vectors', [])

        if orphaned:
            logger.info(f"삭제할 고아 벡터: {len(orphaned)}개")
            for vector_id in orphaned:
                try:
                    self.qdrant_client.delete(
                        collection_name='youtube_content',
                        points_selector=[vector_id]
                    )
                    logger.info(f"  ✅ 벡터 {vector_id} 삭제됨")
                except Exception as e:
                    logger.error(f"  ❌ 벡터 {vector_id} 삭제 실패: {e}")
        else:
            logger.info("정리할 고아 벡터가 없습니다.")

    def reset_stuck_jobs(self):
        """멈춘 작업 초기화"""
        logger.info("\n멈춘 작업 초기화...")

        with self.SessionLocal() as session:
            try:
                result = session.execute(
                    text("""
                        UPDATE processing_jobs
                        SET status = 'pending', started_at = NULL
                        WHERE status = 'processing'
                        AND started_at < NOW() - INTERVAL '1 day'
                    """)
                )
                session.commit()

                if result.rowcount > 0:
                    logger.info(f"✅ {result.rowcount}개 작업을 'pending'으로 재설정")
                else:
                    logger.info("재설정할 작업이 없습니다.")

            except Exception as e:
                logger.error(f"❌ 작업 재설정 실패: {e}")
                session.rollback()


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='데이터 정합성 체크')
    parser.add_argument('--fix', action='store_true', help='발견된 문제 자동 수정')
    parser.add_argument('--json', action='store_true', help='JSON 형식으로 출력')
    args = parser.parse_args()

    checker = DataIntegrityChecker()
    report = checker.generate_report()

    if args.fix and report['status'] != 'healthy':
        logger.info("\n" + "="*50)
        logger.info("문제 자동 수정 시작")
        logger.info("="*50)
        checker.fix_orphaned_vectors()
        checker.reset_stuck_jobs()

        # 재검증
        logger.info("\n재검증 중...")
        checker.issues = []
        report = checker.generate_report()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    # 종료 코드
    if report['status'] == 'healthy':
        sys.exit(0)
    elif report['status'] == 'warning':
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()