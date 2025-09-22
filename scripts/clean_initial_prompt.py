#!/usr/bin/env python3
"""
기존 데이터에서 "다음은 한국어 팟캐스트입니다" 문구를 제거하는 스크립트
PostgreSQL과 Qdrant 모두 업데이트
"""

import os
import sys
import json
import logging
from typing import List, Dict
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny, PointStruct

# 프로젝트 경로 추가
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import Content, Transcript, get_database_url

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 제거할 문구들
PHRASES_TO_REMOVE = [
    "다음은 한국어 팟캐스트입니다.",
    "다음은 한국어 팟캐스트입니다",
    "다음은 한국어 팟캐스트입니다. ",
]

class DataCleaner:
    def __init__(self):
        """초기화"""
        # PostgreSQL 연결
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Qdrant 연결
        qdrant_url = os.getenv('QDRANT_URL', 'http://qdrant:6333')
        self.qdrant_client = QdrantClient(url=qdrant_url)

        self.stats = {
            'postgres_transcripts_cleaned': 0,
            'postgres_summaries_cleaned': 0,
            'qdrant_points_cleaned': 0,
            'total_processed': 0
        }

    def clean_text(self, text: str) -> tuple[str, bool]:
        """
        텍스트에서 불필요한 문구 제거

        Returns:
            (cleaned_text, was_modified)
        """
        if not text:
            return text, False

        original_text = text
        cleaned_text = text

        # 각 문구를 제거
        for phrase in PHRASES_TO_REMOVE:
            # 문장 시작 부분에 있는 경우
            if cleaned_text.startswith(phrase):
                cleaned_text = cleaned_text[len(phrase):].strip()

            # 문장 중간에 있는 경우 (첫 번째 발견된 것만 제거)
            if phrase in cleaned_text:
                cleaned_text = cleaned_text.replace(phrase, "", 1).strip()

        # 연속된 공백 정리
        cleaned_text = ' '.join(cleaned_text.split())

        return cleaned_text, (cleaned_text != original_text)

    def clean_postgresql_data(self):
        """PostgreSQL 데이터 정리"""
        logger.info("Starting PostgreSQL data cleaning...")

        db = self.SessionLocal()
        try:
            # 1. Transcript 테이블 정리
            logger.info("Cleaning transcripts...")
            transcripts = db.query(Transcript).all()

            for transcript in transcripts:
                cleaned_text, was_modified = self.clean_text(transcript.text)
                if was_modified:
                    transcript.text = cleaned_text
                    self.stats['postgres_transcripts_cleaned'] += 1
                    logger.debug(f"Cleaned transcript {transcript.id}")

            # 2. Content 테이블은 summary 필드가 없으므로 건너뜀
            # Summary는 Qdrant vector DB에만 저장됨
            logger.info("Skipping content summaries (stored in Qdrant only)...")

            # 변경사항 커밋
            db.commit()
            logger.info(f"PostgreSQL cleaning complete. Transcripts: {self.stats['postgres_transcripts_cleaned']}, Summaries: {self.stats['postgres_summaries_cleaned']}")

        except Exception as e:
            logger.error(f"Error cleaning PostgreSQL data: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    def clean_qdrant_collection(self, collection_name: str):
        """Qdrant 컬렉션 데이터 정리"""
        logger.info(f"Cleaning Qdrant collection: {collection_name}")

        try:
            # 컬렉션 정보 확인
            collection_info = self.qdrant_client.get_collection(collection_name)
            total_points = collection_info.points_count
            logger.info(f"Total points in {collection_name}: {total_points}")

            # 배치 단위로 처리
            batch_size = 100
            offset = None
            cleaned_count = 0

            while True:
                # 포인트 가져오기
                points = self.qdrant_client.scroll(
                    collection_name=collection_name,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )

                if not points[0]:
                    break

                # 각 포인트 처리
                updates = []
                for point in points[0]:
                    payload = point.payload
                    modified = False

                    # text 필드 정리
                    if 'text' in payload:
                        cleaned_text, was_modified = self.clean_text(payload['text'])
                        if was_modified:
                            payload['text'] = cleaned_text
                            modified = True

                    # summary 필드 정리
                    if 'summary' in payload:
                        cleaned_summary, was_modified = self.clean_text(payload['summary'])
                        if was_modified:
                            payload['summary'] = cleaned_summary
                            modified = True

                    # content 필드 정리
                    if 'content' in payload:
                        cleaned_content, was_modified = self.clean_text(payload['content'])
                        if was_modified:
                            payload['content'] = cleaned_content
                            modified = True

                    # 수정된 경우 업데이트 목록에 추가
                    if modified:
                        updates.append({
                            'id': point.id,
                            'payload': payload
                        })
                        cleaned_count += 1

                # 업데이트 실행
                if updates:
                    for update in updates:
                        self.qdrant_client.set_payload(
                            collection_name=collection_name,
                            payload=update['payload'],
                            points=[update['id']]
                        )
                    logger.info(f"Updated {len(updates)} points in batch")

                # 다음 배치로 이동
                offset = points[1]
                if offset is None:
                    break

            logger.info(f"Cleaned {cleaned_count} points in {collection_name}")
            self.stats['qdrant_points_cleaned'] += cleaned_count

        except Exception as e:
            logger.error(f"Error cleaning Qdrant collection {collection_name}: {e}")
            # 컬렉션이 존재하지 않는 경우 건너뜀
            if "Not found" in str(e):
                logger.warning(f"Collection {collection_name} not found, skipping...")
            else:
                raise

    def run(self):
        """전체 정리 프로세스 실행"""
        logger.info("=" * 60)
        logger.info("Starting data cleaning process...")
        logger.info("=" * 60)

        try:
            # 1. PostgreSQL 데이터 정리
            self.clean_postgresql_data()

            # 2. Qdrant 컬렉션들 정리
            collections = ['youtube_content', 'youtube_summaries']
            for collection in collections:
                self.clean_qdrant_collection(collection)

            # 통계 출력
            logger.info("=" * 60)
            logger.info("Data cleaning complete!")
            logger.info(f"PostgreSQL Transcripts cleaned: {self.stats['postgres_transcripts_cleaned']}")
            logger.info(f"PostgreSQL Summaries cleaned: {self.stats['postgres_summaries_cleaned']}")
            logger.info(f"Qdrant points cleaned: {self.stats['qdrant_points_cleaned']}")
            logger.info(f"Total items processed: {sum(self.stats.values())}")
            logger.info("=" * 60)

            return self.stats

        except Exception as e:
            logger.error(f"Critical error during cleaning: {e}")
            raise


if __name__ == "__main__":
    cleaner = DataCleaner()
    cleaner.run()