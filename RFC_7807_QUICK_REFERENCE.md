"""
RFC 7807 Problem Details - Quick Reference Card

Type Keyword Conflict Resolution & Common Patterns
"""

# ============================================================================
# QUICK REFERENCE: Python 'type' Keyword Conflict
# ============================================================================

"""
THE PROBLEM:
============
In Python, 'type' is a reserved keyword - cannot be used as variable/field name:

    class MyModel(BaseModel):
        type: str  # ✗ SyntaxError: 'type' is a reserved keyword

THE SOLUTION:
=============
Use Field(alias="type") to map Python field name to JSON field:

    class MyModel(BaseModel):
        error_type: str = Field(alias="type")  # ✓ Valid Python code

USAGE:
======
    # Input (JSON/dict with 'type' key via alias)
    model = MyModel(type="value_error.email")
    
    # Access in Python (via field name)
    print(model.error_type)  # "value_error.email"
    
    # Output (JSON with 'type' key via alias)
    json_dict = model.model_dump(by_alias=True)
    print(json_dict["type"])  # "value_error.email"

PYDANTIC MODELS NEEDING ALIASES:
================================
In fastapi.responses_rfc7807:

1. ProblemDetails:
   - Python field: problem_type
   - JSON field: "type"
   - Field alias: Field(alias="type")

2. ValidationErrorDetail:
   - Python field: error_type
   - JSON field: "type"
   - Field alias: Field(alias="type")
"""

# ============================================================================
# QUICK REFERENCE: Creating Problem Details
# ============================================================================

from fastapi.responses_rfc7807 import (
    ProblemDetails,
    ValidationProblemDetails,
    ValidationErrorDetail,
    AuthenticationProblemDetails,
    AuthorizationProblemDetails,
    ConflictProblemDetails,
    RateLimitProblemDetails,
    InternalServerErrorProblemDetails,
)


examples = {
    # 1. Basic HTTP Error (404 Not Found)
    "404_not_found": """
        problem = ProblemDetails(
            problem_type="https://api.example.com/errors/not-found",
            title="Item Not Found",
            status=404,
            detail="Item with ID 123 does not exist",
            instance="/api/v1/items/123",
        )
    """,

    # 2. Validation Error (400 Bad Request)
    "400_validation": """
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
                constraint="minimum_value=18",
            ),
        ]
        
        problem = ValidationProblemDetails(
            problem_type="https://api.example.com/errors/validation",
            title="Validation Failed",
            status=400,
            detail="2 validation errors",
            instance="/api/v1/users",
            errors=errors,
            error_count=2,
        )
    """,

    # 3. Authentication Error (401 Unauthorized)
    "401_authentication": """
        problem = AuthenticationProblemDetails(
            problem_type="https://api.example.com/errors/authentication",
            title="Unauthorized",
            status=401,
            detail="Bearer token is expired",
            instance="/api/v1/protected",
            challenge_scheme="Bearer",
            realm="protected-api",
            required_scopes=["read:items"],
        )
    """,

    # 4. Authorization Error (403 Forbidden)
    "403_authorization": """
        problem = AuthorizationProblemDetails(
            problem_type="https://api.example.com/errors/authorization",
            title="Forbidden",
            status=403,
            detail="Insufficient permissions",
            instance="/api/v1/admin/users",
            required_role="admin",
            current_role="user",
        )
    """,

    # 5. Conflict Error (409 Conflict)
    "409_conflict": """
        problem = ConflictProblemDetails(
            problem_type="https://api.example.com/errors/conflict",
            title="Conflict",
            status=409,
            detail="Username already exists",
            instance="/api/v1/users",
            conflict_field="username",
        )
    """,

    # 6. Rate Limit Error (429 Too Many Requests)
    "429_rate_limit": """
        problem = RateLimitProblemDetails(
            problem_type="https://api.example.com/errors/rate-limit",
            title="Too Many Requests",
            status=429,
            detail="Rate limit exceeded",
            instance="/api/v1/items",
            limit=1000,
            window_seconds=3600,
            retry_after_seconds=300,
            remaining=0,
        )
    """,

    # 7. Server Error (500 Internal Server Error)
    "500_internal_error": """
        problem = InternalServerErrorProblemDetails(
            problem_type="https://api.example.com/errors/internal-server-error",
            title="Internal Server Error",
            status=500,
            detail="An unexpected error occurred",
            instance="/api/v1/items",
            support_url="https://support.example.com/error",
        )
    """,
}


# ============================================================================
# QUICK REFERENCE: Serialization Patterns
# ============================================================================

serialization_patterns = {
    "RFC7807_compliant_output": """
        # Get RFC 7807 compliant JSON (default behavior)
        problem = ProblemDetails(...)
        json_dict = problem.model_dump_rfc7807()
        
        # Result: {"type": "...", "title": "...", "status": 400, ...}
        # Note: 'type' field is automatically aliased from 'problem_type'
    """,

    "with_legacy_fields": """
        # Include deprecated legacy fields (backward compatibility)
        problem = ProblemDetails(
            ...,
            error_code="VALIDATION_ERROR",
            timestamp=datetime.utcnow(),
            request_id=uuid4(),
        )
        json_dict = problem.model_dump_with_legacy()
        # Result: RFC 7807 + error_code + timestamp + request_id
    """,

    "exclude_none_values": """
        # Exclude None/optional fields from JSON
        problem = ProblemDetails(
            ...,
            instance=None,  # Optional field
        )
        json_dict = problem.model_dump_rfc7807(include_none=False)
        # Result: JSON does not contain "instance" field
    """,

    "custom_serialization": """
        # Use model_dump with custom parameters
        problem = ProblemDetails(...)
        
        # Validate all fields during serialization
        json_dict = problem.model_dump(
            by_alias=True,          # Use 'type' not 'problem_type'
            exclude_none=True,      # Skip None values
            exclude={"legacy_field"} # Skip specific fields
        )
    """,

    "json_string_output": """
        # Get JSON string directly
        problem = ProblemDetails(...)
        json_string = problem.model_dump_json(by_alias=True)
        # Result: '{"type": "...", "title": "...", ...}'
    """,
}


# ============================================================================
# QUICK REFERENCE: Exception Handler Pattern
# ============================================================================

exception_handler_pattern = """
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request

app = FastAPI()

# Pattern: Convert specific exception to RFC 7807 response
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # 1. Parse exception into domain objects
    errors = [
        ValidationErrorDetail(
            field=".".join(str(x) for x in err["loc"]),
            message=err["msg"],
            error_type=err["type"],
        )
        for err in exc.errors()
    ]
    
    # 2. Create RFC 7807 problem details
    problem = ValidationProblemDetails(
        problem_type="https://api.example.com/errors/validation",
        title="Validation Failed",
        status=400,
        detail=f"{len(errors)} error(s)",
        instance=str(request.url.path),
        errors=errors,
        error_count=len(errors),
    )
    
    # 3. Return with proper headers
    return JSONResponse(
        status_code=400,
        content=problem.model_dump_rfc7807(),
        headers={"Content-Type": "application/problem+json"},
    )
"""


# ============================================================================
# QUICK REFERENCE: Field Validation Examples
# ============================================================================

validation_examples = {
    "uri_validation": """
        # problem_type must be valid URI
        ✓ Valid:
          - "https://api.example.com/errors/validation"
          - "urn:error:validation"
          - "/errors/validation"
          - "#invalid-param"
        
        ✗ Invalid:
          - "not-a-uri"
          - "invalid"
        
        Error: ValidationError("must be a valid URI reference")
    """,

    "status_code_validation": """
        # status must be 100-599
        ✓ Valid: 400, 404, 500
        ✗ Invalid: 99, 600
        
        Error: ValidationError("must be a valid HTTP status code (100-599)")
    """,

    "non_empty_strings": """
        # title and detail must not be empty
        ✓ Valid: "Validation Failed"
        ✗ Invalid: "" (empty string)
        ✗ Invalid: "   " (whitespace only)
        
        Note: str_strip_whitespace=True auto-strips whitespace
    """,

    "validation_problem_status_range": """
        # ValidationProblemDetails status must be 400-499
        ✓ Valid: 400, 422
        ✗ Invalid: 500 (outside 4xx range)
        
        Status-specific models enforce range:
        - AuthenticationProblemDetails → 401
        - AuthorizationProblemDetails → 403
        - ConflictProblemDetails → 409
        - RateLimitProblemDetails → 429
        - InternalServerErrorProblemDetails → 5xx
    """,
}


# ============================================================================
# QUICK REFERENCE: OpenAPI Schema Generation
# ============================================================================

openapi_reference = """
AUTOMATIC OpenAPI SCHEMA GENERATION:
====================================

Pydantic v2 automatically generates correct OpenAPI schemas with Field aliases.

Expected OpenAPI schema properties for ProblemDetails:

{
  "components": {
    "schemas": {
      "ProblemDetails": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "title": "Problem Type",
            "description": "A URI reference identifying the problem type"
          },
          "title": {"type": "string"},
          "status": {"type": "integer", "minimum": 100, "maximum": 599},
          "detail": {"type": "string"},
          "instance": {"type": "string"}
        },
        "required": ["type", "title", "status", "detail"]
      }
    }
  }
}

KEY POINTS:
- Schema shows "type" field (via alias), NOT "problem_type"
- JSON schema correctly reflects RFC 7807 structure
- IDEs can validate API responses against schema
- OpenAPI clients (Swagger, ReDoc) display correct fields

SWAGGER UI:
- Visit /docs to see interactive API documentation
- Error responses show RFC 7807 structure
- Example payloads demonstrate Field aliases
"""


# ============================================================================
# QUICK REFERENCE: Content-Type Headers
# ============================================================================

content_type_reference = """
RFC 7807 CONTENT-TYPE HEADER:
=============================

CORRECT:
--------
response = JSONResponse(
    status_code=400,
    content=problem.model_dump_rfc7807(),
    headers={"Content-Type": "application/problem+json"}  # ✓ RFC 7807
)

INCORRECT:
----------
response = JSONResponse(
    status_code=400,
    content={"detail": "..."},
    headers={"Content-Type": "application/json"}  # ✗ Generic JSON
)

WHY IT MATTERS:
- Clients use Content-Type to determine response format
- "application/problem+json" signals RFC 7807 compliance
- Helps API gateway recognize problem responses
- Enables automated error handling in clients
- Required for RFC 7807 strict compliance

TESTING:
--------
curl -i http://localhost:8000/items/invalid
# Should include: Content-Type: application/problem+json
"""


# ============================================================================
# QUICK REFERENCE: Type Safety & IDE Support
# ============================================================================

type_safety_reference = """
PYTHON TYPE HINTS & IDE SUPPORT:
=================================

✓ Full IDE autocomplete for all fields:
  problem = ProblemDetails(...)
  problem.problem_type  # IDE knows this is str
  problem.title         # IDE knows this is str
  problem.status        # IDE knows this is int
  
✓ Type checking:
  def handle_error(problem: ProblemDetails) -> None:
      # Type checker verifies fields exist
      message = problem.detail  # ✓ Correct type
  
✓ No 'type' keyword conflict in Python:
  # ✗ BAD: type: str  (keyword conflict)
  # ✓ GOOD: error_type: str = Field(alias="type")
  
✓ JSON still uses correct field name:
  json_dict = problem.model_dump(by_alias=True)
  json_dict["type"]  # ← Correct RFC 7807 field name
  
✓ Factory functions are type-safe:
  problem = create_validation_problem(
      detail="...",
      errors=[...],  # ← Type checked
      instance="...",
  )
"""


# ============================================================================
# QUICK REFERENCE: Backward Compatibility
# ============================================================================

backward_compat_reference = """
BACKWARD COMPATIBILITY FIELDS:
==============================

Optional legacy fields supported for migration:

1. error_code (str, optional)
   Purpose: Custom error code from old system
   Usage: problem = ProblemDetails(..., error_code="ERR001")
   Status: Deprecated, use 'type' field instead

2. timestamp (datetime, optional)
   Purpose: Track when error occurred
   Usage: problem = ProblemDetails(..., timestamp=datetime.utcnow())
   Status: Deprecated

3. request_id (str | UUID, optional)
   Purpose: Correlate errors with requests
   Usage: problem = ProblemDetails(..., request_id=uuid4())
   Status: Deprecated, use 'instance' field instead

LEGACY FIELDS BEHAVIOR:
=======================

model_dump_rfc7807():
  ✓ Excludes legacy fields by default
  ✓ Returns pure RFC 7807 response
  
model_dump_with_legacy():
  ✓ Includes legacy fields
  ✓ Use only for backward compatibility
  
MIGRATION PATH:
===============
1. Old clients: Receive RFC 7807 + legacy fields
2. New clients: Expect RFC 7807 only
3. Eventually: Remove legacy fields (v2.0)
"""


# ============================================================================
# QUICK REFERENCE: Common Mistakes & Solutions
# ============================================================================

common_mistakes = {
    "mistake_1_missing_alias": """
        ✗ WRONG:
        class MyError(BaseModel):
            type: str  # SyntaxError!
        
        ✓ CORRECT:
        class MyError(BaseModel):
            error_type: str = Field(alias="type")
    """,

    "mistake_2_missing_content_type": """
        ✗ WRONG:
        JSONResponse(content=problem.model_dump_rfc7807())
        
        ✓ CORRECT:
        JSONResponse(
            content=problem.model_dump_rfc7807(),
            headers={"Content-Type": "application/problem+json"}
        )
    """,

    "mistake_3_not_using_by_alias": """
        ✗ WRONG:
        problem.model_dump()  # Outputs 'problem_type', not 'type'
        
        ✓ CORRECT:
        problem.model_dump(by_alias=True)  # Outputs 'type'
    """,

    "mistake_4_wrong_status_code": """
        ✗ WRONG:
        ValidationProblemDetails(..., status=500)  # Should be 4xx
        
        ✓ CORRECT:
        ValidationProblemDetails(..., status=400)
    """,

    "mistake_5_exposing_debug_info": """
        ✗ WRONG (Production):
        problem = ProblemDetails(
            ...,
            debug_info=str(exception),  # Leaks internals!
        )
        
        ✓ CORRECT (Production):
        problem = ProblemDetails(
            ...,
            detail="An error occurred",  # Generic message
        )
    """,

    "mistake_6_invalid_uri": """
        ✗ WRONG:
        problem_type="invalid"  # Not a valid URI
        
        ✓ CORRECT:
        problem_type="https://api.example.com/errors/validation"
    """,
}


# ============================================================================
# QUICK REFERENCE: Testing RFC 7807 Responses
# ============================================================================

testing_patterns = """
UNIT TEST PATTERN:
==================

from fastapi.testclient import TestClient
from fastapi.responses_rfc7807 import ValidationProblemDetails

client = TestClient(app)

def test_validation_error_is_rfc7807_compliant():
    response = client.post("/users", json={"email": "invalid"})
    
    # Check status code
    assert response.status_code == 400
    
    # Check content type
    assert response.headers["content-type"] == "application/problem+json"
    
    # Parse response
    data = response.json()
    
    # Verify RFC 7807 structure
    assert "type" in data  # ← 'type' not 'problem_type'
    assert "title" in data
    assert "status" in data
    assert "detail" in data
    
    # Verify validation extension
    assert "errors" in data
    assert "error_count" in data
    
    # Parse into model
    problem = ValidationProblemDetails(**data)
    assert len(problem.errors) > 0
    
    # Verify error detail structure
    error = problem.errors[0]
    assert error.field == "email"
    assert error.error_type == "value_error.email"  # ← via alias


INTEGRATION TEST PATTERN:
=========================

def test_api_error_flow():
    # Create user without auth
    response = client.get("/admin/users", headers={})
    
    assert response.status_code == 401
    data = response.json()
    
    # Verify authentication problem details
    assert data["type"] == "https://api.example.com/errors/authentication"
    assert data["status"] == 401
    assert "challenge_scheme" in data
"""


# ============================================================================
# SUMMARY CARD
# ============================================================================

print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                   RFC 7807 PROBLEM DETAILS - SUMMARY                      ║
╚════════════════════════════════════════════════════════════════════════════╝

KEY CONCEPT: Python Keyword 'type' Conflict
═══════════════════════════════════════════════════════════════════════════
  Python field name:  problem_type, error_type
  Field alias:        Field(alias="type")
  JSON field name:    "type"
  Serialization:      model_dump(by_alias=True)
  
  Example:
    problem = ProblemDetails(
        problem_type="https://...",  ← Python field
        ...
    )
    json_dict = problem.model_dump(by_alias=True)
    json_dict["type"]  ← JSON field via alias


REQUIRED RFC 7807 FIELDS
═════════════════════════════════════════════════════════════════════════════
  1. type              → Problem type URI (e.g., "https://api.example.com/...")
  2. title             → Human-readable summary
  3. status            → HTTP status code
  4. detail            → Specific explanation
  5. instance          → (OPTIONAL) URI identifying occurrence


PROBLEM DETAIL MODELS
═════════════════════════════════════════════════════════════════════════════
  • ProblemDetails (base)
  • ValidationProblemDetails (400)
  • AuthenticationProblemDetails (401)
  • AuthorizationProblemDetails (403)
  • ConflictProblemDetails (409)
  • RateLimitProblemDetails (429)
  • InternalServerErrorProblemDetails (5xx)


SERIALIZATION METHODS
═════════════════════════════════════════════════════════════════════════════
  model_dump_rfc7807()           → RFC 7807 only (no legacy fields)
  model_dump_with_legacy()       → RFC 7807 + backward compat fields
  model_dump(by_alias=True)      → Use 'type' not 'problem_type'
  model_dump_json(by_alias=True) → JSON string output


EXCEPTION HANDLER PATTERN
═════════════════════════════════════════════════════════════════════════════
  @app.exception_handler(SomeException)
  async def handler(request, exc):
      problem = ProblemDetails(...)
      return JSONResponse(
          status_code=400,
          content=problem.model_dump_rfc7807(),
          headers={"Content-Type": "application/problem+json"}
      )


CONTENT-TYPE HEADER
═════════════════════════════════════════════════════════════════════════════
  ✓ CORRECT:   "Content-Type": "application/problem+json"
  ✗ WRONG:     "Content-Type": "application/json"


VALIDATION RULES
═════════════════════════════════════════════════════════════════════════════
  • problem_type: Must be valid URI reference (http://, https://, urn:, /, #)
  • status: Must be 100-599 HTTP status code
  • title, detail: Must not be empty
  • instance: Must be valid URI or path


BACKWARD COMPATIBILITY
═════════════════════════════════════════════════════════════════════════════
  Legacy fields (optional):
    • error_code (deprecated)
    • timestamp (deprecated)
    • request_id (deprecated)
  
  Excluded from model_dump_rfc7807() by default
  Included in model_dump_with_legacy()


IDE & TYPE SAFETY
═════════════════════════════════════════════════════════════════════════════
  ✓ Full autocomplete and type hints
  ✓ No 'type' keyword syntax errors
  ✓ Static analysis works correctly
  ✓ JSON output still uses 'type' field name


REFERENCES
═════════════════════════════════════════════════════════════════════════════
  RFC 7807:       https://datatracker.ietf.org/doc/html/rfc7807
  Pydantic v2:    https://docs.pydantic.dev/latest/
  Field alias:    https://docs.pydantic.dev/latest/concepts/fields/#field-aliases
  FastAPI errors: https://fastapi.tiangolo.com/tutorial/handling-errors/

╚════════════════════════════════════════════════════════════════════════════╝
""")
