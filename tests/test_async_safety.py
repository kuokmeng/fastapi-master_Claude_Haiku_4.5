"""
Async Safety Tests for build_from_pydantic_error

These tests validate that the build_from_pydantic_error function is:
- Async-safe (no race conditions)
- Thread-safe (no data races)
- Re-entrant (safe for concurrent calls)
- Compatible with FastAPI async handlers

Run with: pytest tests/test_async_safety.py -v
"""

import asyncio
import pytest
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pydantic import BaseModel, ValidationError
from fastapi.responses_rfc7807 import (
    build_from_pydantic_error,
    ValidationProblemDetails,
)


class TestAsyncConcurrency:
    """Test concurrent async usage"""

    @pytest.mark.asyncio
    async def test_concurrent_error_processing(self):
        """Multiple concurrent calls produce independent results"""

        async def process_error(error_id: int):
            error_list = [
                {
                    "type": "value_error",
                    "loc": ("field", error_id),
                    "msg": f"Error {error_id}",
                }
            ]
            return build_from_pydantic_error(error_list)

        # Run 10 concurrent error processing tasks
        problems = await asyncio.gather(*[process_error(i) for i in range(10)])

        # Each should have independent data
        assert len(problems) == 10
        for i, problem in enumerate(problems):
            assert problem.error_count == 1
            assert problem.errors[0].field == f"/field/{i}"
            assert problem.errors[0].message == f"Error {i}"

    @pytest.mark.asyncio
    async def test_many_concurrent_calls(self):
        """Stress test: 100+ concurrent calls"""

        async def process():
            errors = [
                {"type": "error", "loc": ("field",), "msg": "msg"} for _ in range(5)
            ]
            return build_from_pydantic_error(errors)

        # 100 concurrent tasks
        tasks = [process() for _ in range(100)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 100
        for problem in results:
            assert problem.error_count == 5
            assert len(problem.errors) == 5

    @pytest.mark.asyncio
    async def test_concurrent_with_different_parameters(self):
        """Concurrent calls with different parameters"""

        async def process(instance: str, problem_type: str):
            error_list = [{"type": "error", "loc": ("f",), "msg": "msg"}]
            return build_from_pydantic_error(
                error_list,
                instance=instance,
                problem_type=problem_type,
            )

        tasks = [process(f"/api/v{i}", f"urn:error:type{i}") for i in range(20)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 20
        for i, problem in enumerate(results):
            assert problem.instance == f"/api/v{i}"
            assert problem.problem_type == f"urn:error:type{i}"

    @pytest.mark.asyncio
    async def test_rapid_sequential_calls(self):
        """Very rapid sequential calls"""
        problems = []

        for i in range(100):
            error_list = [{"type": "error", "loc": ("field", i), "msg": f"msg{i}"}]
            problem = build_from_pydantic_error(error_list)
            problems.append(problem)

        assert len(problems) == 100
        for i, problem in enumerate(problems):
            assert problem.errors[0].field == f"/field/{i}"

    @pytest.mark.asyncio
    async def test_nested_async_calls(self):
        """Nested async context calls"""

        async def outer_process(n: int):
            async def inner_process(i: int):
                errors = [{"type": "error", "loc": ("field", i), "msg": f"msg{i}"}]
                return build_from_pydantic_error(errors)

            inner_results = await asyncio.gather(*[inner_process(i) for i in range(n)])
            return inner_results

        results = await asyncio.gather(*[outer_process(5) for _ in range(3)])

        assert len(results) == 3
        assert all(len(r) == 5 for r in results)


class TestThreadSafety:
    """Test thread safety for multi-threaded usage"""

    def test_concurrent_threading(self):
        """Multiple threads can safely call the function"""

        def process_in_thread(error_id: int) -> ValidationProblemDetails:
            error_list = [
                {
                    "type": "value_error",
                    "loc": ("field", error_id),
                    "msg": f"Error {error_id}",
                }
            ]
            return build_from_pydantic_error(error_list)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(process_in_thread, i) for i in range(50)]
            results = [f.result() for f in futures]

        assert len(results) == 50
        for i, problem in enumerate(results):
            assert problem.error_count == 1
            assert problem.errors[0].field == f"/field/{i}"

    def test_thread_isolation(self):
        """Each thread gets isolated results"""
        results = []
        results_lock = __import__("threading").Lock()

        def thread_worker(thread_id: int):
            for i in range(10):
                errors = [
                    {
                        "type": "error",
                        "loc": ("thread", thread_id, "iter", i),
                        "msg": f"msg",
                    }
                ]
                problem = build_from_pydantic_error(errors)
                with results_lock:
                    results.append(problem)

        threads = [
            __import__("threading").Thread(target=thread_worker, args=(i,))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 50  # 5 threads * 10 iterations


class TestReentrancy:
    """Test that function is re-entrant"""

    def test_recursive_calls(self):
        """Recursive calls produce correct results"""

        def recursive_process(depth: int) -> ValidationProblemDetails:
            if depth == 0:
                errors = [{"type": "error", "loc": ("depth", depth), "msg": "msg"}]
                return build_from_pydantic_error(errors)

            # Call recursively
            inner = recursive_process(depth - 1)

            # Create new problem at this level
            errors = [{"type": "error", "loc": ("depth", depth), "msg": "msg"}]
            return build_from_pydantic_error(errors)

        result = recursive_process(5)
        assert result.error_count == 1
        assert result.errors[0].field == "/depth/5"

    def test_callback_style_processing(self):
        """Process errors in callback-style chains"""

        def process_and_callback(
            error_list: list, callback
        ) -> ValidationProblemDetails:
            problem = build_from_pydantic_error(error_list)
            if callback:
                return callback(problem)
            return problem

        def chain_callback(problem):
            # Create new problem from existing one
            new_errors = [
                {
                    "type": "error",
                    "loc": ("chained",),
                    "msg": f"Wrapped: {problem.detail}",
                }
            ]
            return build_from_pydantic_error(new_errors)

        initial_errors = [
            {"type": "error", "loc": ("initial",), "msg": "Initial error"}
        ]

        result = process_and_callback(initial_errors, chain_callback)

        assert result.error_count == 1
        assert "Wrapped" in result.errors[0].message


class TestDataIsolation:
    """Test that data is properly isolated between calls"""

    def test_input_list_not_modified(self):
        """Input error_list is never modified"""
        error_list = [{"type": "error", "loc": ("field",), "msg": "msg"}]

        # Store original
        original = [dict(e) for e in error_list]

        # Process
        problem = build_from_pydantic_error(error_list)

        # Verify not modified
        assert error_list == original

    def test_independent_problem_instances(self):
        """Each call produces independent ValidationProblemDetails"""
        errors = [{"type": "error", "loc": ("field",), "msg": "msg"}]

        problem1 = build_from_pydantic_error(errors, instance="/api/v1")
        problem2 = build_from_pydantic_error(errors, instance="/api/v2")

        # Different instances
        assert problem1 is not problem2
        assert problem1.errors is not problem2.errors
        assert problem1.errors[0] is not problem2.errors[0]

        # Different data
        assert problem1.instance == "/api/v1"
        assert problem2.instance == "/api/v2"

    def test_no_shared_state_between_calls(self):
        """No shared state accumulation between calls"""
        problems = []

        for i in range(20):
            errors = [{"type": "error", "loc": ("field", i), "msg": f"msg{i}"}]
            problem = build_from_pydantic_error(errors)
            problems.append(problem)

        # Each should have exactly 1 error (not accumulating)
        for i, problem in enumerate(problems):
            assert problem.error_count == 1
            assert len(problem.errors) == 1
            assert problem.errors[0].field == f"/field/{i}"


class TestAsyncContextManagement:
    """Test compatibility with async context managers"""

    @pytest.mark.asyncio
    async def test_with_async_context_manager(self):
        """Works correctly within async context managers"""

        class AsyncContextual:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return False

            async def process_error(self, error_list):
                return build_from_pydantic_error(error_list)

        async with AsyncContextual() as ctx:
            errors = [{"type": "error", "loc": ("field",), "msg": "msg"}]
            problem = await ctx.process_error(errors)

        assert problem.error_count == 1

    @pytest.mark.asyncio
    async def test_with_timeout(self):
        """Completes quickly even with timeout"""

        async def slow_process():
            errors = [
                {"type": "error", "loc": (f"field{i}",), "msg": "msg"}
                for i in range(100)
            ]
            return build_from_pydantic_error(errors)

        # Should complete in well under 1 second
        result = await asyncio.wait_for(slow_process(), timeout=1.0)

        assert result.error_count == 100

    @pytest.mark.asyncio
    async def test_after_exception_handling(self):
        """Works correctly after async exceptions"""

        async def failing_task():
            raise ValueError("Task failed")

        async def recovery_process():
            try:
                await failing_task()
            except ValueError:
                errors = [
                    {
                        "type": "error",
                        "loc": ("recovery",),
                        "msg": "Recovered from exception",
                    }
                ]
                return build_from_pydantic_error(errors)

        problem = await recovery_process()

        assert problem.error_count == 1
        assert problem.errors[0].field == "/recovery"


class TestConcurrentErrorHandling:
    """Test error handling in concurrent scenarios"""

    @pytest.mark.asyncio
    async def test_handles_concurrent_validation_errors(self):
        """Multiple pydantic ValidationErrors in parallel"""

        class TestModel(BaseModel):
            email: str
            age: int

        async def validate_and_handle(data: dict):
            try:
                TestModel(**data)
            except ValidationError as e:
                return build_from_pydantic_error(e.errors())

        test_cases = [
            {"email": "invalid", "age": "not-int"},
            {"email": "", "age": -5},
            {"email": "missing-at", "age": 1000},
            {"email": "test@test.com", "age": "invalid"},
        ]

        problems = await asyncio.gather(
            *[validate_and_handle(data) for data in test_cases]
        )

        assert len(problems) == 4
        assert all(isinstance(p, ValidationProblemDetails) for p in problems)
        assert all(p.error_count >= 1 for p in problems)

    @pytest.mark.asyncio
    async def test_concurrent_different_error_types(self):
        """Different error types processed concurrently"""

        async def process(error_type: str, count: int):
            errors = [
                {
                    "type": error_type,
                    "loc": ("field", i),
                    "msg": f"Error {i}",
                }
                for i in range(count)
            ]
            return build_from_pydantic_error(errors)

        problems = await asyncio.gather(
            process("value_error", 5),
            process("type_error", 3),
            process("validation_error", 7),
        )

        assert problems[0].error_count == 5
        assert problems[1].error_count == 3
        assert problems[2].error_count == 7


class TestMemorySafety:
    """Test memory safety in concurrent scenarios"""

    def test_no_memory_leaks_in_loop(self):
        """Repeated calls don't accumulate memory"""
        import gc
        import sys

        gc.collect()
        initial_count = len(gc.get_objects())

        # Process 1000 errors
        for i in range(1000):
            errors = [{"type": "error", "loc": ("field", i), "msg": "msg"}]
            build_from_pydantic_error(errors)

        gc.collect()
        final_count = len(gc.get_objects())

        # Reasonable growth (not 1000+ new objects)
        growth = final_count - initial_count
        assert growth < 500, f"Possible memory leak: {growth} new objects"

    @pytest.mark.asyncio
    async def test_async_no_handle_leaks(self):
        """Async calls don't leak event loop handles"""

        async def process_batch():
            tasks = [
                asyncio.create_task(
                    asyncio.sleep(0)
                    or build_from_pydantic_error(
                        [
                            {
                                "type": "error",
                                "loc": ("field",),
                                "msg": "msg",
                            }
                        ]
                    )
                )
                for _ in range(100)
            ]
            return await asyncio.gather(*tasks)

        results = await process_batch()
        assert len(results) == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
