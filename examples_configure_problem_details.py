"""
configure_problem_details Integration Guide

Demonstrates how to use the configure_problem_details utility for safe RFC 7807 rollout
with backward compatibility for legacy clients.

This guide shows:
1. Basic configuration setup
2. Client detection and format negotiation
3. Gradual rollout strategies
4. Deprecation management
5. Monitoring and statistics
6. Integration with FastAPI
"""

from fastapi import FastAPI, Request
from fastapi.middleware import ErrorMiddleware
from fastapi.responses import JSONResponse
from fastapi.configure_problem_details import (
    ProblemDetailsConfigurationManager,
    ProblemDetailsConfig,
    ConfigurationPresets,
    RolloutMode,
    ResponseFormat,
    get_config_manager,
    set_config_manager,
    ClientTier,
)
from typing import Optional, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Example 1: Basic Setup with Production Defaults
# ============================================================================


def example_1_production_setup():
    """
    Production setup with backward compatibility

    Scenario: Existing API needs to support both RFC 7807 and legacy format
    Strategy: Detect legacy clients and serve appropriate format
    """
    app = FastAPI(title="Production API with RFC 7807")

    # Create manager with production preset
    manager = ProblemDetailsConfigurationManager(ConfigurationPresets.production())

    # Set as global manager
    set_config_manager(manager)

    @app.get("/users/{user_id}")
    async def get_user(user_id: int, request: Request):
        """Get user with format negotiation"""
        manager = get_config_manager()

        # Detect client tier
        client_tier = manager.get_client_tier(
            user_agent=request.headers.get("User-Agent"),
            accept_header=request.headers.get("Accept"),
            client_id=request.headers.get("X-Client-ID"),
        )

        # Choose response format
        response_format = manager.choose_format(client_tier)

        # Simulate user fetch
        user_data = {"id": user_id, "name": "John Doe"}

        # In error case, convert response based on format
        # (This is simplified; actual implementation would use middleware)

        return user_data

    return app


# ============================================================================
# Example 2: Gradual Rollout with Hybrid Mode
# ============================================================================


def example_2_hybrid_rollout():
    """
    Gradual rollout using hybrid mode

    Scenario: Rolling out RFC 7807 to new clients while maintaining legacy support
    Strategy: HYBRID mode with automatic client detection
    """
    app = FastAPI(title="Hybrid RFC 7807 Rollout")

    # Create hybrid configuration
    config = ProblemDetailsConfig(
        mode=RolloutMode.HYBRID,  # Both formats
        detect_legacy_clients=True,  # Auto-detect
        support_legacy=True,  # Maintain legacy support
    )

    manager = ProblemDetailsConfigurationManager(config)
    set_config_manager(manager)

    @app.middleware("http")
    async def format_negotiation_middleware(request: Request, call_next):
        """Format negotiation middleware"""
        manager = get_config_manager()

        # Detect client
        client_tier = manager.get_client_tier(
            user_agent=request.headers.get("User-Agent"),
            accept_header=request.headers.get("Accept"),
        )

        # Store in request state for use in handlers
        request.state.client_tier = client_tier
        request.state.response_format = manager.choose_format(client_tier)

        # Log decision
        manager.log_format_decision(
            request.headers.get("X-Client-ID"),
            client_tier,
            request.state.response_format,
            "Auto-detected from headers",
        )

        response = await call_next(request)
        return response

    @app.get("/stats")
    async def get_format_stats():
        """Get RFC 7807 rollout statistics"""
        manager = get_config_manager()
        return manager.get_statistics()

    return app


# ============================================================================
# Example 3: Opt-In Strategy (Explicit Client Choice)
# ============================================================================


def example_3_opt_in_strategy():
    """
    Opt-in strategy for RFC 7807 adoption

    Scenario: New clients can opt-in to RFC 7807 via Accept header
    Strategy: OPT_IN mode - require explicit request for RFC 7807
    """
    app = FastAPI(title="RFC 7807 Opt-In API")

    # OPT_IN mode: clients must explicitly request RFC 7807
    config = ProblemDetailsConfig(
        mode=RolloutMode.OPT_IN,
        respect_accept_header=True,
    )

    manager = ProblemDetailsConfigurationManager(config)
    set_config_manager(manager)

    @app.get("/api/v1/items")
    async def list_items(request: Request):
        """
        List items with format negotiation

        Legacy clients: GET /api/v1/items
        - Returns: {"detail": "error"} (legacy format)

        Modern clients: GET /api/v1/items with Accept: application/problem+json
        - Returns: {"type": "...", "title": "...", ...} (RFC 7807)
        """
        return [{"id": 1, "name": "Item 1"}]

    return app


# ============================================================================
# Example 4: Deprecation and Migration Path
# ============================================================================


def example_4_deprecation_management():
    """
    Manage deprecation and migration of legacy format

    Scenario: Plan transition away from legacy format
    Strategy: Set deprecation date and provide migration guidance
    """
    from datetime import datetime, timedelta

    app = FastAPI(title="Legacy Format Deprecation")

    # Configure deprecation
    config = ConfigurationPresets.production()
    config.deprecation_enabled = True
    config.deprecation_date = datetime.now() + timedelta(days=180)  # 6 months
    config.migration_guide_url = "https://api.example.com/migration/rfc7807"

    manager = ProblemDetailsConfigurationManager(config)
    set_config_manager(manager)

    @app.middleware("http")
    async def deprecation_warning_middleware(request: Request, call_next):
        """Add deprecation warning header if needed"""
        response = await call_next(request)

        # Add deprecation header to legacy format responses
        if request.state.get("using_legacy_format"):
            manager = get_config_manager()
            deprecation_header = manager.get_deprecation_header()
            if deprecation_header:
                response.headers["Deprecation"] = deprecation_header

        return response

    @app.get("/migration-info")
    async def migration_info():
        """Provide migration information"""
        manager = get_config_manager()
        config = manager.config

        return {
            "deprecation_enabled": config.deprecation_enabled,
            "deprecation_date": (
                config.deprecation_date.isoformat() if config.deprecation_date else None
            ),
            "migration_guide": config.migration_guide_url,
            "deadline": "2026-07-30",
        }

    return app


# ============================================================================
# Example 5: Custom Client Registration
# ============================================================================


def example_5_custom_client_registration():
    """
    Register custom client types

    Scenario: Known legacy clients that need special handling
    Strategy: Explicitly register known clients
    """
    app = FastAPI(title="Custom Client Handling")

    manager = ProblemDetailsConfigurationManager(ConfigurationPresets.production())

    # Register known legacy mobile app
    manager.detector.register_legacy_client(
        "mobile_app_v1",
        "com.example.mobile/1",
        tier=ClientTier.LEGACY,
    )

    # Register known modern client
    manager.detector.register_modern_client(
        "web_app_v3",
        tier=ClientTier.MODERN,
    )

    set_config_manager(manager)

    @app.get("/api/items")
    async def list_items(request: Request):
        """API endpoint with custom client handling"""
        manager = get_config_manager()

        user_agent = request.headers.get("User-Agent")
        client_tier = manager.get_client_tier(user_agent=user_agent)

        return {
            "client_tier": client_tier.value,
            "detected_from": "User-Agent header",
            "items": [{"id": 1, "name": "Item"}],
        }

    return app


# ============================================================================
# Example 6: Configuration from Environment Variables
# ============================================================================


def example_6_environment_configuration():
    """
    Load configuration from environment variables

    Scenario: Different environments (dev, staging, prod) need different configs
    Strategy: Load configuration from environment

    Environment variables:
    - RFC7807_MODE: HYBRID, OPT_IN, OPT_OUT, ENABLED, LEGACY_ONLY, DISABLED
    - RFC7807_ENABLED: true/false
    - RFC7807_SUPPORT_LEGACY: true/false
    - RFC7807_EXPOSE_INTERNAL: true/false
    """
    app = FastAPI(title="Environment-Based Configuration")

    # Create manager with environment-based config
    manager = ProblemDetailsConfigurationManager(ConfigurationPresets.production())

    # Load from environment
    manager.configure_from_env()

    # Validate configuration
    issues = manager.validate_config()
    if issues:
        logger.warning(f"Configuration issues: {issues}")

    set_config_manager(manager)

    @app.get("/config")
    async def get_config_info():
        """Get current configuration (safe to expose)"""
        manager = get_config_manager()
        config = manager.config

        return {
            "mode": config.mode.value,
            "enabled": config.enabled,
            "support_legacy": config.support_legacy,
            "language_standard": config.language_standard.value,
        }

    return app


# ============================================================================
# Example 7: Integration with ErrorMiddleware
# ============================================================================


def example_7_middleware_integration():
    """
    Full integration with ErrorMiddleware for complete exception handling

    Scenario: Complete API with RFC 7807 error responses and backward compatibility
    Strategy: Combine ErrorMiddleware with ProblemDetailsConfigurationManager
    """
    app = FastAPI(title="Complete RFC 7807 Integration")

    # Configure Problem Details
    manager = ProblemDetailsConfigurationManager(ConfigurationPresets.production())
    set_config_manager(manager)

    # Add ErrorMiddleware
    app.add_middleware(ErrorMiddleware, debug=False)

    @app.middleware("http")
    async def format_negotiation(request: Request, call_next):
        """Negotiate response format based on client"""
        manager = get_config_manager()

        # Detect client
        client_tier = manager.get_client_tier(
            user_agent=request.headers.get("User-Agent"),
            accept_header=request.headers.get("Accept"),
        )

        # Store format choice in request state
        response_format = manager.choose_format(client_tier)
        request.state.response_format = response_format

        response = await call_next(request)
        return response

    @app.get("/api/users/{user_id}")
    async def get_user(user_id: int):
        """Get user - demonstrates error handling"""
        if user_id < 0:
            # ErrorMiddleware will catch and convert to RFC 7807
            raise ValueError("User ID must be positive")

        if user_id > 1000000:
            # KeyError will be converted by ErrorMiddleware
            users = {}
            return users[user_id]

        return {"id": user_id, "name": "John Doe"}

    @app.get("/api/admin")
    async def admin_only():
        """Admin endpoint - demonstrates permission error"""
        raise PermissionError("Admin access required")

    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy"}

    return app


# ============================================================================
# Example 8: Monitoring and Analytics
# ============================================================================


def example_8_monitoring_analytics():
    """
    Monitor RFC 7807 adoption and format usage

    Scenario: Track migration progress to RFC 7807
    Strategy: Collect and analyze format decision statistics
    """
    app = FastAPI(title="RFC 7807 Monitoring")

    manager = ProblemDetailsConfigurationManager(ConfigurationPresets.production())
    set_config_manager(manager)

    @app.middleware("http")
    async def format_tracking(request: Request, call_next):
        """Track format decisions"""
        manager = get_config_manager()

        client_tier = manager.get_client_tier(
            user_agent=request.headers.get("User-Agent"),
            accept_header=request.headers.get("Accept"),
        )

        response_format = manager.choose_format(client_tier)

        # Log the decision
        manager.log_format_decision(
            client_id=request.headers.get("X-Client-ID", "unknown"),
            client_tier=client_tier,
            chosen_format=response_format,
            reason=f"Detected: {client_tier.value}",
        )

        response = await call_next(request)
        return response

    @app.get("/metrics/rfc7807-adoption")
    async def get_adoption_metrics():
        """Get RFC 7807 adoption metrics"""
        manager = get_config_manager()
        stats = manager.get_statistics()

        # Calculate adoption percentage
        total = stats.get("total_decisions", 0)
        if total == 0:
            adoption_pct = 0
        else:
            rfc7807_count = stats.get("formats", {}).get("rfc7807", 0)
            adoption_pct = (rfc7807_count / total) * 100

        return {
            "total_requests": total,
            "rfc7807_adoption_percentage": adoption_pct,
            "format_breakdown": stats.get("formats", {}),
            "client_tier_breakdown": stats.get("client_tiers", {}),
            "recent_decisions": stats.get("recent_decisions", []),
        }

    return app


# ============================================================================
# Test Function - Run Examples
# ============================================================================


def test_all_examples():
    """Test all configuration examples"""
    examples = [
        ("Production Setup", example_1_production_setup()),
        ("Hybrid Rollout", example_2_hybrid_rollout()),
        ("Opt-In Strategy", example_3_opt_in_strategy()),
        ("Deprecation Management", example_4_deprecation_management()),
        ("Custom Clients", example_5_custom_client_registration()),
        ("Environment Config", example_6_environment_configuration()),
        ("Middleware Integration", example_7_middleware_integration()),
        ("Monitoring", example_8_monitoring_analytics()),
    ]

    print("\n" + "=" * 70)
    print("RFC 7807 Problem Details Configuration Examples")
    print("=" * 70)

    for name, app in examples:
        print(f"\n✓ {name}")
        print(f"  - Routes: {len(app.routes)}")
        print(f"  - Middlewares: {len(app.middleware)}")

    print("\n" + "=" * 70)
    print("All examples created successfully!")
    print("=" * 70)


if __name__ == "__main__":
    test_all_examples()
