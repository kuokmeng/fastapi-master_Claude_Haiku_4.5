"""
Test Suite for configure_problem_details Utility

Validates:
1. Configuration management and presets
2. Legacy client detection
3. Format negotiation and conversion
4. Backward compatibility
5. Configuration validation
6. Environment variable loading
"""

import pytest
import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi.configure_problem_details import (
    ProblemDetailsConfig,
    ProblemDetailsConfigurationManager,
    LegacyClientDetector,
    ResponseFormatConverter,
    ConfigurationPresets,
    RolloutMode,
    ClientTier,
    LanguageStandard,
    ResponseFormat,
    get_config_manager,
    reset_config_manager,
    create_production_config,
    create_development_config,
)


# ============================================================================
# Test Configuration Models
# ============================================================================


class TestProblemDetailsConfig:
    """Test configuration model"""

    def test_default_config(self):
        """Test default configuration values"""
        config = ProblemDetailsConfig()
        assert config.mode == RolloutMode.HYBRID
        assert config.enabled is True
        assert config.support_legacy is True
        assert config.sanitize_messages is True

    def test_config_to_dict(self):
        """Test configuration serialization to dict"""
        config = ProblemDetailsConfig(
            mode=RolloutMode.ENABLED,
            enabled=True,
        )
        config_dict = config.to_dict()
        assert config_dict["mode"] == "enabled"
        assert config_dict["enabled"] is True

    def test_config_from_dict(self):
        """Test configuration deserialization from dict"""
        data = {
            "mode": "opt_in",
            "enabled": True,
            "support_legacy": False,
            "language_standard": "hal",
        }
        config = ProblemDetailsConfig.from_dict(data)
        assert config.mode == RolloutMode.OPT_IN
        assert config.support_legacy is False
        assert config.language_standard == LanguageStandard.HAL

    def test_config_round_trip(self):
        """Test config serialization round-trip"""
        original = ProblemDetailsConfig(
            mode=RolloutMode.OPT_OUT,
            expose_internal_errors=True,
            deprecation_date=datetime.now(),
        )
        serialized = original.to_dict()
        restored = ProblemDetailsConfig.from_dict(serialized)
        assert restored.mode == original.mode
        assert restored.expose_internal_errors == original.expose_internal_errors


# ============================================================================
# Test Configuration Presets
# ============================================================================


class TestConfigurationPresets:
    """Test pre-configured presets"""

    def test_development_preset(self):
        """Test development configuration"""
        config = ConfigurationPresets.development()
        assert config.enabled is True
        assert config.support_legacy is True
        assert config.expose_internal_errors is True
        assert config.sanitize_messages is False
        assert config.include_trace_id is True

    def test_staging_preset(self):
        """Test staging configuration"""
        config = ConfigurationPresets.staging()
        assert config.mode == RolloutMode.OPT_OUT
        assert config.expose_internal_errors is False
        assert config.sanitize_messages is True

    def test_production_preset(self):
        """Test production configuration"""
        config = ConfigurationPresets.production()
        assert config.mode == RolloutMode.HYBRID
        assert config.support_legacy is True
        assert config.detect_legacy_clients is True
        assert config.expose_internal_errors is False
        assert config.include_trace_id is False

    def test_legacy_only_preset(self):
        """Test legacy-only configuration"""
        config = ConfigurationPresets.legacy_only()
        assert config.mode == RolloutMode.LEGACY_ONLY
        assert config.enabled is False

    def test_rfc7807_only_preset(self):
        """Test RFC 7807 only configuration"""
        config = ConfigurationPresets.rfc7807_only()
        assert config.mode == RolloutMode.ENABLED
        assert config.support_legacy is False


# ============================================================================
# Test Legacy Client Detection
# ============================================================================


class TestLegacyClientDetector:
    """Test legacy client detection"""

    @pytest.fixture
    def detector(self):
        return LegacyClientDetector()

    def test_detect_legacy_user_agent(self, detector):
        """Test detection of legacy user agent"""
        tier = detector.detect(user_agent="com.example.app/0.9")
        assert tier == ClientTier.LEGACY

    def test_detect_modern_user_agent(self, detector):
        """Test detection of modern user agent"""
        tier = detector.detect(user_agent="axios/1.0")
        assert tier in [ClientTier.COMPATIBLE, ClientTier.MODERN]

    def test_detect_rfc7807_accept_header(self, detector):
        """Test detection of RFC 7807 accept header"""
        tier = detector.detect(accept_header="application/problem+json")
        assert tier == ClientTier.MODERN

    def test_detect_unknown_client(self, detector):
        """Test unknown client detection"""
        tier = detector.detect(user_agent="unknown-client/1.0")
        assert tier == ClientTier.UNKNOWN

    def test_register_legacy_client(self, detector):
        """Test registering a custom legacy client"""
        detector.register_legacy_client("custom_app", "custom_app", ClientTier.LEGACY)
        tier = detector.detect(user_agent="custom_app/1.0")
        assert tier == ClientTier.LEGACY

    def test_register_modern_client(self, detector):
        """Test registering a custom modern client"""
        detector.register_modern_client("new_client", ClientTier.MODERN)
        tier = detector.detect(user_agent="new_client/2.0")
        assert tier == ClientTier.MODERN

    def test_version_comparison(self, detector):
        """Test semantic version comparison"""
        assert detector._compare_versions("1.0.0", "2.0.0") == -1
        assert detector._compare_versions("2.0.0", "2.0.0") == 0
        assert detector._compare_versions("3.0.0", "2.0.0") == 1
        assert detector._compare_versions("1.1.0", "1.0.9") == 1


# ============================================================================
# Test Format Conversion
# ============================================================================


class TestResponseFormatConverter:
    """Test response format conversion"""

    @pytest.fixture
    def problem_details(self):
        return {
            "type": "https://httpwg.org/specs/rfc7807#bad-request",
            "title": "Bad Request",
            "status": 400,
            "detail": "Invalid input provided",
            "instance": "/api/v1/items/123",
        }

    def test_to_legacy_fastapi(self, problem_details):
        """Test conversion to FastAPI legacy format"""
        result = ResponseFormatConverter.to_legacy_fastapi(problem_details)
        assert result["detail"] == "Invalid input provided"
        assert result["status_code"] == 400

    def test_to_simple_json(self, problem_details):
        """Test conversion to simple JSON format"""
        result = ResponseFormatConverter.to_simple_json(problem_details)
        assert result["status"] == 400
        assert result["message"] == "Invalid input provided"
        assert "type" not in result

    def test_to_hateoas(self, problem_details):
        """Test conversion to HATEOAS format"""
        result = ResponseFormatConverter.to_hateoas(problem_details, "/api/items/1")
        assert "_links" in result
        assert result["_links"]["self"]["href"] == "/api/items/1"

    def test_from_legacy_fastapi(self):
        """Test conversion from FastAPI legacy format"""
        legacy = {
            "detail": "Invalid input",
            "status_code": 400,
            "error_type": "validation_error",
        }
        result = ResponseFormatConverter.from_legacy_fastapi(legacy)
        assert result["title"] == "API Error"
        assert result["status"] == 400
        assert result["detail"] == "Invalid input"


# ============================================================================
# Test Configuration Manager
# ============================================================================


class TestProblemDetailsConfigurationManager:
    """Test configuration manager"""

    @pytest.fixture
    def manager(self):
        return ProblemDetailsConfigurationManager(ConfigurationPresets.production())

    def test_initialization(self, manager):
        """Test manager initialization"""
        assert manager.config is not None
        assert manager.detector is not None
        assert manager.converter is not None

    def test_get_client_tier(self, manager):
        """Test client tier detection"""
        tier = manager.get_client_tier(
            user_agent="axios/1.0",
            accept_header="application/json",
        )
        assert tier in [ClientTier.COMPATIBLE, ClientTier.MODERN, ClientTier.UNKNOWN]

    def test_should_use_rfc7807_hybrid_mode(self, manager):
        """Test RFC 7807 decision in hybrid mode"""
        manager.config.mode = RolloutMode.HYBRID

        # Modern client should get RFC 7807
        assert manager.should_use_rfc7807(ClientTier.MODERN) is True

        # Legacy client should not get RFC 7807
        assert manager.should_use_rfc7807(ClientTier.LEGACY) is False

        # Unknown should get RFC 7807 in hybrid mode
        assert manager.should_use_rfc7807(ClientTier.UNKNOWN) is True

    def test_should_use_rfc7807_enabled_mode(self, manager):
        """Test RFC 7807 decision in enabled mode"""
        manager.config.mode = RolloutMode.ENABLED

        # All clients should get RFC 7807
        assert manager.should_use_rfc7807(ClientTier.MODERN) is True
        assert manager.should_use_rfc7807(ClientTier.LEGACY) is True
        assert manager.should_use_rfc7807(ClientTier.UNKNOWN) is True

    def test_should_use_rfc7807_legacy_only_mode(self, manager):
        """Test RFC 7807 decision in legacy_only mode"""
        manager.config.mode = RolloutMode.LEGACY_ONLY

        # No clients should get RFC 7807
        assert manager.should_use_rfc7807(ClientTier.MODERN) is False
        assert manager.should_use_rfc7807(ClientTier.LEGACY) is False

    def test_should_use_rfc7807_disabled(self, manager):
        """Test RFC 7807 disabled"""
        manager.config.enabled = False
        assert manager.should_use_rfc7807(ClientTier.MODERN) is False

    def test_choose_format_modern_client(self, manager):
        """Test format choice for modern client"""
        manager.config.mode = RolloutMode.HYBRID
        fmt = manager.choose_format(
            ClientTier.MODERN,
            accept_header="application/json",
        )
        assert fmt == ResponseFormat.RFC7807

    def test_choose_format_legacy_client(self, manager):
        """Test format choice for legacy client"""
        manager.config.mode = RolloutMode.HYBRID
        fmt = manager.choose_format(
            ClientTier.LEGACY,
            accept_header="application/json",
        )
        assert fmt == manager.config.legacy_format

    def test_choose_format_explicit_rfc7807_request(self, manager):
        """Test format choice with explicit RFC 7807 request"""
        fmt = manager.choose_format(
            ClientTier.LEGACY,
            accept_header="application/problem+json",
        )
        assert fmt == ResponseFormat.RFC7807

    def test_choose_format_user_preference(self, manager):
        """Test format choice with user preference"""
        fmt = manager.choose_format(
            ClientTier.LEGACY,
            user_preference=ResponseFormat.SIMPLE_JSON,
        )
        assert fmt == ResponseFormat.SIMPLE_JSON

    def test_convert_response_to_rfc7807(self, manager):
        """Test response conversion to RFC 7807"""
        problem = {
            "type": "https://httpwg.org/specs/rfc7807#bad-request",
            "title": "Bad Request",
            "status": 400,
            "detail": "Invalid input",
        }
        result = manager.convert_response(problem, ResponseFormat.RFC7807)
        assert result == problem

    def test_convert_response_to_legacy(self, manager):
        """Test response conversion to legacy format"""
        problem = {
            "type": "validation_error",
            "title": "Bad Request",
            "status": 400,
            "detail": "Invalid input",
        }
        result = manager.convert_response(problem, ResponseFormat.LEGACY_FASTAPI)
        assert "detail" in result
        assert "status_code" in result

    def test_get_content_type(self, manager):
        """Test content type retrieval"""
        ct = manager.get_content_type(ResponseFormat.RFC7807)
        assert ct == "application/problem+json"

        ct = manager.get_content_type(ResponseFormat.LEGACY_FASTAPI)
        assert ct == "application/json"

    def test_deprecation_check(self, manager):
        """Test deprecation checking"""
        manager.config.deprecation_enabled = True
        manager.config.deprecation_date = datetime.now() - timedelta(days=1)
        assert manager.is_deprecated() is True

        manager.config.deprecation_date = datetime.now() + timedelta(days=1)
        assert manager.is_deprecated() is False

    def test_deprecation_header(self, manager):
        """Test deprecation header generation"""
        manager.config.deprecation_enabled = True
        manager.config.deprecation_date = datetime.now() - timedelta(days=1)
        manager.config.migration_guide_url = "https://api.example.com/migration"

        header = manager.get_deprecation_header()
        assert header is not None
        assert "true" in header
        assert "migration" in header.lower()

    def test_log_format_decision(self, manager):
        """Test format decision logging"""
        manager.log_format_decision(
            "client_1",
            ClientTier.MODERN,
            ResponseFormat.RFC7807,
            "Client supports RFC 7807",
        )

        stats = manager.get_statistics()
        assert stats["total_decisions"] == 1
        assert "rfc7807" in stats["formats"]

    def test_validate_config_warnings(self, manager):
        """Test configuration validation"""
        manager.config.enabled = False
        manager.config.mode = RolloutMode.ENABLED
        issues = manager.validate_config()
        assert len(issues) > 0

    def test_export_import_config(self, manager):
        """Test configuration export and import"""
        original_mode = manager.config.mode
        original_debug = manager.config.expose_internal_errors

        # Export
        exported = manager.export_config()
        assert exported["mode"] == original_mode.value

        # Modify
        manager.config.mode = RolloutMode.LEGACY_ONLY
        manager.config.expose_internal_errors = True

        # Import
        manager.import_config(exported)
        assert manager.config.mode == original_mode
        assert manager.config.expose_internal_errors == original_debug

    def test_configure_from_dict(self, manager):
        """Test configuration from dictionary"""
        data = {
            "mode": "opt_in",
            "enabled": True,
            "support_legacy": False,
        }
        manager.config = ProblemDetailsConfig.from_dict(data)
        assert manager.config.mode == RolloutMode.OPT_IN
        assert manager.config.support_legacy is False

    def test_client_detection_caching(self, manager):
        """Test client detection caching"""
        manager.config.cache_detection = True

        tier1 = manager.get_client_tier(user_agent="axios/1.0")
        tier2 = manager.get_client_tier(user_agent="axios/1.0")

        # Should return consistent results
        assert tier1 == tier2


# ============================================================================
# Test Global Configuration Manager
# ============================================================================


class TestGlobalConfigurationManager:
    """Test global configuration manager"""

    def teardown_method(self):
        """Reset global manager after each test"""
        reset_config_manager()

    def test_get_config_manager_singleton(self):
        """Test global config manager is singleton"""
        manager1 = get_config_manager()
        manager2 = get_config_manager()
        assert manager1 is manager2

    def test_config_manager_defaults_to_production(self):
        """Test global manager defaults to production"""
        manager = get_config_manager()
        assert manager.config.mode in [RolloutMode.HYBRID, RolloutMode.ENABLED]


# ============================================================================
# Test Convenience Functions
# ============================================================================


class TestConvenienceFunctions:
    """Test convenience configuration functions"""

    def test_create_production_config(self):
        """Test production config creation"""
        config = create_production_config()
        assert config.support_legacy is True
        assert config.expose_internal_errors is False

    def test_create_development_config(self):
        """Test development config creation"""
        config = create_development_config()
        assert config.expose_internal_errors is True
        assert config.sanitize_messages is False


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for backward compatibility"""

    def test_legacy_to_modern_migration(self):
        """Test migration from legacy to modern format"""
        # Start with legacy only
        legacy_config = ConfigurationPresets.legacy_only()
        legacy_manager = ProblemDetailsConfigurationManager(legacy_config)

        # Transition to hybrid
        hybrid_config = ConfigurationPresets.production()
        hybrid_manager = ProblemDetailsConfigurationManager(hybrid_config)

        # Old client still gets legacy
        legacy_tier = ClientTier.LEGACY
        legacy_format = legacy_manager.choose_format(legacy_tier)
        hybrid_format = hybrid_manager.choose_format(legacy_tier)

        assert legacy_format == ResponseFormat.LEGACY_FASTAPI
        assert hybrid_format == ResponseFormat.LEGACY_FASTAPI

        # New client gets RFC 7807
        modern_tier = ClientTier.MODERN
        hybrid_format_modern = hybrid_manager.choose_format(modern_tier)
        assert hybrid_format_modern == ResponseFormat.RFC7807

    def test_full_rollout_scenario(self):
        """Test complete rollout scenario"""
        manager = ProblemDetailsConfigurationManager(ConfigurationPresets.production())

        # Client 1: Legacy app version 1.0
        legacy_tier = manager.get_client_tier(user_agent="com.example.app/1.0")
        format1 = manager.choose_format(legacy_tier)
        assert format1 == ResponseFormat.LEGACY_FASTAPI

        # Client 2: Modern API client
        modern_tier = manager.get_client_tier(
            user_agent="axios/1.0",
            accept_header="application/problem+json",
        )
        format2 = manager.choose_format(modern_tier)
        assert format2 == ResponseFormat.RFC7807

        # Verify both clients are handled correctly
        assert format1 != format2
