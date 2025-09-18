#!/usr/bin/env python3
"""
개선된 벡터화 워커
임베딩 서버와 통신하여 안정적인 벡터화 처리
"""

import os
import sys
import time
import hashlib
import requests
from datetime import datetime
from typing import List, Dict
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
import re
import redis
import json
import pickle

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import (
    Content, Transcript, ProcessingJob, VectorMapping,
    get_database_url
)
from shared.utils.retry import retry, robust_retry


class ImprovedVectorizeWorker:
    """개선된 벡터화 워커 - 임베딩 서버 클라이언트"""

    def __init__(self):
        self.worker_id = int(os.getenv('VECTORIZE_WORKER_ID', '0'))
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Qdrant 연결
        qdrant_url = os.getenv('QDRANT_URL', 'http://localhost:6333')
        self.qdrant_client = QdrantClient(url=qdrant_url)

        # 임베딩 서버 URL
        self.embedding_server_url = os.getenv('EMBEDDING_SERVER_URL', 'http://localhost:8083')

        # Redis 캐시 연결
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_client = redis.from_url(redis_url, decode_responses=False)
        self.cache_ttl = 3600 * 24 * 7  # 7일간 캐시 유지

        print(f"🚀 개선된 벡터화 워커 #{self.worker_id} 초기화 완료")
        print(f"  🎯 임베딩 서버: {self.embedding_server_url}")
        print(f"  💾 Qdrant: {qdrant_url}")
        print(f"  📦 Redis 캐시 연결됨")

        # 임베딩 서버 연결 확인
        self._check_embedding_server()

    def _check_embedding_server(self):
        """임베딩 서버 연결 상태 확인"""
        try:
            response = requests.get(f"{self.embedding_server_url}/health", timeout=5)
            if response.status_code == 200:
                info = response.json()
                print(f"  ✅ 임베딩 서버 연결됨")
                print(f"    - 모델: {info.get('model', 'unknown')}")
                print(f"    - 타입: {info.get('type', 'unknown')}")
                print(f"    - 차원: {info.get('dimension', 'unknown')}")
                print(f"    - 디바이스: {info.get('device', 'unknown')}")
                self.embedding_dimension = info.get('dimension', 1024)
            else:
                print(f"  ⚠️ 임베딩 서버 응답 오류: {response.status_code}")
                self.embedding_dimension = 1024  # 기본값
        except Exception as e:
            print(f"  ❌ 임베딩 서버 연결 실패: {e}")
            print(f"  💔 임베딩 서버 없이는 작동할 수 없습니다!")
            self.embedding_dimension = 1024  # 기본값

    def get_db(self):
        """데이터베이스 세션 생성"""
        return self.SessionLocal()

    def _create_semantic_chunks(self, transcripts: List[Transcript]) -> List[Dict]:
        """문장 기반 의미 청킹 (강화된 중복 제거 및 시간 검증)"""
        chunks = []
        current_chunk = {
            'text': '',
            'start_time': 0,
            'end_time': 0,
            'sentences': []
        }

        # 텍스트 중복 감지를 위한 해시 세트
        seen_texts = set()

        # 시간 오류 통계
        time_errors = 0

        for transcript in transcripts:
            text = transcript.text.strip()
            if not text or len(text) < 5:  # 너무 짧은 텍스트 제외
                continue

            # 시간 검증 - start_time이 end_time보다 큰 경우 스킵
            if transcript.start_time > transcript.end_time:
                time_errors += 1
                print(f"  ⚠️ 시간 오류 감지: start={transcript.start_time:.2f}, end={transcript.end_time:.2f} - 스킵")
                continue

            # 중복 텍스트 확인
            text_hash = hashlib.md5(text.lower().encode()).hexdigest()
            if text_hash in seen_texts:
                continue
            seen_texts.add(text_hash)

            # 문장 단위로 분할 (한국어 문장 끝 패턴)
            sentences = re.split(r'[.!?。]+', text)
            sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 3]

            for sentence in sentences:
                # 반복 패턴 제거
                cleaned_sentence = self._clean_repetitive_text(sentence)
                if not cleaned_sentence or len(cleaned_sentence) < 5:
                    continue

                # 첫 번째 문장이면 시작 시간 설정
                if not current_chunk['sentences']:
                    current_chunk['start_time'] = transcript.start_time

                current_chunk['sentences'].append(cleaned_sentence)
                current_chunk['text'] += cleaned_sentence + '. '
                current_chunk['end_time'] = max(transcript.end_time, current_chunk['start_time'] + 0.1)  # 최소 0.1초 보장

                # 청크 크기 제한 (1-3 문장 또는 200-600자로 조정)
                chunk_length = len(current_chunk['text'])
                sentence_count = len(current_chunk['sentences'])

                if sentence_count >= 2 or chunk_length >= 600:
                    # 의미 있는 청크만 추가 (시간 검증 포함)
                    if chunk_length > 10 and sentence_count > 0:
                        # 시간 범위 최종 검증
                        if current_chunk['end_time'] < current_chunk['start_time']:
                            current_chunk['end_time'] = current_chunk['start_time'] + 1.0  # 기본 1초
                        chunks.append(current_chunk.copy())
                    current_chunk = {
                        'text': '',
                        'start_time': 0,
                        'end_time': 0,
                        'sentences': []
                    }

        # 마지막 청크 추가
        if current_chunk['sentences'] and len(current_chunk['text']) > 10:
            # 시간 범위 최종 검증
            if current_chunk['end_time'] < current_chunk['start_time']:
                current_chunk['end_time'] = current_chunk['start_time'] + 1.0
            chunks.append(current_chunk)

        if time_errors > 0:
            print(f"  ⚠️ 시간 오류로 스킵된 트랜스크립트: {time_errors}개")

        print(f"  📊 청킹 통계: {len(transcripts)}개 트랜스크립트 -> {len(chunks)}개 청크")
        return chunks

    def _clean_repetitive_text(self, text: str) -> str:
        """반복되는 텍스트 패턴 제거"""
        if not text:
            return text

        # 연속된 동일 단어 제거
        import re
        text = re.sub(r'\b(\w+)(\s+\1\b)+', r'\1', text)

        # 동일 구문 반복 제거
        words = text.split()
        if len(words) < 4:
            return text

        cleaned_words = []
        i = 0
        while i < len(words):
            max_pattern_length = min(3, (len(words) - i) // 2)
            pattern_found = False

            for pattern_len in range(max_pattern_length, 1, -1):
                if i + pattern_len * 2 <= len(words):
                    pattern = words[i:i+pattern_len]
                    next_pattern = words[i+pattern_len:i+pattern_len*2]

                    if pattern == next_pattern:
                        cleaned_words.extend(pattern)
                        i += pattern_len * 2
                        pattern_found = True
                        break

            if not pattern_found:
                cleaned_words.append(words[i])
                i += 1

        return ' '.join(cleaned_words)

    def _create_timestamp_url(self, original_url: str, start_time_seconds: float) -> str:
        """YouTube 타임스탬프 URL 생성"""
        try:
            # URL에서 파라미터 분리
            if '?' in original_url:
                base_url, params = original_url.split('?', 1)
                # 기존 t 파라미터 제거
                param_parts = [p for p in params.split('&') if not p.startswith('t=')]
                if param_parts:
                    url_without_timestamp = f"{base_url}?{'&'.join(param_parts)}"
                else:
                    url_without_timestamp = base_url
            else:
                url_without_timestamp = original_url

            # 시간을 초 단위로 변환
            timestamp_seconds = int(start_time_seconds)

            # URL에 타임스탬프 추가
            separator = '&' if '?' in url_without_timestamp else '?'
            return f"{url_without_timestamp}{separator}t={timestamp_seconds}s"

        except Exception:
            return original_url

    @retry(max_attempts=3, delay=2.0, backoff=2.0)
    def _get_embeddings_from_server(self, texts: List[str]) -> List[List[float]]:
        """임베딩 서버에서 벡터 생성 (재시도 포함)"""
        try:
            # 헬스 체크
            health_response = requests.get(f"{self.embedding_server_url}/health", timeout=2)
            if health_response.status_code != 200:
                raise requests.exceptions.ConnectionError("Embedding server not ready")

            # 임베딩 요청
            response = requests.post(
                f"{self.embedding_server_url}/embed",
                json={"texts": texts},
                timeout=60  # 1분 타임아웃
            )

            if response.status_code == 200:
                result = response.json()
                embeddings = result['embeddings']
                dimension = result['dimension']
                print(f"  ✅ 임베딩 서버 처리 완료: {len(embeddings)}개, {dimension}차원")
                return embeddings
            else:
                raise Exception(f"임베딩 서버 오류: {response.status_code}")

        except Exception as e:
            print(f"  ❌ 임베딩 서버 요청 실패: {e}")
            raise

    def process_vectorization(self, job: ProcessingJob):
        """벡터화 처리"""
        print(f"🔧 [Worker {self.worker_id}] 벡터화 작업 처리: Job {job.id}")

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

            print(f"  📝 [Worker {self.worker_id}] {len(transcripts)}개 트랜스크립트 세그먼트 처리 중...")

            # 문장 기반 청킹 수행
            semantic_chunks = self._create_semantic_chunks(transcripts)
            print(f"  🧩 [Worker {self.worker_id}] {len(semantic_chunks)}개 의미 청크 생성")

            # 배치 처리를 위한 텍스트 수집
            batch_size = 100  # 한 번에 처리할 임베딩 수
            points = []

            # 청크 텍스트 배치로 수집
            for batch_start in range(0, len(semantic_chunks), batch_size):
                batch_end = min(batch_start + batch_size, len(semantic_chunks))
                batch_chunks = semantic_chunks[batch_start:batch_end]

                # 배치 텍스트 준비
                batch_texts = [chunk['text'] for chunk in batch_chunks]

                # 캐시된 임베딩 확인 및 새로운 임베딩 생성
                batch_embeddings = []
                texts_to_embed = []  # 캐시되지 않은 텍스트
                text_indices = []  # 원본 배치에서의 인덱스

                for idx, text in enumerate(batch_texts):
                    # 캐시 키 생성 (텍스트 해시 + 차원)
                    cache_key = f"embedding:1024:{hashlib.md5(text.encode()).hexdigest()}"

                    # Redis에서 캐시된 임베딩 확인
                    cached_embedding = self.redis_client.get(cache_key)

                    if cached_embedding:
                        # 캐시 히트
                        embedding = pickle.loads(cached_embedding)
                        batch_embeddings.append(embedding)
                    else:
                        # 캐시 미스 - 나중에 임베딩할 텍스트로 추가
                        texts_to_embed.append(text)
                        text_indices.append(idx)
                        batch_embeddings.append(None)  # 자리표시자

                # 캐시되지 않은 텍스트들에 대한 배치 임베딩 생성
                if texts_to_embed:
                    print(f"  🔄 [Worker {self.worker_id}] 임베딩 서버 요청 중... (신규: {len(texts_to_embed)}개, 캐시: {len(batch_texts) - len(texts_to_embed)}개)")

                    # 임베딩 서버에서 생성
                    new_embeddings = self._get_embeddings_from_server(texts_to_embed)

                    # 생성된 임베딩을 올바른 위치에 배치하고 캐시에 저장
                    for text, embedding, original_idx in zip(texts_to_embed, new_embeddings, text_indices):
                        batch_embeddings[original_idx] = embedding

                        # Redis에 캐시 저장 (차원 정보 포함)
                        cache_key = f"embedding:1024:{hashlib.md5(text.encode()).hexdigest()}"
                        self.redis_client.setex(
                            cache_key,
                            self.cache_ttl,
                            pickle.dumps(embedding)
                        )
                else:
                    print(f"  ✅ [Worker {self.worker_id}] 모든 임베딩이 캐시에서 로드됨 ({len(batch_texts)}개)")

                # 각 청크에 대한 포인트 생성
                for idx, (chunk_data, embedding) in enumerate(zip(batch_chunks, batch_embeddings)):
                    i = batch_start + idx

                    # 청크 ID 생성
                    chunk_id = hashlib.md5(
                        f"{content.id}_{i}_{chunk_data['text'][:50]}".encode()
                    ).hexdigest()

                    # 타임스탬프 URL 생성
                    timestamp_url = self._create_timestamp_url(content.url, chunk_data['start_time'])

                    # Qdrant 포인트 생성
                    point = PointStruct(
                        id=chunk_id,
                        vector=embedding,
                        payload={
                            "content_id": content.id,
                            "chunk_index": i,
                            "text": chunk_data['text'],
                            "start_time": chunk_data['start_time'],
                            "end_time": chunk_data['end_time'],
                            "title": content.title,
                            "channel_name": content.channel.name if content.channel else "Unknown",
                            "publish_date": content.publish_date.isoformat() if content.publish_date else None,
                            "url": content.url,
                            "timestamp_url": timestamp_url,
                            "language": content.language,
                            "duration": content.duration,
                            "transcript_type": content.transcript_type
                        }
                    )
                    points.append(point)

            # Qdrant 컬렉션 확인 및 생성
            self._ensure_qdrant_collection()

            # Qdrant에 벡터 데이터 저장 (재시도 포함)
            @retry(max_attempts=3, delay=1.0)
            def upsert_to_qdrant():
                self.qdrant_client.upsert(
                    collection_name="youtube_content",
                    points=points
                )

            upsert_to_qdrant()

            # 벡터 매핑 정보 저장
            for i, point in enumerate(points):
                chunk_metadata = {
                    "start_time": semantic_chunks[i]['start_time'],
                    "end_time": semantic_chunks[i]['end_time'],
                    "chunk_index": i
                }

                vector_mapping = VectorMapping(
                    content_id=content.id,
                    chunk_id=point.id,
                    vector_collection="youtube_content",
                    chunk_text=semantic_chunks[i]['text'],
                    chunk_order=i,
                    chunk_metadata=chunk_metadata
                )
                db.add(vector_mapping)

            # 작업 완료
            job.status = 'completed'
            job.completed_at = datetime.utcnow()
            db.commit()

            print(f"  ✅ [Worker {self.worker_id}] 벡터화 완료: {content.title[:50]}... ({len(points)}개 벡터)")

        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] 벡터화 실패: {e}")
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def _ensure_qdrant_collection(self):
        """Qdrant 컬렉션 존재 확인 및 생성"""
        try:
            # 컬렉션 정보 조회
            collection_info = self.qdrant_client.get_collection("youtube_content")
            current_dim = collection_info.config.params.vectors.size

            if current_dim != self.embedding_dimension:
                print(f"  ⚠️ 차원 불일치: 현재 {current_dim}, 필요 {self.embedding_dimension}")
                # 필요하면 재생성할 수 있지만, 데이터 손실 방지를 위해 경고만
        except:
            # 컬렉션이 없으면 생성
            from qdrant_client.models import Distance, VectorParams
            print(f"  📦 Qdrant 컬렉션 생성 중... ({self.embedding_dimension}차원)")
            self.qdrant_client.create_collection(
                collection_name="youtube_content",
                vectors_config=VectorParams(
                    size=self.embedding_dimension,
                    distance=Distance.COSINE
                )
            )

    def start_worker(self):
        """워커 시작 - 워커 ID 기반 파티셔닝으로 작업 분산"""
        print(f"🚀 개선된 벡터화 워커 #{self.worker_id} 시작")
        total_workers = int(os.getenv('TOTAL_VECTORIZE_WORKERS', '3'))
        print(f"  총 워커 수: {total_workers}, 내 ID: {self.worker_id}")

        while True:
            try:
                db = self.get_db()

                # 모든 대기 중인 벡터화 작업 조회
                all_jobs = db.query(ProcessingJob).filter(
                    ProcessingJob.job_type == 'vectorize',
                    ProcessingJob.status == 'pending'
                ).order_by(
                    ProcessingJob.priority.desc(),
                    ProcessingJob.created_at
                ).all()

                # 이 워커가 처리할 작업만 필터링 (job.id % total_workers == worker_id)
                my_jobs = [job for job in all_jobs if job.id % total_workers == self.worker_id]

                if my_jobs:
                    # 최대 5개 작업만 처리
                    for job in my_jobs[:5]:
                        print(f"\n🎯 [Worker {self.worker_id}] 벡터화 작업 선택: Job {job.id} (Priority: {job.priority})")
                        self.process_vectorization(job)
                        time.sleep(2)  # 작업 간 짧은 대기
                else:
                    print(f"📭 [Worker {self.worker_id}] 대기 중인 벡터화 작업 없음")

                db.close()
                time.sleep(10)  # 10초마다 확인

            except KeyboardInterrupt:
                print(f"🛑 벡터화 워커 #{self.worker_id} 종료")
                break
            except Exception as e:
                print(f"❌ [Worker {self.worker_id}] 워커 오류: {e}")
                time.sleep(30)


def main():
    """메인 실행 함수"""
    worker = ImprovedVectorizeWorker()
    worker.start_worker()


if __name__ == "__main__":
    main()