"""Tests for error handler."""

import pytest

from src.handlers.error_handler import (
    APIError,
    LLMError,
    RateLimitError,
    retry_on_error,
)


class TestExceptions:
    """Tests for custom exceptions."""

    def test_api_error(self):
        err = APIError("test error", 500)
        assert str(err) == "test error"
        assert err.status_code == 500

    def test_rate_limit_error(self):
        err = RateLimitError()
        assert err.status_code == 429

    def test_llm_error_inherits_api_error(self):
        err = LLMError("llm failed")
        assert isinstance(err, APIError)


class TestRetryDecorator:
    """Tests for retry_on_error decorator."""

    def test_success_first_attempt(self):
        call_count = 0

        @retry_on_error(max_retries=3, delay=0.01, exceptions=(APIError,))
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    def test_retry_then_succeed(self):
        call_count = 0

        @retry_on_error(max_retries=3, delay=0.01, exceptions=(APIError,))
        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise APIError("temporary failure")
            return "ok"

        assert fail_twice() == "ok"
        assert call_count == 3

    def test_exhausted_retries(self):
        @retry_on_error(max_retries=2, delay=0.01, exceptions=(APIError,))
        def always_fail():
            raise APIError("permanent failure")

        with pytest.raises(APIError, match="permanent failure"):
            always_fail()

    def test_non_matching_exception(self):
        @retry_on_error(max_retries=3, delay=0.01, exceptions=(APIError,))
        def raise_value_error():
            raise ValueError("not an API error")

        with pytest.raises(ValueError):
            raise_value_error()

    def test_backoff_multiplier(self):
        call_count = 0

        @retry_on_error(max_retries=2, delay=0.01, backoff=2.0, exceptions=(APIError,))
        def fail_all():
            nonlocal call_count
            call_count += 1
            raise APIError("fail")

        with pytest.raises(APIError):
            fail_all()
        assert call_count == 3  # initial + 2 retries
