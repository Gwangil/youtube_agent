"""
데이터 처리 및 벡터화 서비스
수집된 콘텐츠의 자막 추출, STT 처리, 텍스트 처리 및 벡터 임베딩
"""

import os
import sys
import time
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import redis
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import openai
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import (
    Channel, Content, Transcript, ProcessingJob, VectorMapping,
    get_database_url
)
from src.youtube_agent.youtube_extractor import YouTubeExtractor
from src.youtube_agent.stt_processor import STTProcessor


class DataProcessor:
    """데이터 처리 및 벡터화 서비스"""

    def __init__(self):
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Redis 연결
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_client = redis.from_url(redis_url)

        # Qdrant 연결
        qdrant_url = os.getenv('QDRANT_URL', 'http://localhost:6333')
        self.qdrant_client = QdrantClient(url=qdrant_url)

        # OpenAI 설정
        openai.api_key = os.getenv('OPENAI_API_KEY')
        self.embeddings = OpenAIEmbeddings()

        # 텍스트 분할기
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )

        # 컴포넌트 초기화
        self.youtube_extractor = YouTubeExtractor()
        self.stt_processor = STTProcessor(model_size="large")

        # Qdrant 컬렉션 초기화
        self._init_vector_collections()

    def _init_vector_collections(self):
        """벡터 컬렉션 초기화"""
        collection_name = "youtube_content"

        try:
            # 컬렉션이 존재하는지 확인
            collections = self.qdrant_client.get_collections()
            collection_exists = any(
                col.name == collection_name
                for col in collections.collections
            )

            if not collection_exists:
                # 컬렉션 생성 (OpenAI embeddings는 1536 차원)
                self.qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=1536,
                        distance=Distance.COSINE
                    )
                )
                print(f"벡터 컬렉션 생성: {collection_name}")
            else:
                print(f"벡터 컬렉션 존재: {collection_name}")

        except Exception as e:
            print(f"벡터 컬렉션 초기화 실패: {e}")

    def get_db(self):
        """데이터베이스 세션 생성"""
        db = self.SessionLocal()
        try:
            return db
        finally:
            pass

    def process_transcript_extraction(self, job: ProcessingJob):
        """자막 추출 작업 처리"""
        print(f"자막 추출 작업 처리: Job {job.id}")

        db = self.get_db()
        try:
            # 작업 상태 업데이트
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            db.commit()

            # 콘텐츠 정보 조회
            content = db.query(Content).filter(Content.id == job.content_id).first()
            if not content:
                raise Exception("콘텐츠를 찾을 수 없습니다")

            # YouTube 자막 추출
            transcript_data = self.youtube_extractor.extract_transcript(
                content.external_id,
                [content.language, 'en']
            )

            if transcript_data:
                # 트랜스크립트 데이터 저장
                for i, segment in enumerate(transcript_data.get('transcript_data', [])):
                    transcript = Transcript(
                        content_id=content.id,
                        text=segment['text'],
                        start_time=segment.get('start', 0),
                        end_time=segment.get('start', 0) + segment.get('duration', 0),
                        segment_order=i
                    )
                    db.add(transcript)

                # 콘텐츠 업데이트
                content.transcript_available = True
                content.transcript_type = transcript_data.get('transcript_type', 'auto')
                content.language = transcript_data.get('language', content.language)

                # 벡터화 작업 큐에 추가
                vector_job = ProcessingJob(
                    job_type='vectorize',
                    content_id=content.id,
                    status='pending'
                )
                db.add(vector_job)

                # 작업 완료
                job.status = 'completed'
                job.completed_at = datetime.utcnow()

                print(f"자막 추출 완료: {content.title}")

            else:
                # 자막이 없는 경우 STT 작업으로 변경
                stt_job = ProcessingJob(
                    job_type='process_audio',
                    content_id=content.id,
                    status='pending',
                    priority=1
                )
                db.add(stt_job)

                job.status = 'completed'
                job.completed_at = datetime.utcnow()

                print(f"자막 없음, STT 작업 생성: {content.title}")

            db.commit()

        except Exception as e:
            print(f"자막 추출 실패: {e}")
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def process_audio_stt(self, job: ProcessingJob):
        """오디오 STT 처리 작업"""
        print(f"STT 작업 처리: Job {job.id}")

        db = self.get_db()
        try:
            # 작업 상태 업데이트
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            db.commit()

            # 콘텐츠 정보 조회
            content = db.query(Content).filter(Content.id == job.content_id).first()
            if not content:
                raise Exception("콘텐츠를 찾을 수 없습니다")

            # STT 처리
            stt_result = self.stt_processor.process_video(
                content.url,
                content.external_id,
                content.language
            )

            if stt_result:
                # 트랜스크립트 데이터 저장
                for i, segment in enumerate(stt_result.get('segments', [])):
                    transcript = Transcript(
                        content_id=content.id,
                        text=segment['text'],
                        start_time=segment.get('start', 0),
                        end_time=segment.get('end', 0),
                        segment_order=i
                    )
                    db.add(transcript)

                # 콘텐츠 업데이트
                content.transcript_available = True
                content.transcript_type = 'stt_whisper'
                content.language = stt_result.get('language', content.language)

                # 벡터화 작업 큐에 추가
                vector_job = ProcessingJob(
                    job_type='vectorize',
                    content_id=content.id,
                    status='pending'
                )
                db.add(vector_job)

                # 작업 완료
                job.status = 'completed'
                job.completed_at = datetime.utcnow()

                print(f"STT 처리 완료: {content.title}")

            else:
                raise Exception("STT 처리 실패")

            db.commit()

        except Exception as e:
            print(f"STT 처리 실패: {e}")
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def process_vectorization(self, job: ProcessingJob):
        """개선된 벡터화 처리 작업 - 문장 기반 청킹 + 타임스탬프"""
        print(f"벡터화 작업 처리: Job {job.id}")

        db = self.get_db()
        try:
            # 작업 상태 업데이트
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            db.commit()

            # 콘텐츠와 트랜스크립트 조회
            content = db.query(Content).filter(Content.id == job.content_id).first()
            if not content:
                raise Exception("콘텐츠를 찾을 수 없습니다")

            transcripts = db.query(Transcript).filter(
                Transcript.content_id == content.id
            ).order_by(Transcript.segment_order).all()

            if not transcripts:
                raise Exception("트랜스크립트가 없습니다")

            # 문장 기반 청킹 수행
            semantic_chunks = self._create_semantic_chunks(transcripts)

            # 각 청크를 벡터화하여 저장
            points = []
            for i, chunk_data in enumerate(semantic_chunks):
                # 벡터 임베딩 생성
                embedding = self.embeddings.embed_query(chunk_data['text'])

                # 청크 ID 생성
                chunk_id = hashlib.md5(
                    f"{content.id}_{i}_{chunk_data['text'][:50]}".encode()
                ).hexdigest()

                # 타임스탬프 URL 생성
                timestamp_url = self._create_timestamp_url(content.url, chunk_data['start_time'])

                # 향상된 메타데이터 준비
                metadata = {
                    'content_id': content.id,
                    'channel_id': content.channel_id,
                    'title': content.title,
                    'url': content.url,
                    'timestamp_url': timestamp_url,
                    'publish_date': content.publish_date.isoformat() if content.publish_date else None,
                    'language': content.language,
                    'platform': db.query(Channel).filter(
                        Channel.id == content.channel_id
                    ).first().platform,
                    'chunk_order': i,
                    'chunk_text': chunk_data['text'],
                    'start_time': chunk_data['start_time'],
                    'end_time': chunk_data['end_time'],
                    'duration': chunk_data['end_time'] - chunk_data['start_time'],
                    'sentence_count': chunk_data['sentence_count'],
                    'chunk_type': chunk_data['chunk_type']
                }

                # Qdrant 포인트 생성
                point = PointStruct(
                    id=chunk_id,
                    vector=embedding,
                    payload=metadata
                )
                points.append(point)

                # 벡터 매핑 정보 DB 저장
                vector_mapping = VectorMapping(
                    content_id=content.id,
                    chunk_id=chunk_id,
                    vector_collection='youtube_content',
                    chunk_text=chunk_data['text'],
                    chunk_order=i,
                    chunk_metadata=metadata
                )
                db.add(vector_mapping)

            # Qdrant에 벡터 저장
            self.qdrant_client.upsert(
                collection_name='youtube_content',
                points=points
            )

            # 콘텐츠 벡터 저장 상태 업데이트
            content.vector_stored = True
            content.processed_at = datetime.utcnow()

            # 작업 완료
            job.status = 'completed'
            job.completed_at = datetime.utcnow()

            db.commit()

            print(f"벡터화 완료: {content.title} ({len(semantic_chunks)}개 청크)")

        except Exception as e:
            print(f"벡터화 실패: {e}")
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def _create_semantic_chunks(self, transcripts):
        """문장 기반 의미 청킹 생성"""
        chunks = []
        current_chunk = {
            'text': '',
            'start_time': None,
            'end_time': None,
            'sentence_count': 0,
            'chunk_type': 'semantic'
        }

        for transcript in transcripts:
            # 첫 번째 세그먼트인 경우 시작 시간 설정
            if current_chunk['start_time'] is None:
                current_chunk['start_time'] = transcript.start_time

            # 텍스트 추가
            current_chunk['text'] += transcript.text + ' '
            current_chunk['end_time'] = transcript.end_time

            # 문장 끝 감지 (.!?)
            if self._is_sentence_end(transcript.text):
                current_chunk['sentence_count'] += 1

                # 청크 크기가 적당하면 (1-3문장 또는 800자 이상) 청크 완료
                if (current_chunk['sentence_count'] >= 1 and len(current_chunk['text']) >= 300) or \
                   (current_chunk['sentence_count'] >= 3) or \
                   (len(current_chunk['text']) >= 800):

                    current_chunk['text'] = current_chunk['text'].strip()
                    chunks.append(current_chunk.copy())

                    # 새 청크 시작
                    current_chunk = {
                        'text': '',
                        'start_time': None,
                        'end_time': None,
                        'sentence_count': 0,
                        'chunk_type': 'semantic'
                    }

        # 마지막 청크 처리
        if current_chunk['text'].strip():
            current_chunk['text'] = current_chunk['text'].strip()
            chunks.append(current_chunk)

        return chunks

    def _is_sentence_end(self, text):
        """문장 끝 판별"""
        text = text.strip()
        return text.endswith(('.', '!', '?', '다.', '요.', '니다.', '습니다.'))

    def _create_timestamp_url(self, original_url, start_time_seconds):
        """YouTube 타임스탬프 URL 생성"""
        if not original_url or start_time_seconds is None:
            return original_url

        # YouTube URL 처리
        if 'youtube.com' in original_url or 'youtu.be' in original_url:
            # 기존 t 파라미터 제거
            import re
            url_without_timestamp = re.sub(r'[&?]t=\d+[ms]?', '', original_url)

            # 시간을 초 단위로 변환
            timestamp_seconds = int(start_time_seconds)

            # URL에 타임스탬프 추가
            separator = '&' if '?' in url_without_timestamp else '?'
            return f"{url_without_timestamp}{separator}t={timestamp_seconds}s"

        return original_url

    def process_pending_jobs(self):
        """대기 중인 작업 처리"""
        db = self.get_db()

        try:
            # 우선순위 순으로 대기 중인 작업 조회
            pending_jobs = db.query(ProcessingJob).filter(
                ProcessingJob.status == 'pending'
            ).order_by(
                ProcessingJob.priority.desc(),
                ProcessingJob.created_at
            ).limit(10).all()

            for job in pending_jobs:
                print(f"\n작업 처리 시작: {job.job_type} (ID: {job.id})")

                if job.job_type == 'extract_transcript':
                    self.process_transcript_extraction(job)
                elif job.job_type == 'process_audio':
                    self.process_audio_stt(job)
                elif job.job_type == 'vectorize':
                    self.process_vectorization(job)
                else:
                    print(f"알 수 없는 작업 타입: {job.job_type}")

                # 작업 간 대기
                time.sleep(1)

        except Exception as e:
            print(f"작업 처리 중 오류: {e}")
        finally:
            db.close()

    def start_worker(self):
        """워커 프로세스 시작"""
        print("데이터 처리 워커 시작")

        while True:
            try:
                self.process_pending_jobs()
                time.sleep(10)  # 10초마다 작업 확인

            except KeyboardInterrupt:
                print("워커 종료")
                break
            except Exception as e:
                print(f"워커 오류: {e}")
                time.sleep(30)  # 오류 시 30초 대기


def main():
    """메인 실행 함수"""
    print("데이터 처리 서비스 시작")

    processor = DataProcessor()
    processor.start_worker()


if __name__ == "__main__":
    main()