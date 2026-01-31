"""
RFC 7807 Problem Details Configuration Utility - Safe Rollout with Backward Compatibility

This module provides a comprehensive configuration system for managing RFC 7807 Problem Details
responses while ensuring seamless backward compatibility with legacy clients and existing API contracts.

Key Features:
1. Feature toggle system for gradual rollout
2. Legacy client auto-detection
3. Fallback response formats (maintain legacy behavior)
4. Content negotiation (Accept header support)
5. Configuration presets (development, staging, production)
6. Migration helpers and deprecation warnings
7. Language-specific standards compliance

Design Principles:
- Backward compatibility first (no breaking changes)
- Gradual rollout (enable for new clients, keep legacy for old ones)
- Auto-detection of legacy clients
- Language-specific standards (REST, HATEOAS, etc.)
- Configuration validation and safety
- Extensibility for custom configurations
"""

import logging
import os
from typing import Optional, Dict, Any, Callable, List, Literal, Set
from enum import Enum
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
import hashlib
import json
from functools import lru_cache

logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================


class RolloutMode(str, Enum):
    """Rollout modes for RFC 7807 adoption"""

    DISABLED = "disabled"  # RFC 7807 disabled, legacy only
    LEGACY_ONLY = "legacy_only"  # Legacy responses only (backward compat)
    HYBRID = "hybrid"  # Both RFC 7807 and legacy based on client detection
    OPT_IN = "opt_in"  # RFC 7807 opt-in via Accept header
    OPT_OUT = "opt_out"  # RFC 7807 default, opt-out via Accept header
    ENABLED = "enabled"  # RFC 7807 always enabled


class ClientTier(str, Enum):
    """Client compatibility tiers"""

    LEGACY = "legacy"  # Old clients (no RFC 7807 support)
    COMPATIBLE = "compatible"  # Supports both formats
    MODERN = "modern"  # Modern clients (RFC 7807 native)
    UNKNOWN = "unknown"  # Client type unknown


class LanguageStandard(str, Enum):
    """Language-specific standards for REST APIs"""

    REST = "rest"  # Generic REST standard (RFC 7807)
    HAL = "hal"  # Hypertext Application Language
    JSONAPI = "json_api"  # JSON:API standard
    GRAPHQL = "graphql"  # GraphQL standard
    CUSTOM = "custom"  # Custom format


class ResponseFormat(str, Enum):
    """Supported response formats"""

    RFC7807 = "rfc7807"  # RFC 7807 Problem Details
    LEGACY_FASTAPI = "legacy_fastapi"  # FastAPI default format
    SIMPLE_JSON = "simple_json"  # Simple JSON (status, message)
    HATEOAS = "hateoas"  # HATEOAS with links
    CUSTOM = "custom"  # Custom format


# ============================================================================
# Legacy Client Detection
# ============================================================================


class LegacyClientDetector:
    """Detects legacy clients based on request headers and patterns"""

    def __init__(self):
        """Initialize legacy client patterns"""
        self.legacy_user_agents = {
            # Mobile apps before RFC 7807 support
            "com.example.app": {"version_max": "1.0.0", "tier": ClientTier.LEGACY},
            "com.mobile.app": {"version_max": "2.0.0", "tier": ClientTier.LEGACY},
            # Old API clients
            "axios/0": {"tier": ClientTier.LEGACY},
            "node-fetch/1": {"tier": ClientTier.LEGACY},
            "urllib3": {"version_max": "1.25.0", "tier": ClientTier.LEGACY},
            # Old browser clients
            "IE": {"tier": ClientTier.LEGACY},
            "old-client": {"tier": ClientTier.LEGACY},
        }

        self.modern_user_agents = {
            "axios": ClientTier.COMPATIBLE,
            "requests": ClientTier.COMPATIBLE,
            "httpx": ClientTier.MODERN,
            "curl": ClientTier.COMPATIBLE,
            "fetch": ClientTier.MODERN,
            "RestClient": ClientTier.COMPATIBLE,
        }

        self.legacy_accept_headers = {
            "application/json": ClientTier.UNKNOWN,  # Generic, could be either
            "*/*": ClientTier.UNKNOWN,  # Generic
        }

        self.rfc7807_accept_headers = {
            "application/problem+json": ClientTier.MODERN,
            "application/vnd.api+json": ClientTier.MODERN,
            "application/ld+json": ClientTier.MODERN,
        }

    def detect(
        self,
        user_agent: Optional[str] = None,
        accept_header: Optional[str] = None,
        client_id: Optional[str] = None,
        api_version: Optional[str] = None,
    ) -> ClientTier:
        """
        Detect client tier from request headers

        Args:
            user_agent: User-Agent header
            accept_header: Accept header
            client_id: Custom client identifier
            api_version: Client API version

        Returns:
            ClientTier indicating client compatibility level
        """
        # Check explicit RFC 7807 support in Accept header
        if accept_header:
            for rfc_header in self.rfc7807_accept_headers:
                if rfc_header in accept_header:
                    return ClientTier.MODERN

        # Check User-Agent for known legacy clients
        if user_agent:
            # Check legacy patterns
            for pattern, config in self.legacy_user_agents.items():
                if pattern.lower() in user_agent.lower():
                    # Check version if specified
                    if "version_max" in config and api_version:
                        if (
                            self._compare_versions(api_version, config["version_max"])
                            <= 0
                        ):
                            return ClientTier.LEGACY
                    return config["tier"]

            # Check modern patterns
            for pattern, tier in self.modern_user_agents.items():
                if pattern.lower() in user_agent.lower():
                    return tier

        # Check client ID registry if available
        if client_id and self._is_legacy_client_id(client_id):
            return ClientTier.LEGACY

        return ClientTier.UNKNOWN

    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compare semantic versions (-1: v1<v2, 0: equal, 1: v1>v2)"""
        try:
            parts1 = [int(x) for x in v1.split(".")]
            parts2 = [int(x) for x in v2.split(".")]

            # Pad shorter version with zeros
            max_len = max(len(parts1), len(parts2))
            parts1 += [0] * (max_len - len(parts1))
            parts2 += [0] * (max_len - len(parts2))

            if parts1 < parts2:
                return -1
            elif parts1 > parts2:
                return 1
            return 0
        except (ValueError, AttributeError):
            return 0

    def _is_legacy_client_id(self, client_id: str) -> bool:
        """Check if client ID is in legacy registry"""
        # This would be populated from database/config
        legacy_clients = {"client_old_1", "client_legacy_2"}
        return client_id in legacy_clients

    def register_legacy_client(
        self, client_id: str, pattern: str, tier: ClientTier = ClientTier.LEGACY
    ) -> None:
        """Register a new legacy client pattern"""
        self.legacy_user_agents[pattern] = {"tier": tier}
        logger.info(f"Registered legacy client: {client_id} (pattern: {pattern})")

    def register_modern_client(
        self, pattern: str, tier: ClientTier = ClientTier.MODERN
    ) -> None:
        """Register a new modern client pattern"""
        self.modern_user_agents[pattern] = tier
        logger.info(f"Registered modern client: {pattern}")


# ============================================================================
# Response Format Converters
# ============================================================================


class ResponseFormatConverter:
    """Converts Problem Details between different formats"""

    @staticmethod
    def to_legacy_fastapi(problem_details: Dict[str, Any]) -> Dict[str, Any]:
        """Convert RFC 7807 to FastAPI legacy format"""
        return {
            "detail": problem_details.get("detail", "An error occurred"),
            "status_code": problem_details.get("status", 500),
            # Include type as error_type for compatibility
            "error_type": problem_details.get("type"),
        }

    @staticmethod
    def to_simple_json(problem_details: Dict[str, Any]) -> Dict[str, Any]:
        """Convert to simple JSON format (status + message)"""
        return {
            "status": problem_details.get("status", 500),
            "message": problem_details.get("detail", "An error occurred"),
        }

    @staticmethod
    def to_hateoas(
        problem_details: Dict[str, Any], instance_url: str
    ) -> Dict[str, Any]:
        """Convert to HATEOAS format with links"""
        base = {**problem_details}
        base["_links"] = {
            "self": {"href": instance_url},
            "help": {
                "href": f"https://api.example.com/help/{problem_details.get('type', 'error')}"
            },
        }
        return base

    @staticmethod
    def from_legacy_fastapi(legacy_response: Dict[str, Any]) -> Dict[str, Any]:
        """Convert FastAPI legacy format to RFC 7807"""
        return {
            "type": legacy_response.get(
                "error_type", "https://httpwg.org/specs/rfc7807#error"
            ),
            "title": "API Error",
            "status": legacy_response.get("status_code", 500),
            "detail": legacy_response.get("detail", "An error occurred"),
        }


# ============================================================================
# Configuration Models
# ============================================================================


@dataclass
class ProblemDetailsConfig:
    """Configuration for RFC 7807 Problem Details responses"""

    # Rollout settings
    mode: RolloutMode = RolloutMode.HYBRID
    language_standard: LanguageStandard = LanguageStandard.REST
    enabled: bool = True

    # Legacy support
    support_legacy: bool = True
    detect_legacy_clients: bool = True
    legacy_format: ResponseFormat = ResponseFormat.LEGACY_FASTAPI

    # Format negotiation
    respect_accept_header: bool = True
    default_format: ResponseFormat = ResponseFormat.RFC7807
    allowed_formats: Set[ResponseFormat] = field(
        default_factory=lambda: {
            ResponseFormat.RFC7807,
            ResponseFormat.LEGACY_FASTAPI,
            ResponseFormat.SIMPLE_JSON,
        }
    )

    # Security & Privacy
    expose_error_types: bool = False
    expose_internal_errors: bool = False
    sanitize_messages: bool = True
    max_detail_length: int = 500

    # Headers & Metadata
    include_error_id: bool = True
    include_timestamp: bool = True
    include_request_id: bool = True
    include_trace_id: bool = False

    # Extension members
    custom_extensions: Dict[str, Any] = field(default_factory=dict)
    extension_fields: Set[str] = field(
        default_factory=lambda: {"timestamp", "error_id", "request_id", "trace_id"}
    )

    # Content negotiation
    content_type_mapping: Dict[ResponseFormat, str] = field(
        default_factory=lambda: {
            ResponseFormat.RFC7807: "application/problem+json",
            ResponseFormat.LEGACY_FASTAPI: "application/json",
            ResponseFormat.SIMPLE_JSON: "application/json",
            ResponseFormat.HATEOAS: "application/hal+json",
            ResponseFormat.CUSTOM: "application/json",
        }
    )

    # Deprecation & Migration
    deprecation_enabled: bool = True
    deprecation_date: Optional[datetime] = None
    migration_guide_url: Optional[str] = None
    api_version: str = "1.0.0"

    # Performance
    cache_detection: bool = True
    detection_cache_ttl: int = 3600  # 1 hour

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary"""
        config_dict = asdict(self)
        # Convert enums to strings
        config_dict["mode"] = self.mode.value
        config_dict["language_standard"] = self.language_standard.value
        config_dict["legacy_format"] = self.legacy_format.value
        config_dict["default_format"] = self.default_format.value
        config_dict["allowed_formats"] = [f.value for f in self.allowed_formats]
        # Convert datetime
        if self.deprecation_date:
            config_dict["deprecation_date"] = self.deprecation_date.isoformat()
        return config_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProblemDetailsConfig":
        """Create config from dictionary"""
        # Convert string enums back
        if isinstance(data.get("mode"), str):
            data["mode"] = RolloutMode(data["mode"])
        if isinstance(data.get("language_standard"), str):
            data["language_standard"] = LanguageStandard(data["language_standard"])
        if isinstance(data.get("legacy_format"), str):
            data["legacy_format"] = ResponseFormat(data["legacy_format"])
        if isinstance(data.get("default_format"), str):
            data["default_format"] = ResponseFormat(data["default_format"])
        if isinstance(data.get("allowed_formats"), list):
            data["allowed_formats"] = {
                ResponseFormat(f) for f in data["allowed_formats"]
            }
        return cls(**data)


# ============================================================================
# Configuration Presets
# ============================================================================


class ConfigurationPresets:
    """Pre-configured settings for common scenarios"""

    @staticmethod
    def development() -> ProblemDetailsConfig:
        """Development configuration (RFC 7807 enabled, legacy support)"""
        return ProblemDetailsConfig(
            mode=RolloutMode.HYBRID,
            enabled=True,
            support_legacy=True,
            expose_error_types=True,
            expose_internal_errors=True,
            sanitize_messages=False,
            include_trace_id=True,
            deprecation_enabled=True,
        )

    @staticmethod
    def staging() -> ProblemDetailsConfig:
        """Staging configuration (mostly RFC 7807, legacy fallback)"""
        return ProblemDetailsConfig(
            mode=RolloutMode.OPT_OUT,
            enabled=True,
            support_legacy=True,
            expose_error_types=False,
            expose_internal_errors=False,
            sanitize_messages=True,
            include_trace_id=True,
            deprecation_enabled=True,
        )

    @staticmethod
    def production() -> ProblemDetailsConfig:
        """Production configuration (secure, backward compatible)"""
        return ProblemDetailsConfig(
            mode=RolloutMode.HYBRID,
            enabled=True,
            support_legacy=True,
            detect_legacy_clients=True,
            expose_error_types=False,
            expose_internal_errors=False,
            sanitize_messages=True,
            include_error_id=True,
            include_timestamp=True,
            include_request_id=True,
            include_trace_id=False,
            deprecation_enabled=True,
            deprecation_date=datetime.now() + timedelta(days=180),  # 6 months
        )

    @staticmethod
    def legacy_only() -> ProblemDetailsConfig:
        """Legacy-only configuration (no RFC 7807 yet)"""
        return ProblemDetailsConfig(
            mode=RolloutMode.LEGACY_ONLY,
            enabled=False,
            support_legacy=True,
            legacy_format=ResponseFormat.LEGACY_FASTAPI,
        )

    @staticmethod
    def rfc7807_only() -> ProblemDetailsConfig:
        """RFC 7807 only (breaking change, new APIs)"""
        return ProblemDetailsConfig(
            mode=RolloutMode.ENABLED,
            enabled=True,
            support_legacy=False,
            default_format=ResponseFormat.RFC7807,
        )


# ============================================================================
# Main Configuration Manager
# ============================================================================


class ProblemDetailsConfigurationManager:
    """Manages RFC 7807 Problem Details configuration with backward compatibility"""

    def __init__(self, config: Optional[ProblemDetailsConfig] = None):
        """
        Initialize configuration manager

        Args:
            config: Configuration object (defaults to production preset)
        """
        self.config = config or ConfigurationPresets.production()
        self.detector = LegacyClientDetector()
        self.converter = ResponseFormatConverter()
        self._client_cache: Dict[str, ClientTier] = {}
        self._format_decision_log: List[Dict[str, Any]] = []

    def configure_from_env(self) -> None:
        """Load configuration from environment variables"""
        env_mode = os.getenv("RFC7807_MODE", "HYBRID").upper()
        try:
            self.config.mode = RolloutMode[env_mode]
        except KeyError:
            logger.warning(f"Invalid RFC7807_MODE: {env_mode}, using default")

        # Load other settings from env
        self.config.enabled = os.getenv("RFC7807_ENABLED", "true").lower() == "true"
        self.config.support_legacy = (
            os.getenv("RFC7807_SUPPORT_LEGACY", "true").lower() == "true"
        )
        self.config.expose_internal_errors = (
            os.getenv("RFC7807_EXPOSE_INTERNAL", "false").lower() == "true"
        )

        logger.info(
            f"Configuration loaded from environment: mode={self.config.mode.value}"
        )

    def configure_from_file(self, filepath: str) -> None:
        """Load configuration from JSON file"""
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            self.config = ProblemDetailsConfig.from_dict(data)
            logger.info(f"Configuration loaded from file: {filepath}")
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load configuration file: {e}")

    def get_client_tier(
        self,
        user_agent: Optional[str] = None,
        accept_header: Optional[str] = None,
        client_id: Optional[str] = None,
        api_version: Optional[str] = None,
    ) -> ClientTier:
        """
        Determine client tier with caching

        Args:
            user_agent: User-Agent header
            accept_header: Accept header
            client_id: Custom client identifier
            api_version: Client API version

        Returns:
            ClientTier for the request
        """
        if not self.config.detect_legacy_clients:
            return ClientTier.MODERN

        # Create cache key
        cache_key = hashlib.md5(
            f"{user_agent}{accept_header}{client_id}".encode()
        ).hexdigest()

        # Check cache
        if self.config.cache_detection and cache_key in self._client_cache:
            return self._client_cache[cache_key]

        # Detect tier
        tier = self.detector.detect(user_agent, accept_header, client_id, api_version)

        # Cache result
        if self.config.cache_detection:
            self._client_cache[cache_key] = tier

        return tier

    def should_use_rfc7807(self, client_tier: ClientTier) -> bool:
        """
        Determine if RFC 7807 should be used for this client

        Args:
            client_tier: Detected client tier

        Returns:
            True if RFC 7807 should be used
        """
        if not self.config.enabled:
            return False

        mode = self.config.mode

        if mode == RolloutMode.DISABLED:
            return False
        elif mode == RolloutMode.LEGACY_ONLY:
            return False
        elif mode == RolloutMode.HYBRID:
            # Use RFC 7807 for modern clients, legacy for old
            return client_tier != ClientTier.LEGACY
        elif mode == RolloutMode.OPT_IN:
            # Use only if client explicitly requests
            return client_tier == ClientTier.MODERN
        elif mode == RolloutMode.OPT_OUT:
            # Use for all except legacy
            return client_tier != ClientTier.LEGACY
        elif mode == RolloutMode.ENABLED:
            # Always use RFC 7807
            return True

        return False

    def choose_format(
        self,
        client_tier: ClientTier,
        accept_header: Optional[str] = None,
        user_preference: Optional[ResponseFormat] = None,
    ) -> ResponseFormat:
        """
        Choose response format based on client and headers

        Args:
            client_tier: Client compatibility tier
            accept_header: Accept header from request
            user_preference: User-specified preference

        Returns:
            ResponseFormat to use
        """
        # User preference takes precedence
        if user_preference and user_preference in self.config.allowed_formats:
            return user_preference

        # Check Accept header
        if self.config.respect_accept_header and accept_header:
            # Check for explicit RFC 7807 request
            if "application/problem+json" in accept_header:
                return ResponseFormat.RFC7807
            # Check for legacy formats
            if "application/json" in accept_header:
                if client_tier == ClientTier.LEGACY:
                    return self.config.legacy_format

        # Default based on client tier
        if self.should_use_rfc7807(client_tier):
            return ResponseFormat.RFC7807
        else:
            return self.config.legacy_format

    def convert_response(
        self,
        problem_details: Dict[str, Any],
        target_format: ResponseFormat,
        instance_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert Problem Details to target format

        Args:
            problem_details: RFC 7807 Problem Details object
            target_format: Target response format
            instance_url: URL for HATEOAS links

        Returns:
            Converted response object
        """
        if target_format == ResponseFormat.RFC7807:
            return problem_details
        elif target_format == ResponseFormat.LEGACY_FASTAPI:
            return self.converter.to_legacy_fastapi(problem_details)
        elif target_format == ResponseFormat.SIMPLE_JSON:
            return self.converter.to_simple_json(problem_details)
        elif target_format == ResponseFormat.HATEOAS:
            return self.converter.to_hateoas(problem_details, instance_url or "/")
        else:
            return problem_details

    def get_content_type(self, response_format: ResponseFormat) -> str:
        """Get Content-Type header for response format"""
        return self.config.content_type_mapping.get(response_format, "application/json")

    def is_deprecated(self) -> bool:
        """Check if legacy format is deprecated"""
        if not self.config.deprecation_enabled:
            return False
        if not self.config.deprecation_date:
            return False
        return datetime.now() >= self.config.deprecation_date

    def get_deprecation_header(self) -> Optional[str]:
        """Get Deprecation header value if legacy format is used"""
        if not self.is_deprecated():
            return None

        header = f"true"
        if self.config.deprecation_date:
            header += f'; date="{self.config.deprecation_date.isoformat()}"'
        if self.config.migration_guide_url:
            header += f'; link="{self.config.migration_guide_url}"'

        return header

    def log_format_decision(
        self,
        client_id: Optional[str],
        client_tier: ClientTier,
        chosen_format: ResponseFormat,
        reason: str,
    ) -> None:
        """Log format decision for monitoring"""
        self._format_decision_log.append(
            {
                "timestamp": datetime.now().isoformat(),
                "client_id": client_id,
                "client_tier": client_tier.value,
                "format": chosen_format.value,
                "reason": reason,
            }
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about format usage"""
        if not self._format_decision_log:
            return {"total_decisions": 0}

        format_counts = {}
        tier_counts = {}

        for decision in self._format_decision_log:
            fmt = decision["format"]
            tier = decision["client_tier"]

            format_counts[fmt] = format_counts.get(fmt, 0) + 1
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        return {
            "total_decisions": len(self._format_decision_log),
            "formats": format_counts,
            "client_tiers": tier_counts,
            "recent_decisions": self._format_decision_log[-10:],  # Last 10
        }

    def export_config(self) -> Dict[str, Any]:
        """Export current configuration"""
        return self.config.to_dict()

    def import_config(self, data: Dict[str, Any]) -> None:
        """Import configuration from dictionary"""
        self.config = ProblemDetailsConfig.from_dict(data)
        logger.info("Configuration imported successfully")

    def validate_config(self) -> List[str]:
        """Validate configuration for issues"""
        issues = []

        if not self.config.enabled and self.config.mode != RolloutMode.DISABLED:
            issues.append("Configuration: enabled=False but mode is not DISABLED")

        if (
            self.config.mode == RolloutMode.LEGACY_ONLY
            and ResponseFormat.RFC7807 in self.config.allowed_formats
        ):
            issues.append(
                "LEGACY_ONLY mode should not have RFC 7807 in allowed_formats"
            )

        if self.config.sanitize_messages and self.config.expose_internal_errors:
            issues.append(
                "Warning: sanitize_messages=True but expose_internal_errors=True"
            )

        return issues


# ============================================================================
# Convenience Functions
# ============================================================================


def create_development_config() -> ProblemDetailsConfig:
    """Create development configuration"""
    return ConfigurationPresets.development()


def create_production_config() -> ProblemDetailsConfig:
    """Create production configuration"""
    return ConfigurationPresets.production()


def create_staging_config() -> ProblemDetailsConfig:
    """Create staging configuration"""
    return ConfigurationPresets.staging()


def create_custom_config(
    mode: RolloutMode,
    support_legacy: bool = True,
    expose_internal_errors: bool = False,
) -> ProblemDetailsConfig:
    """Create custom configuration"""
    return ProblemDetailsConfig(
        mode=mode,
        support_legacy=support_legacy,
        expose_internal_errors=expose_internal_errors,
    )


# ============================================================================
# Global Instance
# ============================================================================

# Create global configuration manager instance
_global_config_manager: Optional[ProblemDetailsConfigurationManager] = None


def get_config_manager() -> ProblemDetailsConfigurationManager:
    """Get global configuration manager instance"""
    global _global_config_manager

    if _global_config_manager is None:
        # Load from environment or use default
        _global_config_manager = ProblemDetailsConfigurationManager(
            ConfigurationPresets.production()
        )
        _global_config_manager.configure_from_env()

    return _global_config_manager


def reset_config_manager() -> None:
    """Reset global configuration manager (for testing)"""
    global _global_config_manager
    _global_config_manager = None


def set_config_manager(manager: ProblemDetailsConfigurationManager) -> None:
    """Set global configuration manager instance"""
    global _global_config_manager
    _global_config_manager = manager
