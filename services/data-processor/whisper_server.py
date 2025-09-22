#!/usr/bin/env python3
"""
Whisper STT 전용 서빙 서버
GPU/CPU 자동 감지 및 모델 크기 최적화
"""

import os
import sys
import json
import re
import tempfile
import torch
import whisper
from datetime import datetime
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from pydantic import BaseModel
from typing import Optional, List, Dict
import uvicorn

app = FastAPI(title="Whisper STT Server")

class STTRequest(BaseModel):
    audio_path: str
    language: Optional[str] = "ko"

class STTResponse(BaseModel):
    segments: List[Dict]
    language: str
    model_info: Dict


class WhisperServer:
    def __init__(self):
        self.device_info = self._get_device_info()
        self.model_name = self._select_optimal_model()
        self.model = None
        self._load_model()

        print(f"🎙️ Whisper 서버 초기화 완료")
        print(f"  디바이스: {self.device_info['type']} ({self.device_info['name']})")
        print(f"  모델: {self.model_name}")
        if self.device_info['type'] == 'cuda':
            print(f"  VRAM: {self.device_info['memory']:.1f}GB")

    def _get_device_info(self) -> Dict:
        """GPU/CPU 디바이스 정보 조회"""
        device_info = {"type": "cpu", "name": "CPU", "memory": 0}

        if torch.cuda.is_available():
            device_info["type"] = "cuda"
            device_info["name"] = torch.cuda.get_device_name(0)
            device_info["memory"] = torch.cuda.get_device_properties(0).total_memory / 1024**3

        return device_info

    def _select_optimal_model(self) -> str:
        """디바이스에 따른 최적 모델 선택"""
        if self.device_info["type"] == "cuda":
            # GPU 사용 가능 시 VRAM에 따라 모델 선택
            vram_gb = self.device_info["memory"]
            if vram_gb >= 8:
                return "large-v3"  # ~3GB VRAM 사용 (최신 버전)
            elif vram_gb >= 4:
                return "medium"  # ~1.5GB VRAM 사용
            else:
                return "base"   # ~0.5GB VRAM 사용
        else:
            # CPU 모드: 속도 우선으로 작은 모델 선택
            return "base"  # 가장 빠른 처리

    def _load_model(self):
        """모델 로딩"""
        try:
            print(f"🔄 Whisper {self.model_name} 모델 로딩 중...")
            start_time = datetime.now()

            device = self.device_info["type"]

            # Whisper 캐시 디렉토리를 모델 디렉토리로 설정
            os.environ['TORCH_HOME'] = '/app/models'

            # 로컬 모델 경로 확인
            model_mapping = {
                "large-v3": "/app/models/whisper/large-v3.pt",
                "large": "/app/models/whisper/large.pt",
                "medium": "/app/models/whisper/medium.pt",
                "base": "/app/models/whisper/base.pt",
            }

            local_model_path = model_mapping.get(self.model_name)

            if local_model_path and os.path.exists(local_model_path):
                print(f"  📂 로컬 모델 사용: {local_model_path}")

                # 직접 torch.load로 모델 로드 시도
                try:
                    import torch
                    # 모델 파일 직접 로드
                    print(f"  🔧 모델 파일 직접 로드 중...")

                    # Whisper load_model을 download_root와 함께 사용
                    self.model = whisper.load_model(
                        name=self.model_name,
                        device=device,
                        download_root="/app/models/whisper",
                        in_memory=True  # 메모리에 직접 로드
                    )
                    print(f"  ✅ 로컬 모델 로드 성공")
                except Exception as load_error:
                    print(f"  ⚠️ 직접 로드 실패: {load_error}")
                    # 폴백: 캐시 디렉토리 복사 방식
                    cache_dir = os.path.expanduser("~/.cache/whisper")
                    os.makedirs(cache_dir, exist_ok=True)

                    # 파일명 매핑 (Whisper가 기대하는 해시)
                    hash_mapping = {
                        "large-v3": "large-v3.pt",  # 직접 파일명 사용
                        "large": "large-v2.pt",
                        "medium": "medium.pt",
                        "base": "base.pt",
                    }

                    cache_filename = hash_mapping.get(self.model_name, f"{self.model_name}.pt")
                    cache_path = os.path.join(cache_dir, cache_filename)

                    if not os.path.exists(cache_path):
                        import shutil
                        print(f"  📋 모델을 캐시로 복사: {cache_path}")
                        shutil.copy2(local_model_path, cache_path)

                    # 모델 로드
                    self.model = whisper.load_model(
                        self.model_name,
                        device=device
                    )
            else:
                print(f"  ⚠️ 로컬 모델 없음, 온라인에서 다운로드")
                self.model = whisper.load_model(
                    self.model_name,
                    device=device,
                    download_root="/app/models/whisper"
                )

            load_time = (datetime.now() - start_time).total_seconds()
            print(f"✅ 모델 로딩 완료 ({load_time:.1f}초)")

        except Exception as e:
            print(f"❌ 모델 로딩 실패: {e}")
            import traceback
            traceback.print_exc()

            # 폴백: 더 작은 모델로 재시도
            if self.model_name != "tiny":
                fallback_models = {"large-v3": "large", "large": "medium", "medium": "base", "base": "tiny"}
                self.model_name = fallback_models.get(self.model_name, "tiny")
                print(f"🔄 폴백 모델로 재시도: {self.model_name}")
                self._load_model()
            else:
                raise

    def _clean_repetitive_text(self, text: str) -> str:
        """반복되는 텍스트 패턴 제거"""
        if not text:
            return text

        # 연속된 동일 단어 제거 (예: "안녕 안녕 안녕" -> "안녕")
        text = re.sub(r'\b(\w+)(\s+\1\b)+', r'\1', text)

        # 연속된 동일 구문 제거 (예: "안녕하세요 안녕하세요" -> "안녕하세요")
        words = text.split()
        if len(words) < 4:
            return text

        cleaned_words = []
        i = 0
        while i < len(words):
            # 2-gram부터 5-gram까지 반복 패턴 체크
            max_pattern_length = min(5, (len(words) - i) // 2)
            pattern_found = False

            for pattern_len in range(max_pattern_length, 1, -1):
                if i + pattern_len * 2 <= len(words):
                    pattern = words[i:i+pattern_len]
                    next_pattern = words[i+pattern_len:i+pattern_len*2]

                    if pattern == next_pattern:
                        # 패턴 발견 - 한 번만 추가하고 모든 반복 건너뛰기
                        cleaned_words.extend(pattern)
                        # 연속된 모든 반복을 찾아서 제거
                        j = i + pattern_len * 2
                        while j + pattern_len <= len(words):
                            if words[j:j+pattern_len] == pattern:
                                j += pattern_len
                            else:
                                break
                        i = j
                        pattern_found = True
                        break

            if not pattern_found:
                cleaned_words.append(words[i])
                i += 1

        return ' '.join(cleaned_words)

    def _remove_repetitive_segments(self, segments: List[Dict]) -> List[Dict]:
        """반복되는 세그먼트 제거 및 텍스트 정리"""
        if not segments:
            return segments

        cleaned_segments = []
        prev_text = None
        text_history = set()

        for segment in segments:
            if "text" not in segment:
                continue

            original_text = segment["text"].strip()
            if not original_text:
                continue

            # 텍스트 정리
            cleaned_text = self._clean_repetitive_text(original_text)

            # 빈 텍스트나 너무 짧은 텍스트 필터링
            if not cleaned_text or len(cleaned_text.strip()) < 3:
                continue

            current_text_lower = cleaned_text.lower()

            # 이전 세그먼트와 완전히 동일한 경우 제외
            if prev_text and current_text_lower == prev_text:
                continue

            # 이전에 나온 텍스트와 매우 유사한 경우 제외
            if current_text_lower in text_history:
                continue

            # 유사도 체크 (80% 이상 유사하면 제외)
            is_similar = False
            for hist_text in text_history:
                if self._similarity_ratio(current_text_lower, hist_text) > 0.8:
                    is_similar = True
                    break

            if is_similar:
                continue

            # 정리된 세그먼트 추가
            cleaned_segment = segment.copy()
            cleaned_segment["text"] = cleaned_text
            cleaned_segments.append(cleaned_segment)

            # 히스토리 업데이트
            prev_text = current_text_lower
            text_history.add(current_text_lower)

            # 히스토리 크기 제한 (메모리 효율성)
            if len(text_history) > 100:
                text_history.pop()

        print(f"  🔧 세그먼트 정리: {len(segments)} -> {len(cleaned_segments)}")
        return cleaned_segments

    def _similarity_ratio(self, text1: str, text2: str) -> float:
        """두 텍스트의 유사도 계산 (0.0 ~ 1.0)"""
        if not text1 or not text2:
            return 0.0

        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        return intersection / union if union > 0 else 0.0

    def transcribe_audio(self, audio_path: str, language: str = "ko") -> Dict:
        """오디오 파일 STT 처리"""
        if not self.model:
            raise Exception("모델이 로딩되지 않았습니다")

        try:
            print(f"🎙️ STT 처리 시작: {os.path.basename(audio_path)}")
            start_time = datetime.now()

            # Whisper 처리 옵션 (강화된 반복 방지)
            options = {
                "language": language,
                "beam_size": 1,  # 할루시네이션 방지
                "best_of": 1,
                "temperature": (0.0, 0.2, 0.4, 0.6, 0.8),
                "compression_ratio_threshold": 2.0,  # 반복 텍스트 감지 (강화)
                "logprob_threshold": -0.8,  # 낮은 품질 텍스트 필터링 (강화)
                "no_speech_threshold": 0.7,  # 무음 구간 감지 강화
                "condition_on_previous_text": False,
                "initial_prompt": None  # 실제 텍스트에 포함되는 문제로 제거
            }

            raw_result = self.model.transcribe(audio_path, **options)

            # 반복 제거 후처리
            cleaned_segments = self._remove_repetitive_segments(raw_result["segments"])

            result = {
                "segments": cleaned_segments,
                "language": raw_result["language"]
            }

            process_time = (datetime.now() - start_time).total_seconds()
            print(f"✅ STT 처리 완료 ({process_time:.1f}초)")

            return {
                "segments": result["segments"],
                "language": result["language"],
                "model_info": {
                    "model_name": self.model_name,
                    "device": self.device_info["type"],
                    "processing_time": process_time
                }
            }

        except Exception as e:
            print(f"❌ STT 처리 실패: {e}")
            raise


# 전역 서버 인스턴스
whisper_server = None

@app.on_event("startup")
async def startup_event():
    global whisper_server
    if whisper_server is None:
        whisper_server = WhisperServer()

@app.get("/")
async def root():
    return {
        "service": "Whisper STT Server",
        "model": whisper_server.model_name if whisper_server else "Not loaded",
        "device": whisper_server.device_info if whisper_server else "Unknown",
        "status": "ready" if whisper_server and whisper_server.model else "loading"
    }

@app.get("/health")
async def health_check():
    if not whisper_server or not whisper_server.model:
        raise HTTPException(status_code=503, detail="모델이 로딩되지 않았습니다")

    return {
        "status": "healthy",
        "model": whisper_server.model_name,
        "device": whisper_server.device_info["type"]
    }

@app.post("/transcribe")
async def transcribe_file(
    audio: UploadFile = File(...),
    language: str = Form("ko")
):
    """파일 업로드 방식의 transcribe 엔드포인트"""
    if not whisper_server or not whisper_server.model:
        raise HTTPException(status_code=503, detail="모델이 로딩되지 않았습니다")

    import tempfile
    temp_audio_path = None

    try:
        # 업로드된 파일을 임시 파일로 저장
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            temp_audio_path = tmp_file.name
            content = await audio.read()
            tmp_file.write(content)

        # STT 처리
        result = whisper_server.transcribe_audio(temp_audio_path, language)

        # 응답 형식 변환 (stt_worker가 기대하는 형식)
        return {
            "segments": result["segments"],
            "language": result["language"],
            "text": " ".join([s.get("text", "") for s in result["segments"]])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # 임시 파일 삭제
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except:
                pass

@app.post("/transcribe_path", response_model=STTResponse)
async def transcribe_path(request: STTRequest):
    """경로 기반 transcribe 엔드포인트 (기존 방식)"""
    if not whisper_server or not whisper_server.model:
        raise HTTPException(status_code=503, detail="모델이 로딩되지 않았습니다")

    if not os.path.exists(request.audio_path):
        raise HTTPException(status_code=404, detail="오디오 파일을 찾을 수 없습니다")

    try:
        result = whisper_server.transcribe_audio(request.audio_path, request.language)
        return STTResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/model-info")
async def get_model_info():
    if not whisper_server:
        return {"status": "not_initialized"}

    return {
        "model_name": whisper_server.model_name,
        "device_info": whisper_server.device_info,
        "status": "ready" if whisper_server.model else "loading"
    }


if __name__ == "__main__":
    print("🚀 Whisper STT 서버 시작")
    # 서버 시작 전에 모델 초기화
    print("📦 Whisper 모델 사전 초기화...")
    whisper_server = WhisperServer()
    print(f"✅ Whisper 서버 준비 완료: {whisper_server.model_name} ({whisper_server.device_info['type']})")

    uvicorn.run(app, host="0.0.0.0", port=8082)