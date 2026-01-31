#!/usr/bin/env python
"""
Quick validation script for build_from_pydantic_error implementation.
Tests JSON Pointer conversion and error mapping without pytest dependency.
"""

import sys
from typing import List, Tuple


# Test the JSON Pointer conversion function
def test_json_pointer_conversion():
    """Test RFC 6901 JSON Pointer conversion"""
    from fastapi.responses_rfc7807 import _loc_to_json_pointer

    test_cases: List[Tuple[tuple, str]] = [
        # (input_loc, expected_pointer)
        ((), ""),
        (("email",), "/email"),
        (("user", "email"), "/user/email"),
        (("items", 0), "/items/0"),
        (("items", 0, "name"), "/items/0/name"),
        (("field~name",), "/field~0name"),
        (("data/field",), "/data~1field"),
        (("field~with/slash",), "/field~0with~1slash"),
        (("users", 0, "addresses", 2, "zip_code"), "/users/0/addresses/2/zip_code"),
    ]

    print("Testing JSON Pointer Conversion...")
    for loc, expected in test_cases:
        result = _loc_to_json_pointer(loc)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {loc!r} → {result!r} (expected {expected!r})")
        if result != expected:
            print(f"    ERROR: Mismatch!")
            return False

    print("  All JSON Pointer tests passed!\n")
    return True


def test_build_from_pydantic_error():
    """Test conversion of Pydantic errors to RFC 7807 format"""
    from pydantic import BaseModel, ValidationError, Field
    from fastapi.responses_rfc7807 import (
        build_from_pydantic_error,
        ValidationProblemDetails,
    )

    print("Testing build_from_pydantic_error...")

    # Test 1: Single field error
    print("  Test 1: Single field validation error")

    class SimpleModel(BaseModel):
        email: str

    try:
        SimpleModel(email="not-email")
    except ValidationError as e:
        problem = build_from_pydantic_error(e.errors())
        assert isinstance(problem, ValidationProblemDetails)
        assert problem.status == 400
        assert problem.error_count == 1
        assert problem.errors[0].field == "/email"
        print("    ✓ Single field error converted correctly")

    # Test 2: Multiple field errors
    print("  Test 2: Multiple field validation errors")

    class MultiModel(BaseModel):
        email: str
        age: int

    try:
        MultiModel(email="invalid", age="not-int")
    except ValidationError as e:
        problem = build_from_pydantic_error(e.errors())
        assert problem.error_count == 2
        assert len(problem.errors) == 2
        field_names = {err.field for err in problem.errors}
        assert "/email" in field_names
        assert "/age" in field_names
        print("    ✓ Multiple errors converted correctly")

    # Test 3: Nested field errors
    print("  Test 3: Nested field validation errors")

    class Address(BaseModel):
        zip_code: int

    class UserModel(BaseModel):
        address: Address

    try:
        UserModel(address={"zip_code": "not-int"})
    except ValidationError as e:
        problem = build_from_pydantic_error(e.errors())
        assert problem.error_count == 1
        assert "/address/zip_code" in problem.errors[0].field
        print("    ✓ Nested field error converted correctly")

    # Test 4: Custom instance parameter
    print("  Test 4: Custom instance parameter")
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
    print("    ✓ Custom instance parameter applied correctly")

    # Test 5: Detail message singular/plural
    print("  Test 5: Detail message singular/plural")
    single_error = [{"type": "value_error", "loc": ("field",), "msg": "Invalid"}]
    problem_single = build_from_pydantic_error(single_error)
    assert "1 validation error occurred" in problem_single.detail
    print("    ✓ Singular detail message correct")

    multiple_errors = [
        {"type": "value_error", "loc": ("field1",), "msg": "Invalid"},
        {"type": "value_error", "loc": ("field2",), "msg": "Invalid"},
    ]
    problem_multiple = build_from_pydantic_error(multiple_errors)
    assert "2 validation errors occurred" in problem_multiple.detail
    print("    ✓ Plural detail message correct")

    # Test 6: Special characters escaping
    print("  Test 6: Special character escaping")
    errors_special = [
        {"type": "value_error", "loc": ("data/field",), "msg": "Invalid"},
        {"type": "value_error", "loc": ("field~name",), "msg": "Invalid"},
    ]
    problem = build_from_pydantic_error(errors_special)
    assert problem.errors[0].field == "/data~1field"
    assert problem.errors[1].field == "/field~0name"
    print("    ✓ Special characters properly escaped")

    # Test 7: RFC 7807 compliance
    print("  Test 7: RFC 7807 compliance")
    problem = build_from_pydantic_error(
        [{"type": "value_error", "loc": ("test",), "msg": "Invalid"}]
    )
    data = problem.model_dump_rfc7807()
    assert "type" in data
    assert "title" in data
    assert "status" in data
    assert "detail" in data
    assert "errors" in data
    print("    ✓ RFC 7807 required fields present")

    print("  All build_from_pydantic_error tests passed!\n")
    return True


def test_performance():
    """Test performance with many errors"""
    from fastapi.responses_rfc7807 import build_from_pydantic_error
    import time

    print("Testing performance with many errors...")

    # Generate 100 errors
    error_list = [
        {
            "type": "value_error",
            "loc": ("field", i),
            "msg": f"Error {i}",
            "ctx": {"min_length": 5},
        }
        for i in range(100)
    ]

    start = time.time()
    problem = build_from_pydantic_error(error_list)
    elapsed = time.time() - start

    assert problem.error_count == 100
    assert len(problem.errors) == 100

    print(f"  ✓ Converted 100 errors in {elapsed*1000:.2f}ms")
    print(f"  ✓ Average time per error: {(elapsed/100)*1000:.3f}ms")
    print()
    return True


def main():
    """Run all validation tests"""
    print("=" * 70)
    print("RFC 7807 build_from_pydantic_error - Validation Tests")
    print("=" * 70)
    print()

    try:
        success = True
        success = test_json_pointer_conversion() and success
        success = test_build_from_pydantic_error() and success
        success = test_performance() and success

        if success:
            print("=" * 70)
            print("✓ ALL TESTS PASSED")
            print("=" * 70)
            return 0
        else:
            print("=" * 70)
            print("✗ SOME TESTS FAILED")
            print("=" * 70)
            return 1

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
