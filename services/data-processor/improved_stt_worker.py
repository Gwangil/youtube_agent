#!/usr/bin/env python3
"""
개선된 STT 워커
Whisper 서빙 서버와 통신하여 효율적인 STT 처리
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
    """개선된 STT 워커 - Whisper 서버 클라이언트"""

    def __init__(self, worker_id: int = 0):
        self.worker_id = worker_id
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

        # YouTube 추출기
        self.youtube_extractor = YouTubeExtractor()

        # Whisper 서버 URL
        self.whisper_server_url = os.getenv('WHISPER_SERVER_URL', 'http://localhost:8082')

        print(f"🚀 개선된 STT 워커 #{worker_id} 초기화 완료")
        print(f"  Whisper 서버: {self.whisper_server_url}")

        # 서버 연결 확인
        self._check_whisper_server()

    def _check_whisper_server(self):
        """Whisper 서버 연결 상태 확인 - 실패시 대기"""
        max_retries = 30
        retry_delay = 10

        for attempt in range(max_retries):
            try:
                response = requests.get(f"{self.whisper_server_url}/health", timeout=5)
                if response.status_code == 200:
                    info = response.json()
                    device = info.get('device', 'unknown')

                    # GPU 확인
                    if 'cuda' not in device.lower() and 'gpu' not in device.lower():
                        print(f"  ❌ Whisper 서버가 GPU를 사용하지 않음: {device}")
                        raise Exception("GPU가 아닌 디바이스")

                    print(f"  ✅ Whisper 서버 연결됨 - 모델: {info.get('model', 'unknown')}, 디바이스: {device}")
                    return True
                else:
                    print(f"  ⚠️ Whisper 서버 응답 오류: {response.status_code}")
            except Exception as e:
                print(f"  ⚠️ Whisper 서버 연결 시도 {attempt+1}/{max_retries} 실패: {e}")

            if attempt < max_retries - 1:
                print(f"  ⏳ {retry_delay}초 후 재시도...")
                time.sleep(retry_delay)

        raise Exception("❌ Whisper GPU 서버 연결 실패 - STT 워커를 종료합니다.")

    def get_db(self):
        """데이터베이스 세션 생성"""
        return self.SessionLocal()

    def _update_job_status(self, db, job: ProcessingJob, status: str, error_message: str = None):
        """작업 상태 업데이트 (즉시 DB 반영)"""
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
        """개선된 오디오 STT 처리"""
        print(f"🎙️ [Worker {self.worker_id}] STT 작업 처리: Job {job.id}")

        db = self.get_db()
        try:
            # 작업 상태를 processing으로 즉시 업데이트
            self._update_job_status(db, job, 'processing')

            # 콘텐츠 정보 조회
            content = db.query(Content).filter(Content.id == job.content_id).first()
            if not content:
                raise Exception("콘텐츠를 찾을 수 없습니다")

            print(f"  🎯 [Worker {self.worker_id}] 처리 중: {content.title[:50]}...")

            # 오디오 파일을 공유 디렉토리에 다운로드
            print(f"  📥 [Worker {self.worker_id}] 오디오 다운로드 중...")

            # 공유 임시 디렉토리 사용 (/tmp는 docker-compose에서 마운트됨)
            shared_temp_dir = "/tmp/shared_audio"
            os.makedirs(shared_temp_dir, exist_ok=True)

            # 오디오 파일 다운로드를 공유 디렉토리로
            audio_filename = f"{content.external_id}_{self.worker_id}.m4a"
            audio_file = os.path.join(shared_temp_dir, audio_filename)

            # 기존 파일이 있으면 삭제
            if os.path.exists(audio_file):
                os.remove(audio_file)

            # YouTube에서 직접 다운로드 (공유 경로에)
            audio_file = self._download_audio_to_shared(content.url, content.external_id, shared_temp_dir)

            if not audio_file or not os.path.exists(audio_file):
                raise Exception("오디오 다운로드 실패")

            # Whisper 서버로 STT 처리 요청 (실패시 작업 실패 처리)
            try:
                stt_result = self._process_with_whisper_server(audio_file, content.language)
            except Exception as e:
                # Whisper 서버 처리 실패시 작업을 다시 대기 상태로
                self._update_job_status(db, job, 'pending')
                print(f"  ⏳ [Worker {self.worker_id}] 작업을 대기 큐로 반환: {e}")
                # 30초 대기 후 다른 작업 처리
                time.sleep(30)
                return

            if stt_result:
                segments = stt_result.get('segments', [])

                # 세그먼트 중복 제거 (해시 기반)
                seen_hashes = set()
                unique_segments = []

                for segment in segments:
                    # 텍스트 해시 생성 (중복 감지용)
                    text_hash = hashlib.md5(segment['text'].lower().encode()).hexdigest()

                    if text_hash not in seen_hashes:
                        unique_segments.append(segment)
                        seen_hashes.add(text_hash)

                print(f"  🔧 [Worker {self.worker_id}] 세그먼트 중복 제거: {len(segments)} -> {len(unique_segments)}")
                print(f"  💾 [Worker {self.worker_id}] {len(unique_segments)}개 세그먼트 저장 중...")

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

                # 벡터화 작업 큐에 추가 (높은 우선순위)
                vector_job = ProcessingJob(
                    job_type='vectorize',
                    content_id=content.id,
                    status='pending',
                    priority=10  # 높은 우선순위
                )
                db.add(vector_job)

                # 작업 완료
                self._update_job_status(db, job, 'completed')

                print(f"  ✅ [Worker {self.worker_id}] STT 처리 완료: {content.title[:50]}...")

                # 임시 오디오 파일 삭제
                try:
                    if os.path.exists(audio_file):
                        os.remove(audio_file)
                except:
                    pass

            else:
                raise Exception("STT 처리 실패")

        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] STT 처리 실패: {e}")
            self._update_job_status(db, job, 'failed', str(e))
        finally:
            db.close()

    def _download_audio_to_shared(self, video_url: str, video_id: str, shared_dir: str) -> Optional[str]:
        """YouTube 오디오를 공유 디렉토리에 다운로드"""
        import yt_dlp

        try:
            # 출력 템플릿 (확장자는 자동으로 결정됨)
            output_template = os.path.join(shared_dir, f"{video_id}.%(ext)s")

            # 간단한 설정 - 후처리 없이 직접 다운로드
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
            }

            # 다운로드 실행
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)

                # 실제 다운로드된 파일명 가져오기
                if 'requested_downloads' in info and info['requested_downloads']:
                    filepath = info['requested_downloads'][0]['filepath']
                    if os.path.exists(filepath):
                        print(f"  ✅ [Worker {self.worker_id}] 오디오 다운로드 완료: {os.path.basename(filepath)}")
                        return filepath

            # 폴백: 알려진 확장자로 파일 찾기
            base_path = os.path.join(shared_dir, video_id)
            for ext in ['.webm', '.m4a', '.mp4', '.opus', '.mp3']:
                check_path = base_path + ext
                if os.path.exists(check_path):
                    print(f"  ✅ [Worker {self.worker_id}] 오디오 파일 발견: {os.path.basename(check_path)}")
                    return check_path

            return None

        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] 오디오 다운로드 실패: {e}")
            import traceback
            traceback.print_exc()
            return None

    @retry(max_attempts=3, delay=2.0, backoff=2.0)
    def _process_with_whisper_server(self, audio_file: str, language: str = "ko") -> dict:
        """Whisper 서버로 STT 처리 요청 (재시도 포함)"""
        # 먼저 Whisper 서버가 준비되었는지 확인
        try:
            health_response = requests.get(f"{self.whisper_server_url}/health", timeout=2)
            if health_response.status_code == 200:
                info = health_response.json()
                device = info.get('device', 'unknown')
                model = info.get('model', 'unknown')
                print(f"  ✅ [Worker {self.worker_id}] GPU Whisper 서버 사용 가능: {model} 모델, {device}")
            else:
                raise requests.exceptions.ConnectionError("Whisper server not ready")
        except Exception as e:
            print(f"  ⚠️ [Worker {self.worker_id}] Whisper 서버 연결 실패, OpenAI API로 폴백: {e}")
            return self._process_locally(audio_file, language)

        try:
            # Whisper 서버 요청
            payload = {
                "audio_path": audio_file,
                "language": language
            }

            response = requests.post(
                f"{self.whisper_server_url}/transcribe",
                json=payload,
                timeout=300  # 5분 타임아웃
            )

            if response.status_code == 200:
                result = response.json()
                model_info = result.get('model_info', {})
                print(f"  🎙️ [Worker {self.worker_id}] GPU Whisper 처리 완료: {model_info.get('model_name', 'unknown')} 모델, {model_info.get('processing_time', 0):.1f}초")
                return result
            elif response.status_code == 404:
                print(f"  ❌ [Worker {self.worker_id}] Whisper 서버 오디오 파일 접근 실패: {audio_file}")
                print(f"  🔄 [Worker {self.worker_id}] OpenAI API로 폴백")
                return self._process_locally(audio_file, language)
            else:
                print(f"  ❌ [Worker {self.worker_id}] Whisper 서버 오류: {response.status_code}")
                return self._process_locally(audio_file, language)

        except requests.exceptions.ConnectionError:
            print(f"  ❌ [Worker {self.worker_id}] Whisper 서버 연결 실패 - OpenAI API로 폴백")
            return self._process_locally(audio_file, language)
        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] Whisper 서버 요청 실패: {e}")
            return self._process_locally(audio_file, language)

    def _process_locally(self, audio_file: str, language: str = "ko") -> dict:
        """OpenAI Whisper API 처리 (GPU 서버 실패시 폴백)"""
        try:
            from openai import OpenAI
            import os

            # OpenAI API 설정
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OpenAI API Key not configured")

            print(f"  🌐 [Worker {self.worker_id}] OpenAI Whisper API로 처리 중...")

            client = OpenAI(api_key=api_key)

            # 오디오 파일 열기
            with open(audio_file, "rb") as audio:
                # OpenAI Whisper API 호출
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio,
                    language=language,
                    response_format="verbose_json",
                    temperature=0.2
                )

            # 응답을 Whisper 서버 형식으로 변환
            segments = []
            if hasattr(response, 'segments'):
                for seg in response.segments:
                    segments.append({
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text
                    })
            else:
                # 전체 텍스트만 있는 경우
                segments.append({
                    "start": 0,
                    "end": response.duration if hasattr(response, 'duration') else 0,
                    "text": response.text
                })

            print(f"  ✅ [Worker {self.worker_id}] OpenAI Whisper API 처리 완료")

            return {
                "segments": segments,
                "language": language,
                "model_info": {
                    "model_name": "whisper-1",
                    "device": "openai_cloud",
                    "processing_mode": "openai_api"
                }
            }

        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] OpenAI API 처리 실패: {e}")
            return None

    def start_worker(self):
        """STT 워커 시작"""
        print(f"🚀 개선된 STT 워커 #{self.worker_id} 시작")

        while True:
            try:
                db = self.get_db()

                # STT 작업만 조회 (우선순위 높은 순)
                stt_jobs = db.query(ProcessingJob).filter(
                    ProcessingJob.job_type == 'process_audio',
                    ProcessingJob.status == 'pending'
                ).order_by(
                    ProcessingJob.priority.desc(),
                    ProcessingJob.created_at
                ).limit(1).all()

                if stt_jobs:
                    for job in stt_jobs:
                        print(f"\n🎯 [Worker {self.worker_id}] STT 작업 선택: Job {job.id}")
                        self.process_audio_stt(job)
                        time.sleep(2)  # 작업 간 짧은 대기
                else:
                    print(f"📭 [Worker {self.worker_id}] 대기 중인 STT 작업 없음")

                db.close()
                time.sleep(10)  # 10초마다 확인

            except KeyboardInterrupt:
                print(f"🛑 STT 워커 #{self.worker_id} 종료")
                break
            except Exception as e:
                print(f"❌ [Worker {self.worker_id}] 워커 오류: {e}")
                time.sleep(30)


def main():
    """메인 실행 함수"""
    # 워커 ID를 환경변수나 CLI 인자로 받기
    worker_id = int(os.getenv('STT_WORKER_ID', sys.argv[1] if len(sys.argv) > 1 else 0))

    worker = ImprovedSTTWorker(worker_id)
    worker.start_worker()


if __name__ == "__main__":
    main()