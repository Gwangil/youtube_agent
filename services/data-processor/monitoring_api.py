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
    Channel, Content, ProcessingJob, VectorMapping, Transcript,
    get_database_url
)
from qdrant_client import QdrantClient
import requests

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

            /* 콘텐츠 목록 스타일 추가 */
            .content-table { width: 100%; border-collapse: collapse; }
            .content-table th { background: #007bff; color: white; padding: 10px; text-align: left; cursor: pointer; position: relative; }
            .content-table th:hover { background: #0056b3; }
            .content-table th.sortable::after { content: ' ⇅'; opacity: 0.5; }
            .content-table th.sorted-asc::after { content: ' ↑'; opacity: 1; }
            .content-table th.sorted-desc::after { content: ' ↓'; opacity: 1; }
            .content-table td { padding: 8px; border-bottom: 1px solid #dee2e6; }
            .content-table tr:hover { background: #f8f9fa; }
            .stage-completed { color: #28a745; font-weight: bold; }
            .stage-processing { color: #007bff; font-weight: bold; }
            .stage-waiting { color: #ffc107; }
            .stage-failed { color: #dc3545; font-weight: bold; }
            .content-stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 20px; }
            .content-stat-item { text-align: center; padding: 10px; background: #f8f9fa; border-radius: 6px; }
            .content-stat-number { font-size: 1.5em; font-weight: bold; }
            .content-stat-label { font-size: 0.9em; color: #666; }

            /* 페이징 스타일 */
            .pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin: 20px 0; }
            .pagination button { padding: 8px 12px; border: 1px solid #007bff; background: white; color: #007bff; border-radius: 4px; cursor: pointer; }
            .pagination button:hover:not(:disabled) { background: #007bff; color: white; }
            .pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
            .pagination .page-info { padding: 8px 12px; background: #f8f9fa; border-radius: 4px; }
            .page-size-selector { margin-left: 10px; padding: 5px; border-radius: 4px; border: 1px solid #dee2e6; }
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
                <h2>📚 콘텐츠 목록</h2>
                <div class="content-stats" id="content-stats">
                    <!-- 콘텐츠 통계가 여기에 동적으로 로드됩니다 -->
                </div>
                <div style="margin-bottom: 10px;">
                    <label>페이지당 항목:
                        <select id="page-size" class="page-size-selector" onchange="changePageSize()">
                            <option value="10">10개</option>
                            <option value="20" selected>20개</option>
                            <option value="50">50개</option>
                            <option value="100">100개</option>
                        </select>
                    </label>
                </div>
                <div style="overflow-x: auto;">
                    <table class="content-table">
                        <thead>
                            <tr>
                                <th class="sortable" data-column="channel" onclick="sortTable('channel')">채널</th>
                                <th class="sortable" data-column="title" onclick="sortTable('title')">제목</th>
                                <th class="sortable" data-column="created_at" onclick="sortTable('created_at')">업로드 일자</th>
                                <th>처리 단계</th>
                                <th>트랜스크립트</th>
                                <th>벡터</th>
                                <th class="sortable" data-column="duration" onclick="sortTable('duration')">길이(분)</th>
                            </tr>
                        </thead>
                        <tbody id="content-list">
                            <!-- 콘텐츠 목록이 여기에 동적으로 로드됩니다 -->
                        </tbody>
                    </table>
                </div>
                <div class="pagination" id="pagination">
                    <!-- 페이징 컨트롤이 여기에 동적으로 로드됩니다 -->
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
            let currentPage = 1;
            let pageSize = 20;
            let sortBy = 'created_at';
            let sortOrder = 'desc';

            async function loadContent(resetTimer = false) {
                try {
                    const params = new URLSearchParams({
                        page: currentPage,
                        page_size: pageSize,
                        sort_by: sortBy,
                        sort_order: sortOrder
                    });
                    const response = await fetch(`/api/content?${params}`);
                    const data = await response.json();

                    // 콘텐츠 통계 업데이트
                    const stats = data.statistics;
                    document.getElementById('content-stats').innerHTML = `
                        <div class="content-stat-item">
                            <div class="content-stat-number">${stats.total}</div>
                            <div class="content-stat-label">총 콘텐츠</div>
                        </div>
                        <div class="content-stat-item">
                            <div class="content-stat-number stage-completed">${stats.completed}</div>
                            <div class="content-stat-label">완료</div>
                        </div>
                        <div class="content-stat-item">
                            <div class="content-stat-number stage-processing">${stats.processing}</div>
                            <div class="content-stat-label">처리 중</div>
                        </div>
                        <div class="content-stat-item">
                            <div class="content-stat-number stage-waiting">${stats.waiting}</div>
                            <div class="content-stat-label">대기 중</div>
                        </div>
                        <div class="content-stat-item">
                            <div class="content-stat-number stage-failed">${stats.failed}</div>
                            <div class="content-stat-label">실패</div>
                        </div>
                    `;

                    // 콘텐츠 목록 업데이트
                    let contentHtml = '';
                    data.contents.forEach(item => {
                        let stageClass = '';
                        if (item.processing_stage === '완료') stageClass = 'stage-completed';
                        else if (item.processing_stage === '실패') stageClass = 'stage-failed';
                        else if (item.processing_stage.includes('처리')) stageClass = 'stage-processing';
                        else stageClass = 'stage-waiting';

                        contentHtml += `
                            <tr>
                                <td>${item.channel}</td>
                                <td title="${item.title}">${item.title.length > 50 ? item.title.substring(0, 50) + '...' : item.title}</td>
                                <td>${item.created_at ? new Date(item.created_at).toLocaleDateString('ko-KR') : '-'}</td>
                                <td class="${stageClass}">${item.processing_stage}</td>
                                <td>${item.transcript_count}</td>
                                <td>${item.vector_count}</td>
                                <td>${item.duration_min ? item.duration_min.toFixed(1) : '-'}</td>
                            </tr>
                        `;
                    });
                    document.getElementById('content-list').innerHTML = contentHtml || '<tr><td colspan="7" style="text-align: center;">콘텐츠가 없습니다</td></tr>';

                    // 페이징 UI 업데이트
                    updatePagination(data.pagination);

                } catch (error) {
                    console.error('콘텐츠 로드 실패:', error);
                }
            }

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
                            <div class="stat-number">${data.vectors_in_qdrant || 0}</div>
                            <div class="stat-label">Qdrant 벡터</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number">${data.transcript_segments || 0}</div>
                            <div class="stat-label">트랜스크립트</div>
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

            function updatePagination(pagination) {
                let paginationHtml = '';

                // 이전 페이지 버튼
                paginationHtml += `<button onclick="goToPage(${pagination.current_page - 1})" ${!pagination.has_previous ? 'disabled' : ''}>이전</button>`;

                // 페이지 정보
                paginationHtml += `<span class="page-info">페이지 ${pagination.current_page} / ${pagination.total_pages} (총 ${pagination.total_items}개)</span>`;

                // 다음 페이지 버튼
                paginationHtml += `<button onclick="goToPage(${pagination.current_page + 1})" ${!pagination.has_next ? 'disabled' : ''}>다음</button>`;

                document.getElementById('pagination').innerHTML = paginationHtml;
            }

            function goToPage(page) {
                currentPage = page;
                loadContent(true);
                countdown = 10;
            }

            function changePageSize() {
                pageSize = parseInt(document.getElementById('page-size').value);
                currentPage = 1;  // 페이지 크기 변경시 첫 페이지로
                loadContent(true);
                countdown = 10;
            }

            function sortTable(column) {
                // 같은 컬럼을 다시 클릭하면 정렬 순서 반대로
                if (sortBy === column) {
                    sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
                } else {
                    sortBy = column;
                    sortOrder = 'desc';  // 새 컬럼 선택시 기본 내림차순
                }

                // 헤더 스타일 업데이트
                document.querySelectorAll('.content-table th').forEach(th => {
                    th.classList.remove('sorted-asc', 'sorted-desc');
                });

                const selectedTh = document.querySelector(`th[data-column="${column}"]`);
                if (selectedTh) {
                    selectedTh.classList.add(sortOrder === 'asc' ? 'sorted-asc' : 'sorted-desc');
                }

                currentPage = 1;  // 정렬 변경시 첫 페이지로
                loadContent(true);
                countdown = 10;
            }

            function refreshData() {
                loadStats();
                loadContent();
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
            loadContent();
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
        # 기본 통계 (Content 테이블 기준 - 실제 상태)
        content_total = db.query(Content).count()
        stt_completed = db.query(Content).filter(Content.transcript_available == True).count()
        vector_completed = db.query(Content).filter(Content.vector_stored == True).count()

        # 트랜스크립트 세그먼트 수
        transcript_segments = db.query(Transcript).count()

        # Qdrant 벡터 수 확인
        try:
            qdrant_client = QdrantClient(url='http://qdrant:6333')
            collection_info = qdrant_client.get_collection('youtube_content')
            vectorized_count = collection_info.points_count
        except:
            vectorized_count = 0

        # 지식화 진행률 (vector_stored 기준)
        knowledge_progress = (vector_completed / content_total * 100) if content_total > 0 else 0

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

        # 워커 상태 확인
        processing_jobs = db.query(ProcessingJob).filter(
            ProcessingJob.status == 'processing'
        ).all()

        stt_active = sum(1 for job in processing_jobs if job.job_type in ['process_audio', 'extract_transcript'])
        vec_active = sum(1 for job in processing_jobs if job.job_type == 'vectorize')

        # 에이전트 서비스 상태 확인
        try:
            agent_response = requests.get('http://agent-service:8000/health', timeout=1)
            agent_status = 'Active' if agent_response.status_code == 200 else 'Error'
        except:
            agent_status = 'Offline'

        workers = {
            "STT Workers": {
                "active": 3,
                "processing": stt_active,
                "last_activity": "진행 중" if stt_active > 0 else "대기 중"
            },
            "Vectorization Workers": {
                "active": 3,
                "processing": vec_active,
                "last_activity": "진행 중" if vec_active > 0 else "대기 중"
            },
            "RAG Agent Service": {
                "active": 1,
                "status": agent_status,
                "last_activity": agent_status
            },
            "Whisper Server": {
                "active": 1,
                "status": "GPU Active" if stt_active > 0 else "Ready",
                "last_activity": "GPU 모델 사용 중"
            },
            "Embedding Server": {
                "active": 1,
                "status": "GPU Active" if vec_active > 0 else "Ready",
                "last_activity": "BGE-M3 모델 사용 중"
            }
        }

        return {
            "content_total": content_total,
            "stt_completed": stt_completed,
            "vectorized": vector_completed,  # Content 테이블 기준으로 통일
            "vectors_in_qdrant": vectorized_count,
            "transcript_segments": transcript_segments,
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
async def get_content_list(
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc"
):
    """콘텐츠 목록 조회 (처리 상태 포함, 페이징 및 정렬 지원)"""
    db = get_db()
    try:
        # 전체 통계를 위한 쿼리
        total_content_count = db.query(Content).count()
        all_contents_for_stats = db.query(Content).all()

        # 정렬 처리
        query = db.query(Content)
        if sort_by == "title":
            order_column = Content.title
        elif sort_by == "duration":
            order_column = Content.duration
        elif sort_by == "channel":
            # 채널명으로 정렬하려면 조인 필요
            query = query.join(Channel)
            order_column = Channel.name
        else:  # 기본값: created_at
            order_column = Content.created_at

        if sort_order == "asc":
            query = query.order_by(order_column.asc())
        else:
            query = query.order_by(order_column.desc())

        # 페이징 처리
        offset = (page - 1) * page_size
        contents = query.offset(offset).limit(page_size).all()

        # 총 페이지 수 계산
        total_pages = (total_content_count + page_size - 1) // page_size

        result = []
        stats_completed = 0
        stats_processing = 0
        stats_waiting = 0
        stats_failed = 0

        # 전체 콘텐츠의 통계 계산
        for content in all_contents_for_stats:
            # 트랜스크립트 상태 확인
            transcript_count = db.query(Transcript).filter(
                Transcript.content_id == content.id
            ).count()

            # 벡터 매핑 상태 확인
            vector_count = db.query(VectorMapping).filter(
                VectorMapping.content_id == content.id
            ).count()

            # 처리 작업 상태 확인
            latest_job = db.query(ProcessingJob).filter(
                ProcessingJob.content_id == content.id
            ).order_by(ProcessingJob.created_at.desc()).first()

            # 처리 단계 결정 (통계용)
            if content.vector_stored and vector_count > 0:
                stats_completed += 1
            elif content.transcript_available and transcript_count > 0:
                stats_waiting += 1
            elif latest_job:
                if latest_job.status == "processing":
                    stats_processing += 1
                elif latest_job.status == "failed":
                    stats_failed += 1
                else:
                    stats_waiting += 1
            else:
                stats_waiting += 1

        # 표시용 콘텐츠 처리 (최근 100개)
        for content in contents:
            # 트랜스크립트 상태 확인
            transcript_count = db.query(Transcript).filter(
                Transcript.content_id == content.id
            ).count()

            # 벡터 매핑 상태 확인
            vector_count = db.query(VectorMapping).filter(
                VectorMapping.content_id == content.id
            ).count()

            # 처리 작업 상태 확인
            latest_job = db.query(ProcessingJob).filter(
                ProcessingJob.content_id == content.id
            ).order_by(ProcessingJob.created_at.desc()).first()

            # 처리 단계 결정 (표시용)
            processing_stage = "대기중"
            if content.vector_stored and vector_count > 0:
                processing_stage = "완료"
            elif content.transcript_available and transcript_count > 0:
                processing_stage = "벡터화 대기"
            elif latest_job:
                if latest_job.status == "processing":
                    processing_stage = "STT 처리중"
                elif latest_job.status == "completed":
                    processing_stage = "벡터화 대기"
                elif latest_job.status == "failed":
                    processing_stage = "실패"

            # 채널 정보
            channel = db.query(Channel).filter(Channel.id == content.channel_id).first()

            result.append({
                "id": content.id,
                "title": content.title[:80] if content.title else "제목 없음",
                "channel": channel.name if channel else "Unknown",
                "duration": content.duration,
                "duration_min": round(content.duration / 60, 1) if content.duration else 0,
                "transcript_available": content.transcript_available,
                "transcript_count": transcript_count,
                "vector_stored": content.vector_stored,
                "vector_count": vector_count,
                "processing_stage": processing_stage,
                "job_status": latest_job.status if latest_job else None,
                "created_at": content.created_at.isoformat() if content.created_at else None,
                "url": content.url
            })

        # 전체 통계 정보 (모든 콘텐츠 기준)
        return {
            "statistics": {
                "total": total_content_count,
                "completed": stats_completed,
                "processing": stats_processing,
                "waiting": stats_waiting,
                "failed": stats_failed,
                "completion_rate": round((stats_completed / total_content_count * 100) if total_content_count > 0 else 0, 1)
            },
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "total_items": total_content_count,
                "has_next": page < total_pages,
                "has_previous": page > 1
            },
            "sorting": {
                "sort_by": sort_by,
                "sort_order": sort_order
            },
            "contents": result
        }

    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)