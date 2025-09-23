"""
Admin Dashboard for YouTube Content Agent
채널 관리 및 시스템 모니터링 웹 인터페이스
"""

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
import json
from datetime import datetime
from typing import Optional
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# 데이터베이스 설정
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://youtube_user:youtube_pass@postgres:5432/youtube_agent")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def get_db():
    """데이터베이스 세션 생성"""
    db = SessionLocal()
    try:
        return db
    except:
        db.close()
        raise

# 간단한 모델 정의 (필요한 것만)
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func

class Content(Base):
    __tablename__ = "content"

    id = Column(Integer, primary_key=True)
    title = Column(String)
    transcript_available = Column(Boolean, default=False)
    vector_stored = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer)
    job_type = Column(String)
    status = Column(String)
    created_at = Column(DateTime, server_default=func.now())

class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer)

class VectorMapping(Base):
    __tablename__ = "vector_mappings"

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer)

app = FastAPI(
    title="YouTube Agent Admin Dashboard",
    description="관리자 대시보드",
    version="1.0.0"
)

# 템플릿 설정
templates = Jinja2Templates(directory="templates")

# API 서비스 URL
AGENT_API_URL = os.getenv("AGENT_API_URL", "http://agent-service:8000")
MONITORING_URL = os.getenv("MONITORING_URL", "http://localhost:8081")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """메인 대시보드"""
    try:
        # 통계 정보 가져오기
        async with httpx.AsyncClient() as client:
            stats_response = await client.get(f"{AGENT_API_URL}/stats")
            stats = stats_response.json()
    except:
        stats = {"error": "통계를 불러올 수 없습니다"}

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


@app.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request):
    """채널 관리 페이지"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AGENT_API_URL}/channels")
            channels = response.json()
    except:
        channels = []

    return templates.TemplateResponse("channels.html", {
        "request": request,
        "channels": channels
    })


@app.post("/channels/add")
async def add_channel(
    name: str = Form(...),
    url: str = Form(...),
    platform: str = Form(default="youtube"),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    language: str = Form(default="ko")
):
    """채널 추가"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_API_URL}/api/channels",
                json={
                    "name": name,
                    "url": url,
                    "platform": platform,
                    "category": category,
                    "description": description,
                    "language": language
                }
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url="/channels", status_code=303)


@app.post("/channels/{channel_id}/toggle")
async def toggle_channel(channel_id: int):
    """채널 활성/비활성 토글"""
    try:
        async with httpx.AsyncClient() as client:
            # 먼저 채널 정보 가져오기
            response = await client.get(f"{AGENT_API_URL}/channels")
            channels = response.json()
            channel = next((c for c in channels if c["id"] == channel_id), None)

            if not channel:
                raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")

            # 활성 상태 토글
            if channel["is_active"]:
                response = await client.delete(f"{AGENT_API_URL}/api/channels/{channel_id}")
            else:
                response = await client.post(f"{AGENT_API_URL}/api/channels/{channel_id}/activate")

            if response.status_code not in [200, 204]:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url="/channels", status_code=303)


@app.post("/channels/{channel_id}/delete")
async def delete_channel(channel_id: int):
    """채널 삭제"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{AGENT_API_URL}/api/channels/{channel_id}")
            if response.status_code not in [200, 204]:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url="/channels", status_code=303)


@app.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(request: Request):
    """모니터링 페이지"""
    return templates.TemplateResponse("monitoring.html", {
        "request": request,
        "monitoring_url": MONITORING_URL
    })


@app.get("/api-docs", response_class=HTMLResponse)
async def api_docs_page(request: Request):
    """API 문서 페이지"""
    # 브라우저에서 접근 가능한 URL 사용
    browser_api_url = "http://localhost:8000"
    return templates.TemplateResponse("api_docs.html", {
        "request": request,
        "api_url": browser_api_url
    })


@app.get("/contents", response_class=HTMLResponse)
async def contents_page(
    request: Request,
    channel_id: Optional[int] = None,
    status: str = "all",
    page: int = 1,
    sort_by: str = "created_at",
    sort_order: str = "desc"
):
    """콘텐츠 관리 페이지"""
    try:
        # 채널 목록 가져오기
        async with httpx.AsyncClient() as client:
            channels_response = await client.get(f"{AGENT_API_URL}/channels")
            channels = channels_response.json()

            # 콘텐츠 가져오기
            params = {
                "page": page,
                "page_size": 50,
                "sort_by": sort_by,
                "sort_order": sort_order
            }
            if channel_id:
                params["channel_id"] = channel_id
            if status != "all":
                params["is_active"] = status == "active"

            contents_response = await client.get(f"{AGENT_API_URL}/api/contents", params=params)
            contents_data = contents_response.json()

    except httpx.RequestError as e:
        contents_data = {"contents": [], "total": 0, "pages": 1}
        channels = []

    contents = contents_data.get("contents", [])
    active_count = sum(1 for c in contents if c.get("is_active", True))
    inactive_count = len(contents) - active_count

    return templates.TemplateResponse("contents.html", {
        "request": request,
        "channels": channels,
        "contents": contents,
        "selected_channel_id": channel_id,
        "status_filter": status,
        "current_page": page,
        "total_pages": contents_data.get("pages", 1),
        "active_count": active_count,
        "inactive_count": inactive_count,
        "sort_by": sort_by,
        "sort_order": sort_order
    })


@app.post("/contents/{content_id}/toggle")
async def toggle_content(content_id: int):
    """콘텐츠 활성/비활성 토글"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{AGENT_API_URL}/api/contents/{content_id}/toggle")
            if response.status_code not in [200, 204]:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url="/contents", status_code=303)


@app.post("/contents/bulk-toggle")
async def bulk_toggle_contents(
    content_ids: list[int] = Form(...),
    is_active: bool = Form(...)
):
    """여러 콘텐츠 일괄 활성/비활성"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_API_URL}/api/contents/bulk-toggle",
                json={"content_ids": content_ids, "is_active": is_active}
            )
            if response.status_code not in [200, 204]:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok", "count": len(content_ids)}


@app.post("/contents/{content_id}/reprocess")
async def reprocess_content(content_id: int):
    """콘텐츠 재처리"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{AGENT_API_URL}/api/contents/{content_id}/reprocess")
            if response.status_code not in [200, 204]:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok"}


# =================== 데이터 품질 관리 ===================
@app.get("/data-quality")
async def data_quality_page():
    """데이터 품질 관리 페이지"""
    return templates.TemplateResponse("data_quality.html", {"request": {}})


@app.get("/api/data-quality/status")
async def get_quality_status():
    """데이터 품질 상태 조회"""
    db = get_db()
    try:
        # 전체 통계
        total_content = db.query(Content).count()

        # 정상 데이터 (transcript와 vector 모두 있음)
        healthy_data = db.query(Content).filter(
            Content.transcript_available == True,
            Content.vector_stored == True
        ).count()

        # 불일치 데이터
        mismatch_transcript = db.execute(text("""
            SELECT COUNT(*) FROM content c
            WHERE c.transcript_available = TRUE
            AND NOT EXISTS (SELECT 1 FROM transcripts t WHERE t.content_id = c.id)
        """)).scalar()

        mismatch_vector = db.execute(text("""
            SELECT COUNT(*) FROM content c
            WHERE c.vector_stored = TRUE
            AND NOT EXISTS (SELECT 1 FROM vector_mappings v WHERE v.content_id = c.id)
        """)).scalar()

        # 고아 데이터
        orphan_transcripts = db.execute(text("""
            SELECT COUNT(*) FROM transcripts t
            WHERE NOT EXISTS (SELECT 1 FROM content c WHERE c.id = t.content_id)
        """)).scalar()

        orphan_vectors = db.execute(text("""
            SELECT COUNT(*) FROM vector_mappings v
            WHERE NOT EXISTS (SELECT 1 FROM content c WHERE c.id = v.content_id)
        """)).scalar()

        # 문제 목록
        issues = []
        recommendations = []

        if mismatch_transcript > 0:
            issues.append({
                "type": "플래그 불일치",
                "description": "transcript_available=True이지만 실제 트랜스크립트 없음",
                "count": mismatch_transcript
            })
            recommendations.append("플래그 자동 수정을 실행하세요")

        if mismatch_vector > 0:
            issues.append({
                "type": "벡터 불일치",
                "description": "vector_stored=True이지만 실제 벡터 없음",
                "count": mismatch_vector
            })
            recommendations.append("벡터 플래그를 수정하거나 재벡터화하세요")

        if orphan_transcripts > 0 or orphan_vectors > 0:
            issues.append({
                "type": "고아 데이터",
                "description": "콘텐츠가 삭제되었지만 관련 데이터 남음",
                "count": orphan_transcripts + orphan_vectors
            })
            recommendations.append("고아 데이터 정리를 실행하세요")

        # 처리 통계
        stats = {
            "transcript_total": total_content,
            "transcript_completed": db.query(Content).filter(Content.transcript_available == True).count(),
            "transcript_pending": db.query(ProcessingJob).filter(
                ProcessingJob.job_type == "extract_transcript",
                ProcessingJob.status == "pending"
            ).count(),
            "transcript_failed": db.query(ProcessingJob).filter(
                ProcessingJob.job_type == "extract_transcript",
                ProcessingJob.status == "failed"
            ).count(),
            "vector_total": total_content,
            "vector_completed": db.query(Content).filter(Content.vector_stored == True).count(),
            "vector_pending": db.query(ProcessingJob).filter(
                ProcessingJob.job_type == "vectorize",
                ProcessingJob.status == "pending"
            ).count(),
            "vector_failed": db.query(ProcessingJob).filter(
                ProcessingJob.job_type == "vectorize",
                ProcessingJob.status == "failed"
            ).count()
        }

        # 진행률 계산
        if stats["transcript_total"] > 0:
            stats["transcript_progress"] = round((stats["transcript_completed"] / stats["transcript_total"]) * 100, 1)
        else:
            stats["transcript_progress"] = 0

        if stats["vector_total"] > 0:
            stats["vector_progress"] = round((stats["vector_completed"] / stats["vector_total"]) * 100, 1)
        else:
            stats["vector_progress"] = 0

        return {
            "total_content": total_content,
            "healthy_data": healthy_data,
            "mismatch_data": mismatch_transcript + mismatch_vector,
            "orphan_data": orphan_transcripts + orphan_vectors,
            "issues": issues,
            "recommendations": recommendations,
            "stats": stats
        }

    finally:
        db.close()


@app.post("/api/data-quality/check")
async def run_quality_check():
    """정합성 체크 실행"""
    db = get_db()
    try:
        checked = 0
        issues_found = 0
        auto_fixed = 0

        # 모든 콘텐츠 체크
        contents = db.query(Content).all()
        checked = len(contents)

        for content in contents:
            # transcript 체크
            has_transcript = db.query(Transcript).filter(Transcript.content_id == content.id).count() > 0
            if content.transcript_available != has_transcript:
                issues_found += 1
                content.transcript_available = has_transcript
                auto_fixed += 1

            # vector 체크
            has_vector = db.query(VectorMapping).filter(VectorMapping.content_id == content.id).count() > 0
            if content.vector_stored != has_vector:
                issues_found += 1
                content.vector_stored = has_vector
                auto_fixed += 1

        db.commit()

        return {
            "checked": checked,
            "issues_found": issues_found,
            "auto_fixed": auto_fixed
        }

    finally:
        db.close()


@app.post("/api/data-quality/fix-flags")
async def fix_flags():
    """플래그 불일치 수정"""
    db = get_db()
    try:
        # transcript_available 수정
        result1 = db.execute(text("""
            UPDATE content c
            SET transcript_available = FALSE
            WHERE transcript_available = TRUE
            AND NOT EXISTS (SELECT 1 FROM transcripts t WHERE t.content_id = c.id)
        """))

        result2 = db.execute(text("""
            UPDATE content c
            SET transcript_available = TRUE
            WHERE transcript_available = FALSE
            AND EXISTS (SELECT 1 FROM transcripts t WHERE t.content_id = c.id)
        """))

        # vector_stored 수정
        result3 = db.execute(text("""
            UPDATE content c
            SET vector_stored = FALSE
            WHERE vector_stored = TRUE
            AND NOT EXISTS (SELECT 1 FROM vector_mappings v WHERE v.content_id = c.id)
        """))

        result4 = db.execute(text("""
            UPDATE content c
            SET vector_stored = TRUE
            WHERE vector_stored = FALSE
            AND EXISTS (SELECT 1 FROM vector_mappings v WHERE v.content_id = c.id)
        """))

        db.commit()

        total_fixed = result1.rowcount + result2.rowcount + result3.rowcount + result4.rowcount

        return {
            "success": True,
            "message": f"{total_fixed}개 플래그 수정 완료"
        }

    finally:
        db.close()


@app.post("/api/data-quality/restart-stuck")
async def restart_stuck_jobs():
    """멈춘 작업 재시작"""
    db = get_db()
    try:
        result = db.execute(text("""
            UPDATE processing_jobs
            SET status = 'pending', updated_at = NOW()
            WHERE status = 'processing'
            AND created_at < NOW() - INTERVAL '30 minutes'
        """))

        db.commit()

        return {
            "success": True,
            "message": f"{result.rowcount}개 작업 재시작"
        }

    finally:
        db.close()


@app.post("/api/data-quality/clean-orphans")
async def clean_orphan_data():
    """고아 데이터 정리"""
    db = get_db()
    try:
        # 고아 트랜스크립트 정리
        result1 = db.execute(text("""
            DELETE FROM transcripts t
            WHERE NOT EXISTS (SELECT 1 FROM content c WHERE c.id = t.content_id)
        """))

        # 고아 벡터 매핑 정리
        result2 = db.execute(text("""
            DELETE FROM vector_mappings v
            WHERE NOT EXISTS (SELECT 1 FROM content c WHERE c.id = v.content_id)
        """))

        db.commit()

        total_cleaned = result1.rowcount + result2.rowcount

        return {
            "success": True,
            "message": f"{total_cleaned}개 고아 데이터 정리 완료"
        }

    finally:
        db.close()


@app.post("/api/data-quality/full-fix")
async def run_full_fix():
    """전체 자동 수정"""
    # 모든 수정 작업 실행
    results = []

    # 1. 플래그 수정
    flag_result = await fix_flags()
    results.append(f"플래그: {flag_result['message']}")

    # 2. 멈춘 작업 재시작
    stuck_result = await restart_stuck_jobs()
    results.append(f"작업: {stuck_result['message']}")

    # 3. 고아 데이터 정리
    orphan_result = await clean_orphan_data()
    results.append(f"정리: {orphan_result['message']}")

    return {
        "success": True,
        "message": " | ".join(results)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090, reload=True)