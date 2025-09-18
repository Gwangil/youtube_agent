"""
재시도 메커니즘 유틸리티
"""

import time
import functools
from typing import Callable, Any, Optional, Type, Tuple
import logging

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    log_errors: bool = True
):
    """
    지수 백오프를 사용한 재시도 데코레이터

    Args:
        max_attempts: 최대 시도 횟수
        delay: 초기 대기 시간 (초)
        backoff: 백오프 배수 (각 시도마다 delay * backoff)
        exceptions: 재시도할 예외 타입들
        log_errors: 에러 로깅 여부
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if log_errors:
                        logger.warning(
                            f"[Attempt {attempt}/{max_attempts}] {func.__name__} 실패: {str(e)}"
                        )

                    if attempt < max_attempts:
                        if log_errors:
                            logger.info(f"{current_delay}초 후 재시도...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        if log_errors:
                            logger.error(
                                f"{func.__name__} 최종 실패 (시도 {max_attempts}회)"
                            )
                        raise last_exception

        return wrapper
    return decorator


def retry_with_fallback(
    max_attempts: int = 3,
    delay: float = 1.0,
    fallback: Optional[Callable] = None
):
    """
    재시도 실패 시 폴백 함수 실행

    Args:
        max_attempts: 최대 시도 횟수
        delay: 재시도 간격
        fallback: 실패 시 실행할 폴백 함수
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"[Attempt {attempt}/{max_attempts}] 실패: {str(e)}")

                    if attempt < max_attempts:
                        time.sleep(delay)
                    elif fallback:
                        logger.info(f"폴백 함수 실행: {fallback.__name__}")
                        return fallback(*args, **kwargs)
                    else:
                        raise

        return wrapper
    return decorator


class RetryableOperation:
    """재시도 가능한 작업 클래스"""

    def __init__(
        self,
        operation: Callable,
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff: float = 2.0
    ):
        self.operation = operation
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff = backoff

    def execute(self, *args, **kwargs) -> Any:
        """작업 실행 (재시도 포함)"""
        current_delay = self.delay

        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.operation(*args, **kwargs)
            except Exception as e:
                logger.warning(
                    f"[작업 시도 {attempt}/{self.max_attempts}] 실패: {str(e)}"
                )

                if attempt < self.max_attempts:
                    time.sleep(current_delay)
                    current_delay *= self.backoff
                else:
                    raise


# 일반적인 재시도 설정
quick_retry = functools.partial(retry, max_attempts=3, delay=0.5, backoff=2.0)
robust_retry = functools.partial(retry, max_attempts=5, delay=1.0, backoff=2.0)
network_retry = functools.partial(
    retry,
    max_attempts=5,
    delay=2.0,
    backoff=2.0,
    exceptions=(ConnectionError, TimeoutError, OSError)
)