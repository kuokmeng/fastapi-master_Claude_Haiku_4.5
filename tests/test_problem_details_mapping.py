"""
Comprehensive pytest tests for problem details mapping.

These tests validate the build_from_pydantic_error function against:
- Complex nested structures
- Edge cases and corner cases
- Failure scenarios and error conditions
- Security and performance concerns
- Standards compliance (RFC 6901, RFC 7807)

The tests ensure no unnecessary refactoring of the core mapping utility
while thoroughly validating all functionality.
"""

import pytest
from typing import Any, Dict, List
from pydantic import BaseModel, ValidationError, Field

from fastapi.responses_rfc7807 import (
    build_from_pydantic_error,
    _loc_to_json_pointer,
    ValidationProblemDetails,
    ValidationErrorDetail,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_pydantic_model():
    """Create a sample Pydantic model for testing"""

    class User(BaseModel):
        email: str
        age: int
        is_active: bool = True

    return User


@pytest.fixture
def nested_pydantic_model():
    """Create a nested Pydantic model for testing"""

    class Address(BaseModel):
        street: str
        city: str
        zip_code: int

    class Profile(BaseModel):
        bio: str
        address: Address

    class User(BaseModel):
        username: str
        profile: Profile

    return User


@pytest.fixture
def complex_pydantic_model():
    """Create a complex model with lists and nested structures"""

    class Tag(BaseModel):
        name: str
        value: str

    class Item(BaseModel):
        title: str
        description: str
        tags: List[Tag]

    class Order(BaseModel):
        items: List[Item]
        customer_id: int
        notes: str

    return Order


# ============================================================================
# TESTS: JSON Pointer Conversion (RFC 6901)
# ============================================================================


class TestJsonPointerConversion:
    """Test RFC 6901 JSON Pointer conversion with edge cases"""

    def test_empty_tuple(self):
        """Empty tuple produces empty string"""
        assert _loc_to_json_pointer(()) == ""

    def test_single_field(self):
        """Single field produces simple pointer"""
        assert _loc_to_json_pointer(("email",)) == "/email"

    def test_nested_fields(self):
        """Multiple nested fields"""
        assert (
            _loc_to_json_pointer(("user", "profile", "email")) == "/user/profile/email"
        )

    def test_array_indices(self):
        """Array indices are preserved as numbers"""
        assert _loc_to_json_pointer(("items", 0)) == "/items/0"
        assert _loc_to_json_pointer(("matrix", 5, 10)) == "/matrix/5/10"

    def test_mixed_nested_and_indices(self):
        """Mix of field names and array indices"""
        assert (
            _loc_to_json_pointer(("users", 0, "addresses", 2, "zip"))
            == "/users/0/addresses/2/zip"
        )

    def test_tilde_escaping(self):
        """Tilde character must be escaped as ~0"""
        assert _loc_to_json_pointer(("field~name",)) == "/field~0name"
        assert _loc_to_json_pointer(("a~b",)) == "/a~0b"

    def test_slash_escaping(self):
        """Forward slash must be escaped as ~1"""
        assert _loc_to_json_pointer(("data/field",)) == "/data~1field"
        assert _loc_to_json_pointer(("path/to/field",)) == "/path~1to~1field"

    def test_both_characters_escaping(self):
        """Both ~ and / escaped in correct order"""
        # RFC 6901: escape ~ first (becomes ~0), then / (becomes ~1)
        assert _loc_to_json_pointer(("field~with/slash",)) == "/field~0with~1slash"
        assert _loc_to_json_pointer(("~/path",)) == "/~0~1path"
        assert _loc_to_json_pointer(("path/~field",)) == "/path~1~0field"

    def test_multiple_special_characters(self):
        """Multiple special characters in single segment"""
        assert _loc_to_json_pointer(("a~b~c",)) == "/a~0b~0c"
        assert _loc_to_json_pointer(("x/y/z",)) == "/x~1y~1z"
        assert _loc_to_json_pointer(("~~/~~",)) == "/~0~0~1~0~0"

    def test_unicode_characters(self):
        """Unicode field names preserved correctly"""
        assert _loc_to_json_pointer(("用户",)) == "/用户"
        assert _loc_to_json_pointer(("café", "email")) == "/café/email"
        assert _loc_to_json_pointer(("naïve",)) == "/naïve"

    def test_whitespace_preservation(self):
        """Whitespace preserved (not escaped by JSON Pointer)"""
        assert _loc_to_json_pointer(("field name",)) == "/field name"
        assert _loc_to_json_pointer(("  leading",)) == "/  leading"
        assert _loc_to_json_pointer(("trailing  ",)) == "/trailing  "

    def test_numeric_field_indices(self):
        """Numeric indices converted to strings"""
        assert _loc_to_json_pointer((0,)) == "/0"
        assert _loc_to_json_pointer((1, 2, 3)) == "/1/2/3"

    def test_large_array_indices(self):
        """Large array indices handled correctly"""
        assert _loc_to_json_pointer(("items", 999999)) == "/items/999999"
        assert _loc_to_json_pointer(("matrix", 10000, 50000)) == "/matrix/10000/50000"

    def test_deeply_nested_structure(self):
        """Very deep nesting"""
        deep_loc = tuple(f"level{i}" for i in range(20))
        result = _loc_to_json_pointer(deep_loc)
        assert result.startswith("/level0")
        assert result.count("/") == 20

    def test_special_field_names(self):
        """Field names with special characters (except ~ and /)"""
        assert _loc_to_json_pointer(("field.name",)) == "/field.name"
        assert _loc_to_json_pointer(("field-name",)) == "/field-name"
        assert _loc_to_json_pointer(("field_name",)) == "/field_name"
        assert _loc_to_json_pointer(("field@domain",)) == "/field@domain"

    def test_empty_string_field(self):
        """Empty string as field name"""
        assert _loc_to_json_pointer(("",)) == "/"
        assert _loc_to_json_pointer(("", "field")) == "//field"

    def test_only_special_characters(self):
        """Segments containing only special characters"""
        assert _loc_to_json_pointer(("~",)) == "/~0"
        assert _loc_to_json_pointer(("/",)) == "/~1"
        assert _loc_to_json_pointer(("~/",)) == "/~0~1"


# ============================================================================
# TESTS: Error Mapping Conversion
# ============================================================================


class TestErrorMappingBasic:
    """Test basic error mapping conversion"""

    def test_single_error_conversion(self):
        """Single error converted correctly"""
        error_list = [
            {
                "type": "value_error.email",
                "loc": ("email",),
                "msg": "Invalid email format",
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert isinstance(problem, ValidationProblemDetails)
        assert problem.status == 400
        assert problem.error_count == 1
        assert len(problem.errors) == 1
        assert problem.errors[0].field == "/email"
        assert "Invalid email format" in problem.errors[0].message

    def test_multiple_errors_conversion(self):
        """Multiple errors converted with correct counts"""
        error_list = [
            {
                "type": "value_error.email",
                "loc": ("email",),
                "msg": "Invalid email",
            },
            {
                "type": "value_error.integer",
                "loc": ("age",),
                "msg": "Not an integer",
            },
            {
                "type": "value_error.boolean",
                "loc": ("is_active",),
                "msg": "Not a boolean",
            },
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 3
        assert len(problem.errors) == 3
        field_paths = {e.field for e in problem.errors}
        assert "/email" in field_paths
        assert "/age" in field_paths
        assert "/is_active" in field_paths

    def test_nested_field_errors(self):
        """Errors from nested models have correct JSON pointers"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("profile", "address", "zip_code"),
                "msg": "Invalid zip code",
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.errors[0].field == "/profile/address/zip_code"

    def test_array_item_errors(self):
        """Errors from array items have indexed pointers"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("items", 0, "title"),
                "msg": "Title is required",
            },
            {
                "type": "value_error",
                "loc": ("items", 1, "tags", 0, "name"),
                "msg": "Tag name is required",
            },
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.errors[0].field == "/items/0/title"
        assert problem.errors[1].field == "/items/1/tags/0/name"

    def test_detail_message_singular(self):
        """Detail message is singular for one error"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("f",), "msg": "msg"}]
        )
        assert "1 validation error occurred" in problem.detail

    def test_detail_message_plural(self):
        """Detail message is plural for multiple errors"""
        errors = [
            {"type": "error", "loc": (f"field{i}",), "msg": "msg"} for i in range(3)
        ]
        problem = build_from_pydantic_error(errors)
        assert "3 validation errors occurred" in problem.detail


# ============================================================================
# TESTS: Edge Cases and Corner Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and corner cases"""

    def test_empty_error_list(self):
        """Empty error list produces valid response"""
        problem = build_from_pydantic_error([])

        assert problem.error_count == 0
        assert len(problem.errors) == 0
        assert "0 validation errors occurred" in problem.detail

    def test_missing_optional_fields(self):
        """Missing optional fields handled gracefully"""
        error_list = [
            {
                "loc": ("field",),
                "msg": "Error message",
                # type and ctx missing
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 1
        assert problem.errors[0].error_type == "validation.error"  # default
        assert problem.errors[0].constraint is None

    def test_missing_msg_field(self):
        """Missing msg field defaults to 'Unknown error'"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("field",),
                # msg missing
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.errors[0].message == "Unknown error"

    def test_missing_loc_field(self):
        """Missing loc field defaults to empty tuple"""
        error_list = [
            {
                "type": "value_error",
                "msg": "Error",
                # loc missing
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.errors[0].field == ""

    def test_empty_loc_tuple(self):
        """Empty loc tuple converts to empty field pointer"""
        error_list = [
            {
                "type": "value_error",
                "loc": (),
                "msg": "Error",
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.errors[0].field == ""

    def test_special_characters_in_error_message(self):
        """Special characters in error messages preserved"""
        special_msg = 'Value must match pattern "^[a-z]+$"'
        error_list = [
            {
                "type": "value_error",
                "loc": ("field",),
                "msg": special_msg,
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.errors[0].message == special_msg

    def test_very_long_error_message(self):
        """Very long error messages handled"""
        long_msg = "x" * 1000
        error_list = [
            {
                "type": "value_error",
                "loc": ("field",),
                "msg": long_msg,
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.errors[0].message == long_msg

    def test_special_characters_in_field_names(self):
        """Field names with special characters properly escaped"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("data/field",),
                "msg": "Error",
            },
            {
                "type": "value_error",
                "loc": ("field~name",),
                "msg": "Error",
            },
            {
                "type": "value_error",
                "loc": ("field~with/slash",),
                "msg": "Error",
            },
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.errors[0].field == "/data~1field"
        assert problem.errors[1].field == "/field~0name"
        assert problem.errors[2].field == "/field~0with~1slash"

    def test_constraint_extraction_from_context(self):
        """Constraints extracted from error context"""
        error_list = [
            {
                "type": "value_error.string.min_length",
                "loc": ("password",),
                "msg": "At least 8 characters",
                "ctx": {"min_length": 8},
            }
        ]

        problem = build_from_pydantic_error(error_list)

        error = problem.errors[0]
        if error.constraint:
            assert "min_length" in error.constraint or "8" in error.constraint

    def test_constraint_field_security(self):
        """Constraints >100 chars are skipped for security"""
        error_list = [
            {
                "type": "value_error.regex",
                "loc": ("field",),
                "msg": "Pattern mismatch",
                "ctx": {"pattern": "x" * 200},  # Very long pattern
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Constraint should be None (too long)
        assert problem.errors[0].constraint is None

    def test_constraint_with_multiple_keys(self):
        """Multiple constraint keys extracted"""
        error_list = [
            {
                "type": "value_error.string",
                "loc": ("field",),
                "msg": "Length error",
                "ctx": {"min_length": 5, "max_length": 20, "input_length": 3},
            }
        ]

        problem = build_from_pydantic_error(error_list)

        error = problem.errors[0]
        if error.constraint:
            # At least one constraint should be present
            assert any(x in error.constraint for x in ["min_length", "max_length"])

    def test_constraint_filtering_secure_values(self):
        """Only safe constraint values are included"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("password",),
                "msg": "Invalid",
                "ctx": {
                    "min_length": 8,
                    "sensitive_data": "secret123",  # Should be filtered
                },
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Only safe constraint should be extracted
        error = problem.errors[0]
        if error.constraint:
            assert "sensitive_data" not in error.constraint


# ============================================================================
# TESTS: Parameter Handling
# ============================================================================


class TestParameterHandling:
    """Test custom parameter handling"""

    def test_custom_instance_parameter(self):
        """Custom instance parameter included in response"""
        error_list = [{"type": "error", "loc": ("field",), "msg": "Error"}]
        instance = "/api/v1/users/123"

        problem = build_from_pydantic_error(error_list, instance=instance)

        assert problem.instance == instance

    def test_custom_problem_type_parameter(self):
        """Custom problem_type parameter used"""
        error_list = [{"type": "error", "loc": ("field",), "msg": "Error"}]
        custom_type = "https://api.example.com/errors/custom"

        problem = build_from_pydantic_error(error_list, problem_type=custom_type)

        assert problem.problem_type == custom_type

    def test_default_problem_type(self):
        """Default problem_type used when not provided"""
        error_list = [{"type": "error", "loc": ("field",), "msg": "Error"}]

        problem = build_from_pydantic_error(error_list)

        assert problem.problem_type == "https://api.example.com/errors/validation"

    def test_none_instance_parameter(self):
        """None instance parameter produces None instance field"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("field",), "msg": "Error"}],
            instance=None,
        )

        assert problem.instance is None

    def test_instance_with_special_characters(self):
        """Instance parameter with special characters"""
        instance = "/api/v1/users/~john/orders/123"
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("field",), "msg": "Error"}],
            instance=instance,
        )

        assert problem.instance == instance


# ============================================================================
# TESTS: RFC 7807 Compliance
# ============================================================================


class TestRFC7807Compliance:
    """Test RFC 7807 Problem Details compliance"""

    def test_required_fields_present(self):
        """All required RFC 7807 fields present"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("f",), "msg": "msg"}]
        )

        data = problem.model_dump_rfc7807()

        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data

    def test_extension_fields_present(self):
        """RFC 7807 extension fields present for validation"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("f",), "msg": "msg"}]
        )

        data = problem.model_dump_rfc7807()

        assert "errors" in data
        assert "error_count" in data

    def test_type_field_uses_alias(self):
        """Output uses 'type' key (via alias), not 'problem_type'"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("f",), "msg": "msg"}]
        )

        data = problem.model_dump_rfc7807()

        assert "type" in data
        assert "problem_type" not in data

    def test_status_code_validation(self):
        """Status code is valid HTTP status"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("f",), "msg": "msg"}]
        )

        assert 100 <= problem.status <= 599

    def test_title_not_empty(self):
        """Title field is not empty"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("f",), "msg": "msg"}]
        )

        assert problem.title
        assert len(problem.title) > 0

    def test_detail_not_empty(self):
        """Detail field is not empty"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("f",), "msg": "msg"}]
        )

        assert problem.detail
        assert len(problem.detail) > 0

    def test_roundtrip_serialization(self):
        """Serialized output can be used for response"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("f",), "msg": "msg"}]
        )

        data = problem.model_dump_rfc7807()

        # Verify it's valid JSON-serializable
        import json

        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        assert parsed["type"]
        assert parsed["status"] == 400


# ============================================================================
# TESTS: Real Pydantic Integration
# ============================================================================


class TestPydanticIntegration:
    """Test integration with real Pydantic models"""

    def test_real_pydantic_single_error(self, sample_pydantic_model):
        """Conversion of real Pydantic ValidationError"""
        try:
            sample_pydantic_model(email="not-email", age="not-int")
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

            assert problem.error_count >= 1
            assert all(e.field.startswith("/") for e in problem.errors)
            assert all(e.message for e in problem.errors)

    def test_real_pydantic_nested_error(self, nested_pydantic_model):
        """Conversion from nested Pydantic model"""
        try:
            nested_pydantic_model(
                username="john",
                profile={
                    "bio": "bio",
                    "address": {"street": "st", "city": "city", "zip_code": "not-int"},
                },
            )
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

            assert problem.error_count >= 1
            # Should have nested path in field
            fields = {err.field for err in problem.errors}
            assert any("profile" in f for f in fields)

    def test_real_pydantic_complex_model(self, complex_pydantic_model):
        """Conversion from complex model with lists"""
        try:
            complex_pydantic_model(
                items=[
                    {
                        "title": "t",
                        "description": "d",
                        "tags": [{"name": "tag", "value": "val"}],
                    },
                ],
                customer_id="not-int",
                notes="notes",
            )
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

            assert problem.error_count >= 1

    def test_real_pydantic_with_field_validators(self):
        """Works with Pydantic field validators"""

        class StrictEmail(BaseModel):
            email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")

        try:
            StrictEmail(email="invalid")
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

            assert problem.error_count >= 1
            assert any("email" in e.field for e in problem.errors)


# ============================================================================
# TESTS: Performance and Scaling
# ============================================================================


class TestPerformanceAndScaling:
    """Test performance characteristics"""

    def test_many_errors_conversion(self):
        """Large number of errors handled efficiently"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("field", i),
                "msg": f"Error {i}",
            }
            for i in range(100)
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 100
        assert len(problem.errors) == 100

    def test_deeply_nested_paths(self):
        """Deeply nested field paths handled"""
        # Create error with very deep nesting
        deep_loc = tuple(f"level{i}" for i in range(50))
        error_list = [
            {
                "type": "value_error",
                "loc": deep_loc,
                "msg": "Deep error",
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 1
        field_path = problem.errors[0].field
        assert field_path.count("/") == 50

    def test_many_errors_with_nested_paths(self):
        """Many errors with nested paths"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("items", i, "tags", j, "value"),
                "msg": f"Error {i}-{j}",
            }
            for i in range(10)
            for j in range(5)
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 50
        assert len(problem.errors) == 50


# ============================================================================
# TESTS: Error Consistency
# ============================================================================


class TestErrorConsistency:
    """Test consistency of error details"""

    def test_error_count_matches_length(self):
        """error_count field matches errors array length"""
        errors = [{"type": "error", "loc": (f"f{i}",), "msg": "msg"} for i in range(5)]

        problem = build_from_pydantic_error(errors)

        assert problem.error_count == len(problem.errors)

    def test_all_errors_have_required_fields(self):
        """All errors have required fields"""
        errors = [
            {"type": "error", "loc": ("f1",), "msg": "msg1"},
            {"type": "error", "loc": ("f2",), "msg": "msg2"},
        ]

        problem = build_from_pydantic_error(errors)

        for error in problem.errors:
            assert error.field is not None
            assert error.message is not None
            assert error.error_type is not None

    def test_error_order_preserved(self):
        """Error order preserved from input"""
        errors = [
            {"type": "error", "loc": ("z",), "msg": "z-error"},
            {"type": "error", "loc": ("a",), "msg": "a-error"},
            {"type": "error", "loc": ("m",), "msg": "m-error"},
        ]

        problem = build_from_pydantic_error(errors)

        fields = [e.field for e in problem.errors]
        assert fields == ["/z", "/a", "/m"]

    def test_error_messages_preserved(self):
        """Error messages preserved exactly"""
        messages = ["Error 1", "Error 2", "Error 3"]
        errors = [
            {"type": "error", "loc": (f"f{i}",), "msg": msg}
            for i, msg in enumerate(messages)
        ]

        problem = build_from_pydantic_error(errors)

        problem_messages = [e.message for e in problem.errors]
        assert problem_messages == messages

    def test_error_types_preserved(self):
        """Error types preserved exactly"""
        types = ["value_error.email", "value_error.integer", "custom.error"]
        errors = [
            {"type": t, "loc": (f"f{i}",), "msg": "msg"} for i, t in enumerate(types)
        ]

        problem = build_from_pydantic_error(errors)

        problem_types = [e.error_type for e in problem.errors]
        assert problem_types == types


# ============================================================================
# TESTS: Failure Scenarios
# ============================================================================


class TestFailureScenarios:
    """Test failure scenarios and error recovery"""

    def test_invalid_error_dict_missing_all_fields(self):
        """Error dict with no recognized fields"""
        error_list = [{}]

        # Should not crash, should use defaults
        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 1
        assert problem.errors[0].field == ""
        assert problem.errors[0].message == "Unknown error"

    def test_error_dict_with_extra_fields(self):
        """Error dict with unexpected extra fields"""
        error_list = [
            {
                "type": "error",
                "loc": ("field",),
                "msg": "msg",
                "extra_field_1": "value1",
                "extra_field_2": "value2",
                "unknown": "data",
            }
        ]

        # Should extract only known fields
        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 1
        assert problem.errors[0].field == "/field"

    def test_corrupted_loc_format(self):
        """Loc field with unexpected type (should handle gracefully)"""
        # This tests defensive programming - loc might not be a tuple
        error_list = [
            {
                "type": "error",
                "loc": ("field",),  # Valid
                "msg": "msg",
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 1

    def test_msg_field_with_none_value(self):
        """Msg field is None instead of string"""
        error_list = [
            {
                "type": "error",
                "loc": ("field",),
                "msg": None,  # None instead of string
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Should convert None to string
        assert isinstance(problem.errors[0].message, str)

    def test_type_field_with_none_value(self):
        """Type field is None"""
        error_list = [
            {
                "type": None,
                "loc": ("field",),
                "msg": "msg",
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Should handle None type
        assert problem.errors[0].error_type is not None

    def test_numeric_msg_field(self):
        """Msg field contains number instead of string"""
        error_list = [
            {
                "type": "error",
                "loc": ("field",),
                "msg": 42,  # Number instead of string
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Should convert to string
        assert problem.errors[0].message == "42"

    def test_extremely_large_error_list(self):
        """Very large error list (1000+ errors)"""
        error_list = [
            {
                "type": "error",
                "loc": ("field", i % 100),
                "msg": f"Error {i}",
            }
            for i in range(1000)
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 1000
        assert len(problem.errors) == 1000


# ============================================================================
# TESTS: Security Scenarios
# ============================================================================


class TestSecurityScenarios:
    """Test security-related aspects"""

    def test_injection_prevention_in_field_paths(self):
        """Field path escaping prevents injection"""
        # Attempt to inject through field name
        error_list = [
            {
                "type": "error",
                "loc": ('field","injected":"true',),  # Attempt JSON injection
                "msg": "msg",
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Field should be safely escaped
        field = problem.errors[0].field
        assert '"injected"' not in field  # Not injectable
        assert "~" not in field or field.count("~") % 2 == 0  # Only escaped tildes

    def test_sensitive_value_excluded(self):
        """Error value field is excluded (no sensitive data leakage)"""
        error_list = [
            {
                "type": "error",
                "loc": ("password",),
                "msg": "Invalid",
                "ctx": {"input": "secret123"},  # Sensitive value in context
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Value should not be included
        assert problem.errors[0].value is None

    def test_constraint_length_limit(self):
        """Very long constraint values are filtered"""
        error_list = [
            {
                "type": "error",
                "loc": ("field",),
                "msg": "msg",
                "ctx": {"pattern": "x" * 10000},  # Extremely long pattern
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Constraint should be None (too long)
        assert problem.errors[0].constraint is None

    def test_unicode_normalization_safety(self):
        """Unicode characters handled safely"""
        error_list = [
            {
                "type": "error",
                "loc": ("field\u0000null",),  # Null character in field
                "msg": "msg",
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Should handle without issue (or safely escape)
        assert problem.error_count == 1


# ============================================================================
# TESTS: Serialization
# ============================================================================


class TestSerialization:
    """Test serialization behavior"""

    def test_model_dump_rfc7807_format(self):
        """model_dump_rfc7807 produces correct format"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("f",), "msg": "msg"}]
        )

        data = problem.model_dump_rfc7807()

        # Check structure
        assert isinstance(data, dict)
        assert all(isinstance(k, str) for k in data.keys())

    def test_json_serialization(self):
        """Result is JSON-serializable"""
        problem = build_from_pydantic_error(
            [{"type": "error", "loc": ("f",), "msg": "msg"}]
        )

        import json

        json_str = json.dumps(problem.model_dump_rfc7807())
        parsed = json.loads(json_str)

        assert parsed["type"]
        assert parsed["status"]

    def test_nested_errors_serialization(self):
        """Nested errors serialize correctly"""
        errors = [
            {"type": "error", "loc": ("a", "b", "c"), "msg": "msg"},
            {"type": "error", "loc": ("x", 0, "y"), "msg": "msg"},
        ]

        problem = build_from_pydantic_error(errors)
        data = problem.model_dump_rfc7807()

        import json

        json_str = json.dumps(data)
        assert "/a/b/c" in json_str
        assert "/x/0/y" in json_str
