"""
Tests for build_from_pydantic_error and JSON Pointer conversion.

Tests RFC 6901 JSON Pointer conversion from Pydantic loc tuples
and the full conversion pipeline from Pydantic ValidationError to RFC 7807.
"""

import pytest
from pydantic import BaseModel, ValidationError, Field

from fastapi.responses_rfc7807 import (
    build_from_pydantic_error,
    ValidationProblemDetails,
    ValidationErrorDetail,
    _loc_to_json_pointer,
)


# ============================================================================
# Tests for JSON Pointer Conversion (_loc_to_json_pointer)
# ============================================================================


class TestJsonPointerConversion:
    """Test RFC 6901 JSON Pointer generation from location tuples."""

    def test_empty_loc(self):
        """Empty loc should produce empty string"""
        assert _loc_to_json_pointer(()) == ""

    def test_single_field(self):
        """Single field should produce simple pointer"""
        assert _loc_to_json_pointer(("email",)) == "/email"

    def test_nested_fields(self):
        """Nested fields should produce nested pointer"""
        assert _loc_to_json_pointer(("user", "email")) == "/user/email"

    def test_array_index(self):
        """Array indices should be preserved as numbers"""
        assert _loc_to_json_pointer(("items", 0)) == "/items/0"
        assert _loc_to_json_pointer(("items", 5, "name")) == "/items/5/name"

    def test_escape_tilde(self):
        """Tilde must be escaped as ~0"""
        assert _loc_to_json_pointer(("field~name",)) == "/field~0name"
        assert _loc_to_json_pointer(("a~b~c",)) == "/a~0b~0c"

    def test_escape_forward_slash(self):
        """Forward slash must be escaped as ~1"""
        assert _loc_to_json_pointer(("data/field",)) == "/data~1field"
        assert _loc_to_json_pointer(("a/b/c",)) == "/a~1b~1c"

    def test_escape_both_characters(self):
        """Both ~ and / should be escaped in correct order"""
        # RFC 6901: escape ~ first (becomes ~0), then / (becomes ~1)
        assert _loc_to_json_pointer(("field~with/slash",)) == "/field~0with~1slash"
        assert _loc_to_json_pointer(("a~/b",)) == "/a~0~1b"

    def test_complex_nested_path(self):
        """Complex path with multiple nesting levels"""
        loc = ("users", 0, "addresses", 2, "zip_code")
        assert _loc_to_json_pointer(loc) == "/users/0/addresses/2/zip_code"

    def test_integer_indices_converted_to_strings(self):
        """Integer indices should be converted to strings in pointer"""
        assert _loc_to_json_pointer((123,)) == "/123"
        assert _loc_to_json_pointer(("array", 0, "nested", 42)) == "/array/0/nested/42"

    def test_special_characters_in_field_names(self):
        """Field names with special characters (except ~ and /)"""
        assert _loc_to_json_pointer(("field.name",)) == "/field.name"
        assert _loc_to_json_pointer(("field-name",)) == "/field-name"
        assert _loc_to_json_pointer(("field_name",)) == "/field_name"

    def test_unicode_field_names(self):
        """Unicode characters in field names"""
        assert _loc_to_json_pointer(("café",)) == "/café"
        assert _loc_to_json_pointer(("用户",)) == "/用户"

    def test_whitespace_in_field_names(self):
        """Whitespace should be preserved (not escaped by JSON Pointer)"""
        assert _loc_to_json_pointer(("field name",)) == "/field name"
        assert _loc_to_json_pointer(("a  b",)) == "/a  b"


# ============================================================================
# Tests for build_from_pydantic_error
# ============================================================================


class TestBuildFromPydanticError:
    """Test conversion of Pydantic errors to RFC 7807 format."""

    def test_single_validation_error(self):
        """Single field validation error should convert properly"""

        class Model(BaseModel):
            email: str

        try:
            Model(email="not-email")
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

        assert isinstance(problem, ValidationProblemDetails)
        assert problem.status == 400
        assert problem.title == "Validation Failed"
        assert problem.error_count == 1
        assert len(problem.errors) == 1
        assert problem.errors[0].field == "/email"
        assert "email" in problem.errors[0].message.lower()

    def test_multiple_validation_errors(self):
        """Multiple field errors should all be converted"""

        class Model(BaseModel):
            email: str
            age: int

        try:
            Model(email="invalid", age="not-int")
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

        assert problem.error_count == 2
        assert len(problem.errors) == 2
        # Fields should be converted to JSON pointers
        field_names = {err.field for err in problem.errors}
        assert "/email" in field_names
        assert "/age" in field_names

    def test_nested_field_errors(self):
        """Nested field errors should have proper pointer paths"""

        class Address(BaseModel):
            zip_code: int

        class User(BaseModel):
            address: Address

        try:
            User(address={"zip_code": "not-int"})
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

        assert problem.error_count == 1
        assert problem.errors[0].field == "/address/zip_code"

    def test_array_item_errors(self):
        """Array item validation errors should have indexed pointers"""

        class Model(BaseModel):
            items: list[int]

        try:
            Model(items=[1, "invalid", 3])
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

        assert problem.error_count == 1
        # Should reference the array index
        assert "/items" in problem.errors[0].field

    def test_error_type_preserved(self):
        """Error type from Pydantic should be preserved"""

        class Model(BaseModel):
            email: str

        try:
            Model(email="not-email")
        except ValidationError as e:
            error_dict = e.errors()[0]
            problem = build_from_pydantic_error(e.errors())

            # Error type should match
            assert problem.errors[0].error_type == error_dict["type"]

    def test_error_message_included(self):
        """Error messages should be extracted and included"""

        class Model(BaseModel):
            value: int = Field(gt=0, description="Must be positive")

        try:
            Model(value=-1)
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

        assert len(problem.errors[0].message) > 0
        assert problem.errors[0].message != ""

    def test_constraint_extraction(self):
        """Constraints should be extracted from context when available"""

        class Model(BaseModel):
            name: str = Field(min_length=3, max_length=50)

        try:
            Model(name="ab")
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

        # Constraint should be extracted from error context
        error = problem.errors[0]
        if error.constraint:
            assert "min_length" in error.constraint or "max_length" in error.constraint

    def test_custom_instance_parameter(self):
        """Custom instance parameter should be included in response"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("field",),
                "msg": "Invalid value",
            }
        ]
        instance = "/api/v1/users/123"

        problem = build_from_pydantic_error(error_list, instance=instance)

        assert problem.instance == instance

    def test_custom_problem_type_parameter(self):
        """Custom problem_type parameter should be used"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("field",),
                "msg": "Invalid value",
            }
        ]
        custom_type = "https://api.example.com/custom/validation"

        problem = build_from_pydantic_error(error_list, problem_type=custom_type)

        assert problem.problem_type == custom_type

    def test_detail_message_singular(self):
        """Detail message should be singular for one error"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("field",),
                "msg": "Invalid value",
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert "1 validation error occurred" in problem.detail

    def test_detail_message_plural(self):
        """Detail message should be plural for multiple errors"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("field1",),
                "msg": "Invalid",
            },
            {
                "type": "value_error",
                "loc": ("field2",),
                "msg": "Invalid",
            },
        ]

        problem = build_from_pydantic_error(error_list)

        assert "2 validation errors occurred" in problem.detail

    def test_empty_error_list(self):
        """Empty error list should produce valid but minimal response"""
        problem = build_from_pydantic_error([])

        assert problem.error_count == 0
        assert len(problem.errors) == 0
        assert "0 validation errors occurred" in problem.detail

    def test_missing_optional_fields(self):
        """Errors with missing optional fields should handle gracefully"""
        error_list = [
            {
                "loc": ("field",),
                "msg": "Error message",
                # type missing
                # ctx missing
            }
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 1
        assert problem.errors[0].field == "/field"
        assert problem.errors[0].message == "Error message"
        assert problem.errors[0].error_type == "validation.error"  # default

    def test_special_characters_in_field_names(self):
        """Field names with special characters should be properly escaped"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("data/field",),  # forward slash
                "msg": "Invalid value",
            },
            {
                "type": "value_error",
                "loc": ("field~name",),  # tilde
                "msg": "Invalid value",
            },
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.errors[0].field == "/data~1field"
        assert problem.errors[1].field == "/field~0name"

    def test_rfc7807_compliance(self):
        """Result should be RFC 7807 compliant"""

        class Model(BaseModel):
            email: str

        try:
            Model(email="invalid")
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

        # Check RFC 7807 required fields
        assert problem.problem_type  # type
        assert problem.title  # title
        assert problem.status  # status
        assert problem.detail  # detail
        assert problem.errors  # validation-specific

    def test_serialization_to_rfc7807(self):
        """Problem should serialize correctly as RFC 7807 JSON"""

        class Model(BaseModel):
            value: int

        try:
            Model(value="not-int")
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

        # Serialize to RFC 7807 format
        data = problem.model_dump_rfc7807()

        # Check RFC 7807 field names (with alias)
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data
        assert "errors" in data
        assert "error_count" in data

    def test_error_count_consistency(self):
        """error_count field should match length of errors array"""
        error_list = [
            {"type": "value_error", "loc": (f"field{i}",), "msg": "Invalid"}
            for i in range(5)
        ]

        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == len(problem.errors)
        assert problem.error_count == 5

    def test_complex_nested_validation_errors(self):
        """Complex nested structure should convert correctly"""

        class Item(BaseModel):
            price: float

        class Order(BaseModel):
            items: list[Item]
            shipping: dict

        try:
            Order(items=[{"price": "invalid"}], shipping={"address": 123})
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

        # Should have multiple errors with proper path structure
        assert problem.error_count > 0
        # All errors should have "/" prefix (valid JSON pointers)
        for err in problem.errors:
            if err.field:  # Not empty
                assert err.field.startswith("/")

    def test_security_sensitive_values_excluded(self):
        """Sensitive values should not be included by default"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("password",),
                "msg": "Invalid password",
                "ctx": {"input": "secret123"},  # Sensitive
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Value field should not contain the sensitive input
        assert problem.errors[0].value is None

    def test_constraint_field_length_security(self):
        """Constraint field should skip overly long values"""
        error_list = [
            {
                "type": "value_error",
                "loc": ("field",),
                "msg": "Invalid",
                "ctx": {"pattern": "a" * 1000},  # Very long pattern
            }
        ]

        problem = build_from_pydantic_error(error_list)

        # Constraint should be None (too long for security)
        assert problem.errors[0].constraint is None


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests with real Pydantic models and FastAPI patterns."""

    def test_full_pydantic_validation_error_conversion(self):
        """Real-world scenario: convert actual Pydantic ValidationError"""

        class UserCreate(BaseModel):
            username: str = Field(min_length=3, max_length=20)
            email: str
            age: int = Field(ge=0, le=120)

        test_cases = [
            {"username": "ab", "email": "invalid", "age": "not-int"},  # All fail
            {"username": "valid_user", "email": "no@domain", "age": 200},  # Age invalid
        ]

        for test_data in test_cases:
            try:
                UserCreate(**test_data)
            except ValidationError as e:
                problem = build_from_pydantic_error(
                    e.errors(), instance="/api/v1/users"
                )

                # Verify conversion
                assert problem.status == 400
                assert problem.error_count == len(e.errors())
                assert problem.instance == "/api/v1/users"
                # All errors should have pointers
                for err in problem.errors:
                    assert err.field.startswith("/")
                    assert err.message
                    assert err.error_type

    def test_fastapi_exception_handler_pattern(self):
        """Pattern for FastAPI RequestValidationError handler"""
        # Simulate what FastAPI passes to error handler
        from pydantic import ValidationError

        class Model(BaseModel):
            field: int

        try:
            Model(field="invalid")
        except ValidationError as e:
            # This is what an exception handler would do
            problem = build_from_pydantic_error(
                e.errors(),
                instance="/api/v1/resource",
                problem_type="https://api.example.com/errors/validation",
            )

            # Verify it's ready to return as JSONResponse
            response_data = problem.model_dump_rfc7807()
            assert response_data["type"]
            assert response_data["status"] == 400
            assert response_data["errors"]
            assert len(response_data["errors"]) >= 1

    def test_multiple_errors_in_complex_model(self):
        """Multiple validation errors in complex nested model"""

        class Address(BaseModel):
            street: str
            zip_code: int

        class User(BaseModel):
            name: str = Field(min_length=2)
            address: Address

        try:
            User(name="x", address={"street": "", "zip_code": "abc"})
        except ValidationError as e:
            problem = build_from_pydantic_error(e.errors())

            assert problem.error_count >= 2
            # Should have errors for name, street, and/or zip_code
            fields = {err.field for err in problem.errors}
            # Should reference nested fields with pointers
            assert any("address" in f for f in fields)

    def test_performance_many_errors(self):
        """Performance: conversion should be efficient even with many errors"""
        # Generate many errors
        error_list = [
            {
                "type": "value_error",
                "loc": ("field", i),
                "msg": f"Error {i}",
                "ctx": {"min_length": 5},
            }
            for i in range(100)
        ]

        # Should complete quickly without significant overhead
        problem = build_from_pydantic_error(error_list)

        assert problem.error_count == 100
        assert len(problem.errors) == 100
        # All should be properly formatted
        assert all(e.field for e in problem.errors)
        assert all(e.message for e in problem.errors)
