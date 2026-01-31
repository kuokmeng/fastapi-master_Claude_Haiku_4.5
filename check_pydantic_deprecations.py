#!/usr/bin/env python
"""
Check for Pydantic v2 ConfigDict deprecation warnings
"""
import sys
import warnings

# Capture all warnings
warnings.filterwarnings("error", category=DeprecationWarning)
warnings.filterwarnings("error", category=PendingDeprecationWarning)

try:
    from pydantic import BaseModel, ConfigDict, Field
    from typing import Annotated, Optional, Any

    # Test 1: Check for deprecated parameters
    print("Testing ConfigDict parameters...")

    # These are deprecated in Pydantic v2:
    # - json_schema_extra (dict form) should use json_schema_extra or model_json_schema
    # - use_enum_values → ser_json_schema_extra
    # - str_strip_whitespace → might be deprecated
    # - ser_json_schema_extra might have different form

    class TestModel(BaseModel):
        model_config = ConfigDict(
            json_schema_extra={"example": {"field": "value"}},
            populate_by_name=True,  # OK - Pydantic v2 standard
        )

        field: Annotated[str, Field(min_length=1)]

    # Create instance
    obj = TestModel(field="test")
    print(f"✓ Model instantiation successful: {obj}")

    # Test 2: Check field_validator usage
    from pydantic import field_validator, model_validator

    class TestValidator(BaseModel):
        value: str

        @field_validator("value")
        @classmethod
        def validate_value(cls, v):
            if not v:
                raise ValueError("Cannot be empty")
            return v

    obj2 = TestValidator(value="test")
    print(f"✓ Field validator works: {obj2}")

    # Test 3: Check model_validator usage
    class TestModelValidator(BaseModel):
        field1: str
        field2: Optional[str] = None

        @model_validator(mode="after")
        def check_fields(self):
            return self

    obj3 = TestModelValidator(field1="test")
    print(f"✓ Model validator works: {obj3}")

    print("\n✓ All Pydantic v2 patterns compatible")

except DeprecationWarning as e:
    print(f"✗ Deprecation warning: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
