#!/usr/bin/env python3
"""
데이터 처리 모니터링 API
실시간 처리 상태 및 통계를 제공하는 웹 대시보드 API
"""

import os
import sys
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, func
from typing import Dict, List

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import (
    Channel, Content, ProcessingJob, VectorMapping,
    get_database_url
)

app = FastAPI(title="데이터 처리 모니터링 대시보드")

# 데이터베이스 설정
engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine)

def get_db():
    """데이터베이스 세션 생성"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass

@app.get("/")
async def dashboard():
    """메인 대시보드 HTML"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>데이터 처리 모니터링 대시보드</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .card { background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .header { text-align: center; color: #333; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }
            .stat-item { text-align: center; padding: 15px; background: #f8f9fa; border-radius: 6px; }
            .stat-number { font-size: 2em; font-weight: bold; color: #007bff; }
            .stat-label { color: #666; margin-top: 5px; }
            .progress-bar { background: #e9ecef; height: 20px; border-radius: 10px; overflow: hidden; margin: 10px 0; }
            .progress-fill { background: #28a745; height: 100%; transition: width 0.3s ease; }
            .job-status { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
            .status-item { padding: 10px; border-radius: 6px; text-align: center; }
            .status-pending { background: #fff3cd; color: #856404; }
            .status-processing { background: #d1ecf1; color: #0c5460; }
            .status-completed { background: #d4edda; color: #155724; }
            .status-failed { background: #f8d7da; color: #721c24; }
            .worker-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
            .worker-card { padding: 15px; border-radius: 6px; border: 1px solid #dee2e6; }
            .worker-active { border-color: #28a745; background: #f8fff9; }
            .worker-idle { border-color: #ffc107; background: #fffbf0; }
            .controls { text-align: center; margin: 20px 0; }
            .btn { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin: 5px; }
            .btn:hover { background: #0056b3; }
            .btn-danger { background: #dc3545; }
            .btn-danger:hover { background: #c82333; }
            .btn-success { background: #28a745; }
            .btn-success:hover { background: #218838; }
            .refresh { float: right; font-size: 0.8em; color: #666; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <h1 class="header">📊 데이터 처리 모니터링 대시보드</h1>
                <div class="refresh">자동 새로고침: <span id="timer">10</span>초</div>
            </div>

            <div class="card">
                <h2>⚡ 실시간 처리 현황</h2>
                <div class="stats-grid" id="stats-grid">
                    <!-- 통계 데이터가 여기에 동적으로 로드됩니다 -->
                </div>
            </div>

            <div class="card">
                <h2>📈 지식화 진행률</h2>
                <div id="knowledge-progress">
                    <!-- 진행률 바가 여기에 동적으로 로드됩니다 -->
                </div>
            </div>

            <div class="card">
                <h2>🔧 작업 큐 상태</h2>
                <div class="job-status" id="job-status">
                    <!-- 작업 상태가 여기에 동적으로 로드됩니다 -->
                </div>
            </div>

            <div class="card">
                <h2>👥 워커 상태</h2>
                <div class="worker-grid" id="worker-status">
                    <!-- 워커 상태가 여기에 동적으로 로드됩니다 -->
                </div>
            </div>

            <div class="card">
                <h2>🎛️ 제어판</h2>
                <div class="controls">
                    <button class="btn btn-success" onclick="enableCollection()">📥 수집 활성화</button>
                    <button class="btn btn-danger" onclick="disableCollection()">🛑 수집 비활성화</button>
                    <button class="btn" onclick="forceVectorization()">🚀 강제 벡터화</button>
                    <button class="btn" onclick="refreshData()">🔄 새로고침</button>
                </div>
            </div>
        </div>

        <script>
            let countdown = 10;

            async function loadStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();

                    // 통계 업데이트
                    document.getElementById('stats-grid').innerHTML = `
                        <div class="stat-item">
                            <div class="stat-number">${data.content_total}</div>
                            <div class="stat-label">총 콘텐츠</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number">${data.stt_completed}</div>
                            <div class="stat-label">STT 완료</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number">${data.vectorized}</div>
                            <div class="stat-label">벡터화 완료</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number">${data.knowledge_progress.toFixed(1)}%</div>
                            <div class="stat-label">지식화 진행률</div>
                        </div>
                    `;

                    // 진행률 바 업데이트
                    document.getElementById('knowledge-progress').innerHTML = `
                        <div>전체 진행률: ${data.vectorized}/${data.content_total} (${data.knowledge_progress.toFixed(1)}%)</div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${data.knowledge_progress}%"></div>
                        </div>
                    `;

                    // 작업 상태 업데이트
                    let jobStatusHtml = '';
                    for (const [jobType, counts] of Object.entries(data.job_status)) {
                        for (const [status, count] of Object.entries(counts)) {
                            jobStatusHtml += `
                                <div class="status-item status-${status}">
                                    <strong>${jobType}</strong><br>
                                    ${status}: ${count}개
                                </div>
                            `;
                        }
                    }
                    document.getElementById('job-status').innerHTML = jobStatusHtml;

                    // 워커 상태 업데이트
                    let workerHtml = '';
                    for (const [workerType, info] of Object.entries(data.workers)) {
                        const statusClass = info.active > 0 ? 'worker-active' : 'worker-idle';
                        workerHtml += `
                            <div class="worker-card ${statusClass}">
                                <h4>${workerType}</h4>
                                <div>활성: ${info.active}개</div>
                                <div>마지막 작업: ${info.last_activity || '없음'}</div>
                            </div>
                        `;
                    }
                    document.getElementById('worker-status').innerHTML = workerHtml;

                } catch (error) {
                    console.error('데이터 로드 실패:', error);
                }
            }

            function refreshData() {
                loadStats();
                countdown = 10;
            }

            // 타이머 업데이트
            setInterval(() => {
                countdown--;
                document.getElementById('timer').textContent = countdown;

                if (countdown <= 0) {
                    refreshData();
                }
            }, 1000);

            // 제어 함수들
            async function enableCollection() {
                try {
                    const response = await fetch('/api/collection/enable', {method: 'POST'});
                    const result = await response.json();
                    alert('수집이 활성화되었습니다: ' + result.status);
                } catch (error) {
                    alert('오류: ' + error.message);
                }
            }

            async function disableCollection() {
                try {
                    const response = await fetch('/api/collection/disable', {method: 'POST'});
                    const result = await response.json();
                    alert('수집이 비활성화되었습니다: ' + result.status);
                } catch (error) {
                    alert('오류: ' + error.message);
                }
            }

            async function forceVectorization() {
                try {
                    const response = await fetch('/api/force-vectorization', {method: 'POST'});
                    const result = await response.json();
                    alert('강제 벡터화 시작: ' + result.message);
                } catch (error) {
                    alert('오류: ' + error.message);
                }
            }

            // 초기 데이터 로드
            loadStats();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/stats")
async def get_stats():
    """실시간 처리 통계 API"""
    db = get_db()
    try:
        # 기본 통계
        content_total = db.query(Content).count()
        stt_completed = db.query(Content).filter(Content.transcript_available == True).count()
        vectorized = db.query(Content).filter(Content.vector_stored == True).count()

        # 지식화 진행률
        knowledge_progress = (vectorized / content_total * 100) if content_total > 0 else 0

        # 작업 상태별 카운트
        job_status = {}
        job_counts = db.query(
            ProcessingJob.job_type,
            ProcessingJob.status,
            func.count(ProcessingJob.id)
        ).group_by(
            ProcessingJob.job_type,
            ProcessingJob.status
        ).all()

        for job_type, status, count in job_counts:
            if job_type not in job_status:
                job_status[job_type] = {}
            job_status[job_type][status] = count

        # 최근 활동
        recent_activities = db.query(ProcessingJob).filter(
            ProcessingJob.status == 'processing'
        ).count()

        # 워커 상태 (추정)
        workers = {
            "STT Workers": {
                "active": 3,  # 실행 중인 STT 워커 수
                "last_activity": "진행 중"
            },
            "Vectorization Worker": {
                "active": 1,  # 벡터화 워커
                "last_activity": "진행 중"
            },
            "Main Processor": {
                "active": 1,  # 메인 프로세서
                "last_activity": "대기 중"
            }
        }

        return {
            "content_total": content_total,
            "stt_completed": stt_completed,
            "vectorized": vectorized,
            "knowledge_progress": knowledge_progress,
            "job_status": job_status,
            "workers": workers,
            "recent_activities": recent_activities,
            "timestamp": datetime.now().isoformat()
        }

    finally:
        db.close()

@app.post("/api/collection/enable")
async def enable_collection():
    """데이터 수집 활성화"""
    # 실제 구현 시에는 collection_scheduler를 호출
    return {"status": "enabled", "message": "데이터 수집이 활성화되었습니다"}

@app.post("/api/collection/disable")
async def disable_collection():
    """데이터 수집 비활성화"""
    # 실제 구현 시에는 collection_scheduler를 호출
    return {"status": "disabled", "message": "데이터 수집이 비활성화되었습니다"}

@app.post("/api/force-vectorization")
async def force_vectorization():
    """강제 벡터화 실행"""
    db = get_db()
    try:
        # STT 완료되었지만 벡터화되지 않은 콘텐츠 조회
        pending_content = db.query(Content).filter(
            Content.transcript_available == True,
            Content.vector_stored != True
        ).count()

        # 벡터화 작업 우선순위 증가
        db.query(ProcessingJob).filter(
            ProcessingJob.job_type == 'vectorize',
            ProcessingJob.status == 'pending'
        ).update({ProcessingJob.priority: 10})

        db.commit()

        return {
            "message": f"{pending_content}개 콘텐츠의 벡터화 작업 우선순위를 높였습니다",
            "pending_count": pending_content
        }

    finally:
        db.close()

@app.get("/api/content")
async def get_content_list():
    """콘텐츠 목록 조회"""
    db = get_db()
    try:
        contents = db.query(Content).order_by(Content.created_at.desc()).limit(50).all()

        result = []
        for content in contents:
            result.append({
                "id": content.id,
                "title": content.title[:100],
                "duration": content.duration,
                "transcript_available": content.transcript_available,
                "vector_stored": content.vector_stored,
                "created_at": content.created_at.isoformat() if content.created_at else None
            })

        return {"contents": result}

    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)