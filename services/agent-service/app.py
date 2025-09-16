"""
FastAPI 기반 RAG 에이전트 서비스
OpenAI API 호환 인터페이스 제공
"""

import os
import sys
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import json
import asyncio
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import Channel, Content, get_database_url
from rag_agent import YouTubeRAGAgent


# Pydantic 모델들
class ChatMessage(BaseModel):
    role: str = Field(..., description="메시지 역할 (user, assistant, system)")
    content: str = Field(..., description="메시지 내용")


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="youtube-rag-agent", description="모델 이름")
    messages: List[ChatMessage] = Field(..., description="대화 메시지")
    stream: bool = Field(default=False, description="스트리밍 응답 여부")
    temperature: float = Field(default=0.1, ge=0, le=2, description="응답 창의성")
    max_tokens: Optional[int] = Field(default=None, description="최대 토큰 수")
    top_p: float = Field(default=1.0, ge=0, le=1, description="토큰 선택 확률")


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Dict[str, int]


class SearchRequest(BaseModel):
    query: str = Field(..., description="검색 쿼리")
    platform: Optional[str] = Field(None, description="플랫폼 필터 (youtube)")
    language: Optional[str] = Field(None, description="언어 필터")
    limit: int = Field(default=10, ge=1, le=50, description="결과 수 제한")


class SearchResult(BaseModel):
    id: str
    score: float
    content: str
    title: str
    url: str
    platform: str
    publish_date: Optional[str]
    metadata: Dict[str, Any]


class ChannelInfo(BaseModel):
    id: int
    name: str
    url: str
    platform: str
    category: Optional[str]
    description: Optional[str]
    language: str
    is_active: bool


# FastAPI 앱 생성
app = FastAPI(
    title="YouTube RAG Agent API",
    description="YouTube 콘텐츠 기반 RAG 에이전트 서비스",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 전역 변수
agent: Optional[YouTubeRAGAgent] = None
engine = None
SessionLocal = None


@app.on_event("startup")
async def startup_event():
    """앱 시작 시 초기화"""
    global agent, engine, SessionLocal

    print("RAG 에이전트 서비스 시작 중...")

    # 데이터베이스 연결
    engine = create_engine(get_database_url())
    SessionLocal = sessionmaker(bind=engine)

    # RAG 에이전트 초기화
    try:
        agent = YouTubeRAGAgent()
        print("RAG 에이전트 초기화 완료")
    except Exception as e:
        print(f"RAG 에이전트 초기화 실패: {e}")
        raise


def get_db():
    """데이터베이스 세션 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
async def root():
    """서비스 상태 확인"""
    return {
        "service": "YouTube RAG Agent",
        "status": "running",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """헬스 체크"""
    return {"status": "healthy"}


@app.get("/v1/models")
async def list_models():
    """OpenAI API 호환 모델 목록"""
    return {
        "object": "list",
        "data": [
            {
                "id": "youtube-rag-agent",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "youtube-content-agent",
                "permission": [],
                "root": "youtube-rag-agent",
                "parent": None
            }
        ]
    }


# OpenAI API 호환 엔드포인트
@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI API 호환 채팅 완료 엔드포인트"""
    if not agent:
        raise HTTPException(status_code=500, detail="RAG 에이전트가 초기화되지 않았습니다")

    try:
        # 마지막 사용자 메시지 추출
        user_messages = [msg for msg in request.messages if msg.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="사용자 메시지가 없습니다")

        query = user_messages[-1].content

        # RAG 에이전트로 답변 생성
        result = agent.ask(query)

        # OpenAI API 형식으로 응답 구성
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        created_time = int(time.time())

        choice = ChatCompletionChoice(
            index=0,
            message=ChatMessage(
                role="assistant",
                content=result["answer"]
            ),
            finish_reason="stop"
        )

        response = ChatCompletionResponse(
            id=completion_id,
            created=created_time,
            model=request.model,
            choices=[choice],
            usage={
                "prompt_tokens": len(query.split()),
                "completion_tokens": len(result["answer"].split()),
                "total_tokens": len(query.split()) + len(result["answer"].split())
            }
        )

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"답변 생성 실패: {str(e)}")


@app.post("/search")
async def search_content(request: SearchRequest):
    """콘텐츠 검색 엔드포인트"""
    if not agent:
        raise HTTPException(status_code=500, detail="RAG 에이전트가 초기화되지 않았습니다")

    try:
        # 필터 구성
        filters = {}
        if request.platform:
            filters["platform"] = request.platform
        if request.language:
            filters["language"] = request.language

        # 검색 수행
        results = agent.search_similar_content(
            query=request.query,
            filters=filters,
            limit=request.limit
        )

        # 응답 형식 변환
        search_results = [
            SearchResult(
                id=result["id"],
                score=result["score"],
                content=result["content"],
                title=result["title"],
                url=result["url"],
                platform=result["platform"],
                publish_date=result["publish_date"],
                metadata=result["metadata"]
            )
            for result in results
        ]

        return {
            "query": request.query,
            "results": search_results,
            "total": len(search_results)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 실패: {str(e)}")


@app.post("/ask")
async def ask_question(request: dict):
    """질문 답변 엔드포인트"""
    if not agent:
        raise HTTPException(status_code=500, detail="RAG 에이전트가 초기화되지 않았습니다")

    query = request.get("query") or request.get("question")
    if not query:
        raise HTTPException(status_code=400, detail="질문이 제공되지 않았습니다")

    try:
        result = agent.ask(query)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"답변 생성 실패: {str(e)}")


@app.get("/trending")
async def get_trending_topics(
    platform: Optional[str] = None,
    limit: int = 10
):
    """인기 토픽 조회"""
    if not agent:
        raise HTTPException(status_code=500, detail="RAG 에이전트가 초기화되지 않았습니다")

    try:
        topics = agent.get_trending_topics(platform=platform, limit=limit)
        return {
            "platform": platform,
            "topics": topics,
            "total": len(topics)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"토픽 조회 실패: {str(e)}")


@app.get("/channels", response_model=List[ChannelInfo])
async def get_channels(
    platform: Optional[str] = None,
    is_active: bool = True,
    db = Depends(get_db)
):
    """채널 목록 조회"""
    try:
        query = db.query(Channel)

        if platform:
            query = query.filter(Channel.platform == platform)

        if is_active is not None:
            query = query.filter(Channel.is_active == is_active)

        channels = query.all()

        return [
            ChannelInfo(
                id=channel.id,
                name=channel.name,
                url=channel.url,
                platform=channel.platform,
                category=channel.category,
                description=channel.description,
                language=channel.language,
                is_active=channel.is_active
            )
            for channel in channels
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"채널 조회 실패: {str(e)}")


@app.get("/stats")
async def get_stats(db = Depends(get_db)):
    """서비스 통계 조회"""
    try:
        total_channels = db.query(Channel).count()
        active_channels = db.query(Channel).filter(Channel.is_active == True).count()
        total_content = db.query(Content).count()
        processed_content = db.query(Content).filter(Content.vector_stored == True).count()

        platform_stats = {}
        for platform in ['youtube']:
            platform_channels = db.query(Channel).filter(Channel.platform == platform).count()
            platform_stats[platform] = platform_channels

        return {
            "channels": {
                "total": total_channels,
                "active": active_channels,
                "by_platform": platform_stats
            },
            "content": {
                "total": total_content,
                "processed": processed_content,
                "processing_rate": round(processed_content / total_content * 100, 2) if total_content > 0 else 0
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )