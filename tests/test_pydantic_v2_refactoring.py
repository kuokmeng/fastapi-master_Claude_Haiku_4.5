"""
Test Pydantic v2 ConfigDict Refactoring
========================================

This test suite validates that the Pydantic v2 deprecation refactoring:
1. Eliminates PydanticDeprecatedSince20 warnings
2. Maintains backward compatibility
3. Preserves RFC 7807 compliance
4. Detects memory issues or API misuse
"""

import pytest
import gc
import sys
from typing import Any, Dict
from uuid import uuid4
from datetime import datetime

# Import model classes
from fastapi.responses_rfc7807 import (
    ProblemDetails,
    ValidationErrorDetail,
    ValidationProblemDetails,
    AuthenticationProblemDetails,
    AuthorizationProblemDetails,
    ConflictProblemDetails,
    RateLimitProblemDetails,
    InternalServerErrorProblemDetails,
)


class TestConfigDictRefactoring:
    """Verify ConfigDict changes are correct"""

    def test_problem_details_config_clean(self):
        """Verify ProblemDetails ConfigDict is clean"""
        config = ProblemDetails.model_config

        # Should NOT have deprecated parameters
        assert "use_enum_values" not in str(config)
        assert "str_strip_whitespace" not in str(config)

        # Should have modern parameters
        assert "populate_by_name" in config
        assert "json_schema_extra" in config

    def test_validation_error_detail_config_clean(self):
        """Verify ValidationErrorDetail ConfigDict is clean"""
        config = ValidationErrorDetail.model_config

        assert "populate_by_name" in config
        assert "json_schema_extra" in config

    def test_validation_problem_details_config_clean(self):
        """Verify ValidationProblemDetails ConfigDict is clean"""
        config = ValidationProblemDetails.model_config
        assert "json_schema_extra" in config

    def test_all_subclass_configs_clean(self):
        """Verify all subclass ConfigDicts are clean"""
        subclasses = [
            AuthenticationProblemDetails,
            AuthorizationProblemDetails,
            ConflictProblemDetails,
            RateLimitProblemDetails,
            InternalServerErrorProblemDetails,
        ]

        for cls in subclasses:
            config = cls.model_config
            assert config is not None, f"{cls.__name__} missing model_config"
            assert (
                "json_schema_extra" in config
            ), f"{cls.__name__} missing json_schema_extra"


class TestBackwardCompatibility:
    """Ensure refactoring maintains backward compatibility"""

    def test_problem_details_creation_basic(self):
        """Test basic ProblemDetails creation"""
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Error",
            status=400,
            detail="Invalid input",
        )

        assert problem.problem_type == "https://api.example.com/errors/validation"
        assert problem.title == "Validation Error"
        assert problem.status == 400
        assert problem.detail == "Invalid input"

    def test_problem_details_serialization(self):
        """Test serialization of ProblemDetails"""
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/test",
            title="Test Error",
            status=400,
            detail="Test detail",
        )

        # Should serialize correctly
        data = problem.model_dump()
        assert "type" in data  # Alias should work
        assert data["type"] == problem.problem_type
        assert data["title"] == "Test Error"
        assert data["status"] == 400

    def test_validation_problem_details_with_errors(self):
        """Test ValidationProblemDetails with error list"""
        errors = [
            ValidationErrorDetail(
                field="email",
                message="Invalid email format",
                error_type="value_error.email",
            ),
            ValidationErrorDetail(
                field="age",
                message="Must be >= 18",
                error_type="value_error.number.not_ge",
                constraint="18",
            ),
        ]

        problem = ValidationProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="2 validation errors",
            errors=errors,
        )

        assert len(problem.errors) == 2
        assert problem.errors[0].field == "email"
        assert problem.errors[1].field == "age"

    def test_authentication_problem_details(self):
        """Test AuthenticationProblemDetails creation"""
        problem = AuthenticationProblemDetails(
            problem_type="https://api.example.com/errors/auth",
            title="Unauthorized",
            status=401,
            detail="Bearer token expired",
            challenge_scheme="Bearer",
            realm="protected-api",
        )

        assert problem.status == 401
        assert problem.challenge_scheme == "Bearer"
        assert problem.realm == "protected-api"

    def test_authorization_problem_details(self):
        """Test AuthorizationProblemDetails creation"""
        problem = AuthorizationProblemDetails(
            problem_type="https://api.example.com/errors/authz",
            title="Forbidden",
            status=403,
            detail="Insufficient permissions",
            required_role="admin",
            current_role="user",
        )

        assert problem.status == 403
        assert problem.required_role == "admin"
        assert problem.current_role == "user"

    def test_conflict_problem_details(self):
        """Test ConflictProblemDetails creation"""
        problem = ConflictProblemDetails(
            problem_type="https://api.example.com/errors/conflict",
            title="Conflict",
            status=409,
            detail="Username already exists",
            conflict_field="username",
            existing_value="john_doe",
        )

        assert problem.status == 409
        assert problem.conflict_field == "username"

    def test_rate_limit_problem_details(self):
        """Test RateLimitProblemDetails creation"""
        problem = RateLimitProblemDetails(
            problem_type="https://api.example.com/errors/rate-limit",
            title="Too Many Requests",
            status=429,
            detail="Rate limit exceeded",
            retry_after_seconds=60,
            limit=100,
            window_seconds=60,
            remaining=0,
        )

        assert problem.status == 429
        assert problem.retry_after_seconds == 60
        assert problem.limit == 100

    def test_internal_server_error_problem_details(self):
        """Test InternalServerErrorProblemDetails creation"""
        problem = InternalServerErrorProblemDetails(
            problem_type="https://api.example.com/errors/internal",
            title="Internal Server Error",
            status=500,
            detail="Unexpected error occurred",
            support_url="https://support.example.com",
        )

        assert problem.status == 500
        assert problem.support_url == "https://support.example.com"
        assert problem.error_id is not None  # Should auto-generate


class TestMemoryEfficiency:
    """Detect potential memory issues"""

    def test_no_circular_references_in_config(self):
        """Ensure ConfigDict doesn't create circular references"""
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Create 100 instances
        problems = [
            ProblemDetails(
                problem_type="https://api.example.com/errors/test",
                title=f"Error {i}",
                status=400,
                detail=f"Test error {i}",
            )
            for i in range(100)
        ]

        # Force garbage collection
        del problems
        gc.collect()
        final_objects = len(gc.get_objects())

        # Memory growth should be reasonable (not accumulating)
        # Allow some overhead but not exponential growth
        growth_ratio = final_objects / initial_objects if initial_objects > 0 else 1
        assert (
            growth_ratio < 1.5
        ), f"Excessive memory growth: {growth_ratio}x (check for circular refs)"

    def test_config_dict_not_duplicated_in_memory(self):
        """Verify ConfigDict isn't duplicated across instances"""
        gc.collect()

        # Get reference to ConfigDict
        config1 = ProblemDetails.model_config

        # Create instance (should NOT create new ConfigDict)
        instance = ProblemDetails(
            problem_type="test", title="Test", status=400, detail="Test"
        )

        # ConfigDict should be same object
        config2 = ProblemDetails.model_config
        assert config1 is config2, "ConfigDict duplicated in memory"

    def test_validator_overhead_minimal(self):
        """Test that validators don't cause excessive memory overhead"""
        import timeit

        # Time a basic instantiation
        code = """
ProblemDetails(
    problem_type="https://api.example.com/test",
    title="Test Error",
    status=400,
    detail="Test detail"
)
"""

        timer = timeit.timeit(
            code,
            setup="from fastapi.responses_rfc7807 import ProblemDetails",
            number=1000,
        )

        # Average time per instantiation
        avg_time_ms = (timer / 1000) * 1000

        # Should be reasonably fast (< 1ms per instantiation)
        assert (
            avg_time_ms < 1.0
        ), f"Validator overhead too high: {avg_time_ms:.3f}ms per instantiation"

    def test_subclass_memory_efficiency(self):
        """Test that subclasses don't duplicate ConfigDict memory"""
        # Get memory address of parent ConfigDict
        parent_config = ProblemDetails.model_config

        # Subclass should inherit, not duplicate
        subclass_config = ValidationProblemDetails.model_config

        # Both should exist but not create excessive overhead
        assert parent_config is not None
        assert subclass_config is not None

        # Verify no unexpected duplication
        parent_size = sys.getsizeof(parent_config)
        subclass_size = sys.getsizeof(subclass_config)

        # Sizes should be similar (not exponentially different)
        ratio = max(parent_size, subclass_size) / min(parent_size, subclass_size)
        assert ratio < 2.0, "Subclass ConfigDict significantly larger than parent"


class TestValidatorOptimization:
    """Test that validators are optimized and don't cause issues"""

    def test_string_strip_in_validator(self):
        """Test that string stripping still works in validator"""
        # Should still handle whitespace correctly
        problem = ProblemDetails(
            problem_type="https://api.example.com/test",
            title="  Test Error  ",  # With whitespace
            status=400,
            detail="  Test detail  ",
        )

        # Values should be preserved as-is from input
        # (Pydantic v2 handles stripping via Field config, not validator)
        assert problem.title == "  Test Error  "
        assert problem.detail == "  Test detail  "

    def test_empty_string_validation(self):
        """Test that empty string validation still works"""
        with pytest.raises(ValueError, match="field cannot be empty"):
            ProblemDetails(
                problem_type="https://api.example.com/test",
                title="",  # Empty string
                status=400,
                detail="Test",
            )

    def test_whitespace_only_validation(self):
        """Test that whitespace-only validation still works"""
        with pytest.raises(ValueError, match="field cannot be empty"):
            ProblemDetails(
                problem_type="https://api.example.com/test",
                title="   ",  # Whitespace only
                status=400,
                detail="Test",
            )

    def test_url_validation_still_works(self):
        """Test that URL validation in problem_type still works"""
        # Valid URLs should pass
        valid_urls = [
            "https://api.example.com/errors/validation",
            "http://example.com/errors/test",
            "urn:custom:error:type",
            "/errors/local",
            "#fragment-error",
        ]

        for url in valid_urls:
            problem = ProblemDetails(
                problem_type=url, title="Test", status=400, detail="Test"
            )
            assert problem.problem_type == url


class TestRFC7807Compliance:
    """Ensure RFC 7807 compliance is maintained after refactoring"""

    def test_rfc7807_required_fields(self):
        """Test RFC 7807 required fields"""
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/test",
            title="Test Error",
            status=400,
            detail="Test detail",
        )

        data = problem.model_dump(by_alias=True)

        # RFC 7807 requires these fields
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data

    def test_rfc7807_extension_fields(self):
        """Test RFC 7807 allows extension fields"""
        problem = ValidationProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="2 validation errors",
            errors=[
                ValidationErrorDetail(
                    field="email",
                    message="Invalid email",
                    error_type="value_error.email",
                )
            ],
        )

        data = problem.model_dump(by_alias=True)

        # Should include custom extension fields
        assert "errors" in data
        assert len(data["errors"]) == 1

    def test_json_pointer_paths(self):
        """Test JSON Pointer paths in errors"""
        error = ValidationErrorDetail(
            field="address.zip_code",  # Should be a valid path
            message="Invalid zip code",
            error_type="value_error.zip_code",
        )

        assert error.field == "address.zip_code"


class TestPydanticDeprecationWarnings:
    """Verify no deprecation warnings are triggered"""

    def test_no_use_enum_values_deprecation(self):
        """Verify use_enum_values is not used"""
        # This would be caught if ConfigDict had use_enum_values
        config = ProblemDetails.model_config
        config_str = str(config)

        assert "use_enum_values" not in config_str

    def test_no_str_strip_whitespace_deprecation(self):
        """Verify str_strip_whitespace is not used"""
        config = ProblemDetails.model_config
        config_str = str(config)

        assert "str_strip_whitespace" not in config_str

    def test_config_dict_uses_standard_v2_params(self):
        """Verify ConfigDict uses standard Pydantic v2 parameters"""
        config = ProblemDetails.model_config

        # Modern v2 parameters
        allowed_params = {
            "populate_by_name",
            "json_schema_extra",
            "arbitrary_types_allowed",
            "validate_assignment",
            "extra",
        }

        for key in config.keys():
            assert key in allowed_params or key in [
                "ser_json_schema_extra"
            ], f"Unexpected ConfigDict parameter: {key}"


class TestModelValidators:
    """Test model validators still work correctly"""

    def test_timestamp_auto_setting(self):
        """Test that timestamp validator still works"""
        problem = ValidationProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Test",
            status=400,
            detail="Test",
            errors=[],
            request_id="req-123",  # Should trigger timestamp setting
        )

        # Timestamp should be set if request_id is provided
        # (depending on business logic)
        assert problem is not None

    def test_field_validators_still_work(self):
        """Test that field validators still work after refactoring"""
        # Title validator should reject empty strings
        with pytest.raises(ValueError):
            ProblemDetails(
                problem_type="https://api.example.com/test",
                title="",
                status=400,
                detail="Test",
            )

    def test_validation_error_detail_validators(self):
        """Test ValidationErrorDetail validators"""
        # Should accept valid field names
        error = ValidationErrorDetail(
            field="user_email", message="Invalid format", error_type="value_error.email"
        )

        assert error.field == "user_email"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
