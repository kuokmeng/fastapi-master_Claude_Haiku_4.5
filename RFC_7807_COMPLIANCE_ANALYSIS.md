# RFC 7807 Compliance Analysis & Architecture Review
## FastAPI Error Response Standardization

**Author:** Senior Python Architect  
**Date:** January 30, 2026  
**Scope:** Error Handling Architecture & JSON Compliance  
**Status:** Comprehensive Schema Design Review

---

## Executive Summary

FastAPI's current error handling deviates from **RFC 7807 (Problem Details for HTTP APIs)** standards. The implementation exhibits inconsistent response structures, missing standardized problem fields, and a critical keyword conflict issue that requires Python `Field(..., alias="type")` workarounds. This analysis provides a detailed architectural assessment with compatibility implications for microservices standardization.

---

## Part 1: Current Implementation Analysis

### 1.1 Existing Error Response Architecture

#### Current Exception Handlers (`fastapi/exception_handlers.py`)

```python
async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    # Status: Minimalist approach - only "detail" field
    return JSONResponse(
        {"detail": exc.detail}, status_code=exc.status_code, headers=headers
    )

async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Status: Non-standardized structure
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())},
    )
```

**Problems Identified:**
- ✗ No standardized problem type field
- ✗ No standard instance URL field
- ✗ No title field for human-readable error classification
- ✗ Mismatch: HTTP errors use `"detail"` string, validation errors use `"detail"` array
- ✗ HTTP 422 status code is non-standard (not in RFC 7231)

#### Current ValidationError Structure (`fastapi/openapi/utils.py`)

```python
validation_error_definition = {
    "title": "ValidationError",
    "type": "object",
    "properties": {
        "loc": {               # Location - Pydantic-specific
            "type": "array",
            "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        },
        "msg": {               # Message - non-standard field name
            "type": "string",
        },
        "type": {              # ERROR TYPE CONFLICT: 'type' is Python keyword
            "type": "string",
        },
    },
    "required": ["loc", "msg", "type"],
}

validation_error_response_definition = {
    "title": "HTTPValidationError",
    "properties": {
        "detail": {            # Array of validation errors
            "type": "array",
            "items": {"$ref": "ValidationError"},
        }
    },
}
```

**Problems Identified:**
- ✗ **CRITICAL:** Field name `"type"` conflicts with Python reserved keyword
  - No `Field(..., alias="type")` pattern implemented
  - Creates JSON deserialization complexity for clients
  - Type safety issues in IDE/static analysis tools
- ✗ Pydantic-centric schema (not RFC 7807 compliant)
- ✗ Field naming inconsistency: `msg` vs RFC 7807's `detail`
- ✗ No abstraction mechanism for third-party error formats

---

## Part 2: RFC 7807 Standard Specification

### 2.1 RFC 7807 Problem Details Structure

The standard defines these fields:

```
type         - A URI reference identifying the problem type [REQUIRED for RFC compliance]
title        - A short, human-readable summary [RECOMMENDED]
status       - HTTP status code [OPTIONAL]
detail       - A human-readable explanation specific to this occurrence [OPTIONAL]
instance     - A URI reference identifying the specific occurrence [OPTIONAL]
[custom]     - Application-specific extension members [ALLOWED]
```

### 2.2 RFC 7807 HTTP Response Example

```json
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
    "type": "https://api.example.com/errors/insufficient-funds",
    "title": "Insufficient Funds",
    "status": 403,
    "detail": "Account balance is less than the requested withdrawal amount.",
    "instance": "/accounts/12345/withdrawals/1",
    "account_id": "12345",
    "balance": 30
}
```

---

## Part 3: Critical Issues & Design Flaws

### 3.1 Python Reserved Keyword Conflict: `type`

#### The Problem

```python
# In Pydantic model - THIS FAILS without Field alias
class ValidationErrorDetail(BaseModel):
    type: str  # ✗ SyntaxError: 'type' is a reserved keyword in Python
```

#### Current Implementation Gap

FastAPI OpenAPI schema defines `"type"` field but **provides no Field alias pattern**:

```python
# Current (BROKEN for Pydantic models):
validation_error_definition = {
    "properties": {
        "type": {"title": "Error Type", "type": "string"},  # 'type' keyword conflict
    }
}
```

#### Required Solution Pattern

```python
from pydantic import BaseModel, Field
from typing import Annotated

class ValidationErrorDetail(BaseModel):
    loc: Annotated[list[str | int], Field(title="Location")]
    msg: Annotated[str, Field(title="Message")]
    error_type: Annotated[str, Field(alias="type", title="Error Type")]
    # ^ Uses Python-safe 'error_type' but serializes as "type" in JSON

# Serialization:
model.model_dump(by_alias=True, exclude_none=True)
# Output: {"loc": [...], "msg": "...", "type": "..."}
```

---

### 3.2 Type Safety Issues

#### Problem: Dynamic `any()` Return Types

```python
class ValidationException(Exception):
    def __init__(
        self,
        errors: Sequence[Any],  # ✗ Loses type information
        *,
        endpoint_ctx: Optional[EndpointContext] = None,
    ) -> None:
        self._errors = errors

    def errors(self) -> Sequence[Any]:  # ✗ Returns untyped sequence
        return self._errors
```

**Impact:**
- IDE cannot provide type hints
- No static analysis of error structures
- Runtime errors go undetected
- Client code cannot serialize safely

#### Propagation Chain

```
RequestValidationError(errors: Sequence[Any])
    ↓
request_validation_exception_handler()
    ↓
jsonable_encoder(exc.errors())  # ✗ No schema validation
    ↓
JSONResponse(content={"detail": <untyped>})  # ✗ Anything serializes
```

---

### 3.3 Inconsistent Response Structures

#### HTTP Exception Response

```json
{
    "detail": "Item not found"  // String
}
```

#### Validation Error Response

```json
{
    "detail": [                 // Array
        {
            "loc": ["path", "item_id"],
            "msg": "value is not a valid integer",
            "type": "type_error.integer"
        }
    ]
}
```

**Problem:** Same field name (`detail`), completely different semantics. Client must inspect type at runtime.

---

### 3.4 Missing RFC 7807 Fields

#### Gap Analysis

| RFC 7807 Field | FastAPI HTTP | FastAPI Validation | Status |
|---|---|---|---|
| `type` (URI) | ✗ Missing | ✗ Missing (has custom field) | **CRITICAL** |
| `title` | ✗ Missing | ✗ Missing | **HIGH** |
| `status` | ✗ Missing | ✗ Missing | **HIGH** |
| `detail` | ✓ Present | ✓ Present | OK |
| `instance` | ✗ Missing | ✗ Missing | **HIGH** |
| Content-Type | application/json | application/json | **ISSUE**: Should be `application/problem+json` |

---

### 3.5 HTTP Status Code Misuse

#### 422 Unprocessable Entity

```python
return JSONResponse(
    status_code=422,  # ✗ WebDAV extension, not standard HTTP
    content={"detail": ...}
)
```

**Issues:**
- **RFC 7231** (HTTP semantics) only defines 1xx-5xx ranges
- 422 from **RFC 4918** (WebDAV) - not universally recognized
- Consumers expect standard codes: 400 (Bad Request), 409 (Conflict), etc.
- REST API contracts may not anticipate non-standard codes

**RFC 7807 Guidance:** Use standard 4xx codes (400, 409, 413, etc.)

---

## Part 4: API Misuse & Logic Errors

### 4.1 Error Handler Registration Without Type Safety

```python
# users/exceptions.py
class InsufficientPermissions(Exception):
    def __init__(self, required_role: str, actual_role: str):
        self.required_role = required_role
        self.actual_role = actual_role

# app.py - No typing, weak pattern
@app.exception_handler(InsufficientPermissions)
async def handle_permissions(request: Request, exc: InsufficientPermissions):
    return JSONResponse(
        status_code=403,
        content={  # ✗ No schema validation, can return anything
            "detail": f"Requires {exc.required_role}",
            "actual": exc.actual_role,
            # ✗ No RFC 7807 fields
        }
    )
```

**Misuse Patterns:**
- Handlers are untyped callback functions
- No schema enforcement at registration time
- Inconsistent response structures across handlers
- No mechanism for response validation

---

### 4.2 Pydantic ValidationError Leakage

```python
class ResponseValidationError(ValidationException):
    """Used when response_model validation fails"""
    def __init__(
        self,
        errors: Sequence[Any],  # ✗ Pydantic's raw error format
        *,
        body: Any = None,
        endpoint_ctx: Optional[EndpointContext] = None,
    ) -> None:
        super().__init__(errors, endpoint_ctx=endpoint_ctx)
        self.body = body
```

**Logic Error:** Response validation errors expose internal Pydantic structures but DON'T return to client (500 error by default). This creates:
- Inconsistent debugging experience
- No consistent error format
- Documentation mismatch (clients don't see this format)

---

### 4.3 Endpoint Context Not Exposed to Clients

```python
class ValidationException(Exception):
    def __init__(
        self,
        errors: Sequence[Any],
        *,
        endpoint_ctx: Optional[EndpointContext] = None,
    ) -> None:
        self._errors = errors
        self.endpoint_ctx = endpoint_ctx  # ✗ Never serialized

async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())},
        # ✗ exc.endpoint_ctx information discarded
        # ✗ Client cannot identify which operation failed
    )
```

**Missing:** RFC 7807's `instance` field should reference the operation/endpoint.

---

### 4.4 WebSocket Error Handling Discrepancy

```python
async def websocket_request_validation_exception_handler(
    websocket: WebSocket, exc: WebSocketRequestValidationError
) -> None:
    await websocket.close(
        code=WS_1008_POLICY_VIOLATION,
        reason=jsonable_encoder(exc.errors())  # ✗ String, not JSON Problem Details
    )
```

**Issues:**
- WebSocket close frame `reason` is limited to 123 bytes
- Cannot serialize full RFC 7807 problem details
- Different error format than HTTP responses
- No standard for WebSocket problem details

---

## Part 5: Compatibility Analysis

### 5.1 Microservice Integration Failures

#### Scenario: Aggregating Errors from Multiple Services

```python
# Microservice A (FastAPI current)
response_a = {
    "detail": [
        {"loc": ["query", "page"], "msg": "...", "type": "value_error.number.not_ge"}
    ]
}

# Microservice B (Your API Gateway standardizing on RFC 7807)
response_b = {
    "type": "https://api.example.com/errors/validation",
    "title": "Validation Failed",
    "status": 400,
    "detail": "Query parameter 'page' must be >= 1",
    "errors": [
        {
            "field": "page",
            "message": "Minimum value is 1"
        }
    ]
}

# Problem: Cannot merge or normalize responses
# Gateway must implement custom translation logic
```

#### Error Translation Costs

```python
def normalize_fastapi_validation_errors(fastapi_errors: dict) -> dict:
    """Expensive transformation - must be done for EVERY validation error"""
    rfc7807_errors = []
    for err in fastapi_errors.get("detail", []):
        # Pydantic error type → RFC 7807 type URI
        type_map = {
            "value_error.integer": "https://api.example.com/errors/invalid-integer",
            "value_error.number.not_ge": "https://api.example.com/errors/minimum-value",
            # ... hundreds more
        }
        rfc7807_errors.append({
            "type": type_map.get(err["type"], "https://api.example.com/errors/validation"),
            "title": err["type"],
            "detail": err["msg"],
            "instance": f"/docs#/paths/~1items~1{item_id}",
            "field": err["loc"][-1] if err["loc"] else None,
        })
    
    return {
        "type": "https://api.example.com/errors/validation-failed",
        "title": "Validation Failed",
        "status": 422,
        "detail": f"{len(rfc7807_errors)} validation error(s)",
        "errors": rfc7807_errors,
    }
```

---

### 5.2 Client SDK Generation Issues

#### OpenAPI Schema Generation

```python
# Current OpenAPI schema references non-existent types
"422": {
    "description": "Validation Error",
    "content": {
        "application/json": {
            "schema": {"$ref": "#/components/schemas/HTTPValidationError"}
        }
    }
}
```

#### Problem for Code Generation

```
OpenAPI → TypeScript SDK Generator:
  ✗ Type 'ValidationError.type' conflicts with reserved word 'type'
  ✗ Generated code fails linting: tslint(1) error TS1121: Identifier expected

OpenAPI → Python SDK Generator:
  ✗ Pydantic models cannot use 'type' as field name without Field(alias="type")
  ✗ Generator assumes standard JSON-to-Python mapping
  ✗ No automatic alias handling
```

---

## Part 6: Proposed RFC 7807 Compliant Schema

### 6.1 Core Problem Details Model

```python
from typing import Annotated, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class ProblemDetails(BaseModel):
    """
    RFC 7807 Problem Details for HTTP APIs
    
    Ref: https://datatracker.ietf.org/doc/html/rfc7807
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "https://api.example.com/errors/validation",
                "title": "Validation Failed",
                "status": 400,
                "detail": "One or more fields are invalid",
                "instance": "/api/v1/users/register"
            }
        }
    )
    
    # CRITICAL FIX: Use Field(alias="type") for Python keyword conflict
    type: Annotated[
        str,
        Field(
            alias="type",
            title="Problem Type URI",
            description="A URI reference identifying the problem type",
            examples=["https://api.example.com/errors/validation"],
        )
    ]
    
    title: Annotated[
        str,
        Field(
            title="Problem Title",
            description="A short, human-readable summary of the problem",
            examples=["Validation Failed"],
        )
    ]
    
    status: Annotated[
        int,
        Field(
            title="HTTP Status Code",
            description="The HTTP status code for this problem",
            ge=100,
            le=599,
            examples=[400, 422, 500],
        )
    ]
    
    detail: Annotated[
        str,
        Field(
            title="Problem Detail",
            description="A human-readable explanation specific to this occurrence",
            examples=["Username already exists"],
        )
    ]
    
    instance: Annotated[
        Optional[str],
        Field(
            default=None,
            alias=None,  # Keep as 'instance', not aliased
            title="Problem Instance",
            description="A URI reference identifying the specific occurrence",
            examples=["/api/v1/users/register", "/api/v1/items/123/messages/456"],
        )
    ] = None

    def model_dump_rfc7807(self) -> dict[str, Any]:
        """Export as RFC 7807 compliant JSON (with 'type' field unaliased)"""
        return self.model_dump(by_alias=True, exclude_none=True)
```

### 6.2 Validation Error Extension

```python
class ValidationErrorDetail(BaseModel):
    """Individual validation error - RFC 7807 extension"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "field": "email",
                "message": "Invalid email format",
                "type": "value_error.email"
            }
        }
    )
    
    field: Annotated[
        str,
        Field(
            title="Field Path",
            description="JSON path to the invalid field",
            examples=["email", "address.zip_code", "0.name"],
        )
    ]
    
    message: Annotated[
        str,
        Field(
            title="Error Message",
            description="Human-readable error message",
            examples=["Invalid email format"],
        )
    ]
    
    error_type: Annotated[
        str,
        Field(
            alias="type",
            title="Error Type Code",
            description="Machine-readable error type",
            examples=["value_error.email", "value_error.number.not_ge"],
        )
    ]
    
    value: Annotated[
        Optional[Any],
        Field(
            default=None,
            title="Invalid Value",
            description="The value that failed validation (optional for security)",
        )
    ] = None

    constraint: Annotated[
        Optional[str],
        Field(
            default=None,
            title="Constraint Details",
            description="Specific constraint that was violated",
            examples=["minimum value is 1", "must match regex: ^[a-z]+$"],
        )
    ] = None


class ValidationProblemDetails(ProblemDetails):
    """
    RFC 7807 Problem Details with validation error extension
    Status code is implicitly 400 (Bad Request)
    """
    status: int = 400
    
    errors: Annotated[
        list[ValidationErrorDetail],
        Field(
            title="Validation Errors",
            description="Array of validation errors",
        )
    ]
    
    error_count: Annotated[
        int,
        Field(
            title="Error Count",
            description="Total number of errors",
            ge=0,
        )
    ]
```

---

### 6.3 Refactored Exception Handler

```python
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder

async def rfc7807_request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    RFC 7807 compliant validation error handler
    
    Maps Pydantic ValidationError → RFC 7807 ProblemDetails
    """
    
    # Parse Pydantic errors into structured format
    validation_errors: list[ValidationErrorDetail] = []
    for pydantic_error in exc.errors():
        validation_errors.append(
            ValidationErrorDetail(
                field=_location_to_field(pydantic_error.get("loc", [])),
                message=pydantic_error.get("msg", "Validation failed"),
                type=pydantic_error.get("type", "validation_error"),
                value=pydantic_error.get("input") if request.app.debug else None,
                constraint=_extract_constraint(pydantic_error),
            )
        )
    
    # Create RFC 7807 response
    problem = ValidationProblemDetails(
        type=f"{request.url.scheme}://{request.url.hostname}/errors/validation",
        title="Validation Failed",
        status=400,  # Use standard 400 Bad Request, not 422
        detail=f"{len(validation_errors)} validation error(s)",
        instance=str(request.url.path),
        errors=validation_errors,
        error_count=len(validation_errors),
    )
    
    return JSONResponse(
        status_code=400,  # HTTP 400 Bad Request (standard)
        content=problem.model_dump_rfc7807(),
        headers={"Content-Type": "application/problem+json"},  # RFC 7807 media type
    )

def _location_to_field(location: tuple | list) -> str:
    """Convert Pydantic loc to JSON field path"""
    return ".".join(str(x) for x in location) if location else "root"

def _extract_constraint(error: dict) -> Optional[str]:
    """Extract specific constraint from Pydantic error context"""
    ctx = error.get("ctx", {})
    if "expected" in ctx:
        return f"expected {ctx['expected']}"
    if "min_length" in ctx:
        return f"minimum length is {ctx['min_length']}"
    if "max_length" in ctx:
        return f"maximum length is {ctx['max_length']}"
    if "min_value" in ctx:
        return f"minimum value is {ctx['min_value']}"
    if "max_value" in ctx:
        return f"maximum value is {ctx['max_value']}"
    if "pattern" in ctx:
        return f"must match pattern: {ctx['pattern']}"
    return None
```

---

### 6.4 HTTP Exception Handler Update

```python
async def rfc7807_http_exception_handler(
    request: Request, exc: HTTPException
) -> Response:
    """RFC 7807 compliant HTTP exception handler"""
    
    headers = getattr(exc, "headers", None)
    
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=headers)
    
    # Determine problem type URI based on status code
    problem_type = _status_code_to_problem_type(
        exc.status_code,
        request.url.scheme,
        request.url.hostname
    )
    
    # Create RFC 7807 response
    problem = ProblemDetails(
        type=problem_type,
        title=_status_code_to_title(exc.status_code),
        status=exc.status_code,
        detail=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        instance=str(request.url.path),
    )
    
    response_headers = headers or {}
    response_headers["Content-Type"] = "application/problem+json"
    
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump_rfc7807(),
        headers=response_headers,
    )

def _status_code_to_problem_type(
    status_code: int, scheme: str, hostname: str
) -> str:
    """Map HTTP status code to RFC 7807 problem type URI"""
    problem_map = {
        400: "bad-request",
        401: "unauthorized",
        403: "forbidden",
        404: "not-found",
        409: "conflict",
        413: "payload-too-large",
        429: "too-many-requests",
        500: "internal-server-error",
        502: "bad-gateway",
        503: "service-unavailable",
    }
    problem_id = problem_map.get(status_code, f"http-{status_code}")
    return f"{scheme}://{hostname}/errors/{problem_id}"

def _status_code_to_title(status_code: int) -> str:
    """Get human-readable title for HTTP status code"""
    title_map = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        413: "Payload Too Large",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
    }
    return title_map.get(status_code, "HTTP Error")
```

---

## Part 7: Implementation Compatibility Checklist

### 7.1 Breaking Changes Analysis

| Item | Current | Proposed | Breaking? | Mitigation |
|------|---------|----------|-----------|-----------|
| Status Code | 422 | 400 | ✓ YES | Version flag; deprecation period |
| Response Structure | `{"detail": [...]}` | RFC 7807 | ✓ YES | Content-Type check; version header |
| Field Aliasing | None | `type` → `"type"` | ✗ NO | Transparent in JSON |
| Content-Type | application/json | application/problem+json | ~ MAYBE | Accept header negotiation |

### 7.2 Migration Strategy

```python
# Phase 1: Support both formats (v1.1)
from fastapi import FastAPI
from fastapi.datastructures import DefaultPlaceholder

app = FastAPI(
    enable_rfc7807_errors=DefaultPlaceholder(False),  # Default: backward compat
    # Set to True in v2.0 for strict RFC 7807
)

# Phase 2: Deprecation warning (v1.2-v1.9)
if app.enable_rfc7807_errors:
    import warnings
    warnings.warn(
        "FastAPI's default RFC 7807 compliance is enabled. "
        "Error response format has changed. "
        "See: https://fastapi.tiangolo.com/advanced/rfc7807-migration/",
        FastAPIDeprecationWarning,
        stacklevel=2,
    )

# Phase 3: Strict RFC 7807 (v2.0+)
# All error responses must be RFC 7807 compliant
```

---

## Part 8: Python Keyword Conflict Resolution

### 8.1 The Core Problem

```python
# This is the exact issue:
class ValidationErrorDetail(BaseModel):
    type: str  # ❌ SyntaxError: 'type' is a reserved keyword

# Python keywords (cannot be variable names):
# False, None, True, and, as, assert, async, await, break, class, continue, 
# def, del, elif, else, except, finally, for, from, global, if, import, 
# in, is, lambda, nonlocal, not, or, pass, raise, return, try, while, with, yield
```

### 8.2 Standard Solution: Field Aliases

```python
from pydantic import BaseModel, Field

class ValidationErrorDetail(BaseModel):
    # Use 'error_type' in Python code
    # Serialize as 'type' in JSON
    error_type: str = Field(alias="type")

# Usage:
error = ValidationErrorDetail(type="value_error.email")  # ✓ Works via alias
error.error_type  # ✓ Access via Python attribute
error.model_dump(by_alias=True)  # {"type": "..."}  ✓ Correct JSON
```

### 8.3 OpenAPI Schema Generation

```python
# The Pydantic model's schema already knows about aliases
ValidationErrorDetail.model_json_schema(by_alias=True)
# Output:
{
    "properties": {
        "type": {"type": "string"},  # ✓ Uses alias
    },
    "required": ["type"]
}
```

### 8.4 Client Code Generation

```typescript
// Generated TypeScript SDK (from OpenAPI with aliases)
interface ValidationErrorDetail {
  type: string;  // ✓ Correctly generated
  loc: (string | number)[];
  msg: string;
}

// Python SDK generation also works:
class ValidationErrorDetail(BaseModel):
    error_type: str = Field(alias="type")  # ✓ Type-safe
```

---

## Part 9: Detection of Existing API Misuse

### 9.1 Anti-Patterns Found in Repository

#### Pattern 1: Untyped Exception Content

```python
# ❌ In tests/test_exception_handlers.py
def request_validation_exception_handler(request, exception):
    return JSONResponse({"exception": "request-validation"})  # Any dict allowed
```

**Issue:** No schema enforcement - handler can return anything

#### Pattern 2: Response Modification Without Consistency

```python
# ❌ Custom handlers don't follow same structure
@app.exception_handler(CustomException)
async def custom_handler(request, exc):
    return JSONResponse({
        "error": exc.message,      # Different field name
        "code": exc.code,           # Custom structure
        "timestamp": datetime.now()  # Different format
    })
```

**Issue:** Each handler invents its own structure

#### Pattern 3: Mixing Error Types

```python
# ❌ In exception_handlers.py line 19
return JSONResponse(
    {"detail": exc.detail},  # String for HTTP errors
)

# vs. line 24-25
return JSONResponse(
    {"detail": jsonable_encoder(exc.errors())},  # Array for validation errors
)
```

**Issue:** Same key name, different semantics

#### Pattern 4: No Instance Field for Traceability

```python
# ❌ Current implementation
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # endpoint_ctx is available in exc but never exposed
    return JSONResponse(
        status_code=422,
        content={"detail": ...}  # ✗ Client can't identify which operation failed
    )
```

**Issue:** Missing RFC 7807 `instance` field → poor error correlation

---

### 9.2 Compatibility Issues with Standards

#### Content-Type Negotiation Failure

```python
# Current
response = JSONResponse(
    content={...},
    # ✗ No Content-Type header or uses application/json
)

# RFC 7807 requires
response.headers["Content-Type"] = "application/problem+json"
```

**Issue:** API clients expect `application/problem+json` per RFC 7807

#### HTTP Status Code Semantics

```python
# Current uses 422 Unprocessable Entity
# ✗ WebDAV extension, not universally recognized
# ✗ Not in RFC 7231 base HTTP

# RFC 7807 recommends
# ✓ 400 Bad Request - client-side validation error
# ✓ 409 Conflict - business logic conflict
# ✓ 413 Payload Too Large - request body too large
```

---

## Part 10: Schema Design Validation Patterns

### 10.1 Pydantic v2 Validation

```python
from pydantic import BaseModel, Field, field_validator
from typing_extensions import Self

class ProblemDetails(BaseModel):
    type: str = Field(alias="type")  # ✓ Alias for keyword
    status: int = Field(ge=100, le=599)  # ✓ Range validation
    
    @field_validator("type")
    @classmethod
    def validate_type_uri(cls, v: str) -> str:
        if not v.startswith("http://") and not v.startswith("https://"):
            raise ValueError("type must be a valid URI")
        return v
```

### 10.2 JSON Schema Validation

```json
{
  "type": "object",
  "properties": {
    "type": {
      "type": "string",
      "format": "uri-reference",
      "description": "Problem type URI"
    },
    "title": {"type": "string"},
    "status": {"type": "integer", "minimum": 100, "maximum": 599},
    "detail": {"type": "string"},
    "instance": {"type": "string", "format": "uri-reference"}
  },
  "required": ["type", "title", "status", "detail"]
}
```

### 10.3 Runtime Validation Example

```python
def validate_rfc7807_response(response: dict) -> tuple[bool, list[str]]:
    """Validate response conforms to RFC 7807"""
    errors = []
    
    # Required fields
    required = ["type", "title", "status", "detail"]
    for field in required:
        if field not in response:
            errors.append(f"Missing required field: {field}")
    
    # Type checks
    if "type" in response and not isinstance(response["type"], str):
        errors.append("'type' must be a string")
    if "status" in response and not (100 <= response["status"] <= 599):
        errors.append("'status' must be HTTP status code (100-599)")
    
    # URI validation
    if "type" in response:
        if not response["type"].startswith(("http://", "https://", "#")):
            errors.append("'type' should be a URI reference")
    
    return len(errors) == 0, errors
```

---

## Summary of Critical Findings

| Category | Finding | Severity | Impact |
|----------|---------|----------|--------|
| **Keyword Conflict** | `type` field requires Field(alias="type") | CRITICAL | SDK generation fails without alias |
| **Type Safety** | `Sequence[Any]` loses error structure info | CRITICAL | Runtime deserialization errors |
| **RFC Compliance** | Missing type, title, instance fields | CRITICAL | Microservice integration breaks |
| **Status Codes** | Uses 422 instead of 400 | HIGH | Non-standard, not universally recognized |
| **Content-Type** | application/json instead of application/problem+json | HIGH | Clients cannot identify RFC 7807 responses |
| **Response Structure** | Same "detail" key for HTTP and validation errors | HIGH | Inconsistent client parsing logic |
| **Handler Typing** | Untyped exception_handler callbacks | MEDIUM | IDE cannot validate schemas |
| **Instance Field** | No endpoint reference in response | MEDIUM | Poor error correlation in logs |
| **WebSocket Gap** | Different error format for WebSocket errors | MEDIUM | Inconsistent error handling across protocols |
| **Traceability** | endpoint_ctx information discarded | LOW | Makes debugging harder |

---

## Recommendations

1. **Immediate (v1.1)**: Implement Field(alias="type") pattern in validation error schemas
2. **Short-term (v1.2)**: Add RFC 7807 ProblemDetails model with feature flag
3. **Medium-term (v1.5)**: Deprecate 422 status code, move to 400
4. **Long-term (v2.0)**: Enforce RFC 7807 compliance by default

---

## References

- **RFC 7807**: Problem Details for HTTP APIs - https://datatracker.ietf.org/doc/html/rfc7807
- **RFC 7231**: HTTP/1.1 Semantics and Content - https://datatracker.ietf.org/doc/html/rfc7231
- **Pydantic Field Aliases**: https://docs.pydantic.dev/latest/concepts/fields/#field-aliases
- **FastAPI Error Handling**: https://fastapi.tiangolo.com/tutorial/handling-errors/
