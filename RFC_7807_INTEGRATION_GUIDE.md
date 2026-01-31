"""
RFC 7807 Problem Details Integration Guide

This guide explains how to use the RFC 7807 compliant ProblemDetails models
in FastAPI applications, addressing the Python 'type' keyword conflict and
ensuring backward compatibility.
"""

# ============================================================================
# INTEGRATION GUIDE: RFC 7807 Problem Details for FastAPI
# ============================================================================

## Quick Start

### 1. Basic HTTP Exception (404 Not Found)

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses_rfc7807 import ProblemDetails
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/items/{item_id}")
async def get_item(item_id: int):
    if item_id not in items:
        # Old way (non-standard)
        # raise HTTPException(status_code=404, detail="Item not found")
        
        # New RFC 7807 way
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/not-found",
            title="Item Not Found",
            status=404,
            detail=f"Item with ID {item_id} does not exist",
            instance=f"/items/{item_id}",
        )
        return JSONResponse(
            status_code=404,
            content=problem.model_dump_rfc7807(),
            headers={"Content-Type": "application/problem+json"},
        )
    
    return {"item_id": item_id, "name": items[item_id]}
```

### 2. Validation Error (400 Bad Request)

```python
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses_rfc7807 import (
    ValidationProblemDetails,
    ValidationErrorDetail,
    create_validation_problem,
)
from starlette.requests import Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """RFC 7807 compliant validation error handler"""
    
    # Convert Pydantic errors to ValidationErrorDetail
    error_details = []
    for pydantic_error in exc.errors():
        error_details.append(
            ValidationErrorDetail(
                field=".".join(str(x) for x in pydantic_error.get("loc", [])),
                message=pydantic_error.get("msg", "Validation failed"),
                error_type=pydantic_error.get("type", "validation_error"),
            )
        )
    
    # Create RFC 7807 response
    problem = create_validation_problem(
        detail=f"{len(error_details)} validation error(s)",
        errors=error_details,
        instance=str(request.url.path),
    )
    
    return JSONResponse(
        status_code=400,
        content=problem.model_dump_rfc7807(),
        headers={"Content-Type": "application/problem+json"},
    )
```

### 3. Authentication Error (401 Unauthorized)

```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses_rfc7807 import (
    create_authentication_problem,
)
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer

app = FastAPI()
security = HTTPBearer()

async def verify_token(credentials = Depends(security)):
    token = credentials.credentials
    if not is_valid_token(token):
        problem = create_authentication_problem(
            detail="Bearer token is invalid or expired",
            instance=request.url.path,
            challenge_scheme="Bearer",
            realm="protected-api",
        )
        raise HTTPException(
            status_code=401,
            detail=problem.model_dump_rfc7807(),
            headers={"WWW-Authenticate": 'Bearer realm="protected-api"'},
        )
    return token
```

### 4. Authorization Error (403 Forbidden)

```python
from fastapi import FastAPI, Depends
from fastapi.responses_rfc7807 import create_authorization_problem
from fastapi.responses import JSONResponse

app = FastAPI()

async def require_admin(current_user = Depends(get_current_user)):
    if current_user.role != "admin":
        problem = create_authorization_problem(
            detail="You do not have permission to access this resource",
            instance="/api/v1/admin/users",
            required_role="admin",
            current_role=current_user.role,
        )
        return JSONResponse(
            status_code=403,
            content=problem.model_dump_rfc7807(),
            headers={"Content-Type": "application/problem+json"},
        )
    return current_user

@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, admin = Depends(require_admin)):
    # ... delete user
    pass
```

### 5. Conflict Error (409 Conflict)

```python
from fastapi import FastAPI
from fastapi.responses_rfc7807 import create_conflict_problem
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/users")
async def create_user(user: UserCreate):
    if await user_exists(user.email):
        problem = create_conflict_problem(
            detail=f"User with email '{user.email}' already exists",
            instance="/api/v1/users",
            conflict_field="email",
        )
        return JSONResponse(
            status_code=409,
            content=problem.model_dump_rfc7807(),
            headers={"Content-Type": "application/problem+json"},
        )
    
    # ... create user
```

### 6. Rate Limiting (429 Too Many Requests)

```python
from fastapi import FastAPI
from fastapi.responses_rfc7807 import create_rate_limit_problem
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/api/items")
async def list_items(request: Request):
    # Check rate limit
    if rate_limiter.is_exceeded(request.client.host):
        retry_after = rate_limiter.get_retry_after(request.client.host)
        
        problem = create_rate_limit_problem(
            limit=1000,
            window_seconds=3600,
            retry_after_seconds=retry_after,
            instance="/api/items",
            remaining=0,
        )
        
        return JSONResponse(
            status_code=429,
            content=problem.model_dump_rfc7807(),
            headers={
                "Content-Type": "application/problem+json",
                "Retry-After": str(retry_after),
            },
        )
    
    # ... list items
```

### 7. Internal Server Error (500)

```python
from fastapi import FastAPI
from fastapi.responses_rfc7807 import create_internal_server_error_problem
from fastapi.responses import JSONResponse
from starlette.requests import Request
import logging

logger = logging.getLogger(__name__)
app = FastAPI()

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler - never expose internals to client"""
    
    # Log the actual error (with stack trace) on server side
    logger.exception(f"Unhandled exception at {request.url.path}")
    
    # Return generic RFC 7807 error to client (no sensitive details)
    problem = create_internal_server_error_problem(
        detail="An unexpected error occurred. Please try again later.",
        instance=str(request.url.path),
        support_url="https://support.example.com/contact",
    )
    
    return JSONResponse(
        status_code=500,
        content=problem.model_dump_rfc7807(),
        headers={"Content-Type": "application/problem+json"},
    )
```

## ============================================================================
## Handling the Python 'type' Keyword Conflict
## ============================================================================

### The Problem

In Python, `type` is a reserved keyword and cannot be used as a variable name:

```python
# ✗ This fails with SyntaxError
class MyModel(BaseModel):
    type: str  # SyntaxError: invalid syntax
```

### The Solution: Field Alias

Pydantic v2 provides the `Field(alias="...")` pattern to solve this:

```python
from pydantic import BaseModel, Field

class ValidationErrorDetail(BaseModel):
    # In Python code, use 'error_type'
    # In JSON, it serializes as 'type'
    error_type: str = Field(alias="type")

# Usage:
error = ValidationErrorDetail(type="value_error.email")  # ✓ Works via alias
error.error_type  # ✓ Access via Python attribute
error.model_dump(by_alias=True)  # {"type": "..."}  ✓ Correct JSON
```

### Key Points

1. **Field Name**: Use a valid Python identifier: `problem_type`, `error_type`, etc.
2. **Alias**: Set `Field(alias="type")` to map to JSON field `"type"`
3. **Deserialization**: Pydantic accepts both the field name and alias during input
4. **Serialization**: Use `model_dump(by_alias=True)` to serialize as `"type"`

### Example: Complete Workflow

```python
# 1. Create from JSON with 'type' key (via alias)
json_data = {
    "type": "value_error.email",
    "field": "email",
    "message": "Invalid email"
}
error = ValidationErrorDetail(**json_data)

# 2. Access in Python via field name
print(error.error_type)  # "value_error.email"

# 3. Serialize back to JSON with 'type' key
json_output = error.model_dump(by_alias=True)
print(json_output["type"])  # "value_error.email"
```

## ============================================================================
## OpenAPI Schema Generation
## ============================================================================

### Automatic Schema Generation

Pydantic v2 automatically generates correct OpenAPI schemas with aliases:

```python
from fastapi import FastAPI
from fastapi.responses_rfc7807 import ProblemDetails

app = FastAPI()

# OpenAPI schema will be generated with 'type' field (via alias)
# No special configuration needed!

@app.get("/openapi.json")
async def openapi():
    return app.openapi()
```

### Expected OpenAPI Schema

```json
{
  "components": {
    "schemas": {
      "ProblemDetails": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "description": "A URI reference identifying the problem type"
          },
          "title": {"type": "string"},
          "status": {"type": "integer"},
          "detail": {"type": "string"},
          "instance": {"type": "string"}
        },
        "required": ["type", "title", "status", "detail"]
      }
    }
  }
}
```

## ============================================================================
## Backward Compatibility
## ============================================================================

### Supporting Legacy Fields

The models include optional legacy fields for gradual migration:

```python
from datetime import datetime
from uuid import uuid4

problem = ProblemDetails(
    problem_type="https://api.example.com/errors/validation",
    title="Validation Failed",
    status=400,
    detail="Invalid input",
    # RFC 7807 fields above
    # Legacy fields below
    error_code="VALIDATION_ERROR",           # Old FastAPI field
    timestamp=datetime.utcnow(),             # Tracking field
    request_id=uuid4(),                      # Request correlation
)

# RFC 7807 compliant output (legacy fields excluded)
problem.model_dump_rfc7807()
# {"type": "...", "title": "...", "status": 400, "detail": "..."}

# Output with legacy fields included
problem.model_dump_with_legacy()
# Includes: error_code, timestamp, request_id
```

### Migration Strategy

**Phase 1: Support Both Formats**
- New code uses RFC 7807 models
- Existing clients receive RFC 7807 responses
- Legacy fields available but not required

**Phase 2: Deprecation Warning**
- Document that legacy fields are deprecated
- Provide migration guide for client code

**Phase 3: Remove Legacy Support**
- Stop accepting legacy field inputs
- Drop from OpenAPI schema
- Fully RFC 7807 compliant

## ============================================================================
## Type Safety & IDE Support
## ============================================================================

### IDE Autocomplete

```python
from fastapi.responses_rfc7807 import ValidationErrorDetail

error = ValidationErrorDetail(
    field="email",
    message="Invalid",
    error_type="value_error.email"
)

# IDE provides autocomplete for:
error.field
error.message
error.error_type  # ← Python attribute name (no keyword conflict)
error.model_dump(by_alias=True)  # ← Still uses 'type' in JSON
```

### Type Hints

```python
from fastapi.responses_rfc7807 import ValidationProblemDetails

def handle_validation_error(problem: ValidationProblemDetails) -> None:
    # Type checker knows about all fields
    error_count: int = problem.error_count  # ✓ Type-checked
    errors: list = problem.errors            # ✓ Type-checked
```

## ============================================================================
## Testing with RFC 7807 Models
## ============================================================================

### Unit Test Example

```python
from fastapi.testclient import TestClient
from fastapi.responses_rfc7807 import ProblemDetails
import json

client = TestClient(app)

def test_404_returns_rfc7807_problem_details():
    response = client.get("/items/99999")
    
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    
    data = response.json()
    
    # Verify RFC 7807 structure
    assert "type" in data
    assert "title" in data
    assert "status" in data
    assert "detail" in data
    
    # Verify content
    assert data["status"] == 404
    assert data["type"] == "https://api.example.com/errors/not-found"
    
    # Parse into model
    problem = ProblemDetails(**data)
    assert problem.problem_type == data["type"]
```

### Integration Test Example

```python
def test_validation_error_returns_rfc7807_validation_problem():
    response = client.post("/users", json={"email": "invalid-email"})
    
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    
    data = response.json()
    
    # Verify RFC 7807 validation extension
    assert data["status"] == 400
    assert len(data["errors"]) > 0
    
    # Check error details
    error = data["errors"][0]
    assert error["field"] == "email"
    assert "type" in error  # Via alias
    assert "message" in error
```

## ============================================================================
## Content-Type Header
## ============================================================================

### Proper Content-Type

RFC 7807 specifies `application/problem+json` for JSON responses:

```python
from fastapi.responses import JSONResponse
from fastapi.responses_rfc7807 import ProblemDetails

problem = ProblemDetails(...)

# ✓ Correct
response = JSONResponse(
    status_code=400,
    content=problem.model_dump_rfc7807(),
    headers={"Content-Type": "application/problem+json"},  # RFC 7807 media type
)

# ✗ Incorrect (old way)
response = JSONResponse(
    status_code=400,
    content={"detail": "..."},
    headers={"Content-Type": "application/json"},  # Generic JSON
)
```

### Content Negotiation

For flexibility, you can support both:

```python
def get_content_type(accept_header: str) -> str:
    if "application/problem+json" in accept_header:
        return "application/problem+json"  # Preferred
    return "application/json"  # Fallback for legacy clients
```

## ============================================================================
## Common Patterns
## ============================================================================

### Creating Response from Exception

```python
from fastapi import HTTPException

def handle_http_exception(exc: HTTPException) -> JSONResponse:
    # Convert Starlette HTTPException to RFC 7807
    problem = ProblemDetails(
        problem_type=f"https://api.example.com/errors/{exc.status_code}",
        title=get_status_phrase(exc.status_code),
        status=exc.status_code,
        detail=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        instance=...,  # Set from request context
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump_rfc7807(),
        headers={"Content-Type": "application/problem+json"},
    )
```

### Extensible Custom Problem Types

```python
from fastapi.responses_rfc7807 import ProblemDetails

class CustomBusinessLogicProblem(ProblemDetails):
    """Extend RFC 7807 with domain-specific fields"""
    
    insufficient_amount: float  # Custom field
    required_amount: float      # Custom field
    
    # These are automatically included in JSON output
```

Usage:

```python
problem = CustomBusinessLogicProblem(
    problem_type="https://api.example.com/errors/insufficient-funds",
    title="Insufficient Funds",
    status=400,
    detail="Account balance is too low",
    instance="/api/v1/transfers",
    insufficient_amount=100.00,
    required_amount=500.00,
)

# JSON output includes custom fields
data = problem.model_dump(by_alias=True)
# {"type": "...", "insufficient_amount": 100.0, "required_amount": 500.0, ...}
```

## ============================================================================
## Summary
## ============================================================================

✓ RFC 7807 Problem Details for HTTP APIs
✓ Python 'type' keyword handled via Field(alias="type")
✓ Backward compatible with legacy error fields
✓ Type-safe with full IDE support
✓ Extensible for domain-specific errors
✓ Factory functions for common scenarios
✓ Proper Content-Type header support
✓ Comprehensive validation and constraints
