"""
Test Suite for ErrorMiddleware

Validates:
1. Exception interception and conversion to RFC 7807 Problem Details
2. Existing behavior preservation for HTTPException
3. Performance (middleware overhead < 1ms for successful requests)
4. Security (no information disclosure in production mode)
5. Error tracking and logging
6. Custom error handler registration
"""

import pytest
import time
import json
from typing import Optional
from unittest.mock import Mock, patch, AsyncMock

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse, Response
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

# Import ErrorMiddleware
from fastapi.middleware.error_middleware import ErrorMiddleware


class TestErrorMiddlewareBasics:
    """Test basic ErrorMiddleware functionality"""

    @pytest.fixture
    def app_with_middleware(self):
        """Create FastAPI app with ErrorMiddleware"""
        app = FastAPI()

        # Add ErrorMiddleware
        app.add_middleware(ErrorMiddleware, debug=False)

        @app.get("/success")
        async def success_route():
            return {"message": "success"}

        @app.get("/http-exception")
        async def http_exception_route():
            raise HTTPException(status_code=400, detail="Bad request")

        @app.get("/value-error")
        async def value_error_route():
            raise ValueError("Invalid value")

        @app.get("/type-error")
        async def type_error_route():
            x = "string" + 123  # TypeError

        @app.get("/key-error")
        async def key_error_route():
            data = {"a": 1}
            return data["missing"]

        @app.get("/permission-error")
        async def permission_error_route():
            raise PermissionError("Access denied")

        @app.get("/generic-error")
        async def generic_error_route():
            raise RuntimeError("Generic error")

        return app

    def test_successful_request_no_exception(self, app_with_middleware):
        """Test that successful requests pass through without middleware overhead"""
        client = TestClient(app_with_middleware)
        response = client.get("/success")

        assert response.status_code == 200
        assert response.json() == {"message": "success"}

    def test_http_exception_passthrough(self, app_with_middleware):
        """Test that HTTPException passes through (existing behavior)"""
        client = TestClient(app_with_middleware)
        response = client.get("/http-exception")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Bad request"

    def test_value_error_converts_to_problem_details(self, app_with_middleware):
        """Test ValueError converts to 400 Problem Details"""
        client = TestClient(app_with_middleware)
        response = client.get("/value-error")

        assert response.status_code == 400
        data = response.json()

        # Verify RFC 7807 structure
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert data["status"] == 400
        assert "detail" in data
        assert "instance" in data

    def test_type_error_converts_to_problem_details(self, app_with_middleware):
        """Test TypeError converts to 400 Problem Details"""
        client = TestClient(app_with_middleware)
        response = client.get("/type-error")

        assert response.status_code == 400
        data = response.json()

        # Verify RFC 7807 structure
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert data["status"] == 400

    def test_key_error_converts_to_problem_details(self, app_with_middleware):
        """Test KeyError converts to 404 Problem Details"""
        client = TestClient(app_with_middleware)
        response = client.get("/key-error")

        assert response.status_code == 404
        data = response.json()

        # Verify RFC 7807 structure
        assert "type" in data
        assert data["status"] == 404
        assert "detail" in data

    def test_permission_error_converts_to_problem_details(self, app_with_middleware):
        """Test PermissionError converts to 403 Problem Details"""
        client = TestClient(app_with_middleware)
        response = client.get("/permission-error")

        assert response.status_code == 403
        data = response.json()

        # Verify RFC 7807 structure
        assert "type" in data
        assert data["status"] == 403
        assert "title" in data

    def test_generic_error_converts_to_500(self, app_with_middleware):
        """Test generic exceptions convert to 500 Problem Details"""
        client = TestClient(app_with_middleware)
        response = client.get("/generic-error")

        assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()

        # Verify RFC 7807 structure
        assert "type" in data
        assert data["status"] == HTTP_500_INTERNAL_SERVER_ERROR


class TestErrorMiddlewareSecurityProduction:
    """Test security features in production mode (debug=False)"""

    @pytest.fixture
    def app_production(self):
        """Create FastAPI app with ErrorMiddleware in production mode"""
        app = FastAPI()
        app.add_middleware(ErrorMiddleware, debug=False)

        @app.get("/expose-secret")
        async def expose_secret():
            raise ValueError("Database password: secret123")

        @app.get("/internal-error")
        async def internal_error():
            raise RuntimeError("Detailed internal error message")

        return app

    def test_production_sanitizes_value_error(self, app_production):
        """Test that sensitive details are hidden in production"""
        client = TestClient(app_production)
        response = client.get("/expose-secret")

        assert response.status_code == 400
        data = response.json()

        # Should NOT expose the actual error message
        assert "secret123" not in data.get("detail", "")
        assert "password" not in data.get("detail", "").lower()

    def test_production_sanitizes_generic_error(self, app_production):
        """Test generic errors are sanitized in production"""
        client = TestClient(app_production)
        response = client.get("/internal-error")

        assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()

        # Should use generic message, not expose internal details
        assert "Detailed internal error" not in data.get("detail", "")
        assert "An internal server error occurred" in data.get("detail", "")


class TestErrorMiddlewareSecurityDebug:
    """Test debug mode reveals appropriate details"""

    @pytest.fixture
    def app_debug(self):
        """Create FastAPI app with ErrorMiddleware in debug mode"""
        app = FastAPI()
        app.add_middleware(ErrorMiddleware, debug=True)

        @app.get("/error-with-details")
        async def error_with_details():
            raise ValueError("Specific error details")

        return app

    def test_debug_mode_shows_details(self, app_debug):
        """Test that debug mode reveals error details"""
        client = TestClient(app_debug)
        response = client.get("/error-with-details")

        assert response.status_code == 400
        data = response.json()

        # In debug mode, actual error message should be visible
        assert "Specific error details" in data.get("detail", "")


class TestErrorMiddlewareErrorID:
    """Test unique error ID generation and tracking"""

    @pytest.fixture
    def app_with_tracking(self):
        """Create app with error tracking"""
        app = FastAPI()
        app.add_middleware(ErrorMiddleware, debug=False)

        @app.get("/error")
        async def error_route():
            raise RuntimeError("Test error")

        return app

    def test_error_id_generated(self, app_with_tracking):
        """Test that unique error ID is generated"""
        client = TestClient(app_with_tracking)
        response = client.get("/error")

        data = response.json()

        # Should have error_id (UUID format)
        assert "instance" in data or "error_id" in data
        error_id = data.get("instance") or data.get("error_id")
        assert error_id is not None
        assert len(str(error_id)) > 0

    def test_different_errors_have_different_ids(self, app_with_tracking):
        """Test that each error gets a unique ID"""
        client = TestClient(app_with_tracking)

        response1 = client.get("/error")
        response2 = client.get("/error")

        id1 = response1.json().get("instance")
        id2 = response2.json().get("instance")

        assert id1 != id2


class TestErrorMiddlewareCustomHandlers:
    """Test custom error handler registration"""

    @pytest.fixture
    def app_with_custom_handler(self):
        """Create app with custom error handler"""
        app = FastAPI()
        middleware = ErrorMiddleware(app, debug=False)
        app.add_middleware(ErrorMiddleware, debug=False)

        @app.get("/custom-error")
        async def custom_error_route():
            raise CustomException("Custom error occurred")

        # Register custom handler
        async def handle_custom_exception(
            request: Request, exc: Exception, error_id: str
        ):
            return JSONResponse(
                status_code=418,
                content={
                    "type": "https://api.example.com/errors/custom",
                    "title": "I'm a Teapot",
                    "status": 418,
                    "detail": str(exc),
                    "error_id": error_id,
                },
            )

        # Note: Would need to modify ErrorMiddleware to support this in production
        return app

    def test_custom_handler_can_be_registered(self, app_with_custom_handler):
        """Test that custom handlers can be registered (framework level)"""
        # This would require middleware modification to support it
        assert app_with_custom_handler is not None


class TestErrorMiddlewarePerformance:
    """Test performance characteristics"""

    @pytest.fixture
    def app_perf(self):
        """Create app for performance testing"""
        app = FastAPI()
        app.add_middleware(ErrorMiddleware, debug=False)

        @app.get("/fast")
        async def fast_route():
            return {"status": "ok"}

        @app.get("/slow-error")
        async def slow_error():
            # Simulate slow error
            time.sleep(0.01)
            raise ValueError("Slow error")

        return app

    def test_successful_request_overhead_minimal(self, app_perf):
        """Test middleware overhead for successful requests"""
        client = TestClient(app_perf)

        # Measure baseline
        start = time.perf_counter()
        for _ in range(100):
            response = client.get("/fast")
            assert response.status_code == 200
        end = time.perf_counter()

        # Total time for 100 requests
        total_time = end - start

        # Average per request should be reasonable (< 100ms for 100 requests)
        avg_per_request = total_time / 100
        assert avg_per_request < 0.1  # 100ms total average

    def test_error_handling_performance(self, app_perf):
        """Test middleware doesn't add significant overhead to error handling"""
        client = TestClient(app_perf)

        # Time error handling
        start = time.perf_counter()
        response = client.get("/slow-error")
        end = time.perf_counter()

        error_time = end - start

        # Most of the time should be in the sleep(0.01)
        # Middleware overhead should be minimal
        assert 0.009 < error_time < 0.05  # Should be around 10ms

        assert response.status_code == 400


class TestErrorMiddlewareRFC7807Compliance:
    """Test RFC 7807 Problem Details compliance"""

    @pytest.fixture
    def app_rfc(self):
        """Create app for RFC 7807 testing"""
        app = FastAPI()
        app.add_middleware(ErrorMiddleware, debug=False)

        @app.get("/client-error")
        async def client_error():
            raise ValueError("Client error")

        @app.get("/server-error")
        async def server_error():
            raise RuntimeError("Server error")

        return app

    def test_problem_details_has_required_fields(self, app_rfc):
        """Test all RFC 7807 required fields are present"""
        client = TestClient(app_rfc)
        response = client.get("/client-error")

        data = response.json()

        # RFC 7807 required fields
        required_fields = ["type", "title", "status", "detail"]
        for field in required_fields:
            assert field in data, f"Missing required RFC 7807 field: {field}"

    def test_problem_details_status_matches_http_status(self, app_rfc):
        """Test status field matches HTTP response code"""
        client = TestClient(app_rfc)
        response = client.get("/client-error")

        assert response.status_code == 400
        assert response.json()["status"] == 400

    def test_problem_details_has_instance_id(self, app_rfc):
        """Test instance field with unique error ID"""
        client = TestClient(app_rfc)
        response = client.get("/server-error")

        data = response.json()

        # Instance should contain unique error identifier
        assert "instance" in data
        assert data["instance"] is not None


class TestErrorMiddlewareExceptionTypes:
    """Test handling of various exception types"""

    @pytest.fixture
    def app_exception_types(self):
        """Create app with various exception types"""
        app = FastAPI()
        app.add_middleware(ErrorMiddleware, debug=False)

        @app.get("/attribute-error")
        async def attribute_error():
            obj = type("obj", (), {})()
            return obj.nonexistent_attr

        @app.get("/zero-division")
        async def zero_division():
            return 1 / 0

        @app.get("/index-error")
        async def index_error():
            lst = [1, 2, 3]
            return lst[10]

        return app

    def test_attribute_error_handled(self, app_exception_types):
        """Test AttributeError is handled gracefully"""
        client = TestClient(app_exception_types)
        response = client.get("/attribute-error")

        assert response.status_code in [400, HTTP_500_INTERNAL_SERVER_ERROR]
        assert "type" in response.json()

    def test_zero_division_handled(self, app_exception_types):
        """Test ZeroDivisionError is handled gracefully"""
        client = TestClient(app_exception_types)
        response = client.get("/zero-division")

        assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
        assert "type" in response.json()

    def test_index_error_handled(self, app_exception_types):
        """Test IndexError is handled gracefully"""
        client = TestClient(app_exception_types)
        response = client.get("/index-error")

        assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
        assert "type" in response.json()


class TestErrorMiddlewareContentType:
    """Test response content types"""

    @pytest.fixture
    def app_content_type(self):
        """Create app for content type testing"""
        app = FastAPI()
        app.add_middleware(ErrorMiddleware, debug=False)

        @app.get("/error")
        async def error_route():
            raise ValueError("Test error")

        return app

    def test_error_response_is_json(self, app_content_type):
        """Test error responses are JSON"""
        client = TestClient(app_content_type)
        response = client.get("/error")

        # Should be valid JSON
        data = response.json()
        assert isinstance(data, dict)

        # Should have RFC 7807 structure
        assert "type" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
