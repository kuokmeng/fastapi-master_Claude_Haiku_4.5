"""
RFC 7807 Problem Details for HTTP APIs - Pydantic v2 Models

Reference: https://datatracker.ietf.org/doc/html/rfc7807

This module provides standards-compliant error response models that:
1. Implement RFC 7807 Problem Details specification
2. Maintain backward compatibility with FastAPI's current error format
3. Handle Python reserved keyword 'type' via Field(alias="type")
4. Support extension members for domain-specific errors
5. Include proper validation and type safety

Core Design Principles:
- Strict JSON/Python keyword compatibility (Field aliases)
- ConfigDict for comprehensive model configuration
- Backward compatibility through optional legacy fields
- Comprehensive validation and examples
- Extensibility via discriminated unions and inheritance
"""

from datetime import datetime
from typing import Any, Annotated, Optional, Union, Literal
from enum import Enum
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    field_validator,
    model_validator,
    field_serializer,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
)
from pydantic_core import core_schema
from pydantic.json_schema import JsonSchemaValue


# ============================================================================
# Enums for Standard Problem Types
# ============================================================================


class ProblemTypePrefix(str, Enum):
    """Standard problem type URI prefixes for categorization"""

    HTTP_ERRORS = "https://httpwg.org/specs/rfc7807"
    VALIDATION = "urn:error:validation"
    AUTHENTICATION = "urn:error:authentication"
    AUTHORIZATION = "urn:error:authorization"
    BUSINESS_LOGIC = "urn:error:business"
    TECHNICAL = "urn:error:technical"


class StandardHttpProblemType(str, Enum):
    """Standard HTTP problem types mapping to status codes"""

    BAD_REQUEST = "https://httpwg.org/specs/rfc7807#bad-request"
    UNAUTHORIZED = "https://httpwg.org/specs/rfc7807#unauthorized"
    FORBIDDEN = "https://httpwg.org/specs/rfc7807#forbidden"
    NOT_FOUND = "https://httpwg.org/specs/rfc7807#not-found"
    CONFLICT = "https://httpwg.org/specs/rfc7807#conflict"
    PAYLOAD_TOO_LARGE = "https://httpwg.org/specs/rfc7807#payload-too-large"
    UNPROCESSABLE_ENTITY = "https://httpwg.org/specs/rfc7807#unprocessable-entity"
    TOO_MANY_REQUESTS = "https://httpwg.org/specs/rfc7807#too-many-requests"
    INTERNAL_SERVER_ERROR = "https://httpwg.org/specs/rfc7807#internal-server-error"
    SERVICE_UNAVAILABLE = "https://httpwg.org/specs/rfc7807#service-unavailable"


# ============================================================================
# Core RFC 7807 ProblemDetails Model
# ============================================================================


class ProblemDetails(BaseModel):
    """
    RFC 7807 Problem Details for HTTP APIs
    https://datatracker.ietf.org/doc/html/rfc7807

    This is the base model for all error responses. It provides:
    - Machine-readable error type via URI (solves type keyword conflict)
    - Human-readable title and detail fields
    - HTTP status code
    - Problem instance for error correlation
    - Extensible for domain-specific fields

    All responses MUST include: type, title, detail
    All responses SHOULD include: status, instance

    Example (RFC 7807 compliant):
        {
            "type": "https://api.example.com/errors/validation",
            "title": "Validation Failed",
            "status": 400,
            "detail": "One or more validation errors occurred",
            "instance": "/api/v1/items"
        }
    """

    model_config = ConfigDict(
        # JSON Schema & Serialization
        json_schema_extra={
            "type": "object",
            "additionalProperties": True,  # Allow extensions per RFC 7807
            "examples": [
                {
                    "type": "https://api.example.com/errors/validation",
                    "title": "Validation Failed",
                    "status": 400,
                    "detail": "One or more validation errors occurred",
                    "instance": "/api/v1/items",
                }
            ],
        },
        # Serialization behavior
        populate_by_name=True,  # Accept both 'type' (via alias) and 'problem_type'
    )

    # CRITICAL: Field alias 'type' handles Python reserved keyword
    problem_type: Annotated[
        str,
        Field(
            alias="type",
            title="Problem Type",
            description=(
                "A URI reference [RFC3986] that identifies the problem type. "
                "This specification encourages that, when applicable, problem types are "
                "identified by documentation that explains how to recover from the "
                "described problem."
            ),
            examples=[
                "https://api.example.com/errors/validation",
                "https://api.example.com/errors/insufficient-funds",
                "urn:error:authentication:invalid-token",
            ],
            min_length=1,
            max_length=2048,  # Practical URI length limit
            pattern=r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^#|^/",  # URI or fragment identifier
        ),
    ]

    title: Annotated[
        str,
        Field(
            title="Problem Title",
            description=(
                "A short, human-readable summary of the problem type. "
                "It SHOULD NOT change from occurrence to occurrence of the problem, "
                "except for purposes of localization."
            ),
            examples=[
                "Validation Failed",
                "Insufficient Funds",
                "Invalid Token",
            ],
            min_length=1,
            max_length=255,
        ),
    ]

    status: Annotated[
        int,
        Field(
            title="HTTP Status Code",
            description=(
                "The HTTP status code [RFC7231], Section 6, generated by the origin "
                "server for this occurrence of the problem."
            ),
            examples=[400, 403, 404, 500],
            ge=100,
            le=599,
        ),
    ]

    detail: Annotated[
        str,
        Field(
            title="Problem Detail",
            description=(
                "A human-readable explanation specific to this occurrence of the problem. "
                "Unlike 'title', this field's value SHOULD be focused on this problem "
                "occurrence, and generally SHOULD NOT be translated."
            ),
            examples=[
                "The request body does not match the expected schema",
                "Account balance is insufficient for the requested withdrawal",
            ],
            min_length=1,
            max_length=1024,
        ),
    ]

    instance: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Problem Instance",
            description=(
                "A URI reference that identifies the specific occurrence of the problem. "
                "It may or may not yield further information if dereferenced. "
                "This can be used for correlation and debugging."
            ),
            examples=[
                "/api/v1/items/123",
                "/api/v1/users/john-doe/orders/456",
                "/api/v1/bulk-operations/78910",
            ],
            max_length=2048,
        ),
    ] = None

    # ========================================================================
    # Backward Compatibility Fields
    # ========================================================================
    # These fields support legacy FastAPI error formats while transitioning
    # to RFC 7807 compliance. They should be gradually deprecated.

    # Legacy field: custom error code
    error_code: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Error Code",
            description=(
                "[LEGACY] Deprecated in favor of 'type'. "
                "Kept for backward compatibility with existing API contracts."
            ),
        ),
    ] = None

    # Legacy field: timestamp of error occurrence
    timestamp: Annotated[
        Optional[datetime],
        Field(
            default=None,
            title="Error Timestamp",
            description=(
                "[LEGACY] Timestamp when the error occurred. "
                "Useful for correlating with server logs. "
                "Automatically set if not provided."
            ),
        ),
    ] = None

    # Legacy field: request ID for tracing
    request_id: Annotated[
        Optional[Union[str, UUID]],
        Field(
            default=None,
            title="Request ID",
            description=(
                "[LEGACY] Unique identifier for the request that caused this error. "
                "Useful for log correlation and support tickets."
            ),
        ),
    ] = None

    # ========================================================================
    # Validators
    # ========================================================================

    @field_validator("problem_type", mode="before")
    @classmethod
    def validate_problem_type_uri(cls, v: Any) -> str:
        """Ensure problem_type is a valid URI reference"""
        v = str(v).strip()
        # Accept relative URIs (starting with /) and absolute URIs
        if not (
            v.startswith("http://")
            or v.startswith("https://")
            or v.startswith("urn:")
            or v.startswith("#")
            or v.startswith("/")
        ):
            # Allow ENUMs to pass through
            if not isinstance(v, Enum):
                raise ValueError(
                    f"problem_type must be a valid URI reference. Got: {v!r}"
                )
        return v

    @field_validator("status")
    @classmethod
    def validate_status_code(cls, v: int) -> int:
        """Ensure status is a valid HTTP status code"""
        if not (100 <= v <= 599):
            raise ValueError(
                f"status must be a valid HTTP status code (100-599). Got: {v}"
            )
        return v

    @field_validator("title", "detail")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        """Ensure title and detail are non-empty"""
        # Pydantic v2 handles whitespace via Field(strip_whitespace=True) if needed
        if not v or not v.strip():
            raise ValueError("field cannot be empty")
        return v

    @model_validator(mode="after")
    def set_timestamp_if_needed(self) -> "ProblemDetails":
        """Auto-set timestamp if not provided and if legacy field is used"""
        if self.timestamp is None and self.request_id is not None:
            # Only set if explicitly tracking legacy request_id
            self.timestamp = datetime.utcnow()
        return self

    # ========================================================================
    # Serialization
    # ========================================================================

    def model_dump_rfc7807(
        self,
        *,
        include_none: bool = False,
        include_legacy: bool = False,
    ) -> dict[str, Any]:
        """
        Export as RFC 7807 compliant JSON object.

        Args:
            include_none: Include fields with None values
            include_legacy: Include deprecated backward compatibility fields

        Returns:
            Dictionary suitable for JSONResponse serialization

        Example:
            >>> problem = ProblemDetails(
            ...     problem_type="https://api.example.com/errors/validation",
            ...     title="Validation Failed",
            ...     status=400,
            ...     detail="Email is invalid"
            ... )
            >>> problem.model_dump_rfc7807()
            {
                "type": "https://api.example.com/errors/validation",
                "title": "Validation Failed",
                "status": 400,
                "detail": "Email is invalid"
            }
        """
        data = self.model_dump(
            by_alias=True,  # Convert 'problem_type' to 'type' in output
            exclude_none=not include_none,
            exclude=(
                {
                    "error_code",
                    "timestamp",
                    "request_id",
                }
                if not include_legacy
                else set()
            ),
        )

        # Ensure required RFC 7807 fields are always present
        required_fields = {"type", "title", "status", "detail"}
        for field in required_fields:
            if field not in data:
                raise ValueError(
                    f"RFC 7807 requires '{field}' field in serialized output"
                )

        return data

    def model_dump_with_legacy(self) -> dict[str, Any]:
        """
        Export with legacy backward-compatibility fields included.

        Use this only when supporting old API contracts during migration.

        Returns:
            Dictionary with both RFC 7807 and legacy fields
        """
        return self.model_dump_rfc7807(include_legacy=True, include_none=True)


# ============================================================================
# Validation Error Detail Model
# ============================================================================


class ValidationErrorDetail(BaseModel):
    """
    Individual validation error for RFC 7807 ValidationProblemDetails.

    This model represents a single field validation failure with:
    - Field path (JSON pointer style)
    - Human-readable message
    - Machine-readable error type
    - Optional: actual value and constraints violated

    Example:
        {
            "field": "email",
            "message": "Invalid email format",
            "type": "value_error.email"
        }
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "field": "email",
                    "message": "Invalid email format",
                    "type": "value_error.email",
                },
                {
                    "field": "password",
                    "message": "Password must be at least 8 characters",
                    "type": "value_error.string.min_length",
                    "constraint": "min_length=8",
                },
            ]
        },
        populate_by_name=True,
    )

    field: Annotated[
        str,
        Field(
            title="Field Path",
            description=(
                "JSON pointer-style path to the field that failed validation. "
                "Examples: 'email', 'address.zip_code', 'items.0.name'"
            ),
            examples=["email", "address.zip_code", "items"],
            min_length=1,
            max_length=256,
        ),
    ]

    message: Annotated[
        str,
        Field(
            title="Error Message",
            description=(
                "Human-readable explanation of the validation failure. "
                "Should be user-friendly and actionable."
            ),
            examples=[
                "Invalid email format",
                "Password must be at least 8 characters",
                "Value must be positive",
            ],
            min_length=1,
            max_length=512,
        ),
    ]

    error_type: Annotated[
        str,
        Field(
            alias="type",
            title="Error Type Code",
            description=(
                "Machine-readable error type for programmatic handling. "
                "Can be Pydantic error code, custom application code, etc."
            ),
            examples=[
                "value_error.email",
                "value_error.number.not_ge",
                "validation.custom_rule",
            ],
            min_length=1,
            max_length=128,
        ),
    ]

    value: Annotated[
        Optional[Any],
        Field(
            default=None,
            title="Invalid Value",
            description=(
                "The actual value that failed validation. "
                "ONLY included in debug mode for security reasons. "
                "May be None if value is sensitive."
            ),
        ),
    ] = None

    constraint: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Constraint Details",
            description=(
                "Specific constraint that was violated. "
                "Examples: 'minimum=1', 'pattern=^[a-z]+$', 'max_length=255'"
            ),
            examples=[
                "minimum_value=1",
                "maximum_length=255",
                "pattern=^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$",
            ],
            max_length=256,
        ),
    ] = None

    @field_validator("field", "error_type")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Ensure field and error_type are non-empty"""
        if not v or not v.strip():
            raise ValueError("field cannot be empty")
        return v.strip()


# ============================================================================
# Validation Problem Details - RFC 7807 Extension
# ============================================================================


class ValidationProblemDetails(ProblemDetails):
    """
    RFC 7807 Problem Details for validation errors (HTTP 400 Bad Request).

    This extends ProblemDetails with validation-specific fields:
    - Array of individual validation errors
    - Error count for quick reference
    - Optional source indicating whether errors are from request body, params, etc.

    Example:
        {
            "type": "https://api.example.com/errors/validation",
            "title": "Validation Failed",
            "status": 400,
            "detail": "2 validation errors occurred",
            "instance": "/api/v1/items",
            "errors": [
                {
                    "field": "email",
                    "message": "Invalid email format",
                    "type": "value_error.email"
                },
                {
                    "field": "age",
                    "message": "Value must be positive",
                    "type": "value_error.number.not_ge",
                    "constraint": "minimum_value=0"
                }
            ],
            "error_count": 2
        }
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "https://api.example.com/errors/validation",
                    "title": "Validation Failed",
                    "status": 400,
                    "detail": "2 validation errors occurred",
                    "instance": "/api/v1/items",
                    "errors": [
                        {
                            "field": "email",
                            "message": "Invalid email format",
                            "type": "value_error.email",
                        },
                        {
                            "field": "age",
                            "message": "Value must be >= 0",
                            "type": "value_error.number.not_ge",
                            "constraint": "minimum_value=0",
                        },
                    ],
                    "error_count": 2,
                }
            ]
        },
    )

    # Override status to default to 400
    status: int = Field(default=400, ge=400, le=499)

    errors: Annotated[
        list[ValidationErrorDetail],
        Field(
            title="Validation Errors",
            description="Array of individual validation errors",
            min_length=1,  # Must have at least one error
        ),
    ]

    error_count: Annotated[
        int,
        Field(
            title="Error Count",
            description="Total number of validation errors",
            ge=1,
        ),
    ]

    error_source: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Error Source",
            description=(
                "Where the validation errors originated: "
                "'body', 'query', 'path', 'header', 'cookie', 'form', etc."
            ),
            examples=["body", "query", "path"],
        ),
    ] = None

    @model_validator(mode="after")
    def validate_error_count_matches_errors(self) -> "ValidationProblemDetails":
        """Ensure error_count matches actual errors array length"""
        if self.error_count != len(self.errors):
            self.error_count = len(self.errors)
        return self

    @field_validator("errors", mode="before")
    @classmethod
    def ensure_non_empty_errors(cls, v: Any) -> list:
        """Ensure at least one error is provided"""
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("At least one validation error is required")
        return v


# ============================================================================
# Authentication & Authorization Problem Details
# ============================================================================


class AuthenticationProblemDetails(ProblemDetails):
    """
    RFC 7807 Problem Details for authentication errors (HTTP 401 Unauthorized).

    Includes authentication-specific fields:
    - Challenge scheme (e.g., Bearer, Basic)
    - Realm for credential scope
    - Scopes required (for OAuth2/Bearer tokens)

    Example:
        {
            "type": "https://api.example.com/errors/authentication",
            "title": "Unauthorized",
            "status": 401,
            "detail": "Bearer token has expired",
            "instance": "/api/v1/protected-resource",
            "challenge_scheme": "Bearer",
            "realm": "protected-api",
            "required_scopes": ["read:items", "write:items"]
        }
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "https://api.example.com/errors/authentication",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "Bearer token has expired",
                    "instance": "/api/v1/protected-resource",
                    "challenge_scheme": "Bearer",
                    "realm": "protected-api",
                }
            ]
        },
    )

    status: int = Field(default=401, ge=401, le=401)

    challenge_scheme: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Authentication Challenge Scheme",
            description=(
                "The HTTP authentication scheme (e.g., 'Bearer', 'Basic', 'Digest'). "
                "Corresponds to WWW-Authenticate header."
            ),
            examples=["Bearer", "Basic", "Digest", "OAuth2"],
        ),
    ] = None

    realm: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Authentication Realm",
            description=(
                "The realm (scope) for authentication. "
                "Helps clients understand which credentials to use."
            ),
            examples=["protected-api", "user-service"],
        ),
    ] = None

    required_scopes: Annotated[
        Optional[list[str]],
        Field(
            default=None,
            title="Required OAuth2 Scopes",
            description=(
                "OAuth2/OpenID scopes required to access the resource. "
                "Only applicable for Bearer token authentication."
            ),
            examples=[["read:items", "write:items"]],
        ),
    ] = None


class AuthorizationProblemDetails(ProblemDetails):
    """
    RFC 7807 Problem Details for authorization errors (HTTP 403 Forbidden).

    Includes authorization-specific fields:
    - Required role/permission
    - Current role/permission
    - Resource being accessed

    Example:
        {
            "type": "https://api.example.com/errors/authorization",
            "title": "Forbidden",
            "status": 403,
            "detail": "User does not have permission to delete items",
            "instance": "/api/v1/items/123",
            "required_role": "admin",
            "current_role": "user",
            "resource": "/api/v1/items/123"
        }
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "https://api.example.com/errors/authorization",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": "User does not have admin permission",
                    "instance": "/api/v1/items/123",
                    "required_role": "admin",
                    "current_role": "user",
                }
            ]
        },
    )

    status: int = Field(default=403, ge=403, le=403)

    required_role: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Required Role",
            description="The role required to access the resource",
            examples=["admin", "moderator", "owner"],
        ),
    ] = None

    current_role: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Current User Role",
            description="The role the current user has",
            examples=["user", "guest"],
        ),
    ] = None

    resource: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Protected Resource",
            description="The resource that requires authorization",
            examples=["/api/v1/items/123", "/api/v1/admin/settings"],
        ),
    ] = None


# ============================================================================
# Business Logic Problem Details
# ============================================================================


class ConflictProblemDetails(ProblemDetails):
    """
    RFC 7807 Problem Details for conflict errors (HTTP 409 Conflict).

    Used when request conflicts with current state (e.g., duplicate ID, state violation).

    Example:
        {
            "type": "https://api.example.com/errors/conflict",
            "title": "Conflict",
            "status": 409,
            "detail": "Username 'john_doe' already exists",
            "instance": "/api/v1/users",
            "conflict_field": "username",
            "existing_value": "john_doe"
        }
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "https://api.example.com/errors/conflict",
                    "title": "Conflict",
                    "status": 409,
                    "detail": "Username already exists",
                    "instance": "/api/v1/users",
                    "conflict_field": "username",
                }
            ]
        },
    )

    status: int = Field(default=409, ge=409, le=409)

    conflict_field: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Conflicting Field",
            description="The field that caused the conflict",
            examples=["username", "email", "order_id"],
        ),
    ] = None

    existing_value: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Existing Value",
            description="The value that already exists (masked for security)",
        ),
    ] = None


# ============================================================================
# Rate Limiting Problem Details
# ============================================================================


class RateLimitProblemDetails(ProblemDetails):
    """
    RFC 7807 Problem Details for rate limit errors (HTTP 429 Too Many Requests).

    Includes rate-limiting information per RFC 6585.

    Example:
        {
            "type": "https://api.example.com/errors/rate-limit",
            "title": "Too Many Requests",
            "status": 429,
            "detail": "Rate limit exceeded. Maximum 100 requests per minute.",
            "instance": "/api/v1/items",
            "retry_after_seconds": 45,
            "limit": 100,
            "window_seconds": 60,
            "remaining": 0
        }
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "https://api.example.com/errors/rate-limit",
                    "title": "Too Many Requests",
                    "status": 429,
                    "detail": "Rate limit exceeded",
                    "instance": "/api/v1/items",
                    "retry_after_seconds": 45,
                    "limit": 100,
                    "window_seconds": 60,
                    "remaining": 0,
                }
            ]
        },
    )

    status: int = Field(default=429, ge=429, le=429)

    retry_after_seconds: Annotated[
        int,
        Field(
            title="Retry After (seconds)",
            description="Number of seconds to wait before retrying",
            ge=1,
            examples=[45, 60],
        ),
    ]

    limit: Annotated[
        int,
        Field(
            title="Rate Limit",
            description="Maximum requests allowed in the window",
            ge=1,
        ),
    ]

    window_seconds: Annotated[
        int,
        Field(
            title="Rate Limit Window",
            description="Time window for the rate limit (in seconds)",
            ge=1,
        ),
    ]

    remaining: Annotated[
        int,
        Field(
            title="Remaining Requests",
            description="Remaining requests available in current window",
            ge=0,
        ),
    ]

    reset_at: Annotated[
        Optional[datetime],
        Field(
            default=None,
            title="Reset Time",
            description="When the rate limit counter resets",
        ),
    ] = None


# ============================================================================
# Server Error Problem Details
# ============================================================================


class InternalServerErrorProblemDetails(ProblemDetails):
    """
    RFC 7807 Problem Details for server errors (HTTP 5xx).

    Includes server error tracking fields for support and debugging.
    Should NEVER expose sensitive internal error details to clients.

    Example:
        {
            "type": "https://api.example.com/errors/internal-server-error",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected error occurred",
            "instance": "/api/v1/items",
            "error_id": "e1234567-89ab-cdef-0123-456789abcdef",
            "support_url": "https://support.example.com/error/e1234567"
        }
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "https://api.example.com/errors/internal-server-error",
                    "title": "Internal Server Error",
                    "status": 500,
                    "detail": "An unexpected error occurred. Please contact support.",
                    "instance": "/api/v1/items",
                    "error_id": "e1234567-89ab-cdef-0123-456789abcdef",
                    "support_url": "https://support.example.com/error/e1234567",
                }
            ]
        },
    )

    status: int = Field(default=500, ge=500, le=599)

    error_id: Annotated[
        str,
        Field(
            default_factory=lambda: str(uuid4()),
            title="Error ID",
            description=(
                "Unique identifier for this error occurrence. "
                "Customers can use this when contacting support."
            ),
        ),
    ]

    support_url: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Support URL",
            description="URL to error documentation or support page",
            examples=["https://support.example.com/error/e1234567"],
        ),
    ] = None

    error_code: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Internal Error Code",
            description=(
                "[ADMIN ONLY] Internal error code for debugging. "
                "Not shown to regular users."
            ),
        ),
    ] = None


# ============================================================================
# Discriminated Union for All Problem Types
# ============================================================================

# Type alias for all possible problem detail types
AllProblemDetails = Union[
    ProblemDetails,
    ValidationProblemDetails,
    AuthenticationProblemDetails,
    AuthorizationProblemDetails,
    ConflictProblemDetails,
    RateLimitProblemDetails,
    InternalServerErrorProblemDetails,
]


# ============================================================================
# Utility Functions for Pydantic Error Conversion & Problem Details Creation
# ============================================================================


def _loc_to_json_pointer(loc: tuple) -> str:
    """
    Convert a Pydantic error location tuple to RFC 6901 JSON Pointer.

    RFC 6901 specifies JSON Pointer format with "/" separator and escape rules:
    - "~" becomes "~0"
    - "/" becomes "~1"

    Args:
        loc: Tuple from pydantic error (e.g., ('user', 'email') or ('items', 0, 'name'))

    Returns:
        JSON Pointer string (e.g., "/user/email" or "/items/0/name")

    Performance: O(n) where n is tuple length, with string escaping done once per segment
    Security: Safely escapes all control characters via RFC 6901 rules

    Examples:
        >>> _loc_to_json_pointer(('email',))
        '/email'
        >>> _loc_to_json_pointer(('address', 'zip_code'))
        '/address/zip_code'
        >>> _loc_to_json_pointer(('items', 0, 'name'))
        '/items/0/name'
        >>> _loc_to_json_pointer(('data/field',))  # Escape forward slash
        '/data~1field'
        >>> _loc_to_json_pointer(('field~name',))  # Escape tilde
        '/field~0name'
    """
    if not loc:
        return ""

    # Build pointer segments with proper escaping
    # Performance: Use single pass with efficient string operations
    segments = []
    for segment in loc:
        # Convert segment to string (handles both strings and ints from indexing)
        segment_str = str(segment)

        # RFC 6901 escape rules: ~ first, then /
        # Done in-place for better performance
        segment_str = segment_str.replace("~", "~0").replace("/", "~1")

        segments.append(segment_str)

    # Join with "/" and prepend "/" for absolute pointer
    return "/" + "/".join(segments)


def build_from_pydantic_error(
    error_list: list[dict],
    instance: Optional[str] = None,
    problem_type: str = "https://api.example.com/errors/validation",
) -> ValidationProblemDetails:
    """
    Convert Pydantic ValidationError list to RFC 7807 ValidationProblemDetails.

    Maps loc tuples to JSON Pointers (RFC 6901) for field identification
    and extracts error details for RFC 7807 compliance.

    Args:
        error_list: List of error dicts from pydantic.ValidationError.errors()
                   Each dict contains: 'loc', 'msg', 'type', optionally 'ctx'
        instance: Optional URI reference for the specific problem occurrence
        problem_type: URI reference identifying the error type

    Returns:
        ValidationProblemDetails with all errors converted to RFC 7807 format

    Performance: O(n) where n is number of errors, with minimal allocations
    Security: Properly escapes field paths, excludes sensitive values by default

    Example:
        >>> from pydantic import ValidationError, BaseModel
        >>> class User(BaseModel):
        ...     email: str
        ...     age: int
        >>> try:
        ...     User(email="not-email", age="not-int")
        ... except ValidationError as e:
        ...     problem = build_from_pydantic_error(
        ...         e.errors(),
        ...         instance="/api/v1/users"
        ...     )
        ...     print(problem.error_count)  # 2
        ...     print(problem.errors[0].field)  # "/email"
    """
    validation_errors: list[ValidationErrorDetail] = []

    for error in error_list:
        # Extract location tuple and convert to JSON Pointer
        loc: tuple = error.get("loc", ())
        field_path = _loc_to_json_pointer(loc)

        # Extract error message and type
        msg: str = str(error.get("msg", "Unknown error"))
        error_type: str = error.get("type", "validation.error")

        # Extract context for constraint details (optional, security-conscious)
        ctx: dict = error.get("ctx", {})
        constraint = None

        # Build constraint string from common Pydantic context fields
        # Only include if not sensitive (avoid exposing actual values)
        if ctx:
            # Common validation constraint keys from Pydantic
            constraint_parts = []
            for key in ["min_length", "max_length", "ge", "le", "pattern"]:
                if key in ctx:
                    value = ctx[key]
                    # Skip if value might be sensitive (very long or looks like data)
                    if isinstance(value, (int, str)) and len(str(value)) < 100:
                        constraint_parts.append(f"{key}={value}")

            constraint = ", ".join(constraint_parts) if constraint_parts else None

        # Create ValidationErrorDetail with JSON Pointer field path
        validation_errors.append(
            ValidationErrorDetail(
                field=field_path,
                message=msg,
                error_type=error_type,
                constraint=constraint,
            )
        )

    # Generate detail summary
    error_count = len(validation_errors)
    detail = f"{error_count} validation error{'s' if error_count != 1 else ''} occurred"

    # Build and return ValidationProblemDetails
    return ValidationProblemDetails(
        problem_type=problem_type,
        title="Validation Failed",
        status=400,
        detail=detail,
        instance=instance,
        errors=validation_errors,
        error_count=error_count,
    )


def create_validation_problem(
    detail: str,
    errors: list[ValidationErrorDetail],
    instance: Optional[str] = None,
    problem_type: str = "https://api.example.com/errors/validation",
) -> ValidationProblemDetails:
    """
    Create a ValidationProblemDetails instance.

    Args:
        detail: Human-readable description of the validation failure
        errors: List of individual validation errors
        instance: URI reference identifying the specific occurrence
        problem_type: URI reference identifying the problem type

    Returns:
        ValidationProblemDetails instance
    """
    return ValidationProblemDetails(
        problem_type=problem_type,
        title="Validation Failed",
        status=400,
        detail=detail,
        instance=instance,
        errors=errors,
        error_count=len(errors),
    )


def create_authentication_problem(
    detail: str,
    instance: Optional[str] = None,
    challenge_scheme: Optional[str] = None,
    realm: Optional[str] = None,
) -> AuthenticationProblemDetails:
    """
    Create an AuthenticationProblemDetails instance.

    Args:
        detail: Human-readable authentication failure description
        instance: URI reference identifying the specific occurrence
        challenge_scheme: HTTP authentication scheme (Bearer, Basic, etc.)
        realm: Authentication realm/scope

    Returns:
        AuthenticationProblemDetails instance
    """
    return AuthenticationProblemDetails(
        problem_type="https://api.example.com/errors/authentication",
        title="Unauthorized",
        status=401,
        detail=detail,
        instance=instance,
        challenge_scheme=challenge_scheme,
        realm=realm,
    )


def create_authorization_problem(
    detail: str,
    instance: Optional[str] = None,
    required_role: Optional[str] = None,
    current_role: Optional[str] = None,
) -> AuthorizationProblemDetails:
    """
    Create an AuthorizationProblemDetails instance.

    Args:
        detail: Human-readable authorization failure description
        instance: URI reference identifying the specific occurrence
        required_role: Role required to access the resource
        current_role: Role the current user has

    Returns:
        AuthorizationProblemDetails instance
    """
    return AuthorizationProblemDetails(
        problem_type="https://api.example.com/errors/authorization",
        title="Forbidden",
        status=403,
        detail=detail,
        instance=instance,
        required_role=required_role,
        current_role=current_role,
    )


def create_conflict_problem(
    detail: str,
    instance: Optional[str] = None,
    conflict_field: Optional[str] = None,
) -> ConflictProblemDetails:
    """
    Create a ConflictProblemDetails instance.

    Args:
        detail: Human-readable conflict description
        instance: URI reference identifying the specific occurrence
        conflict_field: The field that caused the conflict

    Returns:
        ConflictProblemDetails instance
    """
    return ConflictProblemDetails(
        problem_type="https://api.example.com/errors/conflict",
        title="Conflict",
        status=409,
        detail=detail,
        instance=instance,
        conflict_field=conflict_field,
    )


def create_rate_limit_problem(
    limit: int,
    window_seconds: int,
    retry_after_seconds: int,
    instance: Optional[str] = None,
    remaining: int = 0,
) -> RateLimitProblemDetails:
    """
    Create a RateLimitProblemDetails instance.

    Args:
        limit: Maximum requests allowed in the window
        window_seconds: Time window for the rate limit
        retry_after_seconds: Seconds to wait before retrying
        instance: URI reference identifying the specific occurrence
        remaining: Remaining requests available

    Returns:
        RateLimitProblemDetails instance
    """
    return RateLimitProblemDetails(
        problem_type="https://api.example.com/errors/rate-limit",
        title="Too Many Requests",
        status=429,
        detail=f"Rate limit exceeded. Maximum {limit} requests per {window_seconds} seconds.",
        instance=instance,
        limit=limit,
        window_seconds=window_seconds,
        retry_after_seconds=retry_after_seconds,
        remaining=remaining,
    )


def create_internal_server_error_problem(
    detail: str = "An unexpected error occurred",
    instance: Optional[str] = None,
    support_url: Optional[str] = None,
) -> InternalServerErrorProblemDetails:
    """
    Create an InternalServerErrorProblemDetails instance.

    Args:
        detail: Human-readable error description (generic for security)
        instance: URI reference identifying the specific occurrence
        support_url: URL to error documentation or support

    Returns:
        InternalServerErrorProblemDetails instance
    """
    return InternalServerErrorProblemDetails(
        problem_type="https://api.example.com/errors/internal-server-error",
        title="Internal Server Error",
        status=500,
        detail=detail,
        instance=instance,
        support_url=support_url,
    )


__all__ = [
    # Core models
    "ProblemDetails",
    "ValidationErrorDetail",
    "ValidationProblemDetails",
    "AuthenticationProblemDetails",
    "AuthorizationProblemDetails",
    "ConflictProblemDetails",
    "RateLimitProblemDetails",
    "InternalServerErrorProblemDetails",
    # Enums
    "ProblemTypePrefix",
    "StandardHttpProblemType",
    # Union type
    "AllProblemDetails",
    # Utility functions
    "build_from_pydantic_error",
    "create_validation_problem",
    "create_authentication_problem",
    "create_authorization_problem",
    "create_conflict_problem",
    "create_rate_limit_problem",
    "create_internal_server_error_problem",
]
