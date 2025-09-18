#!/usr/bin/env python3
"""
개선된 STT 워커 - GPU 전용 (CPU 폴백 없음)
Whisper 서빙 서버와만 통신하여 효율적인 STT 처리
"""

import os
import sys
import time
import hashlib
import requests
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import yt_dlp

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import (
    Content, Transcript, ProcessingJob,
    get_database_url
)
from shared.utils.retry import retry, network_retry
from src.youtube_agent.youtube_extractor import YouTubeExtractor


class ImprovedSTTWorker:
    """개선된 STT 워커 - Whisper GPU 서버 전용"""

    def __init__(self, worker_id: int = 0):
        self.worker_id = worker_id
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

        # YouTube 추출기
        self.youtube_extractor = YouTubeExtractor()

        # Whisper 서버 URL
        self.whisper_server_url = os.getenv('WHISPER_SERVER_URL', 'http://whisper-server:8082')

        print(f"🚀 개선된 STT 워커 #{worker_id} 초기화 (GPU 전용 모드)")
        print(f"  Whisper 서버: {self.whisper_server_url}")

        # 서버 연결 확인 (실패시 종료)
        self._wait_for_whisper_server()

    def _wait_for_whisper_server(self):
        """Whisper GPU 서버 대기 - CPU 폴백 없음"""
        max_retries = 60  # 10분 대기
        retry_delay = 10

        for attempt in range(max_retries):
            try:
                response = requests.get(f"{self.whisper_server_url}/health", timeout=5)
                if response.status_code == 200:
                    info = response.json()
                    device = info.get('device', 'unknown')

                    # GPU 확인 (필수)
                    if 'cuda' not in device.lower() and 'gpu' not in device.lower():
                        print(f"  ❌ Whisper 서버가 GPU를 사용하지 않음: {device}")
                        if attempt < max_retries - 1:
                            print(f"  ⏳ {retry_delay}초 후 재확인...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            raise Exception("Whisper 서버가 GPU를 사용하지 않음")

                    print(f"  ✅ Whisper GPU 서버 연결 확인")
                    print(f"     모델: {info.get('model', 'unknown')}")
                    print(f"     디바이스: {device}")
                    return True

            except Exception as e:
                print(f"  ⚠️ Whisper 서버 연결 시도 {attempt+1}/{max_retries}: {e}")

            if attempt < max_retries - 1:
                print(f"  ⏳ {retry_delay}초 후 재시도...")
                time.sleep(retry_delay)

        # 연결 실패시 워커 종료
        print("❌ Whisper GPU 서버 연결 실패 - STT 워커를 종료합니다.")
        sys.exit(1)

    def get_db(self):
        """데이터베이스 세션 생성"""
        return self.SessionLocal()

    def _update_job_status(self, db, job: ProcessingJob, status: str, error_message: str = None):
        """작업 상태 업데이트"""
        try:
            job.status = status

            if status == 'processing':
                job.started_at = datetime.utcnow()
            elif status in ['completed', 'failed']:
                job.completed_at = datetime.utcnow()
                if error_message:
                    job.error_message = error_message

            db.commit()
            print(f"  📊 [Worker {self.worker_id}] Job {job.id} 상태: {status}")

        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] 상태 업데이트 실패: {e}")
            db.rollback()

    def process_audio_stt(self, job: ProcessingJob):
        """개선된 오디오 STT 처리 - GPU 전용"""
        print(f"🎙️ [Worker {self.worker_id}] STT 작업 처리: Job {job.id}")

        db = self.get_db()
        audio_file = None

        try:
            # 작업 상태를 processing으로 업데이트
            self._update_job_status(db, job, 'processing')

            # 콘텐츠 정보 조회
            content = db.query(Content).filter(Content.id == job.content_id).first()
            if not content:
                raise Exception("콘텐츠를 찾을 수 없습니다")

            print(f"  🎯 [Worker {self.worker_id}] 처리 중: {content.title[:50]}...")

            # 공유 디렉토리에 오디오 다운로드
            shared_temp_dir = "/tmp/shared_audio"
            os.makedirs(shared_temp_dir, exist_ok=True)

            # 오디오 다운로드
            print(f"  📥 [Worker {self.worker_id}] 오디오 다운로드 중...")
            audio_file = self._download_audio(content.url, content.external_id, shared_temp_dir)

            if not audio_file or not os.path.exists(audio_file):
                raise Exception("오디오 다운로드 실패")

            # GPU Whisper 서버로 STT 처리
            stt_result = self._process_with_gpu_whisper(audio_file, content.language)

            if stt_result:
                segments = stt_result.get('segments', [])

                # 중복 제거
                seen_hashes = set()
                unique_segments = []

                for segment in segments:
                    text_hash = hashlib.md5(segment['text'].lower().encode()).hexdigest()

                    if text_hash not in seen_hashes:
                        unique_segments.append(segment)
                        seen_hashes.add(text_hash)

                print(f"  🔧 [Worker {self.worker_id}] 세그먼트 정리: {len(segments)} -> {len(unique_segments)}")
                print(f"  💾 [Worker {self.worker_id}] {len(unique_segments)}개 세그먼트 저장 중...")

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
                content.transcript_type = 'stt_whisper_gpu'
                content.language = stt_result.get('language', content.language)

                # 벡터화 작업 추가
                vector_job = ProcessingJob(
                    job_type='vectorize',
                    content_id=content.id,
                    status='pending',
                    priority=10
                )
                db.add(vector_job)

                # 작업 완료
                self._update_job_status(db, job, 'completed')

                print(f"  ✅ [Worker {self.worker_id}] GPU STT 처리 완료: {content.title[:50]}...")

            else:
                raise Exception("STT 처리 실패")

        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] STT 처리 실패: {e}")
            self._update_job_status(db, job, 'failed', str(e))
        finally:
            # 오디오 파일 삭제
            if audio_file and os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                    print(f"  🗑️ [Worker {self.worker_id}] 임시 파일 삭제: {os.path.basename(audio_file)}")
                except:
                    pass
            db.close()

    def _download_audio(self, video_url: str, video_id: str, shared_dir: str) -> Optional[str]:
        """YouTube 오디오 다운로드 - 공유 디렉토리 사용"""
        try:
            output_template = os.path.join(shared_dir, f"{video_id}.%(ext)s")

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)

                # 다운로드된 파일 찾기
                if 'requested_downloads' in info and info['requested_downloads']:
                    filepath = info['requested_downloads'][0]['filepath']
                    if os.path.exists(filepath):
                        print(f"  ✅ [Worker {self.worker_id}] 오디오 다운로드 완료: {os.path.basename(filepath)}")
                        return filepath

            # 폴백: 파일 직접 찾기
            base_path = os.path.join(shared_dir, video_id)
            for ext in ['.webm', '.m4a', '.mp4', '.opus', '.mp3']:
                check_path = base_path + ext
                if os.path.exists(check_path):
                    print(f"  ✅ [Worker {self.worker_id}] 오디오 파일 발견: {os.path.basename(check_path)}")
                    return check_path

            return None

        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] 오디오 다운로드 실패: {e}")
            return None

    @retry(max_attempts=5, delay=10.0, backoff=2.0)
    def _process_with_gpu_whisper(self, audio_file: str, language: str = "ko") -> dict:
        """GPU Whisper 서버로만 STT 처리 - CPU 폴백 없음"""

        # 서버 상태 확인
        try:
            health_response = requests.get(f"{self.whisper_server_url}/health", timeout=5)
            if health_response.status_code != 200:
                raise Exception(f"Whisper 서버 준비되지 않음: {health_response.status_code}")

            info = health_response.json()
            device = info.get('device', 'unknown')

            # GPU 확인 (필수)
            if 'cuda' not in device.lower() and 'gpu' not in device.lower():
                raise Exception(f"Whisper 서버가 GPU를 사용하지 않음: {device}")

        except Exception as e:
            print(f"  ⚠️ [Worker {self.worker_id}] Whisper 서버 확인 실패: {e}")
            raise  # 재시도

        # STT 처리 요청
        try:
            payload = {
                "audio_path": audio_file,
                "language": language
            }

            print(f"  🚀 [Worker {self.worker_id}] GPU Whisper 서버로 요청 중...")

            response = requests.post(
                f"{self.whisper_server_url}/transcribe",
                json=payload,
                timeout=600  # 10분 타임아웃 (large 모델용)
            )

            if response.status_code == 200:
                result = response.json()
                model_info = result.get('model_info', {})

                # GPU 사용 재확인
                if 'cuda' not in str(model_info.get('device', '')).lower():
                    raise Exception(f"결과가 GPU에서 처리되지 않음: {model_info.get('device')}")

                print(f"  ✅ [Worker {self.worker_id}] GPU STT 완료")
                print(f"     모델: {model_info.get('model_name', 'unknown')}")
                print(f"     처리시간: {model_info.get('processing_time', 0):.1f}초")

                return result

            elif response.status_code == 404:
                # 파일 접근 불가 - 재시도 의미 없음
                raise Exception(f"오디오 파일 접근 실패: {audio_file}")
            else:
                # 기타 오류는 재시도
                raise Exception(f"Whisper 서버 오류: {response.status_code}")

        except requests.exceptions.Timeout:
            print(f"  ⏰ [Worker {self.worker_id}] Whisper 서버 타임아웃 - 재시도")
            raise
        except requests.exceptions.ConnectionError:
            print(f"  🔌 [Worker {self.worker_id}] Whisper 서버 연결 실패 - 재시도")
            raise
        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] Whisper 처리 실패: {e}")
            raise

    def run(self):
        """워커 메인 루프"""
        print(f"🚀 개선된 STT 워커 #{self.worker_id} 시작 (GPU 전용)")

        while True:
            db = self.get_db()
            try:
                # STT 작업 선택 (워커 ID로 파티셔닝)
                job = db.query(ProcessingJob).filter(
                    ProcessingJob.job_type == 'stt',
                    ProcessingJob.status == 'pending',
                    ProcessingJob.content_id % 3 == self.worker_id  # 워커별 분산
                ).order_by(
                    ProcessingJob.priority.desc(),
                    ProcessingJob.created_at
                ).first()

                if job:
                    print(f"\n🎯 [Worker {self.worker_id}] STT 작업 선택: Job {job.id}")
                    self.process_audio_stt(job)
                else:
                    # GPU 서버 상태 주기적 확인
                    try:
                        response = requests.get(f"{self.whisper_server_url}/health", timeout=2)
                        if response.status_code != 200:
                            print(f"  ⚠️ Whisper 서버 응답 이상: {response.status_code}")
                            time.sleep(30)
                            continue

                        info = response.json()
                        if 'cuda' not in info.get('device', '').lower():
                            print(f"  ⚠️ Whisper 서버가 GPU를 사용하지 않음!")
                            time.sleep(60)
                            continue

                    except Exception:
                        pass

                    time.sleep(5)

            except Exception as e:
                print(f"❌ [Worker {self.worker_id}] 처리 오류: {e}")
                time.sleep(10)
            finally:
                db.close()


if __name__ == "__main__":
    # 워커 ID 설정
    worker_id = int(os.getenv('STT_WORKER_ID', '0'))

    # STT 워커 실행
    worker = ImprovedSTTWorker(worker_id)
    worker.run()