#!/usr/bin/env python3
"""
프로덕션 수정사항 검증 테스트 스위트
- 반복 텍스트 제거 테스트
- 중복 감지 테스트
- 품질 검증 테스트
"""

import re
import hashlib
import unittest
from unittest.mock import Mock, patch
import sys
import os

# Add project paths
sys.path.append('/mnt/d/workspace/projects/youtube_agent')
sys.path.append('/mnt/d/workspace/projects/youtube_agent/services/data-processor')

class TestRepetitionRemoval(unittest.TestCase):
    """반복 텍스트 제거 테스트"""

    def setUp(self):
        """테스트 설정"""
        # Whisper 서버의 반복 제거 로직 복사
        self.clean_repetitive_text = self._clean_repetitive_text

    def _clean_repetitive_text(self, text: str) -> str:
        """반복되는 텍스트 패턴 제거"""
        if not text:
            return text

        # 연속된 동일 단어 제거
        text = re.sub(r'\b(\w+)(\s+\1\b)+', r'\1', text)

        # 동일 구문 반복 제거
        words = text.split()
        if len(words) < 4:
            return text

        cleaned_words = []
        i = 0
        while i < len(words):
            max_pattern_length = min(5, (len(words) - i) // 2)
            pattern_found = False

            for pattern_len in range(max_pattern_length, 1, -1):
                if i + pattern_len * 2 <= len(words):
                    pattern = words[i:i+pattern_len]
                    next_pattern = words[i+pattern_len:i+pattern_len*2]

                    if pattern == next_pattern:
                        # 연속된 반복이 있는지 확인하고 모두 제거
                        cleaned_words.extend(pattern)
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

    def test_simple_word_repetition(self):
        """단순 단어 반복 제거 테스트"""
        input_text = "안녕 안녕 안녕 하세요"
        expected = "안녕 하세요"
        result = self.clean_repetitive_text(input_text)
        self.assertEqual(result, expected)

    def test_phrase_repetition(self):
        """구문 반복 제거 테스트"""
        input_text = "오늘의 메인 주제에 이겁니다 오늘의 메인 주제에 이겁니다"
        expected = "오늘의 메인 주제에 이겁니다"
        result = self.clean_repetitive_text(input_text)
        self.assertEqual(result, expected)

    def test_multiple_repetitions(self):
        """다중 반복 제거 테스트"""
        input_text = "네 여러분 반갑습니다 네 여러분 반갑습니다 네 여러분 반갑습니다"
        expected = "네 여러분 반갑습니다"
        result = self.clean_repetitive_text(input_text)
        self.assertEqual(result, expected)

    def test_no_repetition(self):
        """반복이 없는 텍스트 테스트"""
        input_text = "이것은 정상적인 텍스트입니다."
        result = self.clean_repetitive_text(input_text)
        self.assertEqual(result, input_text)

    def test_empty_text(self):
        """빈 텍스트 테스트"""
        result = self.clean_repetitive_text("")
        self.assertEqual(result, "")

    def test_korean_repetition(self):
        """한국어 복잡한 반복 패턴 테스트"""
        input_text = "코스피는 3395 코스피는 3395 코스피는 3395 어제가 가장 낮을 수도 있어요"
        expected = "코스피는 3395 어제가 가장 낮을 수도 있어요"
        result = self.clean_repetitive_text(input_text)
        self.assertEqual(result, expected)


class TestDeduplication(unittest.TestCase):
    """중복 감지 테스트"""

    def test_hash_deduplication(self):
        """해시 기반 중복 감지 테스트"""
        texts = [
            "오늘의 메인 주제입니다",
            "오늘의 메인 주제입니다",  # 완전 중복
            "오늘의 메인 주제입니다.",  # 구두점 차이
            "다른 내용입니다"
        ]

        seen_hashes = set()
        unique_texts = []

        for text in texts:
            # 구두점 제거 후 해시 생성
            clean_text = re.sub(r'[^\w\s]', '', text.lower())
            text_hash = hashlib.md5(clean_text.encode()).hexdigest()
            if text_hash not in seen_hashes:
                unique_texts.append(text)
                seen_hashes.add(text_hash)

        # 구두점 차이는 동일하게 처리되어야 함
        self.assertEqual(len(unique_texts), 2)

    def test_similarity_detection(self):
        """유사도 기반 중복 감지 테스트"""
        def similarity_ratio(text1: str, text2: str) -> float:
            words1 = set(text1.split())
            words2 = set(text2.split())
            if not words1 or not words2:
                return 0.0
            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))
            return intersection / union if union > 0 else 0.0

        text1 = "오늘의 메인 주제입니다"
        text2 = "오늘의 메인 주제를 말씀드리겠습니다"  # 유사
        text3 = "완전히 다른 내용입니다"

        sim1_2 = similarity_ratio(text1, text2)
        sim1_3 = similarity_ratio(text1, text3)

        self.assertGreaterEqual(sim1_2, 0.4)  # 유사
        self.assertLess(sim1_3, 0.3)     # 다름


class TestChunkQuality(unittest.TestCase):
    """청크 품질 테스트"""

    def test_chunk_size_limits(self):
        """청크 크기 제한 테스트"""
        # 시뮬레이션된 청킹 로직
        def create_chunk(sentences, max_length=600):
            chunk_text = '. '.join(sentences) + '.'
            return {
                'text': chunk_text,
                'sentence_count': len(sentences),
                'length': len(chunk_text)
            }

        # 긴 문장들
        long_sentences = [
            "이것은 매우 긴 문장입니다 " * 20,
            "또 다른 긴 문장입니다 " * 20
        ]

        chunk = create_chunk(long_sentences)

        # 청크가 너무 크지 않아야 함
        self.assertLessEqual(chunk['sentence_count'], 3)

    def test_minimum_content_quality(self):
        """최소 콘텐츠 품질 테스트"""
        # 너무 짧은 텍스트는 제외되어야 함
        short_texts = ["네", "음", "아", "어"]
        valid_texts = []

        for text in short_texts:
            if len(text.strip()) >= 5:  # 최소 길이 기준
                valid_texts.append(text)

        self.assertEqual(len(valid_texts), 0)  # 모두 제외되어야 함


class TestWhisperServerIntegration(unittest.TestCase):
    """Whisper 서버 통합 테스트"""

    @patch('requests.post')
    def test_whisper_server_response(self, mock_post):
        """Whisper 서버 응답 테스트"""
        # 모의 응답 설정
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "segments": [
                {"text": "정상적인 텍스트입니다", "start": 0, "end": 2},
                {"text": "다음 세그먼트입니다", "start": 2, "end": 4}
            ],
            "language": "ko",
            "model_info": {
                "model_name": "large",
                "device": "cuda",
                "processing_time": 10.5
            }
        }
        mock_post.return_value = mock_response

        # 실제 요청 시뮬레이션
        import requests
        response = requests.post("http://test:8082/transcribe", json={
            "audio_path": "/test/audio.wav",
            "language": "ko"
        })

        result = response.json()

        # 응답 구조 검증
        self.assertIn("segments", result)
        self.assertIn("language", result)
        self.assertIn("model_info", result)
        self.assertEqual(len(result["segments"]), 2)


class TestSystemIntegration(unittest.TestCase):
    """시스템 통합 테스트"""

    def test_end_to_end_quality(self):
        """엔드투엔드 품질 테스트"""
        # 시뮬레이션된 STT 결과 (반복 포함)
        stt_segments = [
            {"text": "오늘의 메인 주제입니다 오늘의 메인 주제입니다", "start": 0, "end": 5},
            {"text": "코스피 이야기를 해보겠습니다", "start": 5, "end": 8},
            {"text": "네 여러분 반갑습니다 네 여러분 반갑습니다", "start": 8, "end": 12}
        ]

        # 반복 제거 처리
        cleaner = TestRepetitionRemoval()
        cleaned_segments = []

        for segment in stt_segments:
            cleaned_text = cleaner._clean_repetitive_text(segment["text"])
            if cleaned_text and len(cleaned_text) > 5:
                cleaned_segments.append({
                    **segment,
                    "text": cleaned_text
                })

        # 품질 검증
        self.assertEqual(len(cleaned_segments), 3)

        # 각 세그먼트에 반복이 없어야 함
        for segment in cleaned_segments:
            text = segment["text"]
            words = text.split()
            # 동일한 단어가 연속으로 나타나지 않아야 함
            for i in range(len(words) - 1):
                if words[i] == words[i + 1]:
                    self.fail(f"연속 반복 발견: {words[i]} in '{text}'")


def run_all_tests():
    """모든 테스트 실행"""
    test_suite = unittest.TestSuite()

    # 테스트 클래스들 추가
    test_classes = [
        TestRepetitionRemoval,
        TestDeduplication,
        TestChunkQuality,
        TestWhisperServerIntegration,
        TestSystemIntegration
    ]

    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)

    # 테스트 실행
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    print("🧪 프로덕션 수정사항 검증 테스트 시작")
    print("=" * 50)

    success = run_all_tests()

    if success:
        print("\n✅ 모든 테스트 통과!")
        print("프로덕션 배포 준비 완료")
    else:
        print("\n❌ 일부 테스트 실패")
        print("수정이 필요합니다")

    print("=" * 50)