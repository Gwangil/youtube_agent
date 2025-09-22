#!/usr/bin/env python3
"""
임베딩 서버 래퍼
환경변수에 따라 BGE-M3 또는 OpenAI Embeddings 사용
"""

import os
import sys

# 환경변수 확인
USE_OPENAI_EMBEDDINGS = os.getenv('USE_OPENAI_EMBEDDINGS', 'false').lower() == 'true'
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'BGE-M3')

if USE_OPENAI_EMBEDDINGS or EMBEDDING_MODEL == 'OPENAI':
    print("☁️ OpenAI Embeddings 모드로 실행")
    # OpenAI 임베딩을 사용하는 간단한 프록시 서버
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    from typing import List
    import uvicorn
    from openai import OpenAI

    app = FastAPI(title="OpenAI Embedding Server")
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    class EmbeddingRequest(BaseModel):
        texts: List[str]
        model: str = "text-embedding-3-small"

    class EmbeddingResponse(BaseModel):
        embeddings: List[List[float]]
        model: str
        dimension: int

    @app.get("/")
    async def root():
        return {
            "service": "OpenAI Embedding Server",
            "model": "text-embedding-3-small",
            "dimension": 1536
        }

    @app.get("/health")
    async def health():
        return {"status": "healthy", "model": "openai"}

    @app.post("/embed")
    async def embed(request: EmbeddingRequest):
        try:
            # OpenAI API 호출
            response = client.embeddings.create(
                input=request.texts,
                model=request.model
            )

            embeddings = [item.embedding for item in response.data]

            return EmbeddingResponse(
                embeddings=embeddings,
                model=request.model,
                dimension=len(embeddings[0]) if embeddings else 0
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    if __name__ == "__main__":
        port = int(os.getenv('EMBEDDING_SERVER_PORT', '8083'))
        print(f"🚀 OpenAI Embedding Server 시작 (포트: {port})")
        uvicorn.run(app, host="0.0.0.0", port=port)

else:
    print("🎮 BGE-M3 GPU 모드로 실행")
    # 기존 embedding_server.py 실행
    exec(open('/app/services/data-processor/embedding_server.py').read())