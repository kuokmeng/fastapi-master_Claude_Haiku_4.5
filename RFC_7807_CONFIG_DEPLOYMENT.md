"""
RFC 7807 Configuration & Deployment Guide

ConfigDict Settings, Environment-Specific Behavior, and Production Deployment
"""

# ============================================================================
# PYDANTIC V2 ConfigDict REFERENCE
# ============================================================================

"""
ConfigDict provides comprehensive model configuration including:

1. JSON Schema & Validation
   - json_schema_extra: Add custom JSON schema properties
   - json_encoders: Custom serialization functions
   - str_strip_whitespace: Strip whitespace from str fields

2. Serialization Behavior
   - populate_by_name: Accept both field name and alias during input
   - use_enum_values: Serialize enums as their values
   - exclude_none: Exclude None values from serialization
   - exclude_unset: Exclude unset fields from serialization

3. Validation Configuration
   - validate_default: Validate default values
   - validate_assignment: Validate on field assignment
   - arbitrary_types_allowed: Allow non-standard types

4. Type Checking & Compatibility
   - extra: 'forbid' | 'ignore' | 'allow' - how to handle extra fields
   - frozen: Make model immutable
   - from_attributes: Support orm_mode (Pydantic v1 compatibility)

Reference: https://docs.pydantic.dev/latest/concepts/models/#model-config
"""

# ============================================================================
# CONFIGDICT PATTERNS IN FASTAPI RFC 7807 MODELS
# ============================================================================


class ConfigDictPatterns:
    """
    This class documents the ConfigDict patterns used in the RFC 7807 models.
    """

    # Pattern 1: JSON Schema Documentation
    pattern_1_json_schema = {
        "model_config": {
            "json_schema_extra": {
                "examples": [
                    {
                        "type": "https://api.example.com/errors/validation",
                        "title": "Validation Failed",
                        "status": 400,
                        "detail": "One or more validation errors",
                        "instance": "/api/v1/items",
                    }
                ]
            }
        },
        "purpose": "Provides OpenAPI documentation with example responses",
    }

    # Pattern 2: Serialization Control
    pattern_2_serialization = {
        "model_config": {
            "populate_by_name": True,  # Accept both 'type' (alias) and 'problem_type'
            "use_enum_values": True,  # Serialize enums as values
            "str_strip_whitespace": True,  # Clean string inputs
        },
        "purpose": "Control how fields are serialized and deserialized",
    }

    # Pattern 3: JSON Serialization Extra
    pattern_3_json_ser_extra = {
        "model_config": {
            "ser_json_schema_extra": {
                "type": "object",
                "additionalProperties": True,  # Allow extension fields
            }
        },
        "purpose": (
            "OpenAPI schema allows domain-specific extensions per RFC 7807. "
            "additionalProperties: true allows clients to add custom fields."
        ),
    }


# ============================================================================
# ENVIRONMENT-SPECIFIC BEHAVIOR
# ============================================================================


from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
import os


class EnvironmentSpecificConfig:
    """Configure RFC 7807 responses based on environment"""

    @staticmethod
    def get_debug_mode() -> bool:
        """Check if application is in debug mode"""
        return os.getenv("DEBUG", "false").lower() == "true"

    @staticmethod
    def get_environment() -> str:
        """Get deployment environment"""
        return os.getenv("ENVIRONMENT", "production")


class ProblemDetailsWithEnvironment(BaseModel):
    """
    RFC 7807 ProblemDetails with environment-aware behavior
    """

    model_config = ConfigDict(
        # Strict validation in production
        validate_default=True,
        validate_assignment=os.getenv("ENVIRONMENT") == "production",
        # Deny extra fields in production
        extra="forbid" if os.getenv("ENVIRONMENT") == "production" else "ignore",
        # More lenient in development
        str_strip_whitespace=True,
    )

    problem_type: str = Field(..., alias="type")
    title: str
    status: int = Field(..., ge=100, le=599)
    detail: str
    instance: Optional[str] = None

    # Debug-only fields (not included in production)
    debug_info: Optional[str] = Field(
        default=None,
        description="[DEBUG ONLY] Internal debugging information",
    )
    stacktrace: Optional[list[str]] = Field(
        default=None,
        description="[DEBUG ONLY] Stack trace (only in development)",
    )

    @classmethod
    def create_with_environment(
        cls,
        problem_type: str,
        title: str,
        status: int,
        detail: str,
        instance: Optional[str] = None,
        debug_info: Optional[str] = None,
        stacktrace: Optional[list[str]] = None,
    ) -> "ProblemDetailsWithEnvironment":
        """Create problem with environment-aware behavior"""
        return cls(
            problem_type=problem_type,
            title=title,
            status=status,
            detail=detail,
            instance=instance,
            # Only include debug info in development
            debug_info=debug_info if EnvironmentSpecificConfig.get_debug_mode() else None,
            stacktrace=stacktrace if EnvironmentSpecificConfig.get_debug_mode() else None,
        )

    def model_dump_safe(self, **kwargs) -> dict:
        """Export safely, excluding debug info in production"""
        data = self.model_dump(by_alias=True, **kwargs)

        if not EnvironmentSpecificConfig.get_debug_mode():
            # Remove debug fields in production
            data.pop("debug_info", None)
            data.pop("stacktrace", None)

        return data


# ============================================================================
# VALIDATION CONFIGURATION
# ============================================================================


class StrictValidationConfig(BaseModel):
    """RFC 7807 models with strict validation"""

    model_config = ConfigDict(
        # Always validate on assignment
        validate_assignment=True,
        # Reject unknown fields
        extra="forbid",
        # Validate default values
        validate_default=True,
        # Frozen for immutability in production
        frozen=False,  # Set to True for immutable errors
    )

    problem_type: str = Field(..., alias="type")
    title: str = Field(..., min_length=1, max_length=255)
    status: int = Field(..., ge=100, le=599)
    detail: str = Field(..., min_length=1, max_length=1024)


# ============================================================================
# CUSTOM SERIALIZATION PATTERNS
# ============================================================================


from datetime import datetime
from pydantic import field_serializer


class ProblemDetailsWithCustomSerialization(BaseModel):
    """Example of custom serialization for RFC 7807 fields"""

    model_config = ConfigDict(
        ser_json_schema_extra={"additionalProperties": True}
    )

    problem_type: str = Field(..., alias="type")
    title: str
    status: int
    detail: str
    timestamp: Optional[datetime] = None

    @field_serializer("timestamp", when_used="json")
    def serialize_timestamp(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize timestamp in ISO 8601 format"""
        if value is None:
            return None
        return value.isoformat()


# ============================================================================
# EXTENSIBILITY PATTERNS
# ============================================================================


class ExtensibleProblemDetails(BaseModel):
    """
    RFC 7807 with extensible fields
    - Supports domain-specific extensions
    - Validated through ConfigDict
    """

    model_config = ConfigDict(
        # Allow additional properties for RFC 7807 extensions
        extra="allow",
        # Include them in JSON output
        ser_json_schema_extra={
            "type": "object",
            "additionalProperties": True,
        },
    )

    problem_type: str = Field(..., alias="type")
    title: str
    status: int
    detail: str
    instance: Optional[str] = None

    # Usage example:
    # problem = ExtensibleProblemDetails(
    #     problem_type="...",
    #     title="...",
    #     status=400,
    #     detail="...",
    #     insufficient_amount=100.00,  # ← Custom field
    #     required_amount=500.00,       # ← Custom field
    # )


# ============================================================================
# PRODUCTION DEPLOYMENT CHECKLIST
# ============================================================================

PRODUCTION_DEPLOYMENT_CHECKLIST = """
RFC 7807 Problem Details - Production Deployment Checklist

PRE-DEPLOYMENT VERIFICATION
===========================

☐ 1. Field Alias Configuration
  ☐ Verify Field(alias="type") is correctly set for problem_type
  ☐ Test deserialization from JSON with "type" key
  ☐ Test serialization outputs "type" key (not "problem_type")
  ☐ OpenAPI schema shows "type" field (not "problem_type")

☐ 2. Validation Rules
  ☐ problem_type must be valid URI reference
  ☐ status must be 100-599 HTTP status code
  ☐ title and detail must not be empty
  ☐ instance must be valid URI or path (if provided)
  ☐ Test with invalid inputs - proper ValidationError raised

☐ 3. Backward Compatibility
  ☐ Legacy fields (error_code, timestamp, request_id) optional
  ☐ model_dump_rfc7807() excludes legacy fields by default
  ☐ model_dump_with_legacy() includes legacy fields
  ☐ Existing clients receive RFC 7807 responses
  ☐ No breaking changes to core fields

☐ 4. Content-Type Headers
  ☐ All RFC 7807 responses include "Content-Type: application/problem+json"
  ☐ Exception handlers set proper Content-Type
  ☐ OpenAPI documentation shows correct media type
  ☐ Client SDKs recognize application/problem+json responses

☐ 5. Error Handler Registration
  ☐ RequestValidationError uses ValidationProblemDetails
  ☐ HTTPException returns ProblemDetails
  ☐ Custom exceptions mapped to appropriate problem types
  ☐ Unhandled exceptions use InternalServerErrorProblemDetails
  ☐ All handlers return proper HTTP status codes

☐ 6. Security Configuration
  ☐ Production: error_code excluded from responses
  ☐ Production: debug_info excluded from responses
  ☐ Production: stacktrace never included
  ☐ Development: debug fields available (optional)
  ☐ No sensitive data in problem_type or detail fields

☐ 7. Response Format Tests
  ☐ HTTP 400: Validation errors return ValidationProblemDetails
  ☐ HTTP 401: Authentication errors return AuthenticationProblemDetails
  ☐ HTTP 403: Authorization errors return AuthorizationProblemDetails
  ☐ HTTP 404: Not found errors return ProblemDetails
  ☐ HTTP 409: Conflict errors return ConflictProblemDetails
  ☐ HTTP 429: Rate limit errors return RateLimitProblemDetails
  ☐ HTTP 500: Server errors return InternalServerErrorProblemDetails

☐ 8. OpenAPI Documentation
  ☐ OpenAPI schema includes all problem detail models
  ☐ Response examples show RFC 7807 structure
  ☐ Field descriptions are accurate
  ☐ Aliases correctly shown in schema (type, not problem_type)
  ☐ Swagger UI displays responses correctly

☐ 9. Client Integration
  ☐ Client SDKs correctly handle Field(alias="type")
  ☐ OpenAPI code generators produce correct models
  ☐ Clients can deserialize all problem types
  ☐ Error handling logic updated for RFC 7807 format
  ☐ Client tests updated for new response structure

☐ 10. Performance & Monitoring
  ☐ No performance regression from RFC 7807 models
  ☐ Serialization is efficient
  ☐ Monitoring/logging captures error responses
  ☐ Error IDs (error_id) properly logged for tracing
  ☐ Rate limiting and error quotas working

☐ 11. Logging Configuration
  ☐ Server logs capture full error details
  ☐ Logs include error_id for correlation
  ☐ Logs accessible via request_id
  ☐ Sensitive data excluded from logs
  ☐ Error aggregation/monitoring integration working

☐ 12. Load Testing
  ☐ Load test validates RFC 7807 responses under stress
  ☐ Validation errors handled efficiently
  ☐ Rate limiting returns proper problem details
  ☐ No memory leaks in problem detail serialization
  ☐ Response times acceptable with RFC 7807 overhead

DEPLOYMENT COMMANDS
===================

# 1. Validate Pydantic models
python -m pytest tests/test_rfc7807_problem_details.py -v

# 2. Generate OpenAPI schema
curl http://localhost:8000/openapi.json | jq '.components.schemas | keys'

# 3. Test error response format
curl http://localhost:8000/items/invalid -H "Accept: application/problem+json"

# 4. Verify Content-Type header
curl -i http://localhost:8000/items/invalid | grep Content-Type

# 5. Check OpenAPI documentation
open http://localhost:8000/docs

ROLLBACK PROCEDURES
===================

If RFC 7807 migration causes issues:

1. Immediate: Set enable_rfc7807_errors=False in FastAPI()
2. Revert: Use previous exception_handlers.py
3. Notify: Alert API clients of temporary regression
4. Investigate: Debug and re-deploy with fixes
5. Gradual: Re-enable RFC 7807 for subset of endpoints first

POST-DEPLOYMENT MONITORING
==========================

1. Monitor error response format in logs
2. Track client SDK errors (Field alias issues)
3. Alert on ContentType mismatches
4. Monitor validation error patterns
5. Track deprecated field usage (legacy fields)
6. Validate OpenAPI schema updates

CLIENT MIGRATION TIMELINE
========================

Week 1: RFC 7807 responses available (opt-in)
Week 2: Documentation update, SDK changes
Week 3: Gradual rollout (10% → 25% → 50%)
Week 4: 100% RFC 7807 compliant
Week 5: Legacy format deprecated
Week 6: Legacy format support removed

DOCUMENTATION UPDATES
====================

☐ Update API documentation with RFC 7807 structure
☐ Add examples showing Field(alias="type") pattern
☐ Document error type URIs (problem_type values)
☐ Add client migration guide
☐ Document Content-Type header requirement
☐ Add troubleshooting section for common issues
☐ Update OpenAPI/Swagger documentation
☐ Create runbook for error investigation
"""

print(PRODUCTION_DEPLOYMENT_CHECKLIST)


# ============================================================================
# FASTAPI APPLICATION EXAMPLE WITH RFC 7807
# ============================================================================


example_fastapi_app = '''
"""
FastAPI application configured with RFC 7807 Problem Details
"""

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR

from fastapi.responses_rfc7807 import (
    ProblemDetails,
    ValidationProblemDetails,
    ValidationErrorDetail,
    InternalServerErrorProblemDetails,
)
import logging

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="RFC 7807 Compliant API",
    version="1.0.0",
    description="API using RFC 7807 Problem Details for HTTP APIs",
)


# ====================================================================
# Exception Handlers
# ====================================================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert Pydantic validation errors to RFC 7807 format"""
    
    errors = []
    for pydantic_error in exc.errors():
        errors.append(
            ValidationErrorDetail(
                field=".".join(str(x) for x in pydantic_error.get("loc", [])),
                message=pydantic_error.get("msg", "Validation failed"),
                error_type=pydantic_error.get("type", "validation_error"),
            )
        )
    
    problem = ValidationProblemDetails(
        problem_type="https://api.example.com/errors/validation",
        title="Validation Failed",
        status=HTTP_400_BAD_REQUEST,
        detail=f"{len(errors)} validation error(s)",
        instance=str(request.url.path),
        errors=errors,
        error_count=len(errors),
    )
    
    return JSONResponse(
        status_code=HTTP_400_BAD_REQUEST,
        content=problem.model_dump_rfc7807(),
        headers={"Content-Type": "application/problem+json"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return RFC 7807 error"""
    
    # Log actual error server-side
    logger.exception(f"Unhandled exception at {request.url.path}")
    
    # Return generic error to client (no sensitive details)
    problem = InternalServerErrorProblemDetails(
        problem_type="https://api.example.com/errors/internal-server-error",
        title="Internal Server Error",
        status=HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred. Please contact support.",
        instance=str(request.url.path),
        support_url="https://support.example.com/contact",
    )
    
    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content=problem.model_dump_rfc7807(),
        headers={"Content-Type": "application/problem+json"},
    )


# ====================================================================
# Routes
# ====================================================================


@app.get("/items/{item_id}")
async def get_item(item_id: int):
    """Get item by ID"""
    items = {1: "Item One", 2: "Item Two"}
    
    if item_id not in items:
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/not-found",
            title="Item Not Found",
            status=404,
            detail=f"Item with ID {item_id} not found",
            instance=f"/items/{item_id}",
        )
        return JSONResponse(
            status_code=404,
            content=problem.model_dump_rfc7807(),
            headers={"Content-Type": "application/problem+json"},
        )
    
    return {"item_id": item_id, "name": items[item_id]}


@app.post("/users")
async def create_user(email: str, password: str):
    """Create new user"""
    
    # Simple validation
    if "@" not in email:
        errors = [
            ValidationErrorDetail(
                field="email",
                message="Invalid email format",
                error_type="value_error.email",
            )
        ]
        problem = ValidationProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="Email validation failed",
            instance="/users",
            errors=errors,
            error_count=1,
        )
        return JSONResponse(
            status_code=400,
            content=problem.model_dump_rfc7807(),
            headers={"Content-Type": "application/problem+json"},
        )
    
    return {"email": email, "created": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''


# ============================================================================
# CONFIGURATION PRESETS
# ============================================================================


class RFC7807ConfigurationPresets:
    """Pre-built configurations for different scenarios"""

    DEVELOPMENT = {
        "DEBUG": True,
        "ENVIRONMENT": "development",
        "INCLUDE_DEBUG_INFO": True,
        "INCLUDE_STACKTRACE": True,
        "VALIDATION_MODE": "lenient",
        "VALIDATION_STRICT_ASSIGNMENT": False,
        "EXTRA_FIELDS_HANDLING": "ignore",
    }

    STAGING = {
        "DEBUG": False,
        "ENVIRONMENT": "staging",
        "INCLUDE_DEBUG_INFO": True,  # Optional for debugging deployments
        "INCLUDE_STACKTRACE": False,
        "VALIDATION_MODE": "strict",
        "VALIDATION_STRICT_ASSIGNMENT": True,
        "EXTRA_FIELDS_HANDLING": "forbid",
    }

    PRODUCTION = {
        "DEBUG": False,
        "ENVIRONMENT": "production",
        "INCLUDE_DEBUG_INFO": False,
        "INCLUDE_STACKTRACE": False,
        "VALIDATION_MODE": "strict",
        "VALIDATION_STRICT_ASSIGNMENT": True,
        "EXTRA_FIELDS_HANDLING": "forbid",
    }

    @staticmethod
    def apply_preset(environment: str) -> dict:
        """Apply configuration preset"""
        presets = {
            "development": RFC7807ConfigurationPresets.DEVELOPMENT,
            "staging": RFC7807ConfigurationPresets.STAGING,
            "production": RFC7807ConfigurationPresets.PRODUCTION,
        }
        return presets.get(environment, RFC7807ConfigurationPresets.PRODUCTION)


# ============================================================================
# SUMMARY
# ============================================================================

"""
RFC 7807 Configuration & Deployment Summary:

1. CONFIGDICT PATTERNS:
   - json_schema_extra: Document with examples
   - populate_by_name: Accept both field name and alias
   - use_enum_values: Serialize enums properly
   - str_strip_whitespace: Clean inputs
   - extra: Control additional fields (forbid in production)
   - validate_assignment: Strict in production

2. ENVIRONMENT-SPECIFIC:
   - DEBUG mode includes stack traces and debug_info
   - PRODUCTION mode excludes all debug information
   - STAGING allows debug info for troubleshooting

3. FIELD ALIAS HANDLING:
   - Use Field(alias="type") for Python keyword conflict
   - populate_by_name=True accepts both forms
   - model_dump(by_alias=True) serializes as "type"
   - OpenAPI schema automatically shows "type" field

4. PRODUCTION DEPLOYMENT:
   - Follow pre-deployment checklist (12 sections)
   - Validate with comprehensive tests
   - Monitor error responses in logs
   - Gradual rollout (phased approach)
   - Plan rollback procedures

5. CLIENT MIGRATION:
   - Provide 4-6 week migration window
   - Update SDKs to handle Field aliases
   - Test with existing clients
   - Document breaking changes
"""
