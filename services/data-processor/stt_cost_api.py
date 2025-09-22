#!/usr/bin/env python3
"""
STT 비용 관리 웹 API
승인 요청, 비용 모니터링, 설정 관리
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
from stt_cost_manager import STTCostManager

app = FastAPI(
    title="STT Cost Management API",
    description="OpenAI Whisper API 비용 관리 및 승인 시스템",
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

# 전역 매니저 인스턴스
cost_manager = STTCostManager()


# Pydantic 모델들
class ApprovalRequest(BaseModel):
    approval_id: str
    content_id: int
    title: str
    channel_name: Optional[str]
    duration_seconds: float
    duration_minutes: float
    estimated_cost_usd: float
    requested_at: str
    status: str


class ApprovalAction(BaseModel):
    approved_by: str
    reason: Optional[str] = None


class CostSettings(BaseModel):
    daily_limit_usd: float
    monthly_limit_usd: float
    single_video_limit_usd: float
    auto_approve_threshold_usd: float


class CostEstimate(BaseModel):
    duration_seconds: float
    provider: str = 'openai'


# API 엔드포인트들
@app.get("/")
async def root():
    """API 상태 확인"""
    return {
        "service": "STT Cost Management API",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/cost/summary")
async def get_cost_summary():
    """비용 요약 정보 조회"""
    return cost_manager.get_cost_summary()


@app.get("/api/approvals/pending", response_model=List[ApprovalRequest])
async def get_pending_approvals():
    """승인 대기 목록 조회"""
    pending = cost_manager.get_pending_approvals()
    return pending


@app.get("/api/approvals/{approval_id}")
async def get_approval_status(approval_id: str):
    """특정 승인 요청 상태 조회"""
    status = cost_manager.check_approval_status(approval_id)
    if status is None:
        raise HTTPException(status_code=404, detail="승인 요청을 찾을 수 없습니다")

    # 전체 데이터 조회
    import json
    data = cost_manager.redis_client.hget(cost_manager.PENDING_APPROVAL_KEY, approval_id)
    if data:
        return json.loads(data)
    else:
        return {"approval_id": approval_id, "status": status}


@app.post("/api/approvals/{approval_id}/approve")
async def approve_request(approval_id: str, action: ApprovalAction):
    """승인 처리"""
    success = cost_manager.approve_request(approval_id, action.approved_by)
    if not success:
        raise HTTPException(status_code=404, detail="승인 요청을 찾을 수 없습니다")

    return {
        "message": "승인 완료",
        "approval_id": approval_id,
        "approved_by": action.approved_by,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/approvals/{approval_id}/reject")
async def reject_request(approval_id: str, action: ApprovalAction):
    """거부 처리"""
    success = cost_manager.reject_request(
        approval_id,
        action.approved_by,
        action.reason
    )
    if not success:
        raise HTTPException(status_code=404, detail="승인 요청을 찾을 수 없습니다")

    return {
        "message": "거부 완료",
        "approval_id": approval_id,
        "rejected_by": action.approved_by,
        "reason": action.reason,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/approvals/bulk-approve")
async def bulk_approve(approval_ids: List[str], action: ApprovalAction):
    """일괄 승인"""
    results = []
    for approval_id in approval_ids:
        success = cost_manager.approve_request(approval_id, action.approved_by)
        results.append({
            "approval_id": approval_id,
            "success": success
        })

    return {
        "message": f"{sum(r['success'] for r in results)}개 승인 완료",
        "results": results
    }


@app.post("/api/cost/estimate")
async def estimate_cost(estimate: CostEstimate):
    """비용 예상"""
    cost = cost_manager.calculate_cost(estimate.duration_seconds, estimate.provider)
    needs_approval, message, _ = cost_manager.check_cost_limits(0, estimate.duration_seconds)

    return {
        "duration_seconds": estimate.duration_seconds,
        "duration_minutes": estimate.duration_seconds / 60.0,
        "provider": estimate.provider,
        "estimated_cost_usd": cost,
        "needs_approval": needs_approval,
        "message": message
    }


@app.get("/api/cost/settings")
async def get_cost_settings():
    """비용 제한 설정 조회"""
    return {
        "daily_limit_usd": cost_manager.DAILY_COST_LIMIT_USD,
        "monthly_limit_usd": cost_manager.MONTHLY_COST_LIMIT_USD,
        "single_video_limit_usd": cost_manager.SINGLE_VIDEO_COST_LIMIT_USD,
        "auto_approve_threshold_usd": cost_manager.AUTO_APPROVE_THRESHOLD_USD,
        "price_per_minute": cost_manager.OPENAI_WHISPER_PRICE_PER_MINUTE
    }


@app.post("/api/cost/settings")
async def update_cost_settings(settings: CostSettings):
    """비용 제한 설정 업데이트 (환경 변수 업데이트 필요)"""
    # 실제로는 환경 변수나 설정 파일을 업데이트해야 함
    # 여기서는 임시로 메모리 값만 변경
    cost_manager.DAILY_COST_LIMIT_USD = settings.daily_limit_usd
    cost_manager.MONTHLY_COST_LIMIT_USD = settings.monthly_limit_usd
    cost_manager.SINGLE_VIDEO_COST_LIMIT_USD = settings.single_video_limit_usd
    cost_manager.AUTO_APPROVE_THRESHOLD_USD = settings.auto_approve_threshold_usd

    return {
        "message": "설정이 업데이트되었습니다 (재시작 시 초기화됨)",
        "settings": settings
    }


@app.get("/api/cost/history")
async def get_cost_history(limit: int = 100):
    """비용 이력 조회"""
    from sqlalchemy import desc
    from stt_cost_manager import STTCostTracking

    db = cost_manager.SessionLocal()
    try:
        history = db.query(STTCostTracking).order_by(
            desc(STTCostTracking.processed_at)
        ).limit(limit).all()

        return [
            {
                "id": item.id,
                "content_id": item.content_id,
                "duration_seconds": item.duration_seconds,
                "cost_usd": item.cost_usd,
                "api_provider": item.api_provider,
                "processed_at": item.processed_at.isoformat() if item.processed_at else None,
                "approved_by_user": item.approved_by_user,
                "approval_timestamp": item.approval_timestamp.isoformat() if item.approval_timestamp else None
            }
            for item in history
        ]
    finally:
        db.close()


@app.get("/api/cost/alerts")
async def get_cost_alerts():
    """비용 경고 조회"""
    summary = cost_manager.get_cost_summary()
    alerts = []

    # 일일 제한 경고
    if summary['daily']['usage_percent'] > 80:
        alerts.append({
            "level": "warning" if summary['daily']['usage_percent'] < 95 else "critical",
            "type": "daily_limit",
            "message": f"일일 비용이 제한의 {summary['daily']['usage_percent']:.1f}%에 도달했습니다",
            "current": summary['daily']['cost_usd'],
            "limit": summary['daily']['limit_usd']
        })

    # 월별 제한 경고
    if summary['monthly']['usage_percent'] > 80:
        alerts.append({
            "level": "warning" if summary['monthly']['usage_percent'] < 95 else "critical",
            "type": "monthly_limit",
            "message": f"월별 비용이 제한의 {summary['monthly']['usage_percent']:.1f}%에 도달했습니다",
            "current": summary['monthly']['cost_usd'],
            "limit": summary['monthly']['limit_usd']
        })

    return alerts


# HTML 대시보드 (간단한 UI)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """웹 대시보드"""
    from fastapi.responses import HTMLResponse

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>STT 비용 관리 대시보드</title>
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
            .approval-item { padding: 15px; margin: 10px 0; border: 1px solid #dee2e6; border-radius: 6px; }
            .btn { background: #007bff; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin: 5px; }
            .btn-danger { background: #dc3545; }
            .btn-success { background: #28a745; }
            .btn:hover { opacity: 0.9; }
            .progress-bar { background: #e9ecef; height: 20px; border-radius: 10px; overflow: hidden; margin: 10px 0; }
            .progress-fill { background: #007bff; height: 100%; transition: width 0.3s; }
            .progress-fill.warning { background: #ffc107; }
            .progress-fill.danger { background: #dc3545; }
            .alert { padding: 15px; margin: 10px 0; border-radius: 6px; }
            .alert.warning { background: #fff3cd; color: #856404; }
            .alert.critical { background: #f8d7da; color: #721c24; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <h1 class="header">💰 STT 비용 관리 대시보드</h1>
            </div>

            <div class="card">
                <h2>📊 비용 현황</h2>
                <div id="cost-summary"></div>
            </div>

            <div class="card">
                <h2>⚠️ 경고</h2>
                <div id="alerts"></div>
            </div>

            <div class="card">
                <h2>📋 승인 대기 목록</h2>
                <div id="pending-approvals"></div>
            </div>

            <div class="card">
                <h2>⚙️ 설정</h2>
                <div id="settings"></div>
            </div>
        </div>

        <script>
            async function loadData() {
                // 비용 요약 로드
                const summaryResponse = await fetch('/api/cost/summary');
                const summary = await summaryResponse.json();

                document.getElementById('cost-summary').innerHTML = `
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-label">일일 비용</div>
                            <div class="stat-number">$${summary.daily.cost_usd.toFixed(2)}</div>
                            <div class="progress-bar">
                                <div class="progress-fill ${summary.daily.usage_percent > 80 ? (summary.daily.usage_percent > 95 ? 'danger' : 'warning') : ''}"
                                     style="width: ${summary.daily.usage_percent}%"></div>
                            </div>
                            <small>${summary.daily.usage_percent.toFixed(1)}% / $${summary.daily.limit_usd}</small>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">월별 비용</div>
                            <div class="stat-number">$${summary.monthly.cost_usd.toFixed(2)}</div>
                            <div class="progress-bar">
                                <div class="progress-fill ${summary.monthly.usage_percent > 80 ? (summary.monthly.usage_percent > 95 ? 'danger' : 'warning') : ''}"
                                     style="width: ${summary.monthly.usage_percent}%"></div>
                            </div>
                            <small>${summary.monthly.usage_percent.toFixed(1)}% / $${summary.monthly.limit_usd}</small>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">총 처리 시간</div>
                            <div class="stat-number">${summary.total.hours_processed.toFixed(1)}h</div>
                            <div class="stat-label">총 비용: $${summary.total.cost_usd.toFixed(2)}</div>
                        </div>
                    </div>
                `;

                // 경고 로드
                const alertsResponse = await fetch('/api/cost/alerts');
                const alerts = await alertsResponse.json();

                let alertsHtml = '';
                for (const alert of alerts) {
                    alertsHtml += `
                        <div class="alert ${alert.level}">
                            ${alert.message} ($${alert.current.toFixed(2)} / $${alert.limit.toFixed(2)})
                        </div>
                    `;
                }
                document.getElementById('alerts').innerHTML = alertsHtml || '<p>경고 없음</p>';

                // 승인 대기 로드
                const approvalsResponse = await fetch('/api/approvals/pending');
                const approvals = await approvalsResponse.json();

                let approvalsHtml = '';
                for (const approval of approvals) {
                    approvalsHtml += `
                        <div class="approval-item">
                            <strong>${approval.title}</strong><br>
                            채널: ${approval.channel_name || 'Unknown'}<br>
                            길이: ${approval.duration_minutes.toFixed(1)}분<br>
                            예상 비용: <strong>$${approval.estimated_cost_usd.toFixed(2)}</strong><br>
                            <button class="btn btn-success" onclick="approve('${approval.approval_id}')">승인</button>
                            <button class="btn btn-danger" onclick="reject('${approval.approval_id}')">거부</button>
                        </div>
                    `;
                }
                document.getElementById('pending-approvals').innerHTML = approvalsHtml || '<p>대기 중인 승인 없음</p>';

                // 설정 로드
                const settingsResponse = await fetch('/api/cost/settings');
                const settings = await settingsResponse.json();

                document.getElementById('settings').innerHTML = `
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-label">일일 제한</div>
                            <div class="stat-number">$${settings.daily_limit_usd}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">월별 제한</div>
                            <div class="stat-number">$${settings.monthly_limit_usd}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">단일 영상 제한</div>
                            <div class="stat-number">$${settings.single_video_limit_usd}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">자동 승인 임계값</div>
                            <div class="stat-number">$${settings.auto_approve_threshold_usd}</div>
                        </div>
                    </div>
                `;
            }

            async function approve(approvalId) {
                const response = await fetch(`/api/approvals/${approvalId}/approve`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({approved_by: 'web_user'})
                });

                if (response.ok) {
                    alert('승인 완료');
                    loadData();
                }
            }

            async function reject(approvalId) {
                const reason = prompt('거부 사유를 입력하세요:');
                if (!reason) return;

                const response = await fetch(`/api/approvals/${approvalId}/reject`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({approved_by: 'web_user', reason: reason})
                });

                if (response.ok) {
                    alert('거부 완료');
                    loadData();
                }
            }

            // 초기 로드 및 자동 새로고침
            loadData();
            setInterval(loadData, 30000); // 30초마다 새로고침
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8084)