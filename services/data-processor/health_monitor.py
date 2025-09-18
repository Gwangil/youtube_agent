#!/usr/bin/env python3
"""
프로덕션 환경 헬스 모니터 및 자동 복구 시스템
"""

import os
import sys
import time
import requests
import psutil
from datetime import datetime, timedelta
from typing import Dict, List
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, func

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import ProcessingJob, get_database_url


class HealthMonitor:
    """시스템 헬스 모니터링 및 자동 복구"""

    def __init__(self):
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

        # 서비스 엔드포인트
        self.services = {
            "whisper_server": "http://whisper-server:8082/health",
            "monitoring_dashboard": "http://monitoring-dashboard:8081/api/stats",
            "agent_service": "http://agent-service:8000/health",
            "qdrant": "http://qdrant:6333/collections"
        }

        # 알림 임계값
        self.thresholds = {
            "stuck_jobs_minutes": 30,  # 30분 이상 멈춘 작업
            "failed_jobs_ratio": 0.1,  # 실패율 10% 이상
            "memory_usage_percent": 85,  # 메모리 사용률 85% 이상
            "disk_usage_percent": 90    # 디스크 사용률 90% 이상
        }

        print("🔍 헬스 모니터 초기화 완료")

    def check_services_health(self) -> Dict:
        """서비스 헬스 체크"""
        results = {}

        for service_name, endpoint in self.services.items():
            try:
                response = requests.get(endpoint, timeout=10)
                results[service_name] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "response_time": response.elapsed.total_seconds(),
                    "status_code": response.status_code
                }
            except Exception as e:
                results[service_name] = {
                    "status": "unreachable",
                    "error": str(e),
                    "response_time": None
                }

        return results

    def check_job_queue_health(self) -> Dict:
        """작업 큐 상태 확인"""
        db = self.SessionLocal()
        try:
            now = datetime.utcnow()

            # 멈춘 작업 확인 (processing 상태로 30분 이상)
            stuck_threshold = now - timedelta(minutes=self.thresholds["stuck_jobs_minutes"])
            stuck_jobs = db.query(ProcessingJob).filter(
                ProcessingJob.status == 'processing',
                ProcessingJob.started_at < stuck_threshold
            ).count()

            # 최근 1시간 작업 통계
            recent_threshold = now - timedelta(hours=1)
            recent_jobs = db.query(ProcessingJob).filter(
                ProcessingJob.created_at >= recent_threshold
            )

            total_recent = recent_jobs.count()
            failed_recent = recent_jobs.filter(ProcessingJob.status == 'failed').count()
            completed_recent = recent_jobs.filter(ProcessingJob.status == 'completed').count()

            # 실패율 계산
            failure_rate = (failed_recent / total_recent) if total_recent > 0 else 0

            # 대기 중인 작업별 카운트
            pending_by_type = {}
            pending_jobs = db.query(
                ProcessingJob.job_type,
                func.count(ProcessingJob.id)
            ).filter(
                ProcessingJob.status == 'pending'
            ).group_by(ProcessingJob.job_type).all()

            for job_type, count in pending_jobs:
                pending_by_type[job_type] = count

            return {
                "stuck_jobs": stuck_jobs,
                "recent_stats": {
                    "total": total_recent,
                    "completed": completed_recent,
                    "failed": failed_recent,
                    "failure_rate": failure_rate
                },
                "pending_by_type": pending_by_type,
                "alerts": {
                    "stuck_jobs": stuck_jobs > 0,
                    "high_failure_rate": failure_rate > self.thresholds["failed_jobs_ratio"]
                }
            }

        finally:
            db.close()

    def check_system_resources(self) -> Dict:
        """시스템 리소스 사용량 확인"""
        try:
            # CPU 사용률
            cpu_percent = psutil.cpu_percent(interval=1)

            # 메모리 사용률
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # 디스크 사용률
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100

            # GPU 메모리 (nvidia-smi 사용)
            gpu_info = self._get_gpu_info()

            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "disk_percent": disk_percent,
                "gpu_info": gpu_info,
                "alerts": {
                    "high_memory": memory_percent > self.thresholds["memory_usage_percent"],
                    "high_disk": disk_percent > self.thresholds["disk_usage_percent"]
                }
            }

        except Exception as e:
            return {"error": str(e)}

    def _get_gpu_info(self) -> Dict:
        """GPU 정보 조회"""
        try:
            import torch
            if torch.cuda.is_available():
                device = torch.cuda.current_device()
                total_memory = torch.cuda.get_device_properties(device).total_memory
                allocated_memory = torch.cuda.memory_allocated(device)
                cached_memory = torch.cuda.memory_reserved(device)

                return {
                    "available": True,
                    "name": torch.cuda.get_device_name(device),
                    "total_memory_gb": total_memory / 1024**3,
                    "allocated_memory_gb": allocated_memory / 1024**3,
                    "cached_memory_gb": cached_memory / 1024**3,
                    "utilization_percent": (allocated_memory / total_memory) * 100
                }
            else:
                return {"available": False}
        except Exception as e:
            return {"error": str(e)}

    def recover_stuck_jobs(self) -> Dict:
        """멈춘 작업 자동 복구"""
        db = self.SessionLocal()
        try:
            now = datetime.utcnow()
            stuck_threshold = now - timedelta(minutes=self.thresholds["stuck_jobs_minutes"])

            # 멈춘 작업들을 pending으로 되돌림
            stuck_jobs = db.query(ProcessingJob).filter(
                ProcessingJob.status == 'processing',
                ProcessingJob.started_at < stuck_threshold
            ).all()

            recovered_count = 0
            for job in stuck_jobs:
                job.status = 'pending'
                job.started_at = None
                job.error_message = f"Auto-recovered from stuck state at {now}"
                recovered_count += 1

            db.commit()

            return {
                "recovered_jobs": recovered_count,
                "timestamp": now.isoformat()
            }

        except Exception as e:
            db.rollback()
            return {"error": str(e)}
        finally:
            db.close()

    def cleanup_old_jobs(self, days: int = 7) -> Dict:
        """오래된 완료/실패 작업 정리"""
        db = self.SessionLocal()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # 완료되거나 실패한 작업 중 오래된 것 삭제
            old_jobs = db.query(ProcessingJob).filter(
                ProcessingJob.status.in_(['completed', 'failed']),
                ProcessingJob.completed_at < cutoff_date
            )

            deleted_count = old_jobs.count()
            old_jobs.delete()
            db.commit()

            return {
                "deleted_jobs": deleted_count,
                "cutoff_date": cutoff_date.isoformat()
            }

        except Exception as e:
            db.rollback()
            return {"error": str(e)}
        finally:
            db.close()

    def generate_health_report(self) -> Dict:
        """종합 헬스 리포트 생성"""
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "services": self.check_services_health(),
            "job_queue": self.check_job_queue_health(),
            "system_resources": self.check_system_resources()
        }

        # 전체 시스템 상태 결정
        service_issues = sum(1 for s in report["services"].values() if s.get("status") != "healthy")
        job_alerts = sum(1 for alert in report["job_queue"].get("alerts", {}).values() if alert)
        resource_alerts = sum(1 for alert in report["system_resources"].get("alerts", {}).values() if alert)

        total_issues = service_issues + job_alerts + resource_alerts

        if total_issues == 0:
            report["overall_status"] = "healthy"
        elif total_issues <= 2:
            report["overall_status"] = "warning"
        else:
            report["overall_status"] = "critical"

        report["summary"] = {
            "service_issues": service_issues,
            "job_alerts": job_alerts,
            "resource_alerts": resource_alerts,
            "total_issues": total_issues
        }

        return report

    def start_monitoring(self, interval_seconds: int = 60):
        """지속적인 모니터링 시작"""
        print(f"🔍 헬스 모니터링 시작 (간격: {interval_seconds}초)")

        while True:
            try:
                report = self.generate_health_report()

                # 상태에 따른 로그 출력
                status = report["overall_status"]
                if status == "healthy":
                    print(f"✅ {datetime.now().strftime('%H:%M:%S')} - 시스템 정상")
                elif status == "warning":
                    print(f"⚠️ {datetime.now().strftime('%H:%M:%S')} - 경고: {report['summary']['total_issues']}개 이슈")
                else:
                    print(f"🚨 {datetime.now().strftime('%H:%M:%S')} - 위험: {report['summary']['total_issues']}개 이슈")

                # 자동 복구 시도
                if report["job_queue"].get("alerts", {}).get("stuck_jobs"):
                    print("🔧 멈춘 작업 자동 복구 시도...")
                    recovery_result = self.recover_stuck_jobs()
                    if recovery_result.get("recovered_jobs", 0) > 0:
                        print(f"   ✅ {recovery_result['recovered_jobs']}개 작업 복구됨")

                time.sleep(interval_seconds)

            except KeyboardInterrupt:
                print("🛑 헬스 모니터링 종료")
                break
            except Exception as e:
                print(f"❌ 모니터링 오류: {e}")
                time.sleep(30)


def main():
    """메인 실행 함수"""
    monitor = HealthMonitor()

    # CLI 인터페이스
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "report":
            import json
            report = monitor.generate_health_report()
            print(json.dumps(report, indent=2, ensure_ascii=False))
        elif command == "recover":
            result = monitor.recover_stuck_jobs()
            print(f"복구 결과: {result}")
        elif command == "cleanup":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
            result = monitor.cleanup_old_jobs(days)
            print(f"정리 결과: {result}")
        elif command == "monitor":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
            monitor.start_monitoring(interval)
        else:
            print("사용법: python health_monitor.py [report|recover|cleanup|monitor]")
    else:
        # 기본적으로 모니터링 시작
        monitor.start_monitoring()


if __name__ == "__main__":
    main()