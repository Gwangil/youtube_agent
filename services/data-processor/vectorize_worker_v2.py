#!/usr/bin/env python3
"""
향상된 벡터화 워커 (트랜잭션 관리 적용)
- 원자적 처리 보장
- 실패 시 자동 롤백
- 데이터 정합성 유지
"""

import sys
import os
import time
import logging
from typing import List, Dict
import json

# 경로 설정
sys.path.append('/app')
sys.path.append('/app/services/data-integrity')

from shared.models.database import get_database_url, ProcessingJob, Content, Transcript
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient
import redis
from transaction_manager import TransactionManager

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorizeWorkerV2:
    def __init__(self, worker_id: int = 0):
        self.worker_id = worker_id

        # DB 연결
        self.engine = create_engine(get_database_url())
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

        logger.info(f"✅ 향상된 벡터화 워커 #{worker_id} 초기화 완료")

    def process_job(self, job: ProcessingJob):
        """작업 처리 (트랜잭션 관리 적용)"""
        content_id = job.content_id

        with self.SessionLocal() as db:
            # 트랜잭션 관리자 생성
            tx_manager = TransactionManager(db, self.qdrant, self.redis)

            try:
                # 원자적 작업 시작
                with tx_manager.atomic_operation(content_id, "vectorization"):
                    logger.info(f"🔄 벡터화 시작: Content {content_id}")

                    # 1. 콘텐츠와 트랜스크립트 조회
                    content = db.query(Content).filter(Content.id == content_id).first()
                    if not content:
                        raise ValueError(f"콘텐츠를 찾을 수 없음: {content_id}")

                    # 비활성 콘텐츠는 처리하지 않음
                    if hasattr(content, 'is_active') and not content.is_active:
                        logger.info(f"⏭️ 콘텐츠 {content_id}가 비활성화됨, 작업 취소")
                        job.status = 'cancelled'
                        job.error_message = 'Content is inactive'
                        db.commit()
                        return

                    transcripts = db.query(Transcript).filter(
                        Transcript.content_id == content_id
                    ).order_by(Transcript.segment_order).all()

                    if not transcripts:
                        raise ValueError(f"트랜스크립트 없음: Content {content_id}")

                    # 2. 청킹 생성
                    chunks = self._create_chunks(transcripts, content)
                    logger.info(f"📄 {len(chunks)}개 청크 생성")

                    # 3. 임베딩 생성
                    embeddings = self._generate_embeddings([c["text"] for c in chunks])

                    # 4. 기존 벡터 제거 (트랜잭션 내)
                    tx_manager.remove_vectors(content_id)

                    # 5. 새 벡터 추가 (트랜잭션 내)
                    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                        vector_data = {
                            "chunk_id": f"{content_id}_{i}",
                            "text": chunk["text"],
                            "vector": embedding,
                            "order": i,
                            "metadata": {
                                "title": content.title,
                                "url": content.url,
                                "start_time": chunk.get("start_time"),
                                "end_time": chunk.get("end_time"),
                                "timestamp_url": chunk.get("timestamp_url")
                            }
                        }

                        # content 컬렉션에 추가
                        tx_manager.add_vector(
                            content_id,
                            "youtube_content",
                            vector_data
                        )

                    # 6. 요약 생성 및 저장
                    summary = self._generate_summary(transcripts, content)
                    summary_embedding = self._generate_embeddings([summary["text"]])[0]

                    summary_data = {
                        "chunk_id": f"{content_id}_summary",
                        "text": summary["text"],
                        "vector": summary_embedding,
                        "order": 0,
                        "metadata": {
                            "title": content.title,
                            "url": content.url,
                            "type": "summary"
                        }
                    }

                    # summaries 컬렉션에 추가
                    tx_manager.add_vector(
                        content_id,
                        "youtube_summaries",
                        summary_data
                    )

                    # 7. 작업 완료 처리
                    job.status = "completed"
                    job.updated_at = time.time()
                    db.commit()

                    logger.info(f"✅ 벡터화 완료: Content {content_id} ({len(chunks)} chunks + 1 summary)")

                    # 8. 캐시 무효화
                    self.redis.delete(f"cache:content:{content_id}:*")

            except Exception as e:
                # 트랜잭션 매니저가 자동으로 롤백 처리
                logger.error(f"❌ 벡터화 실패 (Content {content_id}): {e}")

                # 작업 실패 처리
                job.status = "failed"
                job.error_message = str(e)
                job.retry_count += 1
                job.updated_at = time.time()
                db.commit()

                raise

    def _create_chunks(self, transcripts: List[Transcript], content: Content) -> List[Dict]:
        """의미 기반 청킹"""
        chunks = []
        current_chunk = {
            "text": "",
            "start_time": None,
            "end_time": None
        }

        for transcript in transcripts:
            # 청크 크기 체크 (300-800자)
            if len(current_chunk["text"]) + len(transcript.text) > 800:
                # 현재 청크 저장
                if current_chunk["text"]:
                    # 타임스탬프 URL 생성
                    if current_chunk["start_time"] is not None:
                        current_chunk["timestamp_url"] = self._create_timestamp_url(
                            content.url,
                            current_chunk["start_time"]
                        )
                    chunks.append(current_chunk)

                # 새 청크 시작
                current_chunk = {
                    "text": transcript.text,
                    "start_time": transcript.start_time,
                    "end_time": transcript.end_time
                }
            else:
                # 기존 청크에 추가
                if current_chunk["text"]:
                    current_chunk["text"] += " " + transcript.text
                else:
                    current_chunk["text"] = transcript.text
                    current_chunk["start_time"] = transcript.start_time

                current_chunk["end_time"] = transcript.end_time

        # 마지막 청크 저장
        if current_chunk["text"]:
            if current_chunk["start_time"] is not None:
                current_chunk["timestamp_url"] = self._create_timestamp_url(
                    content.url,
                    current_chunk["start_time"]
                )
            chunks.append(current_chunk)

        return chunks

    def _create_timestamp_url(self, url: str, start_time: float) -> str:
        """YouTube 타임스탬프 URL 생성"""
        if not url or start_time is None:
            return url

        timestamp_seconds = int(start_time)

        if "youtube.com" in url or "youtu.be" in url:
            # 기존 타임스탬프 제거
            base_url = url.split("&t=")[0].split("?t=")[0]

            # 새 타임스탬프 추가
            separator = "&" if "?" in base_url else "?"
            return f"{base_url}{separator}t={timestamp_seconds}s"

        return url

    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """임베딩 생성 (실제 구현에서는 임베딩 서버 호출)"""
        # TODO: 실제 임베딩 서버 호출
        import random
        return [[random.random() for _ in range(1024)] for _ in texts]

    def _generate_summary(self, transcripts: List[Transcript], content: Content) -> Dict:
        """요약 생성"""
        full_text = " ".join([t.text for t in transcripts])

        # 간단한 요약 (실제로는 LLM 사용)
        summary_text = f"{content.title}. " + full_text[:500]

        return {
            "text": summary_text
        }

    def run(self):
        """워커 실행"""
        logger.info(f"🚀 향상된 벡터화 워커 #{self.worker_id} 시작")

        while True:
            with self.SessionLocal() as db:
                try:
                    # 대기 중인 벡터화 작업 조회
                    job = db.query(ProcessingJob).filter(
                        ProcessingJob.job_type == "vectorize",
                        ProcessingJob.status == "pending"
                    ).order_by(
                        ProcessingJob.priority.desc(),
                        ProcessingJob.created_at
                    ).first()

                    if job:
                        logger.info(f"📋 작업 시작: Job {job.id} (Content {job.content_id})")

                        # 작업 상태를 processing으로 변경
                        job.status = "processing"
                        job.updated_at = time.time()
                        db.commit()

                        # 작업 처리
                        self.process_job(job)

                    else:
                        # 작업이 없으면 대기
                        time.sleep(10)

                except Exception as e:
                    logger.error(f"워커 오류: {e}")
                    time.sleep(5)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="향상된 벡터화 워커")
    parser.add_argument("--worker-id", type=int, default=0, help="워커 ID")

    args = parser.parse_args()

    worker = VectorizeWorkerV2(args.worker_id)
    worker.run()