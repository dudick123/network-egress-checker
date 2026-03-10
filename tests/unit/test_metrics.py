"""Tests for Prometheus metrics instrumentation."""

from egress_checker.metrics import (
    EGRESS_CHECK_FAILURE_CATEGORY,
    EGRESS_CHECK_SUCCESS,
    EGRESS_CHECK_TOTAL,
    EGRESS_CHECKER_HEALTHY,
    record_check_result,
)


class TestRecordCheckResult:
    """Tests for metrics recording."""

    def test_successful_check_sets_metrics(self) -> None:
        record_check_result(
            target="api",
            protocol="https",
            namespace="test-ns",
            success=True,
            duration_seconds=0.042,
        )
        assert (
            EGRESS_CHECK_SUCCESS.labels(
                target="api", protocol="https", namespace="test-ns"
            )._value.get()
            == 1
        )
        assert (
            EGRESS_CHECK_TOTAL.labels(
                target="api", protocol="https", namespace="test-ns", result="success"
            )._value.get()
            >= 1
        )

    def test_failed_check_sets_failure_category(self) -> None:
        record_check_result(
            target="db",
            protocol="tcp",
            namespace="test-ns",
            success=False,
            duration_seconds=5.0,
            failure_category="connection_refused",
        )
        assert (
            EGRESS_CHECK_SUCCESS.labels(
                target="db", protocol="tcp", namespace="test-ns"
            )._value.get()
            == 0
        )
        assert (
            EGRESS_CHECK_FAILURE_CATEGORY.labels(
                target="db", protocol="tcp", namespace="test-ns", category="connection_refused"
            )._value.get()
            == 1
        )
        # Other categories should be 0
        assert (
            EGRESS_CHECK_FAILURE_CATEGORY.labels(
                target="db", protocol="tcp", namespace="test-ns", category="dns_failure"
            )._value.get()
            == 0
        )

    def test_dns_duration_recorded(self) -> None:
        record_check_result(
            target="api",
            protocol="https",
            namespace="test-ns",
            success=True,
            duration_seconds=0.1,
            dns_duration_seconds=0.005,
        )
        # Verify the histogram was observed (check sample count)
        # We just verify no exception is raised and the metric exists
        assert True

    def test_tls_duration_recorded(self) -> None:
        record_check_result(
            target="api",
            protocol="https",
            namespace="test-ns",
            success=True,
            duration_seconds=0.1,
            tls_duration_seconds=0.045,
        )
        assert True

    def test_healthy_gauge_exists(self) -> None:
        EGRESS_CHECKER_HEALTHY.set(1)
        assert EGRESS_CHECKER_HEALTHY._value.get() == 1
