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
    return templates.TemplateResponse("api_docs.html", {
        "request": request,
        "api_url": AGENT_API_URL
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090, reload=True)