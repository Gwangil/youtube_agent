#!/usr/bin/env python3
"""
데이터 초기화 스크립트
PostgreSQL과 Qdrant의 데이터를 선택적으로 초기화합니다.
"""

import os
import sys
import time
from datetime import datetime
from typing import Dict, List
import logging

# 프로젝트 경로 추가
sys.path.append('/app')
sys.path.append('/app/shared')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
import psycopg2

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataResetter:
    """데이터 초기화 클래스"""

    def __init__(self):
        # PostgreSQL 연결
        self.db_url = os.getenv('DATABASE_URL', 'postgresql://youtube_user:youtube_pass@postgres:5432/youtube_agent')
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Qdrant 연결
        self.qdrant_url = os.getenv('QDRANT_URL', 'http://qdrant:6333')
        self.qdrant_client = QdrantClient(url=self.qdrant_url)

        self.stats = {
            'deleted': {},
            'preserved': {},
            'errors': []
        }

    def backup_channels(self) -> List[Dict]:
        """채널 정보 백업 (초기화 후 복원용)"""
        channels = []
        with self.SessionLocal() as session:
            try:
                result = session.execute(
                    text("SELECT name, url, platform, category, description, language, is_active FROM channels")
                )
                for row in result:
                    channels.append({
                        'name': row[0],
                        'url': row[1],
                        'platform': row[2],
                        'category': row[3],
                        'description': row[4],
                        'language': row[5],
                        'is_active': row[6]
                    })
                logger.info(f"✅ {len(channels)}개 채널 정보 백업 완료")
            except Exception as e:
                logger.error(f"❌ 채널 백업 실패: {e}")
                self.stats['errors'].append(f"채널 백업 실패: {e}")

        return channels

    def clear_postgres_data(self, preserve_channels: bool = True):
        """PostgreSQL 데이터 초기화"""
        logger.info("\n" + "="*50)
        logger.info("PostgreSQL 데이터 초기화")
        logger.info("="*50)

        with self.SessionLocal() as session:
            try:
                # 백업할 채널 정보
                channels_backup = []
                if preserve_channels:
                    channels_backup = self.backup_channels()

                # 테이블 초기화 순서 (외래키 의존성 고려)
                tables_to_clear = [
                    ('vector_mappings', 'CASCADE'),
                    ('transcripts', 'CASCADE'),
                    ('processing_jobs', 'CASCADE'),
                    ('content', 'CASCADE')
                ]

                if not preserve_channels:
                    tables_to_clear.append(('channels', 'CASCADE'))

                for table, cascade in tables_to_clear:
                    try:
                        # 레코드 수 확인
                        count_before = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()

                        # 테이블 초기화
                        session.execute(text(f"TRUNCATE TABLE {table} {cascade}"))
                        session.commit()

                        logger.info(f"  ✅ 테이블 '{table}' 초기화 완료 ({count_before}개 레코드 삭제)")
                        self.stats['deleted'][table] = count_before

                    except Exception as e:
                        logger.error(f"  ❌ 테이블 '{table}' 초기화 실패: {e}")
                        self.stats['errors'].append(f"테이블 '{table}' 초기화 실패: {e}")
                        session.rollback()

                # 시퀀스 리셋
                sequences = ['channels_id_seq', 'content_id_seq', 'processing_jobs_id_seq',
                            'transcripts_id_seq', 'vector_mappings_id_seq']

                for seq in sequences:
                    try:
                        if not preserve_channels or seq != 'channels_id_seq':
                            session.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
                            logger.info(f"  ✅ 시퀀스 '{seq}' 리셋")
                    except Exception as e:
                        logger.warning(f"  ⚠️ 시퀀스 '{seq}' 리셋 실패: {e}")

                session.commit()

                # 채널 정보 복원
                if preserve_channels and channels_backup:
                    logger.info(f"\n채널 정보 복원 중...")
                    for channel in channels_backup:
                        session.execute(
                            text("""
                                INSERT INTO channels (name, url, platform, category, description, language, is_active)
                                VALUES (:name, :url, :platform, :category, :description, :language, :is_active)
                                ON CONFLICT (url) DO NOTHING
                            """),
                            channel
                        )
                    session.commit()
                    logger.info(f"  ✅ {len(channels_backup)}개 채널 복원 완료")
                    self.stats['preserved']['channels'] = len(channels_backup)

            except Exception as e:
                logger.error(f"❌ PostgreSQL 초기화 실패: {e}")
                self.stats['errors'].append(f"PostgreSQL 초기화 실패: {e}")
                session.rollback()

    def clear_qdrant_data(self, recreate_collection: bool = True):
        """Qdrant 데이터 초기화"""
        logger.info("\n" + "="*50)
        logger.info("Qdrant 벡터 데이터베이스 초기화")
        logger.info("="*50)

        try:
            # 기존 컬렉션 확인
            collections = self.qdrant_client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if 'youtube_content' in collection_names:
                # 벡터 수 확인
                collection_info = self.qdrant_client.get_collection('youtube_content')
                vector_count = collection_info.points_count
                logger.info(f"  현재 벡터 수: {vector_count}개")

                # 컬렉션 삭제
                self.qdrant_client.delete_collection('youtube_content')
                logger.info(f"  ✅ 'youtube_content' 컬렉션 삭제 완료")
                self.stats['deleted']['qdrant_vectors'] = vector_count

                if recreate_collection:
                    # 컬렉션 재생성
                    self.qdrant_client.recreate_collection(
                        collection_name='youtube_content',
                        vectors_config=VectorParams(
                            size=1536,  # OpenAI embedding dimension
                            distance=Distance.COSINE
                        )
                    )
                    logger.info(f"  ✅ 'youtube_content' 컬렉션 재생성 완료")
            else:
                logger.info("  ℹ️ 'youtube_content' 컬렉션이 존재하지 않습니다")

                if recreate_collection:
                    # 컬렉션 생성
                    self.qdrant_client.create_collection(
                        collection_name='youtube_content',
                        vectors_config=VectorParams(
                            size=1536,  # OpenAI embedding dimension
                            distance=Distance.COSINE
                        )
                    )
                    logger.info(f"  ✅ 'youtube_content' 컬렉션 생성 완료")

        except Exception as e:
            logger.error(f"❌ Qdrant 초기화 실패: {e}")
            self.stats['errors'].append(f"Qdrant 초기화 실패: {e}")

    def clear_redis_cache(self):
        """Redis 캐시 초기화"""
        logger.info("\n" + "="*50)
        logger.info("Redis 캐시 초기화")
        logger.info("="*50)

        try:
            import redis
            redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
            r = redis.from_url(redis_url)

            # 키 수 확인
            key_count = r.dbsize()
            logger.info(f"  현재 키 수: {key_count}개")

            # 모든 키 삭제
            r.flushdb()
            logger.info(f"  ✅ Redis 캐시 초기화 완료")
            self.stats['deleted']['redis_keys'] = key_count

        except Exception as e:
            logger.error(f"❌ Redis 초기화 실패: {e}")
            self.stats['errors'].append(f"Redis 초기화 실패: {e}")

    def clear_temp_files(self):
        """임시 파일 정리"""
        logger.info("\n" + "="*50)
        logger.info("임시 파일 정리")
        logger.info("="*50)

        temp_dirs = ['/tmp/youtube_downloads', '/tmp/whisper_cache', '/app/data/temp']
        deleted_count = 0

        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    import shutil
                    file_count = len(os.listdir(temp_dir))
                    shutil.rmtree(temp_dir)
                    os.makedirs(temp_dir, exist_ok=True)
                    logger.info(f"  ✅ {temp_dir}: {file_count}개 파일 삭제")
                    deleted_count += file_count
                except Exception as e:
                    logger.error(f"  ❌ {temp_dir} 정리 실패: {e}")
                    self.stats['errors'].append(f"{temp_dir} 정리 실패: {e}")

        self.stats['deleted']['temp_files'] = deleted_count

    def soft_reset(self):
        """소프트 리셋 (채널 정보 보존, 콘텐츠만 초기화)"""
        logger.info("\n" + "🔄 소프트 리셋 시작 (채널 정보 보존)")
        logger.info("="*60)

        self.clear_postgres_data(preserve_channels=True)
        self.clear_qdrant_data(recreate_collection=True)
        self.clear_redis_cache()
        self.clear_temp_files()

    def hard_reset(self):
        """하드 리셋 (모든 데이터 초기화)"""
        logger.info("\n" + "⚠️ 하드 리셋 시작 (모든 데이터 삭제)")
        logger.info("="*60)

        self.clear_postgres_data(preserve_channels=False)
        self.clear_qdrant_data(recreate_collection=True)
        self.clear_redis_cache()
        self.clear_temp_files()

    def generate_report(self):
        """초기화 결과 보고서"""
        logger.info("\n" + "="*60)
        logger.info("초기화 완료 보고서")
        logger.info("="*60)

        # 삭제된 데이터
        if self.stats['deleted']:
            logger.info("\n✅ 삭제된 데이터:")
            for key, value in self.stats['deleted'].items():
                logger.info(f"  - {key}: {value}개")

        # 보존된 데이터
        if self.stats['preserved']:
            logger.info("\n💾 보존된 데이터:")
            for key, value in self.stats['preserved'].items():
                logger.info(f"  - {key}: {value}개")

        # 에러
        if self.stats['errors']:
            logger.error("\n❌ 발생한 에러:")
            for error in self.stats['errors']:
                logger.error(f"  - {error}")
        else:
            logger.info("\n✨ 모든 작업이 성공적으로 완료되었습니다.")

        return self.stats


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='데이터 초기화 스크립트')
    parser.add_argument('--mode', choices=['soft', 'hard'], required=True,
                      help='초기화 모드 선택 (soft: 채널 보존, hard: 전체 초기화)')
    parser.add_argument('--force', action='store_true',
                      help='확인 없이 즉시 실행')
    args = parser.parse_args()

    # 확인 프롬프트
    if not args.force:
        logger.warning("\n" + "⚠️ "*10)
        if args.mode == 'hard':
            logger.warning("하드 리셋을 실행하면 모든 데이터가 삭제됩니다!")
            logger.warning("채널 정보를 포함한 모든 데이터가 영구적으로 삭제됩니다.")
        else:
            logger.warning("소프트 리셋을 실행하면 콘텐츠 데이터가 삭제됩니다!")
            logger.warning("채널 정보는 보존되지만 모든 콘텐츠와 처리 데이터가 삭제됩니다.")

        logger.warning("⚠️ "*10 + "\n")

        response = input("정말로 계속하시겠습니까? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("초기화가 취소되었습니다.")
            sys.exit(0)

    # 초기화 실행
    resetter = DataResetter()

    start_time = time.time()

    if args.mode == 'hard':
        resetter.hard_reset()
    else:
        resetter.soft_reset()

    elapsed_time = time.time() - start_time
    report = resetter.generate_report()

    logger.info(f"\n⏱️ 실행 시간: {elapsed_time:.2f}초")

    # 종료 코드
    if report['errors']:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()