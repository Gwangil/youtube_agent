#!/usr/bin/env python3
"""
데이터 수집 스케줄러
신규 데이터 수집을 제어하고 관리하는 시스템
"""

import os
import sys
import json
import time
import schedule
from datetime import datetime, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import Channel, Content, get_database_url


class CollectionScheduler:
    """데이터 수집 스케줄러"""

    def __init__(self):
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

        # 설정 파일 경로
        self.config_file = '/app/collection_config.json'

        # 기본 설정
        self.default_config = {
            "enabled": True,
            "schedule": {
                "daily_full_scan": "06:00",
                "incremental_hours": 4,
                "weekend_mode": "normal"  # normal, reduced, disabled
            },
            "limits": {
                "max_videos_per_channel": 50,
                "max_channels_per_run": 10,
                "rate_limit_seconds": 2
            },
            "last_run": None,
            "statistics": {
                "total_runs": 0,
                "total_videos_collected": 0,
                "last_24h_videos": 0
            }
        }

        # 설정 로드
        self.config = self.load_config()
        print(f"📅 수집 스케줄러 초기화 - 상태: {'활성' if self.config['enabled'] else '비활성'}")

    def load_config(self) -> dict:
        """설정 파일 로드"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 기본값 병합
                    for key, value in self.default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            else:
                return self.default_config.copy()
        except Exception as e:
            print(f"⚠️ 설정 로드 실패, 기본 설정 사용: {e}")
            return self.default_config.copy()

    def save_config(self):
        """설정 파일 저장"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 설정 저장 실패: {e}")

    def is_collection_enabled(self) -> bool:
        """수집 활성화 상태 확인"""
        return self.config.get("enabled", True)

    def enable_collection(self):
        """데이터 수집 활성화"""
        self.config["enabled"] = True
        self.save_config()
        print("✅ 데이터 수집 활성화됨")

    def disable_collection(self):
        """데이터 수집 비활성화"""
        self.config["enabled"] = False
        self.save_config()
        print("🛑 데이터 수집 비활성화됨")

    def should_run_today(self) -> bool:
        """오늘 수집을 실행해야 하는지 확인"""
        if not self.is_collection_enabled():
            return False

        # 주말 모드 확인
        today = datetime.now()
        is_weekend = today.weekday() >= 5  # 토요일(5), 일요일(6)

        weekend_mode = self.config["schedule"].get("weekend_mode", "normal")
        if is_weekend and weekend_mode == "disabled":
            print("📅 주말 수집 비활성화됨")
            return False
        elif is_weekend and weekend_mode == "reduced":
            # 주말에는 50% 확률로 실행
            import random
            if random.random() > 0.5:
                print("📅 주말 축소 모드 - 이번 수집 건너뜀")
                return False

        return True

    def get_collection_stats(self) -> dict:
        """수집 통계 조회"""
        db = self.SessionLocal()
        try:
            # 총 콘텐츠 수
            total_content = db.query(Content).count()

            # 최근 24시간 수집된 콘텐츠
            yesterday = datetime.utcnow() - timedelta(days=1)
            recent_content = db.query(Content).filter(
                Content.created_at >= yesterday
            ).count()

            # 활성 채널 수
            active_channels = db.query(Channel).filter(
                Channel.is_active == True
            ).count()

            return {
                "total_content": total_content,
                "recent_24h": recent_content,
                "active_channels": active_channels,
                "last_run": self.config.get("last_run"),
                "total_runs": self.config["statistics"]["total_runs"]
            }
        finally:
            db.close()

    def trigger_collection(self) -> dict:
        """수집 실행"""
        if not self.should_run_today():
            return {"status": "skipped", "reason": "collection_disabled_or_weekend"}

        print(f"🚀 데이터 수집 시작: {datetime.now()}")

        try:
            # 여기서 실제 수집 로직 호출
            # data_collector 서비스의 collect_all_channels() 호출

            # 통계 업데이트
            self.config["last_run"] = datetime.now().isoformat()
            self.config["statistics"]["total_runs"] += 1
            self.save_config()

            stats = self.get_collection_stats()
            print(f"✅ 데이터 수집 완료: {stats}")

            return {
                "status": "completed",
                "timestamp": self.config["last_run"],
                "statistics": stats
            }

        except Exception as e:
            print(f"❌ 데이터 수집 실패: {e}")
            return {"status": "failed", "error": str(e)}

    def setup_schedule(self):
        """스케줄 설정"""
        # 매일 정해진 시간에 전체 수집
        daily_time = self.config["schedule"]["daily_full_scan"]
        schedule.every().day.at(daily_time).do(self.trigger_collection)

        # 주기적 증분 수집
        incremental_hours = self.config["schedule"]["incremental_hours"]
        schedule.every(incremental_hours).hours.do(self.trigger_collection)

        print(f"📅 스케줄 설정 완료:")
        print(f"  - 매일 {daily_time}에 전체 수집")
        print(f"  - 매 {incremental_hours}시간마다 증분 수집")

    def start_scheduler(self):
        """스케줄러 시작"""
        print("📅 데이터 수집 스케줄러 시작")
        self.setup_schedule()

        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # 1분마다 확인
            except KeyboardInterrupt:
                print("🛑 스케줄러 종료")
                break
            except Exception as e:
                print(f"❌ 스케줄러 오류: {e}")
                time.sleep(300)  # 5분 대기 후 재시도

    def get_status(self) -> dict:
        """현재 상태 조회"""
        next_runs = []
        for job in schedule.jobs:
            next_runs.append({
                "job": str(job.job_func),
                "next_run": job.next_run.isoformat() if job.next_run else None
            })

        return {
            "enabled": self.config["enabled"],
            "schedule": self.config["schedule"],
            "limits": self.config["limits"],
            "statistics": self.config["statistics"],
            "next_runs": next_runs,
            "current_time": datetime.now().isoformat()
        }


def main():
    """메인 실행 함수"""
    scheduler = CollectionScheduler()

    # CLI 인터페이스
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "enable":
            scheduler.enable_collection()
        elif command == "disable":
            scheduler.disable_collection()
        elif command == "status":
            status = scheduler.get_status()
            print(json.dumps(status, ensure_ascii=False, indent=2))
        elif command == "trigger":
            result = scheduler.trigger_collection()
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif command == "start":
            scheduler.start_scheduler()
        else:
            print("사용법: python collection_scheduler.py [enable|disable|status|trigger|start]")
    else:
        # 기본적으로 스케줄러 시작
        scheduler.start_scheduler()


if __name__ == "__main__":
    main()