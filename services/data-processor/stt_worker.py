#!/usr/bin/env python3
"""
비용 관리 기능이 추가된 개선된 STT 워커
GPU 서버 우선, OpenAI API 폴백 시 비용 확인 및 승인
"""

import os
import sys
import time
import hashlib
import requests
import subprocess
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import (
    Content, Transcript, ProcessingJob,
    get_database_url
)
from shared.utils.retry import retry, network_retry
from src.youtube_agent.youtube_extractor import YouTubeExtractor
from stt_cost_manager import STTCostManager


class ImprovedSTTWorkerWithCost:
    """비용 관리 기능이 있는 개선된 STT 워커"""

    def __init__(self, worker_id: int = 0):
        self.worker_id = worker_id
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

        # YouTube 추출기
        self.youtube_extractor = YouTubeExtractor()

        # 비용 관리자
        self.cost_manager = STTCostManager()

        # Whisper 서버 URL
        self.whisper_server_url = os.getenv('WHISPER_SERVER_URL', 'http://whisper-server:8082')

        # OpenAI API 사용 옵션
        self.force_openai_api = os.getenv('FORCE_OPENAI_API', 'false').lower() == 'true'
        self.enable_openai_fallback = os.getenv('ENABLE_OPENAI_STT_FALLBACK', 'true').lower() == 'true'
        self.auto_approve_fallback = os.getenv('AUTO_APPROVE_STT_FALLBACK', 'false').lower() == 'true'

        if self.force_openai_api:
            print(f"☁️ OpenAI API STT 워커 #{worker_id} 초기화 (CPU 모드)")
            print(f"  처리 모드: OpenAI Whisper API 전용")
        else:
            print(f"🚀 개선된 STT 워커 #{worker_id} 초기화 (비용 관리 활성화)")
            print(f"  Whisper 서버: {self.whisper_server_url}")
            print(f"  OpenAI 폴백: {'활성화' if self.enable_openai_fallback else '비활성화'}")
        print(f"  자동 승인: {'활성화' if self.auto_approve_fallback else '비활성화'}")

        # 비용 요약 출력
        cost_summary = self.cost_manager.get_cost_summary()
        print(f"  💰 일일 비용: ${cost_summary['daily']['cost_usd']:.2f} / ${cost_summary['daily']['limit_usd']:.2f}")
        print(f"  💰 월별 비용: ${cost_summary['monthly']['cost_usd']:.2f} / ${cost_summary['monthly']['limit_usd']:.2f}")

    def get_db(self):
        """데이터베이스 세션 생성"""
        return self.SessionLocal()

    def _check_whisper_server(self) -> bool:
        """Whisper 서버 상태 확인"""
        # OpenAI API 강제 사용 모드인 경우
        if self.force_openai_api:
            return False

        try:
            response = requests.get(f"{self.whisper_server_url}/health", timeout=30)
            if response.status_code == 200:
                info = response.json()
                device = info.get('device', 'unknown')

                # GPU 확인
                if 'cuda' in device.lower() or 'gpu' in device.lower():
                    print(f"  ✅ Whisper GPU 서버 사용 가능")
                    return True
                else:
                    print(f"  ⚠️ Whisper 서버가 CPU 모드로 실행 중")
                    return False
            return False
        except Exception as e:
            print(f"  ⚠️ Whisper 서버 연결 실패: {e}")
            return False

    def _get_audio_duration(self, audio_file: str) -> float:
        """오디오 파일 길이 확인 (초)"""
        try:
            cmd = f"ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {audio_file}"
            output = subprocess.check_output(cmd, shell=True)
            return float(output.decode().strip())
        except:
            # 폴백: 예상 길이 사용
            return 600.0  # 10분 기본값

    def _process_with_gpu_whisper(self, audio_file: str, language: str = "ko") -> Optional[dict]:
        """GPU Whisper 서버로 처리"""
        try:
            print(f"  🚀 [Worker {self.worker_id}] GPU Whisper 서버로 처리 중...")

            with open(audio_file, 'rb') as f:
                files = {'audio': f}
                data = {'language': language}

                response = requests.post(
                    f"{self.whisper_server_url}/transcribe",
                    files=files,
                    data=data,
                    timeout=600
                )

            if response.status_code == 200:
                result = response.json()
                print(f"  ✅ [Worker {self.worker_id}] GPU STT 완료")
                return result
            else:
                print(f"  ❌ GPU 서버 오류: {response.status_code}")
                return None

        except Exception as e:
            print(f"  ❌ GPU 서버 처리 실패: {e}")
            return None

    def _process_with_openai_api(self, audio_file: str, language: str = "ko") -> Optional[dict]:
        """OpenAI Whisper API로 처리"""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

            print(f"  🌐 [Worker {self.worker_id}] OpenAI Whisper API 호출 중...")

            with open(audio_file, 'rb') as audio:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio,
                    language=language,
                    response_format="verbose_json"
                )

            # 응답 형식 변환
            segments = []
            if hasattr(response, 'segments') and response.segments:
                segments = response.segments
            else:
                # 전체 텍스트를 하나의 세그먼트로
                segments = [{'text': response.text, 'start': 0, 'end': 0}]

            return {
                'text': response.text,
                'language': response.language if hasattr(response, 'language') else language,
                'segments': segments
            }

        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] OpenAI API 처리 실패: {e}")
            return None

    def _wait_for_approval(self, approval_id: str, max_wait: int = 3600) -> str:
        """승인 대기"""
        check_interval = 30
        waited_time = 0

        print(f"  ⏳ 승인 대기 중... (최대 {max_wait//60}분)")

        while waited_time < max_wait:
            time.sleep(check_interval)
            waited_time += check_interval

            status = self.cost_manager.check_approval_status(approval_id)

            if status == 'approved':
                print(f"  ✅ 승인 완료!")
                return 'approved'
            elif status == 'rejected':
                print(f"  ❌ 거부됨")
                return 'rejected'
            else:
                remaining = max_wait - waited_time
                if waited_time % 300 == 0:  # 5분마다 상태 출력
                    print(f"  ⏳ 승인 대기 중... (남은 시간: {remaining//60}분)")

        print(f"  ⏱️ 승인 대기 시간 초과")
        return 'timeout'

    def process_job(self, job: ProcessingJob):
        """STT 작업 처리 (비용 관리 포함)"""
        db = self.get_db()

        try:
            # 작업 상태 업데이트
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            db.commit()

            # 콘텐츠 로드
            content = db.query(Content).filter(Content.id == job.content_id).first()
            if not content:
                raise Exception(f"콘텐츠를 찾을 수 없음: {job.content_id}")

            print(f"  📺 [Worker {self.worker_id}] 처리 시작: {content.title[:50]}...")

            # 오디오 다운로드
            shared_temp_dir = "/tmp/shared_audio"
            os.makedirs(shared_temp_dir, exist_ok=True)

            print(f"  📥 [Worker {self.worker_id}] 오디오 다운로드 중...")
            audio_file = self._download_audio(content.url, content.external_id, shared_temp_dir)

            if not audio_file or not os.path.exists(audio_file):
                raise Exception("오디오 다운로드 실패")

            # 오디오 길이 확인
            duration_seconds = self._get_audio_duration(audio_file)
            duration_minutes = duration_seconds / 60.0
            print(f"  ⏱️ [Worker {self.worker_id}] 오디오 길이: {duration_minutes:.1f}분")

            # 1. GPU Whisper 서버 시도
            stt_result = None
            if self._check_whisper_server():
                stt_result = self._process_with_gpu_whisper(audio_file, content.language)

                if stt_result:
                    # GPU 성공 - 비용 없음 기록
                    self.cost_manager.record_cost(
                        content.id,
                        duration_seconds,
                        provider='whisper_server',
                        approved=False
                    )
                    print(f"  ✅ GPU 서버로 처리 완료 (비용: $0.00)")

            # 2. OpenAI API 폴백 처리
            if not stt_result and self.enable_openai_fallback:
                # 비용 확인
                needs_approval, message, estimated_cost = self.cost_manager.check_cost_limits(
                    content.id, duration_seconds
                )

                print(f"  💰 예상 비용: ${estimated_cost:.2f}")
                print(f"  📋 {message}")

                # 승인 처리
                approved = False
                if needs_approval and not self.auto_approve_fallback:
                    # 수동 승인 필요
                    approval_id = self.cost_manager.request_approval(
                        content.id,
                        content.title,
                        duration_seconds,
                        content.channel.name if content.channel else None
                    )

                    print(f"  📨 승인 요청 생성: {approval_id}")

                    # 승인 대기
                    approval_status = self._wait_for_approval(approval_id)

                    if approval_status == 'approved':
                        approved = True
                        stt_result = self._process_with_openai_api(audio_file, content.language)
                    else:
                        raise Exception(f"OpenAI API 사용 승인 실패: {approval_status}")
                else:
                    # 자동 승인 또는 제한 내 사용
                    if self.auto_approve_fallback or not needs_approval:
                        print(f"  ✅ 자동 승인 - OpenAI API로 처리")
                        stt_result = self._process_with_openai_api(audio_file, content.language)
                        approved = not needs_approval  # 제한 내면 False, 자동 승인이면 True

                # 비용 기록
                if stt_result:
                    self.cost_manager.record_cost(
                        content.id,
                        duration_seconds,
                        provider='openai',
                        approved=approved
                    )
                    print(f"  💰 OpenAI API 비용 기록: ${estimated_cost:.2f}")

            # 3. 결과 처리
            if not stt_result:
                raise Exception("STT 처리 실패 (GPU 및 OpenAI API 모두 실패)")

            # 트랜스크립트 저장
            segments = stt_result.get('segments', [])
            print(f"  💾 [Worker {self.worker_id}] {len(segments)}개 세그먼트 저장 중...")

            # 중복 제거
            seen_hashes = set()
            unique_segments = []

            for segment in segments:
                text_hash = hashlib.md5(segment['text'].lower().encode()).hexdigest()

                if text_hash not in seen_hashes:
                    unique_segments.append(segment)
                    seen_hashes.add(text_hash)

            # 트랜스크립트 저장
            for i, segment in enumerate(unique_segments):
                transcript = Transcript(
                    content_id=content.id,
                    text=segment['text'],
                    start_time=segment.get('start', 0),
                    end_time=segment.get('end', 0),
                    segment_order=i
                )
                db.add(transcript)

            # 콘텐츠 업데이트
            content.transcript_available = True
            content.transcript_type = 'stt_whisper'
            content.language = stt_result.get('language', content.language)

            # 벡터화 작업 추가
            vector_job = ProcessingJob(
                job_type='vectorize',
                content_id=content.id,
                status='pending',
                priority=job.priority
            )
            db.add(vector_job)

            # 작업 완료
            job.status = 'completed'
            job.completed_at = datetime.utcnow()
            db.commit()

            print(f"  ✅ [Worker {self.worker_id}] STT 완료: {content.title[:50]}")

            # 정리
            if audio_file and os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                except:
                    pass

        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] 처리 실패: {e}")
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
            raise

        finally:
            db.close()

    def _download_audio(self, url: str, external_id: str, temp_dir: str) -> Optional[str]:
        """YouTube 오디오 다운로드"""
        try:
            audio_file = os.path.join(temp_dir, f"{external_id}.mp3")

            # 이미 존재하면 재사용
            if os.path.exists(audio_file):
                print(f"  ♻️ 기존 오디오 파일 재사용: {audio_file}")
                return audio_file

            # yt-dlp로 다운로드
            import yt_dlp

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(temp_dir, f"{external_id}.%(ext)s"),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if os.path.exists(audio_file):
                return audio_file

            return None

        except Exception as e:
            print(f"  ❌ 오디오 다운로드 실패: {e}")
            return None

    def run(self):
        """워커 실행"""
        print(f"🏃 STT 워커 #{self.worker_id} 시작 (비용 관리 활성화)")

        while True:
            db = self.get_db()

            try:
                # 대기 중인 STT 작업 조회
                job = db.query(ProcessingJob).filter(
                    ProcessingJob.job_type == 'extract_transcript',
                    ProcessingJob.status == 'pending'
                ).order_by(
                    ProcessingJob.priority.desc(),
                    ProcessingJob.created_at
                ).first()

                if job:
                    print(f"\n📋 [Worker {self.worker_id}] 작업 시작: Job {job.id} (Content {job.content_id})")

                    try:
                        self.process_job(job)
                    except Exception as e:
                        print(f"  ❌ 작업 처리 실패: {e}")
                        time.sleep(5)
                else:
                    # 작업이 없으면 대기
                    time.sleep(10)

            except Exception as e:
                print(f"❌ [Worker {self.worker_id}] 워커 오류: {e}")
                time.sleep(10)

            finally:
                db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='STT Worker with Cost Management')
    parser.add_argument('--worker-id', type=int, default=0, help='Worker ID')
    parser.add_argument('--cost-summary', action='store_true', help='Show cost summary')
    parser.add_argument('--pending-approvals', action='store_true', help='Show pending approvals')

    args = parser.parse_args()

    if args.cost_summary:
        # 비용 요약 출력
        manager = STTCostManager()
        summary = manager.get_cost_summary()
        import json
        print(json.dumps(summary, indent=2))
    elif args.pending_approvals:
        # 승인 대기 목록
        manager = STTCostManager()
        pending = manager.get_pending_approvals()
        for approval in pending:
            print(f"{approval['approval_id']}: {approval['title']} - ${approval['estimated_cost_usd']:.2f}")
    else:
        # 워커 실행
        worker = ImprovedSTTWorkerWithCost(worker_id=args.worker_id)
        worker.run()