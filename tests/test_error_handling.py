"""Tests for error handling and safety improvements."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from safety.permissions import ActionVerdict, SafetyMiddleware


class TestAuditLogThreadSafety:
    """Verify audit log is safe under concurrent writes."""

    def test_concurrent_audit_writes(self):
        """Multiple threads writing audit entries should not corrupt the list."""
        from core.config import AppConfig

        config = AppConfig()
        middleware = SafetyMiddleware(config)

        n_threads = 10
        n_entries_per_thread = 50
        barrier = threading.Barrier(n_threads)

        def _write_entries():
            barrier.wait()  # All threads start simultaneously
            for i in range(n_entries_per_thread):
                name = threading.current_thread().name
                middleware.check("read_channel", description=f"thread-{name}-{i}")

        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = [pool.submit(_write_entries) for _ in range(n_threads)]
            for f in futures:
                f.result()

        expected = n_threads * n_entries_per_thread
        assert len(middleware.audit_log) == expected, (
            f"Expected {expected} entries, got {len(middleware.audit_log)}"
        )

    def test_concurrent_read_and_write(self):
        """Reading recent audit while writing should not raise."""
        from core.config import AppConfig

        config = AppConfig()
        middleware = SafetyMiddleware(config)
        errors: list[Exception] = []

        def _writer():
            for i in range(100):
                middleware.check("read_channel", description=f"write-{i}")

        def _reader():
            for _ in range(100):
                try:
                    middleware.get_recent_audit(10)
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=_writer)
        t2 = threading.Thread(target=_reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Concurrent read/write raised: {errors}"


class TestAuditLogClassification:
    """Verify action classification works correctly."""

    def test_read_actions_always_allow(self):
        from core.config import AppConfig

        config = AppConfig()
        middleware = SafetyMiddleware(config)
        for action in ("read_channel", "read_message", "search_memory"):
            verdict = middleware.check(action)
            assert verdict == ActionVerdict.ALLOW

    def test_destructive_actions_need_approval(self):
        from core.config import AppConfig

        config = AppConfig()
        middleware = SafetyMiddleware(config)
        for action in ("delete_anything", "merge_pr"):
            verdict = middleware.check(action)
            assert verdict == ActionVerdict.NEEDS_APPROVAL
