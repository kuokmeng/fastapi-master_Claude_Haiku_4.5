"""
RFC 7807 Problem Details Implementation Tests & Usage Examples

This module demonstrates:
1. Creating RFC 7807 compliant error responses
2. Handling the Python 'type' keyword conflict via Field(alias="type")
3. Backward compatibility with legacy error formats
4. Validation and serialization patterns
5. Type safety and IDE support
"""

from datetime import datetime, timedelta
from uuid import UUID, uuid4
import json

import pytest
from pydantic import ValidationError

from fastapi.responses_rfc7807 import (
    ProblemDetails,
    ValidationErrorDetail,
    ValidationProblemDetails,
    AuthenticationProblemDetails,
    AuthorizationProblemDetails,
    ConflictProblemDetails,
    RateLimitProblemDetails,
    InternalServerErrorProblemDetails,
    create_validation_problem,
    create_authentication_problem,
    create_authorization_problem,
    create_conflict_problem,
    create_rate_limit_problem,
    create_internal_server_error_problem,
)


# ============================================================================
# Test: Python Keyword 'type' Conflict Resolution
# ============================================================================


class TestTypeKeywordConflict:
    """Verify that the Field(alias="type") pattern works correctly"""

    def test_problem_type_field_alias(self):
        """Test that 'problem_type' attribute serializes as 'type' in JSON"""
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="Invalid input",
        )

        # In Python code, use problem_type (no keyword conflict)
        assert problem.problem_type == "https://api.example.com/errors/validation"

        # In JSON output, serializes as 'type' (RFC 7807 compliant)
        json_data = problem.model_dump(by_alias=True)
        assert json_data["type"] == "https://api.example.com/errors/validation"
        assert "problem_type" not in json_data

    def test_problem_type_via_alias_deserialization(self):
        """Test that JSON with 'type' field correctly deserializes via alias"""
        json_data = {
            "type": "https://api.example.com/errors/validation",
            "title": "Validation Failed",
            "status": 400,
            "detail": "Invalid input",
        }

        # Pydantic accepts 'type' via the alias
        problem = ProblemDetails(**json_data)
        assert problem.problem_type == "https://api.example.com/errors/validation"

    def test_validation_error_detail_type_alias(self):
        """Test ValidationErrorDetail's error_type alias"""
        error = ValidationErrorDetail(
            field="email",
            message="Invalid email",
            type="value_error.email",  # Via alias, not 'error_type'
        )

        assert error.error_type == "value_error.email"
        assert error.model_dump(by_alias=True)["type"] == "value_error.email"

    def test_populate_by_name_accepts_both_forms(self):
        """Test that model accepts both 'type' (alias) and 'error_type' (field name)"""
        # Using alias 'type'
        error1 = ValidationErrorDetail(
            field="email", message="Invalid", type="value_error.email"
        )

        # Using field name 'error_type'
        error2 = ValidationErrorDetail(
            field="email", message="Invalid", error_type="value_error.email"
        )

        assert error1.error_type == error2.error_type == "value_error.email"


# ============================================================================
# Test: RFC 7807 Compliance
# ============================================================================


class TestRFC7807Compliance:
    """Verify RFC 7807 standard compliance"""

    def test_required_fields_present(self):
        """RFC 7807 requires: type, title, detail"""
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="Invalid input",
        )

        rfc_dump = problem.model_dump_rfc7807()
        assert "type" in rfc_dump
        assert "title" in rfc_dump
        assert "detail" in rfc_dump
        assert "status" in rfc_dump

    def test_instance_field_for_error_correlation(self):
        """RFC 7807 recommends instance field for error correlation"""
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Not Found",
            status=404,
            detail="Item not found",
            instance="/api/v1/items/123",
        )

        rfc_dump = problem.model_dump_rfc7807()
        assert rfc_dump["instance"] == "/api/v1/items/123"

    def test_validation_problem_details_complies_with_rfc7807(self):
        """ValidationProblemDetails extends RFC 7807 with validation errors"""
        errors = [
            ValidationErrorDetail(
                field="email",
                message="Invalid format",
                error_type="value_error.email",
            ),
            ValidationErrorDetail(
                field="age",
                message="Must be positive",
                error_type="value_error.number.not_ge",
                constraint="minimum_value=0",
            ),
        ]

        problem = create_validation_problem(
            detail="2 validation errors",
            errors=errors,
            instance="/api/v1/users",
        )

        # Verify RFC 7807 base fields
        assert problem.problem_type == "https://api.example.com/errors/validation"
        assert problem.title == "Validation Failed"
        assert problem.status == 400
        assert problem.instance == "/api/v1/users"

        # Verify validation-specific fields
        assert len(problem.errors) == 2
        assert problem.error_count == 2

    def test_rfc7807_model_dump_excludes_none(self):
        """RFC 7807 doesn't require optional fields like instance"""
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Bad Request",
            status=400,
            detail="Invalid input",
            # instance=None (not provided)
        )

        rfc_dump = problem.model_dump_rfc7807(include_none=False)
        assert "instance" not in rfc_dump


# ============================================================================
# Test: Backward Compatibility
# ============================================================================


class TestBackwardCompatibility:
    """Verify backward compatibility with legacy FastAPI error formats"""

    def test_legacy_fields_supported(self):
        """Test that legacy fields can still be used"""
        now = datetime.utcnow()
        request_id = uuid4()

        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="Invalid input",
            # Legacy fields
            error_code="VALIDATION_ERROR",
            timestamp=now,
            request_id=request_id,
        )

        assert problem.error_code == "VALIDATION_ERROR"
        assert problem.timestamp == now
        assert problem.request_id == request_id

    def test_legacy_fields_excluded_from_rfc7807_dump(self):
        """By default, legacy fields are excluded from RFC 7807 output"""
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="Invalid input",
            error_code="VALIDATION_ERROR",
            timestamp=datetime.utcnow(),
            request_id=uuid4(),
        )

        # RFC 7807 dump excludes legacy fields
        rfc_dump = problem.model_dump_rfc7807()
        assert "error_code" not in rfc_dump
        assert "timestamp" not in rfc_dump
        assert "request_id" not in rfc_dump

    def test_legacy_fields_included_on_demand(self):
        """Legacy fields can be included when needed for backward compatibility"""
        now = datetime.utcnow()

        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="Invalid input",
            error_code="VALIDATION_ERROR",
            timestamp=now,
        )

        # Include legacy fields
        dump_with_legacy = problem.model_dump_with_legacy()
        assert dump_with_legacy["error_code"] == "VALIDATION_ERROR"
        assert dump_with_legacy["timestamp"] == now.isoformat()


# ============================================================================
# Test: Validation & Constraints
# ============================================================================


class TestValidationConstraints:
    """Test input validation and constraints"""

    def test_problem_type_must_be_uri(self):
        """problem_type must be a valid URI reference"""
        # Valid URIs
        assert ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Title",
            status=400,
            detail="Detail",
        )

        assert ProblemDetails(
            problem_type="urn:error:validation",
            title="Title",
            status=400,
            detail="Detail",
        )

        assert ProblemDetails(
            problem_type="/errors/validation",
            title="Title",
            status=400,
            detail="Detail",
        )

        # Invalid URIs should raise
        with pytest.raises(ValidationError) as exc_info:
            ProblemDetails(
                problem_type="not-a-valid-uri",
                title="Title",
                status=400,
                detail="Detail",
            )
        assert "must be a valid URI reference" in str(exc_info.value)

    def test_status_code_must_be_valid_http(self):
        """status must be a valid HTTP status code (100-599)"""
        # Valid status codes
        assert ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Title",
            status=400,
            detail="Detail",
        )

        assert ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Title",
            status=500,
            detail="Detail",
        )

        # Invalid status codes should raise
        with pytest.raises(ValidationError) as exc_info:
            ProblemDetails(
                problem_type="https://api.example.com/errors/validation",
                title="Title",
                status=99,  # Too low
                detail="Detail",
            )

        with pytest.raises(ValidationError) as exc_info:
            ProblemDetails(
                problem_type="https://api.example.com/errors/validation",
                title="Title",
                status=600,  # Too high
                detail="Detail",
            )

    def test_validation_problem_status_must_be_4xx(self):
        """ValidationProblemDetails status must be in 4xx range"""
        errors = [
            ValidationErrorDetail(
                field="email", message="Invalid", error_type="value_error.email"
            )
        ]

        # Valid 4xx status
        assert ValidationProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="Invalid",
            errors=errors,
            error_count=1,
        )

        # Invalid 5xx status should raise
        with pytest.raises(ValidationError):
            ValidationProblemDetails(
                problem_type="https://api.example.com/errors/validation",
                title="Validation Failed",
                status=500,  # Should be 4xx
                detail="Invalid",
                errors=errors,
                error_count=1,
            )

    def test_authentication_problem_status_is_401(self):
        """AuthenticationProblemDetails has fixed 401 status"""
        problem = AuthenticationProblemDetails(
            problem_type="https://api.example.com/errors/authentication",
            title="Unauthorized",
            detail="Invalid token",
        )
        assert problem.status == 401

    def test_authorization_problem_status_is_403(self):
        """AuthorizationProblemDetails has fixed 403 status"""
        problem = AuthorizationProblemDetails(
            problem_type="https://api.example.com/errors/authorization",
            title="Forbidden",
            detail="Insufficient permissions",
        )
        assert problem.status == 403

    def test_conflict_problem_status_is_409(self):
        """ConflictProblemDetails has fixed 409 status"""
        problem = ConflictProblemDetails(
            problem_type="https://api.example.com/errors/conflict",
            title="Conflict",
            detail="Username already exists",
        )
        assert problem.status == 409

    def test_rate_limit_problem_status_is_429(self):
        """RateLimitProblemDetails has fixed 429 status"""
        problem = RateLimitProblemDetails(
            problem_type="https://api.example.com/errors/rate-limit",
            title="Too Many Requests",
            detail="Rate limit exceeded",
            limit=100,
            window_seconds=60,
            retry_after_seconds=30,
            remaining=0,
        )
        assert problem.status == 429

    def test_internal_error_problem_status_is_5xx(self):
        """InternalServerErrorProblemDetails has status in 5xx range"""
        problem = InternalServerErrorProblemDetails(
            problem_type="https://api.example.com/errors/internal-server-error",
            title="Internal Server Error",
            detail="An error occurred",
        )
        assert problem.status == 500
        assert 500 <= problem.status < 600

    def test_error_count_must_match_errors_array(self):
        """error_count is auto-corrected to match errors list length"""
        errors = [
            ValidationErrorDetail(
                field="email", message="Invalid", error_type="value_error.email"
            ),
            ValidationErrorDetail(
                field="age", message="Required", error_type="value_error.missing"
            ),
        ]

        # Provide mismatched error_count
        problem = ValidationProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="2 errors",
            errors=errors,
            error_count=999,  # Wrong count
        )

        # Auto-corrected to actual count
        assert problem.error_count == 2


# ============================================================================
# Test: Serialization & JSON Output
# ============================================================================


class TestSerialization:
    """Test JSON serialization and deserialization"""

    def test_json_serialization_rfc7807_compliant(self):
        """JSON output matches RFC 7807 specification"""
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="Invalid input",
            instance="/api/v1/items",
        )

        json_str = problem.model_dump_json(by_alias=True)
        json_data = json.loads(json_str)

        # RFC 7807 required fields
        assert json_data["type"] == "https://api.example.com/errors/validation"
        assert json_data["title"] == "Validation Failed"
        assert json_data["status"] == 400
        assert json_data["detail"] == "Invalid input"
        assert json_data["instance"] == "/api/v1/items"

    def test_validation_problem_details_json_output(self):
        """ValidationProblemDetails JSON output includes error details"""
        errors = [
            ValidationErrorDetail(
                field="email",
                message="Invalid format",
                error_type="value_error.email",
            ),
        ]

        problem = create_validation_problem(
            detail="1 validation error",
            errors=errors,
            instance="/api/v1/users",
        )

        json_data = problem.model_dump(by_alias=True)

        # Check error detail structure
        assert json_data["errors"][0]["field"] == "email"
        assert json_data["errors"][0]["message"] == "Invalid format"
        assert json_data["errors"][0]["type"] == "value_error.email"

    def test_deserialization_from_json_dict(self):
        """Can deserialize problem from JSON-like dict"""
        json_dict = {
            "type": "https://api.example.com/errors/validation",
            "title": "Validation Failed",
            "status": 400,
            "detail": "Invalid input",
            "instance": "/api/v1/items",
        }

        problem = ProblemDetails(**json_dict)
        assert problem.problem_type == "https://api.example.com/errors/validation"
        assert problem.title == "Validation Failed"
        assert problem.instance == "/api/v1/items"

    def test_model_dump_rfc7807_returns_proper_dict(self):
        """model_dump_rfc7807() returns RFC 7807 compliant dict"""
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="Invalid input",
        )

        result = problem.model_dump_rfc7807()

        # Ensures 'type' is the serialized key, not 'problem_type'
        assert "type" in result
        assert "problem_type" not in result
        assert result["type"] == "https://api.example.com/errors/validation"


# ============================================================================
# Test: Factory Functions
# ============================================================================


class TestFactoryFunctions:
    """Test convenience factory functions"""

    def test_create_validation_problem(self):
        """Test create_validation_problem factory"""
        errors = [
            ValidationErrorDetail(
                field="email",
                message="Invalid email",
                error_type="value_error.email",
            ),
        ]

        problem = create_validation_problem(
            detail="Email validation failed",
            errors=errors,
            instance="/api/v1/register",
        )

        assert problem.status == 400
        assert problem.title == "Validation Failed"
        assert len(problem.errors) == 1

    def test_create_authentication_problem(self):
        """Test create_authentication_problem factory"""
        problem = create_authentication_problem(
            detail="Token expired",
            instance="/api/v1/protected",
            challenge_scheme="Bearer",
            realm="protected-api",
        )

        assert problem.status == 401
        assert problem.title == "Unauthorized"
        assert problem.challenge_scheme == "Bearer"

    def test_create_authorization_problem(self):
        """Test create_authorization_problem factory"""
        problem = create_authorization_problem(
            detail="Insufficient permissions",
            instance="/api/v1/admin/users",
            required_role="admin",
            current_role="user",
        )

        assert problem.status == 403
        assert problem.required_role == "admin"

    def test_create_conflict_problem(self):
        """Test create_conflict_problem factory"""
        problem = create_conflict_problem(
            detail="Username already exists",
            instance="/api/v1/users",
            conflict_field="username",
        )

        assert problem.status == 409
        assert problem.conflict_field == "username"

    def test_create_rate_limit_problem(self):
        """Test create_rate_limit_problem factory"""
        problem = create_rate_limit_problem(
            limit=100,
            window_seconds=60,
            retry_after_seconds=30,
            instance="/api/v1/items",
            remaining=0,
        )

        assert problem.status == 429
        assert problem.limit == 100
        assert problem.window_seconds == 60
        assert problem.retry_after_seconds == 30

    def test_create_internal_server_error_problem(self):
        """Test create_internal_server_error_problem factory"""
        problem = create_internal_server_error_problem(
            detail="Database connection failed",
            instance="/api/v1/items",
            support_url="https://support.example.com/error/500",
        )

        assert problem.status == 500
        assert problem.title == "Internal Server Error"
        assert problem.support_url == "https://support.example.com/error/500"
        assert isinstance(problem.error_id, str)


# ============================================================================
# Test: Real-World Examples
# ============================================================================


class TestRealWorldExamples:
    """Test real-world usage scenarios"""

    def test_e_commerce_conflict_error(self):
        """Example: E-commerce duplicate username error"""
        problem = ConflictProblemDetails(
            problem_type="https://api.example.com/errors/duplicate-user",
            title="Username Conflict",
            status=409,
            detail="Username 'john_doe' is already taken",
            instance="/api/v1/users/register",
            conflict_field="username",
            existing_value="john_doe",
        )

        json_output = problem.model_dump_rfc7807()
        assert json_output["status"] == 409
        assert json_output["conflict_field"] == "username"

    def test_api_validation_with_multiple_errors(self):
        """Example: API with multiple validation errors"""
        errors = [
            ValidationErrorDetail(
                field="email",
                message="Invalid email format",
                error_type="value_error.email",
                constraint="format=email",
            ),
            ValidationErrorDetail(
                field="password",
                message="Password must be at least 8 characters",
                error_type="value_error.string.min_length",
                constraint="min_length=8",
            ),
            ValidationErrorDetail(
                field="age",
                message="Age must be at least 18",
                error_type="value_error.number.not_ge",
                constraint="minimum_value=18",
            ),
        ]

        problem = ValidationProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="3 validation errors occurred during user registration",
            instance="/api/v1/users",
            errors=errors,
            error_count=3,
            error_source="body",
        )

        json_output = problem.model_dump_rfc7807()
        assert len(json_output["errors"]) == 3
        assert json_output["error_count"] == 3
        assert json_output["error_source"] == "body"

    def test_rate_limiting_scenario(self):
        """Example: API rate limiting"""
        reset_time = datetime.utcnow() + timedelta(minutes=1)

        problem = RateLimitProblemDetails(
            problem_type="https://api.example.com/errors/rate-limit",
            title="Too Many Requests",
            status=429,
            detail="API rate limit exceeded. Max 1000 requests per hour.",
            instance="/api/v1/items",
            limit=1000,
            window_seconds=3600,
            retry_after_seconds=3600,
            remaining=0,
            reset_at=reset_time,
        )

        json_output = problem.model_dump_rfc7807()
        assert json_output["status"] == 429
        assert json_output["limit"] == 1000
        assert json_output["remaining"] == 0

    def test_oauth2_authentication_challenge(self):
        """Example: OAuth2 bearer token authentication failure"""
        problem = AuthenticationProblemDetails(
            problem_type="https://api.example.com/errors/invalid-token",
            title="Unauthorized",
            status=401,
            detail="Bearer token has expired or is invalid",
            instance="/api/v1/protected-resource",
            challenge_scheme="Bearer",
            realm="protected-api",
            required_scopes=["read:items", "write:items"],
        )

        json_output = problem.model_dump_rfc7807()
        assert json_output["challenge_scheme"] == "Bearer"
        assert json_output["required_scopes"] == ["read:items", "write:items"]


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
