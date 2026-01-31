# configure_problem_details: Safe RFC 7807 Rollout with Backward Compatibility

## Overview

The `configure_problem_details` utility provides a comprehensive, production-grade solution for safely rolling out RFC 7807 Problem Details responses to FastAPI applications while maintaining full backward compatibility with legacy clients.

**Key Features**:
- ✅ **Zero Breaking Changes**: Legacy clients continue to receive their expected format
- ✅ **Intelligent Client Detection**: Auto-detect client capabilities and preferences
- ✅ **Flexible Rollout Modes**: From gradual rollout to full adoption
- ✅ **Format Negotiation**: Content-type negotiation for multiple formats
- ✅ **Deprecation Management**: Plan and communicate transitions to clients
- ✅ **Monitoring & Analytics**: Track adoption and migration progress
- ✅ **Language-Specific Standards**: Support REST, HAL, JSON:API, and custom formats
- ✅ **Configuration Flexibility**: Presets, environment variables, and custom configs

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Rollout Modes](#rollout-modes)
3. [Client Detection](#client-detection)
4. [Format Negotiation](#format-negotiation)
5. [Configuration](#configuration)
6. [Migration Guide](#migration-guide)
7. [Best Practices](#best-practices)
8. [API Reference](#api-reference)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. Production Setup (Recommended)

```python
from fastapi import FastAPI
from fastapi.configure_problem_details import (
    ProblemDetailsConfigurationManager,
    ConfigurationPresets,
    get_config_manager,
    set_config_manager,
)

app = FastAPI()

# Create manager with production settings (hybrid mode)
manager = ProblemDetailsConfigurationManager(
    ConfigurationPresets.production()
)
set_config_manager(manager)

# Now add your middleware and routes
```

**What this does**:
- Enables RFC 7807 for modern clients
- Maintains legacy format for old clients
- Auto-detects client capabilities
- Sanitizes sensitive information
- Includes error tracking and logging

### 2. Add Format Negotiation Middleware

```python
from fastapi import Request

@app.middleware("http")
async def format_negotiation(request: Request, call_next):
    """Negotiate response format based on client"""
    manager = get_config_manager()
    
    # Detect client tier
    client_tier = manager.get_client_tier(
        user_agent=request.headers.get("User-Agent"),
        accept_header=request.headers.get("Accept"),
    )
    
    # Choose response format
    response_format = manager.choose_format(client_tier)
    request.state.response_format = response_format
    
    response = await call_next(request)
    return response
```

### 3. Use in Error Handling

```python
from fastapi import HTTPException

@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    manager = get_config_manager()
    
    # Get desired format
    response_format = request.state.response_format
    
    # Create problem details
    problem = {
        "type": "https://api.example.com/errors/internal-server-error",
        "title": "Internal Server Error",
        "status": 500,
        "detail": str(exc),
    }
    
    # Convert to appropriate format
    converted = manager.convert_response(problem, response_format)
    
    # Return with appropriate content type
    return JSONResponse(
        converted,
        status_code=500,
        media_type=manager.get_content_type(response_format),
    )
```

---

## Rollout Modes

### DISABLED
```python
config = ProblemDetailsConfig(mode=RolloutMode.DISABLED)
```
- RFC 7807 completely disabled
- All clients receive legacy format only
- Use during early planning phase

### LEGACY_ONLY
```python
config = ProblemDetailsConfig(mode=RolloutMode.LEGACY_ONLY)
```
- No RFC 7807 yet
- All clients receive legacy format
- Equivalent to not using the utility yet
- Use before rollout starts

### HYBRID (Recommended)
```python
config = ProblemDetailsConfig(mode=RolloutMode.HYBRID)
```
- **Modern clients** → RFC 7807 format
- **Legacy clients** → Legacy format
- Auto-detected based on User-Agent and Accept headers
- **Best for production with existing clients**

### OPT_IN
```python
config = ProblemDetailsConfig(mode=RolloutMode.OPT_IN)
```
- Default: Legacy format for all
- RFC 7807 only if client explicitly requests it
- Client must send: `Accept: application/problem+json`
- Use when clients must opt-in to new format

### OPT_OUT
```python
config = ProblemDetailsConfig(mode=RolloutMode.OPT_OUT)
```
- Default: RFC 7807 for all clients
- Legacy format only if client explicitly requests it
- Client must send: `Accept: application/json`
- Use in later rollout phase

### ENABLED
```python
config = ProblemDetailsConfig(mode=RolloutMode.ENABLED)
```
- All clients receive RFC 7807 format
- No legacy format support
- Breaking change for legacy clients
- Use only for new APIs or after full deprecation

---

## Client Detection

### Automatic Detection

The `LegacyClientDetector` automatically identifies client types:

```python
manager = ProblemDetailsConfigurationManager(ConfigurationPresets.production())

# Detection based on headers
tier = manager.get_client_tier(
    user_agent="axios/1.0",
    accept_header="application/json",
    client_id="client_123"
)

# Returns: ClientTier.COMPATIBLE or MODERN
```

### Known Legacy Clients

Automatically detected:
- Mobile apps (v1.x, v2.x)
- Old API clients
- Legacy browsers
- Custom legacy apps

### Register Custom Clients

```python
# Register a legacy client
manager.detector.register_legacy_client(
    client_id="mobile_app_v1",
    pattern="com.example.mobile/1",
    tier=ClientTier.LEGACY
)

# Register a modern client
manager.detector.register_modern_client(
    pattern="web_app_v3",
    tier=ClientTier.MODERN
)
```

### Client Tiers

| Tier | Behavior | Examples |
|------|----------|----------|
| `LEGACY` | Only legacy format | Old mobile apps, IE, legacy clients |
| `COMPATIBLE` | Both formats (HYBRID mode) | Axios, requests, older clients |
| `MODERN` | Only RFC 7807 | Node.js, curl, modern APIs |
| `UNKNOWN` | Default based on mode | Generic clients, unidentified |

---

## Format Negotiation

### Response Formats

```python
class ResponseFormat(str, Enum):
    RFC7807 = "rfc7807"              # RFC 7807 Problem Details
    LEGACY_FASTAPI = "legacy_fastapi"  # FastAPI default format
    SIMPLE_JSON = "simple_json"      # Simple {status, message}
    HATEOAS = "hateoas"              # HATEOAS with links
    CUSTOM = "custom"                # Custom format
```

### Content-Type Mapping

```python
Format Mapping:
- RFC7807          → application/problem+json
- LEGACY_FASTAPI   → application/json
- SIMPLE_JSON      → application/json
- HATEOAS          → application/hal+json
```

### Format Conversion

```python
manager = ProblemDetailsConfigurationManager(ConfigurationPresets.production())

# Create RFC 7807 response
problem_details = {
    "type": "https://api.example.com/errors/validation",
    "title": "Validation Error",
    "status": 400,
    "detail": "Invalid email address",
}

# Convert to different formats
legacy = manager.convert_response(
    problem_details,
    ResponseFormat.LEGACY_FASTAPI
)
# → {"detail": "Invalid email address", "status_code": 400}

simple = manager.convert_response(
    problem_details,
    ResponseFormat.SIMPLE_JSON
)
# → {"status": 400, "message": "Invalid email address"}
```

---

## Configuration

### Configuration Options

```python
class ProblemDetailsConfig:
    # Rollout settings
    mode: RolloutMode = RolloutMode.HYBRID
    enabled: bool = True
    
    # Legacy support
    support_legacy: bool = True
    detect_legacy_clients: bool = True
    legacy_format: ResponseFormat = ResponseFormat.LEGACY_FASTAPI
    
    # Format negotiation
    respect_accept_header: bool = True
    default_format: ResponseFormat = ResponseFormat.RFC7807
    allowed_formats: Set[ResponseFormat] = {RFC7807, LEGACY_FASTAPI, ...}
    
    # Security
    expose_error_types: bool = False
    expose_internal_errors: bool = False
    sanitize_messages: bool = True
    
    # Metadata
    include_error_id: bool = True
    include_timestamp: bool = True
    include_request_id: bool = True
    include_trace_id: bool = False
    
    # Deprecation
    deprecation_enabled: bool = True
    deprecation_date: Optional[datetime] = None
    migration_guide_url: Optional[str] = None
```

### Using Presets

```python
# Development (debug enabled)
config = ConfigurationPresets.development()

# Staging (mostly RFC 7807)
config = ConfigurationPresets.staging()

# Production (backward compatible)
config = ConfigurationPresets.production()

# Legacy only (no RFC 7807)
config = ConfigurationPresets.legacy_only()

# RFC 7807 only (breaking)
config = ConfigurationPresets.rfc7807_only()
```

### Environment Variables

```bash
# Rollout mode: DISABLED, LEGACY_ONLY, HYBRID, OPT_IN, OPT_OUT, ENABLED
RFC7807_MODE=HYBRID

# Enable RFC 7807
RFC7807_ENABLED=true

# Support legacy format
RFC7807_SUPPORT_LEGACY=true

# Expose internal errors (development only!)
RFC7807_EXPOSE_INTERNAL=false
```

```python
# Load from environment
manager = ProblemDetailsConfigurationManager(ConfigurationPresets.production())
manager.configure_from_env()
```

### Configuration File

```python
# Load from JSON file
manager = ProblemDetailsConfigurationManager(ConfigurationPresets.production())
manager.configure_from_file("config/rfc7807.json")
```

Config file example (`config/rfc7807.json`):
```json
{
    "mode": "hybrid",
    "enabled": true,
    "support_legacy": true,
    "expose_internal_errors": false,
    "deprecation_enabled": true,
    "deprecation_date": "2026-07-30T00:00:00"
}
```

---

## Migration Guide

### Phase 1: Planning (No Code Changes)

1. Review your current API error format
2. Identify legacy clients that need support
3. Plan rollout timeline
4. Create communication plan

### Phase 2: Implementation (Infrastructure Ready)

```python
# Install configure_problem_details
# Add to your FastAPI app with HYBRID mode

manager = ProblemDetailsConfigurationManager(
    ConfigurationPresets.production()
)  # HYBRID mode by default
```

**What happens**:
- Modern clients get RFC 7807
- Legacy clients get familiar format
- Zero breaking changes
- Both formats coexist

### Phase 3: Gradual Rollout (Communication Phase)

1. Deploy with HYBRID mode
2. Monitor adoption metrics
3. Communicate to clients about new format
4. Provide migration guide

```python
# Check adoption
@app.get("/metrics/adoption")
async def get_adoption():
    manager = get_config_manager()
    return manager.get_statistics()
```

### Phase 4: Deprecation (Preparing for Sunset)

```python
from datetime import datetime, timedelta

config = ConfigurationPresets.production()
config.deprecation_enabled = True
config.deprecation_date = datetime.now() + timedelta(days=180)
config.migration_guide_url = "https://api.example.com/migration"

manager = ProblemDetailsConfigurationManager(config)
```

**Effects**:
- Add `Deprecation` header to legacy responses
- Include migration guide link
- Prepare clients for future change

### Phase 5: Full Adoption (New Format Only)

```python
# Final: Switch to RFC 7807 only
config = ConfigurationPresets.rfc7807_only()

manager = ProblemDetailsConfigurationManager(config)
```

**Warning**: This is a breaking change. Only after:
- All legacy clients have migrated
- Sufficient notice period (usually 6+ months)
- Clear communication of deadline

---

## Best Practices

### 1. Always Start with HYBRID Mode

```python
# ✓ GOOD: Start backward compatible
config = ConfigurationPresets.production()  # HYBRID mode

# ✗ BAD: Don't break existing clients
config = ConfigurationPresets.rfc7807_only()  # ENABLED mode
```

### 2. Use Client Detection Caching

```python
# Enable caching for performance
config = ConfigurationPresets.production()
config.cache_detection = True
config.detection_cache_ttl = 3600  # 1 hour
```

### 3. Monitor Adoption Progress

```python
# Track format usage
@app.middleware("http")
async def track_format_usage(request: Request, call_next):
    manager = get_config_manager()
    
    client_tier = manager.get_client_tier(...)
    format_choice = manager.choose_format(client_tier)
    
    # Log for monitoring
    manager.log_format_decision(
        request.headers.get("X-Client-ID"),
        client_tier,
        format_choice,
        "Client-detected format"
    )
    
    return await call_next(request)
```

### 4. Set Realistic Deprecation Dates

```python
# Give clients at least 6 months notice
from datetime import datetime, timedelta

config.deprecation_date = datetime.now() + timedelta(days=180)
config.migration_guide_url = "https://api.example.com/migration/rfc7807"
```

### 5. Provide Clear Migration Documentation

```python
@app.get("/migration/rfc7807")
async def migration_guide():
    return {
        "title": "RFC 7807 Migration Guide",
        "current_format": "application/json (legacy)",
        "new_format": "application/problem+json (RFC 7807)",
        "deadline": "2026-07-30",
        "examples": {...},
        "migration_checklist": [...]
    }
```

### 6. Validate Configuration on Startup

```python
# Validate configuration
manager = ProblemDetailsConfigurationManager(config)
issues = manager.validate_config()

if issues:
    logger.error(f"Configuration issues: {issues}")
    raise RuntimeError("Invalid configuration")
```

### 7. Log Client Detection

```python
# Log for debugging
def detect_client(request: Request):
    manager = get_config_manager()
    
    tier = manager.get_client_tier(
        user_agent=request.headers.get("User-Agent"),
        accept_header=request.headers.get("Accept"),
    )
    
    logger.info(
        f"Client detected",
        extra={
            "client_tier": tier.value,
            "user_agent": request.headers.get("User-Agent"),
        }
    )
    
    return tier
```

---

## API Reference

### ProblemDetailsConfigurationManager

Main configuration manager class.

#### Methods

**`get_client_tier(...)`**
```python
def get_client_tier(
    user_agent: Optional[str] = None,
    accept_header: Optional[str] = None,
    client_id: Optional[str] = None,
    api_version: Optional[str] = None,
) -> ClientTier
```
Returns client compatibility tier.

**`should_use_rfc7807(client_tier: ClientTier) -> bool`**
Returns whether RFC 7807 should be used for this client.

**`choose_format(...) -> ResponseFormat`**
```python
def choose_format(
    client_tier: ClientTier,
    accept_header: Optional[str] = None,
    user_preference: Optional[ResponseFormat] = None,
) -> ResponseFormat
```
Choose response format for client.

**`convert_response(...) -> Dict[str, Any]`**
```python
def convert_response(
    problem_details: Dict[str, Any],
    target_format: ResponseFormat,
    instance_url: Optional[str] = None,
) -> Dict[str, Any]
```
Convert Problem Details to target format.

**`get_content_type(format: ResponseFormat) -> str`**
Get Content-Type header for format.

**`is_deprecated() -> bool`**
Check if legacy format is deprecated.

**`get_deprecation_header() -> Optional[str]`**
Get Deprecation header value.

**`get_statistics() -> Dict[str, Any]`**
Get format usage statistics.

**`export_config() -> Dict[str, Any]`**
Export current configuration.

**`import_config(data: Dict[str, Any])`**
Import configuration from dict.

**`validate_config() -> List[str]`**
Validate configuration and return issues.

---

## Troubleshooting

### "All clients get legacy format"

**Problem**: Even modern clients get legacy format.

**Solution**:
```python
# Check mode
if config.mode == RolloutMode.LEGACY_ONLY:
    print("Mode is LEGACY_ONLY, change to HYBRID")
    config.mode = RolloutMode.HYBRID

# Check enabled flag
if not config.enabled:
    print("RFC 7807 is disabled")
    config.enabled = True
```

### "Client detection not working"

**Problem**: Wrong clients detected or always UNKNOWN.

**Solution**:
```python
# Enable logging
import logging
logging.getLogger("fastapi.configure_problem_details").setLevel(logging.DEBUG)

# Check User-Agent
print(f"User-Agent: {request.headers.get('User-Agent')}")
print(f"Accept: {request.headers.get('Accept')}")

# Register client explicitly
manager.detector.register_legacy_client("my_app", "my_app/1.0", ClientTier.LEGACY)
```

### "Some clients still get wrong format"

**Problem**: Format negotiation choosing wrong format.

**Solution**:
```python
# Check Accept header parsing
accept_header = request.headers.get("Accept")
print(f"Accept header: {accept_header}")

# Explicitly test format selection
tier = manager.get_client_tier(user_agent=ua, accept_header=accept_header)
fmt = manager.choose_format(tier, accept_header)
print(f"Tier: {tier}, Format: {fmt}")

# Override if needed
manager.config.respect_accept_header = False
```

### "Performance is degraded"

**Problem**: Middleware adds too much latency.

**Solution**:
```python
# Enable caching
config.cache_detection = True
config.detection_cache_ttl = 3600

# Reduce detection overhead
config.detect_legacy_clients = False  # If not needed
```

---

## Related Documentation

- [RFC 7807 Specification](https://datatracker.ietf.org/doc/html/rfc7807)
- [ErrorMiddleware Guide](./ERRORMIDDLEWARE_GUIDE.md)
- [FastAPI Error Handling](https://fastapi.tiangolo.com/tutorial/handling-errors/)

---

## Support & Questions

For issues, questions, or contributions, please refer to the main project documentation.

**Last Updated**: 2026-01-30
**Version**: 1.0.0
**Status**: Production Ready
