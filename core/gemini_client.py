import json
import logging
import time
from threading import Lock
from typing import Any, Optional, Type, TypeVar
from pydantic import BaseModel
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)
from google import genai
from google.genai import types
from google.genai.errors import APIError, ServerError

from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class RateLimiter:
    """Sliding-window and interval rate limiter for Gemini Free Tier."""

    def __init__(self, max_rpm: int = 12, min_delay_seconds: float = 4.0):
        self.max_rpm = max_rpm
        self.min_delay_seconds = min_delay_seconds
        self.request_timestamps: list[float] = []
        self._lock = Lock()
        self._last_call_time = 0.0

    def wait(self) -> None:
        """Blocks until it is safe to make another request under the rate limit."""
        with self._lock:
            now = time.time()

            # 1. Enforce minimum delay between consecutive calls
            elapsed = now - self._last_call_time
            if elapsed < self.min_delay_seconds:
                sleep_needed = self.min_delay_seconds - elapsed
                time.sleep(sleep_needed)
                now = time.time()

            # 2. Enforce sliding 60-second window (max_rpm)
            window_start = now - 60.0
            self.request_timestamps = [t for t in self.request_timestamps if t > window_start]

            if len(self.request_timestamps) >= self.max_rpm:
                oldest = self.request_timestamps[0]
                sleep_needed = 60.0 - (now - oldest) + 0.1
                if sleep_needed > 0:
                    logger.warning(
                        f"Rate limit threshold reached ({self.max_rpm} RPM). "
                        f"Throttling for {sleep_needed:.2f}s..."
                    )
                    time.sleep(sleep_needed)
                    now = time.time()
                self.request_timestamps = [t for t in self.request_timestamps if t > (now - 60.0)]

            self.request_timestamps.append(now)
            self._last_call_time = now


class UsageStats(BaseModel):
    """Tracks token and request metrics for observability."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_prompt_tokens: int = 0
    total_candidates_tokens: int = 0


def is_retryable_error(exc: BaseException) -> bool:
    """Determines whether an exception is temporary (e.g. rate limit, 503, connection error)."""
    if isinstance(exc, (ServerError, ConnectionError, TimeoutError)):
        return True
    if isinstance(exc, APIError):
        # Retry on 429 (ResourceExhausted) or 503 (Unavailable)
        if exc.code in (429, 503, 500, 504) or "quota" in str(exc).lower() or "resource" in str(exc).lower():
            return True
    return False


class GeminiClient:
    """Production client wrapper around Google GenAI SDK with free-tier resilience."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.rate_limiter = RateLimiter(
            max_rpm=self.settings.gemini_max_rpm,
            min_delay_seconds=self.settings.gemini_request_delay_seconds,
        )
        self.usage = UsageStats()
        self._client: Optional[genai.Client] = None

        if self.is_configured:
            self._client = genai.Client(api_key=self.settings.gemini_api_key)

    @property
    def is_configured(self) -> bool:
        """Returns True if a valid-looking API key is present."""
        return bool(self.settings.gemini_api_key and self.settings.gemini_api_key != "your_gemini_api_key_here")

    def _ensure_client(self) -> genai.Client:
        if not self._client:
            if not self.is_configured:
                raise ValueError(
                    "Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file.\n"
                    "Get your free key from: https://aistudio.google.com/app/apikey"
                )
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def _call_with_fallback(
        self,
        contents: str,
        config: types.GenerateContentConfig,
        model: Optional[str] = None,
    ) -> Any:
        """Invokes generate_content with automatic retry and model fallback on 503/404."""
        primary_model = model or self.settings.gemini_model
        fallback_model = self.settings.gemini_fallback_model

        @retry(
            retry=retry_if_exception(is_retryable_error),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=3, max=15),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _invoke(target_model: str):
            client = self._ensure_client()
            self.rate_limiter.wait()
            self.usage.total_calls += 1
            return client.models.generate_content(
                model=target_model,
                contents=contents,
                config=config,
            )

        try:
            return _invoke(primary_model)
        except Exception as exc:
            # If primary model fails with 503 (high demand) or 404 (unavailable), try fallback model
            if fallback_model and fallback_model != primary_model and isinstance(exc, (ServerError, APIError)):
                logger.warning(
                    f"Model '{primary_model}' encountered {type(exc).__name__}: {exc}. "
                    f"Falling back to '{fallback_model}'..."
                )
                return _invoke(fallback_model)
            raise

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        """Generates plain text response (e.g. cover letters, resume sections)."""
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
        )

        try:
            response = self._call_with_fallback(
                contents=prompt,
                config=config,
                model=model,
            )
            self.usage.successful_calls += 1
            if response.usage_metadata:
                self.usage.total_prompt_tokens += response.usage_metadata.prompt_token_count or 0
                self.usage.total_candidates_tokens += response.usage_metadata.candidates_token_count or 0

            return response.text or ""
        except Exception as e:
            self.usage.failed_calls += 1
            logger.error(f"Gemini API call failed: {e}")
            raise

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
        model: Optional[str] = None,
    ) -> T:
        """Generates structured response strictly adhering to a Pydantic schema."""
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=schema,
        )

        try:
            response = self._call_with_fallback(
                contents=prompt,
                config=config,
                model=model,
            )
            self.usage.successful_calls += 1
            if response.usage_metadata:
                self.usage.total_prompt_tokens += response.usage_metadata.prompt_token_count or 0
                self.usage.total_candidates_tokens += response.usage_metadata.candidates_token_count or 0

            raw_text = response.text or "{}"
            parsed_data = json.loads(raw_text)
            return schema.model_validate(parsed_data)
        except Exception as e:
            self.usage.failed_calls += 1
            logger.error(f"Gemini structured generation failed: {e}")
            raise
