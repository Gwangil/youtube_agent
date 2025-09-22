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


class ChannelCreateRequest(BaseModel):
    name: str = Field(..., description="채널 이름")
    url: str = Field(..., description="채널 URL")
    platform: str = Field(default="youtube", description="플랫폼 (현재 youtube만 지원)")
    category: Optional[str] = Field(None, description="카테고리")
    description: Optional[str] = Field(None, description="설명")
    language: str = Field(default="ko", description="언어")


class ChannelUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="채널 이름")
    category: Optional[str] = Field(None, description="카테고리")
    description: Optional[str] = Field(None, description="설명")
    language: Optional[str] = Field(None, description="언어")
    is_active: Optional[bool] = Field(None, description="활성 상태")


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
    is_active: Optional[bool] = None,  # Changed: None means all channels
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
        # 채널 통계
        total_channels = db.query(Channel).count()
        active_channels = db.query(Channel).filter(Channel.is_active == True).count()

        # 콘텐츠 통계
        total_content = db.query(Content).count()
        transcript_available = db.query(Content).filter(Content.transcript_available == True).count()

        # Qdrant 벡터 통계
        try:
            from qdrant_client import QdrantClient
            qdrant_client = QdrantClient(url=os.getenv('QDRANT_URL', 'http://qdrant:6333'))
            collection_info = qdrant_client.get_collection('youtube_content')
            vector_count = collection_info.points_count
        except:
            vector_count = 0

        platform_stats = {}
        for platform in ['youtube']:
            platform_channels = db.query(Channel).filter(Channel.platform == platform).count()
            platform_stats[platform] = platform_channels

        # 지식화 진행률
        knowledge_progress = (transcript_available / total_content * 100) if total_content > 0 else 0

        return {
            "channels": {
                "total": total_channels,
                "active": active_channels,
                "by_platform": platform_stats
            },
            "content": {
                "total": total_content,
                "transcript_available": transcript_available,
                "vectors_in_qdrant": vector_count,
                "knowledge_progress": f"{knowledge_progress:.1f}%"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")


@app.post("/api/channels", response_model=ChannelInfo)
async def create_channel(
    request: ChannelCreateRequest,
    db = Depends(get_db)
):
    """새 채널 추가"""
    try:
        # URL 중복 확인
        existing_channel = db.query(Channel).filter(Channel.url == request.url).first()
        if existing_channel:
            raise HTTPException(status_code=400, detail="이미 등록된 채널 URL입니다")

        # 새 채널 생성
        new_channel = Channel(
            name=request.name,
            url=request.url,
            platform=request.platform,
            category=request.category,
            description=request.description,
            language=request.language,
            is_active=True
        )

        db.add(new_channel)
        db.commit()
        db.refresh(new_channel)

        return ChannelInfo(
            id=new_channel.id,
            name=new_channel.name,
            url=new_channel.url,
            platform=new_channel.platform,
            category=new_channel.category,
            description=new_channel.description,
            language=new_channel.language,
            is_active=new_channel.is_active
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"채널 추가 실패: {str(e)}")


@app.put("/api/channels/{channel_id}", response_model=ChannelInfo)
async def update_channel(
    channel_id: int,
    request: ChannelUpdateRequest,
    db = Depends(get_db)
):
    """채널 정보 수정"""
    try:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

        # 제공된 필드만 업데이트
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(channel, field, value)

        db.commit()
        db.refresh(channel)

        return ChannelInfo(
            id=channel.id,
            name=channel.name,
            url=channel.url,
            platform=channel.platform,
            category=channel.category,
            description=channel.description,
            language=channel.language,
            is_active=channel.is_active
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"채널 수정 실패: {str(e)}")


@app.delete("/api/channels/{channel_id}")
async def delete_channel(
    channel_id: int,
    db = Depends(get_db)
):
    """채널 삭제 (소프트 삭제 - 비활성화)"""
    try:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

        # 소프트 삭제 (비활성화)
        channel.is_active = False
        db.commit()

        return {"message": f"채널 '{channel.name}'이 비활성화되었습니다", "channel_id": channel_id}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"채널 삭제 실패: {str(e)}")


@app.post("/api/channels/{channel_id}/activate")
async def activate_channel(
    channel_id: int,
    db = Depends(get_db)
):
    """채널 활성화"""
    try:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

        channel.is_active = True
        db.commit()

        return {"message": f"채널 '{channel.name}'이 활성화되었습니다", "channel_id": channel_id}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"채널 활성화 실패: {str(e)}")


# ===================== 콘텐츠 관리 API =====================

@app.get("/api/contents")
async def get_contents(
    channel_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db = Depends(get_db)
):
    """콘텐츠 목록 조회"""
    try:
        query = db.query(Content, Channel).join(Channel, Content.channel_id == Channel.id)

        if channel_id:
            query = query.filter(Content.channel_id == channel_id)
        if is_active is not None:
            query = query.filter(Content.is_active == is_active)

        # 정렬 처리
        if sort_by == "channel_name":
            sort_column = Channel.name
        elif sort_by == "title":
            sort_column = Content.title
        elif sort_by == "duration":
            sort_column = Content.duration
        elif sort_by == "created_at":
            sort_column = Content.created_at
        else:
            sort_column = Content.created_at

        if sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        total = query.count()
        offset = (page - 1) * page_size
        contents = query.offset(offset).limit(page_size).all()

        result = []
        for content, channel in contents:
            result.append({
                "id": content.id,
                "title": content.title,
                "url": content.url,
                "duration": content.duration,
                "channel_id": content.channel_id,
                "channel_name": channel.name,
                "transcript_available": content.transcript_available,
                "vector_stored": content.vector_stored,
                "is_active": content.is_active if hasattr(content, 'is_active') else True,
                "created_at": content.created_at.isoformat() if content.created_at else None
            })

        return {
            "contents": result,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
            "page": page
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/contents/{content_id}/toggle")
async def toggle_content_status(
    content_id: int,
    db = Depends(get_db)
):
    """콘텐츠 활성/비활성 토글"""
    try:
        content = db.query(Content).filter(Content.id == content_id).first()
        if not content:
            raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다")

        # 토글
        content.is_active = not content.is_active

        # 비활성화 시 벡터 DB에서 제거
        if not content.is_active:
            from qdrant_client import QdrantClient
            qdrant_client = QdrantClient(url=os.getenv('QDRANT_URL', 'http://qdrant:6333'))

            # 해당 콘텐츠의 벡터 삭제
            for collection in ['youtube_content', 'youtube_summaries', 'youtube_paragraphs']:
                try:
                    qdrant_client.delete(
                        collection_name=collection,
                        points_selector={
                            "filter": {
                                "must": [
                                    {"key": "content_id", "match": {"value": content_id}}
                                ]
                            }
                        }
                    )
                except:
                    pass  # 컬렉션이 없으면 무시

        # 재활성화 시 재처리 큐에 추가
        elif content.is_active and content.vector_stored:
            # 이미 처리된 데이터가 있으면 벡터만 재생성
            from shared.models.database import ProcessingJob
            job = ProcessingJob(
                content_id=content_id,
                job_type='vectorize',
                status='pending',
                priority=5
            )
            db.add(job)

        db.commit()

        return {"message": f"콘텐츠가 {'활성화' if content.is_active else '비활성화'}되었습니다"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/contents/bulk-toggle")
async def bulk_toggle_contents(
    request: dict,
    db = Depends(get_db)
):
    """여러 콘텐츠 일괄 활성/비활성"""
    try:
        content_ids = request.get("content_ids", [])
        is_active = request.get("is_active", True)

        # 업데이트
        db.query(Content).filter(Content.id.in_(content_ids)).update(
            {"is_active": is_active},
            synchronize_session=False
        )

        # 벡터 DB 동기화
        if not is_active:
            # 비활성화 시 벡터 삭제
            from qdrant_client import QdrantClient
            qdrant_client = QdrantClient(url=os.getenv('QDRANT_URL', 'http://qdrant:6333'))

            for content_id in content_ids:
                for collection in ['youtube_content', 'youtube_summaries', 'youtube_paragraphs']:
                    try:
                        qdrant_client.delete(
                            collection_name=collection,
                            points_selector={
                                "filter": {
                                    "must": [
                                        {"key": "content_id", "match": {"value": content_id}}
                                    ]
                                }
                            }
                        )
                    except:
                        pass

        db.commit()

        return {"message": f"{len(content_ids)}개 콘텐츠가 {'활성화' if is_active else '비활성화'}되었습니다"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/contents/{content_id}/reprocess")
async def reprocess_content(
    content_id: int,
    db = Depends(get_db)
):
    """콘텐츠 재처리"""
    try:
        content = db.query(Content).filter(Content.id == content_id).first()
        if not content:
            raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다")

        # 기존 데이터 삭제
        from shared.models.database import ProcessingJob, Transcript, VectorMapping

        # 트랜스크립트와 벡터 매핑 삭제
        db.query(Transcript).filter(Transcript.content_id == content_id).delete()
        db.query(VectorMapping).filter(VectorMapping.content_id == content_id).delete()

        # 콘텐츠 상태 리셋
        content.transcript_available = False
        content.vector_stored = False
        content.is_active = True

        # 처리 작업 추가
        db.query(ProcessingJob).filter(ProcessingJob.content_id == content_id).delete()

        jobs = [
            ProcessingJob(
                content_id=content_id,
                job_type='extract_transcript',
                status='pending',
                priority=5
            ),
            ProcessingJob(
                content_id=content_id,
                job_type='process_audio',
                status='pending',
                priority=5
            )
        ]

        for job in jobs:
            db.add(job)

        db.commit()

        return {"message": "콘텐츠가 재처리 큐에 추가되었습니다"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )