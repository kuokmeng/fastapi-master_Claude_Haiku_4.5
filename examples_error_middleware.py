"""
ErrorMiddleware Integration Example

Demonstrates how to integrate ErrorMiddleware with FastAPI applications
and the RFC 7807 Problem Details implementation.

This example shows:
1. Basic setup
2. Error handling scenarios
3. Custom error handlers
4. Production configuration
5. Monitoring and logging
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.error_middleware import ErrorMiddleware
from starlette.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
import logging
import os
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# Example 1: Basic Setup
# ============================================================================


def create_basic_app() -> FastAPI:
    """Create FastAPI app with basic ErrorMiddleware"""
    app = FastAPI(
        title="RFC 7807 Error Handling",
        description="Demonstrates ErrorMiddleware with RFC 7807",
        version="1.0.0",
    )

    # Add ErrorMiddleware with production settings
    app.add_middleware(ErrorMiddleware, debug=False, expose_internal_errors=False)

    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy"}

    @app.get("/users/{user_id}")
    async def get_user(user_id: int):
        """Get user by ID - demonstrates error handling"""
        if user_id < 0:
            raise ValueError("User ID must be positive")
        if user_id > 1000:
            raise KeyError(f"User {user_id} not found")
        return {"user_id": user_id, "name": f"User {user_id}"}

    @app.post("/users")
    async def create_user(name: str):
        """Create user - demonstrates validation"""
        if not name or not name.strip():
            raise ValueError("User name cannot be empty")
        if len(name) > 100:
            raise ValueError("User name too long")
        return {"user_id": 123, "name": name}

    return app


# ============================================================================
# Example 2: Development Mode with Debug
# ============================================================================


def create_debug_app() -> FastAPI:
    """Create app with debug mode enabled (development only!)"""
    app = FastAPI(title="RFC 7807 with Debug Mode")

    # Enable debug mode for development
    debug_mode = os.getenv("DEBUG", "false").lower() == "true"

    app.add_middleware(
        ErrorMiddleware,
        debug=debug_mode,  # ⚠️ Only enable in development!
        expose_internal_errors=debug_mode,
    )

    @app.get("/calculate/{dividend}/{divisor}")
    async def calculate(dividend: int, divisor: int):
        """Endpoint that might raise exceptions"""
        if divisor == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return {"result": dividend / divisor}

    return app


# ============================================================================
# Example 3: Custom Exception Classes
# ============================================================================


class InsufficientFundsError(Exception):
    """Custom business logic exception"""

    def __init__(self, required: float, available: float):
        self.required = required
        self.available = available
        super().__init__(f"Insufficient funds: need {required}, have {available}")


class ResourceLockedError(Exception):
    """Custom exception for resource locks"""

    def __init__(self, resource_id: str, locked_by: str):
        self.resource_id = resource_id
        self.locked_by = locked_by
        super().__init__(f"Resource {resource_id} is locked by {locked_by}")


def create_custom_app() -> FastAPI:
    """Create app with custom error handlers"""
    app = FastAPI(title="RFC 7807 with Custom Handlers")

    # Define custom error handlers
    async def handle_insufficient_funds(
        request: Request, exc: InsufficientFundsError, error_id: str
    ) -> JSONResponse:
        """Handle insufficient funds errors"""
        return JSONResponse(
            status_code=402,  # Payment Required
            content={
                "type": "https://api.example.com/errors/payment-required",
                "title": "Insufficient Funds",
                "status": 402,
                "detail": f"Required: ${exc.required:.2f}, Available: ${exc.available:.2f}",
                "instance": error_id,
                "required_amount": exc.required,
                "available_amount": exc.available,
            },
        )

    async def handle_resource_locked(
        request: Request, exc: ResourceLockedError, error_id: str
    ) -> JSONResponse:
        """Handle resource lock errors"""
        return JSONResponse(
            status_code=409,  # Conflict
            content={
                "type": "https://api.example.com/errors/resource-locked",
                "title": "Resource Locked",
                "status": 409,
                "detail": f"Resource is currently locked",
                "instance": error_id,
                "resource_id": exc.resource_id,
                "locked_by": exc.locked_by,
            },
        )

    # Add middleware with custom handlers
    app.add_middleware(
        ErrorMiddleware,
        debug=False,
        error_handlers={
            InsufficientFundsError: handle_insufficient_funds,
            ResourceLockedError: handle_resource_locked,
        },
    )

    @app.post("/transfer")
    async def transfer_funds(amount: float):
        """Transfer funds - may raise custom errors"""
        available_balance = 100.0
        if amount > available_balance:
            raise InsufficientFundsError(required=amount, available=available_balance)
        return {"success": True, "new_balance": available_balance - amount}

    @app.put("/resources/{resource_id}")
    async def update_resource(resource_id: str):
        """Update resource - may be locked"""
        locked_resources = {"res-123": "user-456"}
        if resource_id in locked_resources:
            raise ResourceLockedError(
                resource_id=resource_id, locked_by=locked_resources[resource_id]
            )
        return {"resource_id": resource_id, "updated": True}

    return app


# ============================================================================
# Example 4: Production Configuration
# ============================================================================


def create_production_app() -> FastAPI:
    """Create app with production-ready configuration"""
    app = FastAPI(
        title="Production API",
        docs_url=None,  # Disable docs in production
        redoc_url=None,
        openapi_url=None,  # Disable OpenAPI schema in production
    )

    # Production-safe configuration
    app.add_middleware(
        ErrorMiddleware,
        debug=False,  # ✅ Never expose details
        expose_internal_errors=False,  # ✅ Never expose internal info
        max_body_size=512,  # ✅ Limit body logging
    )

    # Standard endpoints with error handling
    @app.get("/api/v1/health")
    async def health():
        """Health check - never fails"""
        return {"status": "operational"}

    @app.get("/api/v1/data/{data_id}")
    async def get_data(data_id: str):
        """Get data with standard error handling"""
        try:
            # Simulate data retrieval
            if not data_id.isalnum():
                raise ValueError("Invalid data ID format")

            if data_id == "missing":
                raise KeyError(f"Data {data_id} not found")

            return {"data_id": data_id, "value": "sample data"}

        except Exception as e:
            # ErrorMiddleware will handle this
            raise

    @app.post("/api/v1/process")
    async def process_request(action: str):
        """Process request with validation"""
        valid_actions = ["read", "write", "delete"]

        if action not in valid_actions:
            raise ValueError(
                f"Invalid action: {action}. " f"Must be one of {valid_actions}"
            )

        return {"action": action, "status": "processed"}

    return app


# ============================================================================
# Example 5: Monitoring and Metrics
# ============================================================================


class ErrorMetricsMiddleware(ErrorMiddleware):
    """Extended ErrorMiddleware with metrics tracking"""

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.error_by_type = {}
        self.error_by_status = {}

    async def dispatch(self, request: Request, call_next):
        """Override dispatch to track metrics"""
        try:
            response = await call_next(request)
            return response
        except HTTPException:
            raise
        except Exception as exc:
            # Track error
            exc_type = type(exc).__name__
            self.error_by_type[exc_type] = self.error_by_type.get(exc_type, 0) + 1

            # Re-raise to let parent handle it
            raise

    def get_metrics(self) -> dict:
        """Get error metrics"""
        return {
            "errors_by_type": self.error_by_type,
            "total_errors": sum(self.error_by_type.values()),
        }


def create_monitored_app() -> FastAPI:
    """Create app with error monitoring"""
    app = FastAPI(title="Monitored API")

    # Use custom middleware with metrics
    app.add_middleware(ErrorMetricsMiddleware, debug=False)

    @app.get("/monitored/test/{operation}")
    async def monitored_endpoint(operation: str):
        """Endpoint for monitoring errors"""
        if operation == "value_error":
            raise ValueError("Test value error")
        elif operation == "key_error":
            raise KeyError("test_key")
        elif operation == "runtime_error":
            raise RuntimeError("Test runtime error")
        return {"operation": operation, "status": "success"}

    @app.get("/metrics")
    async def get_metrics():
        """Get error metrics"""
        # Get middleware instance
        middleware = None
        for m in app.user_middleware:
            if isinstance(m.cls, type) and issubclass(m.cls, ErrorMetricsMiddleware):
                # Note: In real app, would track middleware instance
                pass

        return {
            "message": "Metrics endpoint",
            "note": "Access middleware metrics through monitoring tool",
        }

    return app


# ============================================================================
# Example 6: Testing ErrorMiddleware
# ============================================================================


def test_error_middleware():
    """Test ErrorMiddleware functionality"""
    from fastapi.testclient import TestClient

    app = create_basic_app()
    client = TestClient(app)

    print("Testing ErrorMiddleware...\n")

    # Test 1: Successful request
    print("1. Testing successful request (GET /health)")
    response = client.get("/health")
    print(f"   Status: {response.status_code}")
    print(f"   Body: {response.json()}\n")

    # Test 2: ValueError (400)
    print("2. Testing ValueError (GET /users/-1)")
    response = client.get("/users/-1")
    print(f"   Status: {response.status_code}")
    print(f"   Body: {response.json()}\n")

    # Test 3: KeyError (404)
    print("3. Testing KeyError (GET /users/9999)")
    response = client.get("/users/9999")
    print(f"   Status: {response.status_code}")
    print(f"   Body: {response.json()}\n")

    # Test 4: Validation error
    print("4. Testing validation (POST /users)")
    response = client.post("/users", params={"name": ""})
    print(f"   Status: {response.status_code}")
    print(f"   Body: {response.json()}\n")

    print("✅ All tests completed!")


# ============================================================================
# Example 7: Real-World Scenario
# ============================================================================


def create_realistic_api() -> FastAPI:
    """Create realistic API with comprehensive error handling"""
    app = FastAPI(
        title="E-Commerce API",
        version="1.0.0",
    )

    app.add_middleware(ErrorMiddleware, debug=False)

    # Mock database
    products_db = {
        "1": {"id": "1", "name": "Product A", "stock": 10},
        "2": {"id": "2", "name": "Product B", "stock": 0},
    }

    @app.get("/products/{product_id}")
    async def get_product(product_id: str):
        """Get product by ID"""
        if not product_id.isdigit():
            raise ValueError(f"Invalid product ID: {product_id}")

        if product_id not in products_db:
            raise KeyError(f"Product {product_id} not found")

        return products_db[product_id]

    @app.post("/orders")
    async def create_order(product_id: str, quantity: int):
        """Create order"""
        if quantity <= 0:
            raise ValueError("Quantity must be greater than 0")

        if product_id not in products_db:
            raise KeyError(f"Product {product_id} not found")

        product = products_db[product_id]
        if product["stock"] < quantity:
            raise ValueError(
                f"Insufficient stock for {product['name']}: "
                f"requested {quantity}, available {product['stock']}"
            )

        return {
            "order_id": "ORD-123",
            "product_id": product_id,
            "quantity": quantity,
            "status": "created",
        }

    return app


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("ErrorMiddleware Integration Examples\n")
    print("=" * 60)

    # Run tests
    test_error_middleware()

    print("\n" + "=" * 60)
    print("Examples complete! Choose one of these apps to run:\n")
    print("1. create_basic_app() - Basic setup")
    print("2. create_debug_app() - Debug mode (development only)")
    print("3. create_custom_app() - Custom error handlers")
    print("4. create_production_app() - Production configuration")
    print("5. create_monitored_app() - With error monitoring")
    print("6. create_realistic_api() - Real-world e-commerce API")
    print("\nUsage:")
    print("  app = create_basic_app()")
    print("  uvicorn.run(app, host='0.0.0.0', port=8000)")
