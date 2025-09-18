#!/usr/bin/env python3
"""
임베딩 서빙 서버
Whisper 서버처럼 중앙집중식 임베딩 처리
OpenAI API 또는 BGE-M3 모델을 사용하여 1024차원 임베딩 제공
"""

import os
import sys
import time
import torch
import hashlib
import logging
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import uvicorn

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.utils.embeddings import HybridEmbeddings

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 전역 임베딩 모델 인스턴스
embedding_model = None
model_info = {}


class EmbeddingRequest(BaseModel):
    """임베딩 요청 모델"""
    texts: List[str]
    batch_size: Optional[int] = 32


class EmbeddingResponse(BaseModel):
    """임베딩 응답 모델"""
    embeddings: List[List[float]]
    dimension: int
    model_info: dict
    processing_time: float


class SingleEmbeddingRequest(BaseModel):
    """단일 텍스트 임베딩 요청"""
    text: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 실행되는 라이프사이클 관리"""
    global embedding_model, model_info

    # 시작 시 모델 로드
    logger.info("🚀 임베딩 서버 초기화 중...")

    try:
        # HybridEmbeddings 초기화 (OpenAI API 우선, BGE-M3 폴백)
        embedding_model = HybridEmbeddings(prefer_local=False)  # API 우선
        model_info = embedding_model.get_model_info()

        logger.info(f"✅ 임베딩 모델 로드 완료")
        logger.info(f"  📊 모델: {model_info['model_name']}")
        logger.info(f"  🎯 타입: {model_info['model_type']}")
        logger.info(f"  📐 차원: {model_info.get('dimension', 1024)}")
        logger.info(f"  💻 디바이스: {model_info['device']}")

        # 테스트 임베딩 생성
        test_texts = ["테스트 문장입니다."]
        test_embeddings = embedding_model.embed_documents(test_texts)
        actual_dim = len(test_embeddings[0])
        model_info['actual_dimension'] = actual_dim
        logger.info(f"  ✅ 실제 임베딩 차원 확인: {actual_dim}")

    except Exception as e:
        logger.error(f"❌ 임베딩 모델 로드 실패: {e}")
        raise

    yield  # 서버 실행

    # 종료 시 정리
    logger.info("🛑 임베딩 서버 종료")


# FastAPI 앱 생성
app = FastAPI(
    title="Embedding Server",
    description="중앙집중식 임베딩 처리 서버",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """서버 상태 확인"""
    return {
        "service": "Embedding Server",
        "status": "running",
        "model_info": model_info
    }


@app.get("/health")
async def health():
    """헬스체크 엔드포인트"""
    if embedding_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    return {
        "status": "healthy",
        "model": model_info.get('model_name', 'unknown'),
        "type": model_info.get('model_type', 'unknown'),
        "dimension": model_info.get('actual_dimension', model_info.get('dimension', 1024)),
        "device": model_info.get('device', 'unknown')
    }


@app.post("/embed", response_model=EmbeddingResponse)
async def embed_texts(request: EmbeddingRequest):
    """여러 텍스트를 임베딩하는 엔드포인트"""
    if embedding_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")

    try:
        start_time = time.time()

        # 임베딩 생성
        logger.info(f"📝 {len(request.texts)}개 텍스트 임베딩 요청")
        embeddings = embedding_model.embed_documents(request.texts)

        processing_time = time.time() - start_time

        # 실제 차원 확인
        actual_dim = len(embeddings[0]) if embeddings else 0

        logger.info(f"✅ 임베딩 완료: {len(embeddings)}개, {actual_dim}차원, {processing_time:.2f}초")

        return EmbeddingResponse(
            embeddings=embeddings,
            dimension=actual_dim,
            model_info={
                "model_name": model_info.get('model_name'),
                "model_type": model_info.get('model_type'),
                "processing_time": processing_time
            },
            processing_time=processing_time
        )

    except Exception as e:
        logger.error(f"임베딩 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Embedding failed: {str(e)}")


@app.post("/embed_query")
async def embed_query(request: SingleEmbeddingRequest):
    """단일 쿼리 텍스트를 임베딩하는 엔드포인트"""
    if embedding_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not request.text:
        raise HTTPException(status_code=400, detail="No text provided")

    try:
        start_time = time.time()

        # 임베딩 생성
        embedding = embedding_model.embed_query(request.text)

        processing_time = time.time() - start_time

        return {
            "embedding": embedding,
            "dimension": len(embedding),
            "processing_time": processing_time
        }

    except Exception as e:
        logger.error(f"쿼리 임베딩 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Query embedding failed: {str(e)}")


@app.get("/model_info")
async def get_model_info():
    """현재 로드된 모델 정보 반환"""
    if embedding_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    return {
        **model_info,
        "actual_dimension": model_info.get('actual_dimension', 1024)
    }


@app.post("/benchmark")
async def benchmark():
    """임베딩 성능 벤치마크"""
    if embedding_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        test_texts = [
            "이것은 테스트 문장입니다.",
            "The quick brown fox jumps over the lazy dog.",
            "한국어와 영어를 모두 포함한 문장입니다.",
            "임베딩 서버의 성능을 테스트하고 있습니다.",
            "벤치마크 결과는 처리 시간과 차원을 포함합니다."
        ] * 10  # 50개 문장

        start_time = time.time()
        embeddings = embedding_model.embed_documents(test_texts)
        processing_time = time.time() - start_time

        return {
            "num_texts": len(test_texts),
            "total_time": processing_time,
            "avg_time_per_text": processing_time / len(test_texts),
            "texts_per_second": len(test_texts) / processing_time,
            "embedding_dimension": len(embeddings[0]) if embeddings else 0,
            "model_info": model_info
        }

    except Exception as e:
        logger.error(f"벤치마크 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Benchmark failed: {str(e)}")


def main():
    """메인 실행 함수"""
    port = int(os.getenv('EMBEDDING_SERVER_PORT', '8083'))
    host = os.getenv('EMBEDDING_SERVER_HOST', '0.0.0.0')

    logger.info(f"🚀 임베딩 서버 시작: {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()