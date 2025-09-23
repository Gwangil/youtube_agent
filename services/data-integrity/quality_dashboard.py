#!/usr/bin/env python3
"""
데이터 품질 대시보드
- 실시간 데이터 정합성 모니터링
- 자동 복구 상태 확인
- 알림 관리
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
import uvicorn
import json
import asyncio
from datetime import datetime
from data_integrity_manager import DataIntegrityManager
from auto_recovery import AutoRecoveryService

app = FastAPI(title="Data Quality Dashboard")

# 서비스 인스턴스
integrity_manager = DataIntegrityManager()
recovery_service = AutoRecoveryService()

class IntegrityCheckRequest(BaseModel):
    content_id: int

class RecoveryAction(BaseModel):
    action: str  # scan, fix, recover
    content_id: Optional[int] = None

@app.get("/")
async def dashboard():
    """대시보드 메인 페이지"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>데이터 품질 대시보드</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { max-width: 1400px; margin: 0 auto; }
            .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }
            .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .card h3 { margin-top: 0; color: #2c3e50; }
            .status-good { color: #27ae60; font-weight: bold; }
            .status-warning { color: #f39c12; font-weight: bold; }
            .status-error { color: #e74c3c; font-weight: bold; }
            .progress-bar { background: #ecf0f1; border-radius: 4px; overflow: hidden; height: 20px; margin: 10px 0; }
            .progress-fill { height: 100%; background: linear-gradient(90deg, #3498db, #2ecc71); transition: width 0.3s; }
            .btn { padding: 10px 20px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
            .btn:hover { background: #2980b9; }
            .btn-danger { background: #e74c3c; }
            .btn-danger:hover { background: #c0392b; }
            .btn-success { background: #27ae60; }
            .btn-success:hover { background: #229954; }
            .alert { padding: 15px; margin: 10px 0; border-radius: 4px; }
            .alert-info { background: #d1f2eb; border-left: 4px solid #3498db; }
            .alert-warning { background: #fcf3cf; border-left: 4px solid #f39c12; }
            .alert-error { background: #fadbd8; border-left: 4px solid #e74c3c; }
            .log-entry { padding: 10px; margin: 5px 0; background: #f8f9fa; border-radius: 4px; font-family: monospace; font-size: 12px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background: #34495e; color: white; }
            tr:hover { background: #f5f5f5; }
            .chart { height: 200px; position: relative; }
            .auto-refresh { position: absolute; top: 20px; right: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 데이터 품질 대시보드</h1>
                <p>실시간 데이터 정합성 및 품질 모니터링</p>
                <label class="auto-refresh">
                    <input type="checkbox" id="autoRefresh" checked> 자동 새로고침 (10초)
                </label>
            </div>

            <div class="grid">
                <!-- 시스템 상태 -->
                <div class="card">
                    <h3>🔍 시스템 상태</h3>
                    <div id="systemStatus">로딩 중...</div>
                </div>

                <!-- 데이터 정합성 -->
                <div class="card">
                    <h3>✅ 데이터 정합성</h3>
                    <div id="dataIntegrity">로딩 중...</div>
                    <button class="btn" onclick="runFullScan()">전체 스캔 실행</button>
                </div>

                <!-- 자동 복구 상태 -->
                <div class="card">
                    <h3>🔄 자동 복구</h3>
                    <div id="recoveryStatus">로딩 중...</div>
                    <button class="btn btn-success" onclick="runRecovery()">복구 실행</button>
                </div>

                <!-- 최근 알림 -->
                <div class="card">
                    <h3>🔔 최근 알림</h3>
                    <div id="recentAlerts">로딩 중...</div>
                </div>
            </div>

            <!-- 상세 정보 -->
            <div class="card" style="margin-top: 20px;">
                <h3>📈 처리 통계</h3>
                <table id="statisticsTable">
                    <thead>
                        <tr>
                            <th>항목</th>
                            <th>전체</th>
                            <th>정상</th>
                            <th>문제</th>
                            <th>처리율</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr><td colspan="5">로딩 중...</td></tr>
                    </tbody>
                </table>
            </div>

            <!-- 작업 로그 -->
            <div class="card" style="margin-top: 20px;">
                <h3>📝 작업 로그</h3>
                <div id="jobLogs" style="max-height: 300px; overflow-y: auto;">
                    로딩 중...
                </div>
            </div>
        </div>

        <script>
            let refreshInterval;

            async function loadDashboard() {
                try {
                    // 시스템 상태
                    const statusRes = await fetch('/api/status');
                    const status = await statusRes.json();
                    updateSystemStatus(status);

                    // 정합성 보고서
                    const integrityRes = await fetch('/api/integrity/report');
                    const integrity = await integrityRes.json();
                    updateIntegrity(integrity);

                    // 복구 상태
                    const recoveryRes = await fetch('/api/recovery/status');
                    const recovery = await recoveryRes.json();
                    updateRecovery(recovery);

                    // 알림
                    const alertsRes = await fetch('/api/alerts');
                    const alerts = await alertsRes.json();
                    updateAlerts(alerts);

                    // 통계
                    const statsRes = await fetch('/api/statistics');
                    const stats = await statsRes.json();
                    updateStatistics(stats);

                } catch (error) {
                    console.error('Dashboard load error:', error);
                }
            }

            function updateSystemStatus(status) {
                const elem = document.getElementById('systemStatus');
                elem.innerHTML = `
                    <p>DB 연결: <span class="${status.db_connected ? 'status-good' : 'status-error'}">
                        ${status.db_connected ? '정상' : '오류'}</span></p>
                    <p>Qdrant 연결: <span class="${status.qdrant_connected ? 'status-good' : 'status-error'}">
                        ${status.qdrant_connected ? '정상' : '오류'}</span></p>
                    <p>Redis 연결: <span class="${status.redis_connected ? 'status-good' : 'status-error'}">
                        ${status.redis_connected ? '정상' : '오류'}</span></p>
                    <p>마지막 체크: ${new Date(status.last_check).toLocaleString()}</p>
                `;
            }

            function updateIntegrity(integrity) {
                const elem = document.getElementById('dataIntegrity');
                const lastScan = integrity.last_scan || {};
                elem.innerHTML = `
                    <p>총 콘텐츠: ${integrity.database?.total_content || 0}</p>
                    <p>정합성 문제: <span class="${lastScan.issues_found ? 'status-warning' : 'status-good'}">
                        ${lastScan.issues_found || 0}개</span></p>
                    <p>자동 수정: ${lastScan.issues_fixed || 0}개</p>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${integrity.consistency_rate || 0}%"></div>
                    </div>
                    <small>정합성: ${integrity.consistency_rate || 0}%</small>
                `;
            }

            function updateRecovery(recovery) {
                const elem = document.getElementById('recoveryStatus');
                elem.innerHTML = `
                    <p>복구된 작업: ${recovery.recovered_jobs || 0}</p>
                    <p>재시도 작업: ${recovery.retried_jobs || 0}</p>
                    <p>정리된 데이터: ${recovery.cleaned_data || 0}</p>
                    <p>마지막 실행: ${recovery.last_run ? new Date(recovery.last_run).toLocaleString() : '없음'}</p>
                `;
            }

            function updateAlerts(alerts) {
                const elem = document.getElementById('recentAlerts');
                if (!alerts || alerts.length === 0) {
                    elem.innerHTML = '<p>알림 없음</p>';
                    return;
                }

                elem.innerHTML = alerts.slice(0, 5).map(alert => `
                    <div class="alert alert-${alert.level || 'info'}">
                        <strong>${alert.message}</strong><br>
                        <small>${new Date(alert.timestamp).toLocaleString()}</small>
                    </div>
                `).join('');
            }

            function updateStatistics(stats) {
                const tbody = document.querySelector('#statisticsTable tbody');
                tbody.innerHTML = `
                    <tr>
                        <td>콘텐츠</td>
                        <td>${stats.content_total || 0}</td>
                        <td>${stats.content_healthy || 0}</td>
                        <td>${stats.content_issues || 0}</td>
                        <td>${stats.content_rate || 0}%</td>
                    </tr>
                    <tr>
                        <td>트랜스크립트</td>
                        <td>${stats.transcript_total || 0}</td>
                        <td>${stats.transcript_completed || 0}</td>
                        <td>${stats.transcript_failed || 0}</td>
                        <td>${stats.transcript_rate || 0}%</td>
                    </tr>
                    <tr>
                        <td>벡터</td>
                        <td>${stats.vector_total || 0}</td>
                        <td>${stats.vector_stored || 0}</td>
                        <td>${stats.vector_orphaned || 0}</td>
                        <td>${stats.vector_rate || 0}%</td>
                    </tr>
                `;
            }

            async function runFullScan() {
                if (confirm('전체 스캔을 실행하시겠습니까?')) {
                    const res = await fetch('/api/integrity/scan', { method: 'POST' });
                    const result = await res.json();
                    alert(`스캔 완료: ${result.issues_found}개 문제 발견, ${result.issues_fixed}개 수정됨`);
                    loadDashboard();
                }
            }

            async function runRecovery() {
                if (confirm('복구 프로세스를 실행하시겠습니까?')) {
                    const res = await fetch('/api/recovery/run', { method: 'POST' });
                    const result = await res.json();
                    alert(`복구 완료: ${result.recovered}개 작업 복구됨`);
                    loadDashboard();
                }
            }

            // 자동 새로고침
            document.getElementById('autoRefresh').addEventListener('change', (e) => {
                if (e.target.checked) {
                    refreshInterval = setInterval(loadDashboard, 10000);
                } else {
                    clearInterval(refreshInterval);
                }
            });

            // 초기 로드
            loadDashboard();
            refreshInterval = setInterval(loadDashboard, 10000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/status")
async def get_status():
    """시스템 상태 확인"""
    status = {
        "db_connected": False,
        "qdrant_connected": False,
        "redis_connected": False,
        "last_check": datetime.utcnow().isoformat()
    }

    try:
        # DB 연결 체크
        with integrity_manager.SessionLocal() as db:
            db.execute("SELECT 1")
            status["db_connected"] = True
    except:
        pass

    try:
        # Qdrant 연결 체크
        integrity_manager.qdrant.get_collections()
        status["qdrant_connected"] = True
    except:
        pass

    try:
        # Redis 연결 체크
        integrity_manager.redis.ping()
        status["redis_connected"] = True
    except:
        pass

    return status

@app.get("/api/integrity/report")
async def get_integrity_report():
    """정합성 보고서 조회"""
    return integrity_manager.get_integrity_report()

@app.post("/api/integrity/scan")
async def run_integrity_scan(background_tasks: BackgroundTasks):
    """전체 정합성 스캔 실행"""
    background_tasks.add_task(integrity_manager.run_full_scan)
    return {"status": "scan_started", "message": "백그라운드에서 스캔 진행 중"}

@app.post("/api/integrity/check")
async def check_content_integrity(request: IntegrityCheckRequest):
    """특정 콘텐츠 정합성 체크"""
    check = integrity_manager.check_content_integrity(request.content_id)
    return {
        "content_id": check.content_id,
        "status": check.status.value,
        "issues": check.issues,
        "recommendations": check.recommendations
    }

@app.get("/api/recovery/status")
async def get_recovery_status():
    """복구 서비스 상태"""
    last_report = integrity_manager.redis.get("recovery:last_report")
    if last_report:
        report = json.loads(last_report)
        return {
            "recovered_jobs": report.get("stuck_jobs", {}).get("recovered", 0),
            "retried_jobs": report.get("failed_jobs", {}).get("retried", 0),
            "cleaned_data": report.get("orphan_cleanup", {}).get("total", 0),
            "last_run": report.get("timestamp")
        }
    return {
        "recovered_jobs": 0,
        "retried_jobs": 0,
        "cleaned_data": 0,
        "last_run": None
    }

@app.post("/api/recovery/run")
async def run_recovery(background_tasks: BackgroundTasks):
    """복구 프로세스 실행"""
    background_tasks.add_task(recovery_service.run_recovery_cycle)
    return {"status": "recovery_started", "message": "복구 프로세스 시작됨"}

@app.get("/api/alerts")
async def get_alerts():
    """최근 알림 조회"""
    alerts = integrity_manager.redis.lrange("data_integrity:alerts", 0, 10)
    return [json.loads(a) for a in alerts]

@app.get("/api/statistics")
async def get_statistics():
    """통계 정보 조회"""
    with integrity_manager.SessionLocal() as db:
        # 콘텐츠 통계
        content_stats = db.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN transcript_available AND vector_stored THEN 1 ELSE 0 END) as healthy
            FROM content
        """).fetchone()

        # 트랜스크립트 통계
        transcript_stats = db.execute("""
            SELECT
                COUNT(DISTINCT content_id) as completed,
                (SELECT COUNT(*) FROM content) - COUNT(DISTINCT content_id) as pending
            FROM transcripts
        """).fetchone()

        # 벡터 통계
        vector_stats = db.execute("""
            SELECT
                COUNT(DISTINCT content_id) as stored
            FROM vector_mappings
        """).fetchone()

        total = content_stats.total or 1  # 0으로 나누기 방지

        return {
            "content_total": content_stats.total,
            "content_healthy": content_stats.healthy,
            "content_issues": content_stats.total - content_stats.healthy,
            "content_rate": round((content_stats.healthy / total) * 100, 1),
            "transcript_total": content_stats.total,
            "transcript_completed": transcript_stats.completed,
            "transcript_failed": 0,
            "transcript_rate": round((transcript_stats.completed / total) * 100, 1),
            "vector_total": content_stats.total,
            "vector_stored": vector_stats.stored,
            "vector_orphaned": 0,
            "vector_rate": round((vector_stats.stored / total) * 100, 1)
        }

@app.get("/health")
async def health():
    """헬스체크"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8085)