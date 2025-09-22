#!/usr/bin/env python3
"""
Enhanced Vectorizer - 다층 지식 구조 생성
1. Video Summary: 전체 영상 요약 (1개 벡터)
2. Full Transcript: 전체 자막 (1개 벡터)
3. Paragraph Chunks: 문단 단위 청킹 (10-20개 벡터)
4. Semantic Chunks: 의미 단위 청킹 (현재 방식)
"""

import os
import sys
import hashlib
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import requests

sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import Content, Transcript, ProcessingJob, get_database_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedVectorizer:
    """다층 지식 구조를 생성하는 향상된 벡터화기"""

    def __init__(self):
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.qdrant_client = QdrantClient(url=os.getenv('QDRANT_URL', 'http://qdrant:6333'))
        self.embedding_server_url = os.getenv('EMBEDDING_SERVER_URL', 'http://embedding-server:8083')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')

        # 각 레벨별 컬렉션 이름
        self.collections = {
            'summary': 'youtube_summaries',      # 영상 요약
            'full_text': 'youtube_full_texts',   # 전체 자막
            'paragraphs': 'youtube_paragraphs',  # 문단 단위
            'chunks': 'youtube_content'          # 기존 세밀한 청킹
        }

        self._ensure_collections()

    def _ensure_collections(self):
        """모든 컬렉션이 존재하는지 확인하고 생성"""
        for collection_type, collection_name in self.collections.items():
            if collection_type == 'chunks':
                continue  # 기존 컬렉션은 이미 존재

            try:
                self.qdrant_client.get_collection(collection_name)
                logger.info(f"컬렉션 {collection_name} 이미 존재")
            except:
                logger.info(f"컬렉션 {collection_name} 생성 중...")
                self.qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=1024,
                        distance=Distance.COSINE
                    )
                )

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """임베딩 서버에서 벡터 생성"""
        try:
            response = requests.post(
                f"{self.embedding_server_url}/embed",
                json={"texts": texts},
                timeout=60
            )
            if response.status_code == 200:
                return response.json()['embeddings']
            else:
                raise Exception(f"임베딩 서버 오류: {response.status_code}")
        except Exception as e:
            logger.error(f"임베딩 생성 실패: {e}")
            raise

    def _generate_summary(self, title: str, transcripts: List[Transcript]) -> str:
        """OpenAI API를 사용하여 영상 요약 생성"""
        if not self.openai_api_key:
            # API 키가 없으면 간단한 요약 생성
            full_text = ' '.join([t.text for t in transcripts[:50]])  # 처음 50개 세그먼트만
            return f"제목: {title}\n내용: {full_text[:1000]}..."

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.openai_api_key)

            # 전체 텍스트 준비 (최대 10000자)
            full_text = ' '.join([t.text for t in transcripts])
            if len(full_text) > 10000:
                full_text = full_text[:10000] + "..."

            prompt = f"""
다음 YouTube 영상의 자막을 읽고 핵심 내용을 요약해주세요.

제목: {title}

자막:
{full_text}

다음 형식으로 요약해주세요:
1. 주요 주제 (1-2문장)
2. 핵심 포인트 (3-5개 불릿포인트)
3. 전체 요약 (2-3문장)
"""

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "YouTube 영상 내용을 요약하는 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.warning(f"OpenAI 요약 생성 실패: {e}")
            # 폴백: 간단한 요약
            full_text = ' '.join([t.text for t in transcripts[:50]])
            return f"제목: {title}\n내용: {full_text[:1000]}..."

    def _create_paragraphs(self, transcripts: List[Transcript]) -> List[Dict]:
        """문단 단위로 텍스트 분할"""
        paragraphs = []
        current_paragraph = []
        current_start = 0
        current_end = 0

        for transcript in transcripts:
            current_paragraph.append(transcript.text)
            if current_start == 0:
                current_start = transcript.start_time
            current_end = transcript.end_time

            # 문단 구분 조건: 500자 이상 또는 시간 간격 30초 이상
            text_length = sum(len(t) for t in current_paragraph)
            time_gap = transcript.end_time - current_start if transcript.end_time and current_start else 0

            if text_length >= 500 or time_gap >= 30:
                paragraph_text = ' '.join(current_paragraph)
                if paragraph_text.strip():
                    paragraphs.append({
                        'text': paragraph_text,
                        'start_time': current_start,
                        'end_time': current_end
                    })
                current_paragraph = []
                current_start = 0

        # 남은 텍스트 처리
        if current_paragraph:
            paragraph_text = ' '.join(current_paragraph)
            if paragraph_text.strip():
                paragraphs.append({
                    'text': paragraph_text,
                    'start_time': current_start,
                    'end_time': current_end
                })

        return paragraphs

    def process_content(self, content: Content):
        """콘텐츠를 다층 구조로 벡터화"""
        db = self.SessionLocal()

        try:
            # 트랜스크립트 로드
            transcripts = db.query(Transcript).filter(
                Transcript.content_id == content.id
            ).order_by(Transcript.segment_order).all()

            if not transcripts:
                logger.warning(f"Content {content.id}에 트랜스크립트가 없음")
                return

            logger.info(f"Content {content.id} 처리 시작: {content.title}")

            # 1. Video Summary 생성 및 저장
            summary_text = self._generate_summary(content.title, transcripts)
            summary_embedding = self._get_embeddings([summary_text])[0]

            import uuid
            summary_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"summary_{content.id}"))
            summary_point = PointStruct(
                id=summary_id,
                vector=summary_embedding,
                payload={
                    'content_id': content.id,
                    'type': 'summary',
                    'text': summary_text,
                    'title': content.title,
                    'url': content.url,
                    'channel_name': content.channel.name if content.channel else '',
                    'duration': content.duration,
                    'language': content.language
                }
            )

            self.qdrant_client.upsert(
                collection_name=self.collections['summary'],
                points=[summary_point]
            )
            logger.info(f"  ✅ 요약 저장 완료")

            # 2. Full Transcript 저장
            full_text = ' '.join([t.text for t in transcripts])
            full_text_embedding = self._get_embeddings([full_text[:10000]])[0]  # 최대 10000자

            full_text_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"full_{content.id}"))
            full_text_point = PointStruct(
                id=full_text_id,
                vector=full_text_embedding,
                payload={
                    'content_id': content.id,
                    'type': 'full_text',
                    'text': full_text[:10000],  # 저장 크기 제한
                    'title': content.title,
                    'url': content.url,
                    'total_segments': len(transcripts),
                    'total_duration': content.duration
                }
            )

            self.qdrant_client.upsert(
                collection_name=self.collections['full_text'],
                points=[full_text_point]
            )
            logger.info(f"  ✅ 전체 자막 저장 완료")

            # 3. Paragraph Chunks 생성 및 저장
            paragraphs = self._create_paragraphs(transcripts)
            paragraph_texts = [p['text'] for p in paragraphs]
            paragraph_embeddings = self._get_embeddings(paragraph_texts)

            paragraph_points = []
            for i, (paragraph, embedding) in enumerate(zip(paragraphs, paragraph_embeddings)):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"para_{content.id}_{i}"))
                timestamp_url = self._create_timestamp_url(content.url, paragraph['start_time'])

                paragraph_points.append(PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        'content_id': content.id,
                        'type': 'paragraph',
                        'paragraph_index': i,
                        'text': paragraph['text'],
                        'start_time': paragraph['start_time'],
                        'end_time': paragraph['end_time'],
                        'title': content.title,
                        'url': content.url,
                        'timestamp_url': timestamp_url
                    }
                ))

            # 배치로 저장
            if paragraph_points:
                for i in range(0, len(paragraph_points), 50):
                    batch = paragraph_points[i:i+50]
                    self.qdrant_client.upsert(
                        collection_name=self.collections['paragraphs'],
                        points=batch
                    )
                logger.info(f"  ✅ {len(paragraphs)}개 문단 저장 완료")

            # 4. 기존 Semantic Chunks는 이미 처리됨

            logger.info(f"✅ Content {content.id} 다층 벡터화 완료")

        except Exception as e:
            logger.error(f"Content {content.id} 처리 실패: {e}")
            raise
        finally:
            db.close()

    def _create_timestamp_url(self, original_url: str, start_time_seconds: float) -> str:
        """YouTube 타임스탬프 URL 생성"""
        if not original_url or not start_time_seconds:
            return original_url

        timestamp = int(start_time_seconds)
        separator = '&' if '?' in original_url else '?'
        return f"{original_url}{separator}t={timestamp}s"

    def process_all_transcribed_content(self):
        """모든 트랜스크립트가 있는 콘텐츠 처리"""
        db = self.SessionLocal()

        try:
            # 트랜스크립트가 있는 모든 콘텐츠 조회
            contents = db.query(Content).filter(
                Content.transcript_available == True
            ).all()

            logger.info(f"처리할 콘텐츠: {len(contents)}개")

            for content in contents:
                try:
                    self.process_content(content)
                except Exception as e:
                    logger.error(f"Content {content.id} 처리 중 오류: {e}")
                    continue

        finally:
            db.close()


if __name__ == "__main__":
    enhancer = EnhancedVectorizer()
    enhancer.process_all_transcribed_content()