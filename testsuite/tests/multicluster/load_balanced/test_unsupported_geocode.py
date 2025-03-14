"""Test not supported geocode in geo load-balancing"""

import pytest

from testsuite.kuadrant.policy import has_condition
from testsuite.kuadrant.policy.dns import has_record_condition

pytestmark = [pytest.mark.multicluster]


def test_unsupported_geocode(dns_policy2):
    """Change default geocode to not existent one and verify that policy became not enforced"""
    dns_policy2.refresh().model.spec.loadBalancing.geo = "XX"
    res = dns_policy2.apply()
    assert res.status() == 0, res.err()

    assert dns_policy2.wait_until(has_condition("Enforced", "False"))
    assert dns_policy2.wait_until(
        has_record_condition("Ready", "False", "ProviderError")
    ), f"DNSPolicy did not reach expected record status, instead it was: {dns_policy2.model.status.recordConditions}"
