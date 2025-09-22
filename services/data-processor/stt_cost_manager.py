#!/usr/bin/env python3
"""
STT 비용 관리 시스템
OpenAI Whisper API 사용 시 비용 추적 및 제한
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, Boolean, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import redis

Base = declarative_base()

class STTCostTracking(Base):
    """STT 비용 추적 테이블"""
    __tablename__ = 'stt_cost_tracking'

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    cost_usd = Column(Float, nullable=False)
    api_provider = Column(String(50), nullable=False)  # 'openai' or 'whisper_server'
    processed_at = Column(DateTime, default=datetime.utcnow)
    approved_by_user = Column(Boolean, default=False)
    approval_timestamp = Column(DateTime)


class STTCostManager:
    """STT 비용 관리 클래스"""

    # OpenAI Whisper API 가격 (USD per minute)
    OPENAI_WHISPER_PRICE_PER_MINUTE = 0.006

    # 비용 제한 설정
    DAILY_COST_LIMIT_USD = float(os.getenv('STT_DAILY_COST_LIMIT', '10.0'))  # 일일 $10 기본값
    MONTHLY_COST_LIMIT_USD = float(os.getenv('STT_MONTHLY_COST_LIMIT', '100.0'))  # 월 $100 기본값
    SINGLE_VIDEO_COST_LIMIT_USD = float(os.getenv('STT_SINGLE_VIDEO_LIMIT', '2.0'))  # 단일 영상 $2 기본값

    # 자동 승인 임계값 (이 금액 이하는 자동 승인)
    AUTO_APPROVE_THRESHOLD_USD = float(os.getenv('STT_AUTO_APPROVE_THRESHOLD', '0.10'))  # $0.10 이하 자동승인

    def __init__(self):
        """초기화"""
        # 데이터베이스 연결
        from shared.models.database import get_database_url
        self.engine = create_engine(get_database_url())
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Redis 연결 (승인 대기 큐 관리)
        redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
        self.redis_client = redis.from_url(redis_url, decode_responses=True)

        # 승인 대기 큐 키
        self.PENDING_APPROVAL_KEY = 'stt:pending_approval'
        self.COST_TRACKING_KEY = 'stt:cost_tracking'

    def calculate_cost(self, duration_seconds: float, provider: str = 'openai') -> float:
        """
        STT 처리 비용 계산

        Args:
            duration_seconds: 오디오 길이 (초)
            provider: API 제공자 ('openai' or 'whisper_server')

        Returns:
            예상 비용 (USD)
        """
        if provider == 'whisper_server':
            return 0.0  # 자체 서버는 비용 없음

        duration_minutes = duration_seconds / 60.0
        return duration_minutes * self.OPENAI_WHISPER_PRICE_PER_MINUTE

    def check_cost_limits(self, content_id: int, duration_seconds: float) -> Tuple[bool, str, float]:
        """
        비용 제한 확인

        Returns:
            (승인 필요 여부, 메시지, 예상 비용)
        """
        estimated_cost = self.calculate_cost(duration_seconds)

        db = self.SessionLocal()
        try:
            # 1. 단일 영상 비용 확인
            if estimated_cost > self.SINGLE_VIDEO_COST_LIMIT_USD:
                return (True, f"단일 영상 비용 제한 초과 (${estimated_cost:.2f} > ${self.SINGLE_VIDEO_COST_LIMIT_USD})",
                       estimated_cost)

            # 2. 일일 비용 확인
            today = datetime.utcnow().date()
            daily_cost = db.query(
                func.sum(STTCostTracking.cost_usd)
            ).filter(
                STTCostTracking.processed_at >= today,
                STTCostTracking.api_provider == 'openai'
            ).scalar() or 0.0

            if daily_cost + estimated_cost > self.DAILY_COST_LIMIT_USD:
                return (True, f"일일 비용 제한 초과 (현재 ${daily_cost:.2f} + ${estimated_cost:.2f} > ${self.DAILY_COST_LIMIT_USD})",
                       estimated_cost)

            # 3. 월별 비용 확인
            month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
            monthly_cost = db.query(
                func.sum(STTCostTracking.cost_usd)
            ).filter(
                STTCostTracking.processed_at >= month_start,
                STTCostTracking.api_provider == 'openai'
            ).scalar() or 0.0

            if monthly_cost + estimated_cost > self.MONTHLY_COST_LIMIT_USD:
                return (True, f"월별 비용 제한 초과 (현재 ${monthly_cost:.2f} + ${estimated_cost:.2f} > ${self.MONTHLY_COST_LIMIT_USD})",
                       estimated_cost)

            # 4. 자동 승인 임계값 확인
            if estimated_cost <= self.AUTO_APPROVE_THRESHOLD_USD:
                return (False, f"자동 승인 (${estimated_cost:.2f} <= ${self.AUTO_APPROVE_THRESHOLD_USD})",
                       estimated_cost)

            # 5. 승인 필요
            return (True, f"사용자 승인 필요 (예상 비용: ${estimated_cost:.2f})", estimated_cost)

        finally:
            db.close()

    def request_approval(self, content_id: int, title: str, duration_seconds: float,
                        channel_name: str = None) -> str:
        """
        사용자 승인 요청

        Returns:
            승인 요청 ID
        """
        estimated_cost = self.calculate_cost(duration_seconds)
        approval_id = f"stt_approval_{content_id}_{datetime.utcnow().timestamp()}"

        approval_data = {
            'approval_id': approval_id,
            'content_id': content_id,
            'title': title,
            'channel_name': channel_name,
            'duration_seconds': duration_seconds,
            'duration_minutes': duration_seconds / 60.0,
            'estimated_cost_usd': estimated_cost,
            'requested_at': datetime.utcnow().isoformat(),
            'status': 'pending'
        }

        # Redis에 승인 대기 정보 저장
        self.redis_client.hset(
            self.PENDING_APPROVAL_KEY,
            approval_id,
            json.dumps(approval_data)
        )

        # 알림 생성 (별도 구현 필요)
        self._send_approval_notification(approval_data)

        return approval_id

    def _send_approval_notification(self, approval_data: Dict):
        """승인 요청 알림 발송"""
        # TODO: Slack, Email, 또는 웹 UI 알림 구현
        print(f"""
        ⚠️  STT 비용 승인 요청 ⚠️
        ========================
        영상: {approval_data['title']}
        채널: {approval_data.get('channel_name', 'Unknown')}
        길이: {approval_data['duration_minutes']:.1f}분
        예상 비용: ${approval_data['estimated_cost_usd']:.2f}

        승인 ID: {approval_data['approval_id']}
        ========================
        """)

    def check_approval_status(self, approval_id: str) -> Optional[str]:
        """
        승인 상태 확인

        Returns:
            'approved', 'rejected', 'pending', or None
        """
        data = self.redis_client.hget(self.PENDING_APPROVAL_KEY, approval_id)
        if not data:
            return None

        approval_data = json.loads(data)
        return approval_data.get('status', 'pending')

    def approve_request(self, approval_id: str, approved_by: str = 'system') -> bool:
        """승인 처리"""
        data = self.redis_client.hget(self.PENDING_APPROVAL_KEY, approval_id)
        if not data:
            return False

        approval_data = json.loads(data)
        approval_data['status'] = 'approved'
        approval_data['approved_by'] = approved_by
        approval_data['approved_at'] = datetime.utcnow().isoformat()

        # Redis 업데이트
        self.redis_client.hset(
            self.PENDING_APPROVAL_KEY,
            approval_id,
            json.dumps(approval_data)
        )

        return True

    def reject_request(self, approval_id: str, rejected_by: str = 'system', reason: str = None) -> bool:
        """거부 처리"""
        data = self.redis_client.hget(self.PENDING_APPROVAL_KEY, approval_id)
        if not data:
            return False

        approval_data = json.loads(data)
        approval_data['status'] = 'rejected'
        approval_data['rejected_by'] = rejected_by
        approval_data['rejected_at'] = datetime.utcnow().isoformat()
        approval_data['rejection_reason'] = reason

        # Redis 업데이트
        self.redis_client.hset(
            self.PENDING_APPROVAL_KEY,
            approval_id,
            json.dumps(approval_data)
        )

        return True

    def record_cost(self, content_id: int, duration_seconds: float,
                   actual_cost: float = None, provider: str = 'openai',
                   approved: bool = False):
        """실제 비용 기록"""
        db = self.SessionLocal()
        try:
            if actual_cost is None:
                actual_cost = self.calculate_cost(duration_seconds, provider)

            tracking = STTCostTracking(
                content_id=content_id,
                duration_seconds=duration_seconds,
                cost_usd=actual_cost,
                api_provider=provider,
                approved_by_user=approved,
                approval_timestamp=datetime.utcnow() if approved else None
            )

            db.add(tracking)
            db.commit()

            # Redis에 일일/월별 누적 비용 업데이트
            self._update_cost_cache(actual_cost)

            return tracking.id

        finally:
            db.close()

    def _update_cost_cache(self, cost: float):
        """Redis 캐시에 비용 업데이트"""
        today_key = f"stt:daily_cost:{datetime.utcnow().date()}"
        month_key = f"stt:monthly_cost:{datetime.utcnow().strftime('%Y-%m')}"

        # 일일 비용 누적
        self.redis_client.incrbyfloat(today_key, cost)
        self.redis_client.expire(today_key, 86400 * 2)  # 2일 후 만료

        # 월별 비용 누적
        self.redis_client.incrbyfloat(month_key, cost)
        self.redis_client.expire(month_key, 86400 * 35)  # 35일 후 만료

    def get_cost_summary(self) -> Dict:
        """비용 요약 정보 조회"""
        db = self.SessionLocal()
        try:
            # 오늘 비용
            today = datetime.utcnow().date()
            daily_cost = db.query(
                func.sum(STTCostTracking.cost_usd)
            ).filter(
                STTCostTracking.processed_at >= today,
                STTCostTracking.api_provider == 'openai'
            ).scalar() or 0.0

            # 이번 달 비용
            month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
            monthly_cost = db.query(
                func.sum(STTCostTracking.cost_usd)
            ).filter(
                STTCostTracking.processed_at >= month_start,
                STTCostTracking.api_provider == 'openai'
            ).scalar() or 0.0

            # 전체 비용
            total_cost = db.query(
                func.sum(STTCostTracking.cost_usd)
            ).filter(
                STTCostTracking.api_provider == 'openai'
            ).scalar() or 0.0

            # 처리된 시간
            total_hours = db.query(
                func.sum(STTCostTracking.duration_seconds)
            ).filter(
                STTCostTracking.api_provider == 'openai'
            ).scalar() or 0.0
            total_hours /= 3600.0

            return {
                'daily': {
                    'cost_usd': daily_cost,
                    'limit_usd': self.DAILY_COST_LIMIT_USD,
                    'usage_percent': (daily_cost / self.DAILY_COST_LIMIT_USD * 100) if self.DAILY_COST_LIMIT_USD > 0 else 0
                },
                'monthly': {
                    'cost_usd': monthly_cost,
                    'limit_usd': self.MONTHLY_COST_LIMIT_USD,
                    'usage_percent': (monthly_cost / self.MONTHLY_COST_LIMIT_USD * 100) if self.MONTHLY_COST_LIMIT_USD > 0 else 0
                },
                'total': {
                    'cost_usd': total_cost,
                    'hours_processed': total_hours
                },
                'settings': {
                    'auto_approve_threshold': self.AUTO_APPROVE_THRESHOLD_USD,
                    'single_video_limit': self.SINGLE_VIDEO_COST_LIMIT_USD,
                    'price_per_minute': self.OPENAI_WHISPER_PRICE_PER_MINUTE
                }
            }

        finally:
            db.close()

    def get_pending_approvals(self) -> List[Dict]:
        """승인 대기 목록 조회"""
        pending = []
        for key in self.redis_client.hkeys(self.PENDING_APPROVAL_KEY):
            data = self.redis_client.hget(self.PENDING_APPROVAL_KEY, key)
            if data:
                approval_data = json.loads(data)
                if approval_data.get('status') == 'pending':
                    pending.append(approval_data)

        # 최신 요청 순으로 정렬
        pending.sort(key=lambda x: x.get('requested_at', ''), reverse=True)
        return pending


# CLI 인터페이스 (테스트/관리용)
if __name__ == "__main__":
    import sys

    manager = STTCostManager()

    if len(sys.argv) < 2:
        print("""
        사용법:
        python stt_cost_manager.py summary                    # 비용 요약
        python stt_cost_manager.py pending                    # 승인 대기 목록
        python stt_cost_manager.py approve <approval_id>      # 승인
        python stt_cost_manager.py reject <approval_id>       # 거부
        python stt_cost_manager.py check <duration_seconds>   # 비용 확인
        """)
        sys.exit(1)

    command = sys.argv[1]

    if command == 'summary':
        summary = manager.get_cost_summary()
        print(json.dumps(summary, indent=2))

    elif command == 'pending':
        pending = manager.get_pending_approvals()
        for approval in pending:
            print(f"{approval['approval_id']}: {approval['title']} - ${approval['estimated_cost_usd']:.2f}")

    elif command == 'approve' and len(sys.argv) > 2:
        approval_id = sys.argv[2]
        if manager.approve_request(approval_id, 'cli_user'):
            print(f"✅ 승인 완료: {approval_id}")
        else:
            print(f"❌ 승인 실패: {approval_id}")

    elif command == 'reject' and len(sys.argv) > 2:
        approval_id = sys.argv[2]
        reason = sys.argv[3] if len(sys.argv) > 3 else None
        if manager.reject_request(approval_id, 'cli_user', reason):
            print(f"❌ 거부 완료: {approval_id}")
        else:
            print(f"❌ 거부 실패: {approval_id}")

    elif command == 'check' and len(sys.argv) > 2:
        duration = float(sys.argv[2])
        cost = manager.calculate_cost(duration)
        print(f"예상 비용: ${cost:.2f} ({duration/60:.1f}분)")

        needs_approval, message, _ = manager.check_cost_limits(0, duration)
        print(f"승인 필요: {needs_approval}")
        print(f"메시지: {message}")