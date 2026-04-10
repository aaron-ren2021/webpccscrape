#!/usr/bin/env python3
"""Test script to verify identity rotation mechanism.

This script validates that identity rotation works correctly by:
1. Tracking when identities are created/rotated
2. Verifying rotation happens at the expected threshold
3. Confirming each identity has a unique fingerprint
"""
from __future__ import annotations

import logging

from crawler.identity_manager import IdentityManager

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def test_identity_rotation() -> None:
    """Test basic identity rotation behavior."""
    print("=" * 70)
    print("Testing Identity Rotation Mechanism")
    print("=" * 70)
    print()

    # Create identity manager with threshold of 4
    mgr = IdentityManager(max_requests_per_identity=4)

    identities_seen = set()
    fingerprints_seen = set()

    # Simulate 13 requests (matching the user's scenario)
    for i in range(1, 14):
        identity = mgr.get_identity()

        # Track unique identities and fingerprints
        identities_seen.add(identity.id)
        fingerprints_seen.add(identity.fingerprint.user_agent)

        # Simulate request outcome (alternate success/failure for testing)
        success = i % 3 != 0  # Fail every 3rd request
        mgr.record_request(success=success)

        print(
            f"Request {i:2d}: Identity {identity.id} | "
            f"Platform: {identity.fingerprint.platform:10s} | "
            f"Count: {identity.request_count} | "
            f"Result: {'✅' if success else '❌'}"
        )

    print()
    print("-" * 70)
    print("Results:")
    print(f"  Total Identities Created: {len(identities_seen)}")
    print(f"  Unique Fingerprints Used: {len(fingerprints_seen)}")
    print()

    # Get statistics
    stats = mgr.get_statistics()
    print("Statistics:")
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
    print()

    # Verify expectations
    expected_identities = (13 // 4) + 1  # Should rotate every 4 requests
    if len(identities_seen) >= expected_identities:
        print(f"✅ PASS: Created {len(identities_seen)} identities (expected >={expected_identities})")
    else:
        print(f"❌ FAIL: Only {len(identities_seen)} identities (expected >={expected_identities})")

    if len(fingerprints_seen) >= expected_identities:
        print(f"✅ PASS: Used {len(fingerprints_seen)} unique fingerprints")
    else:
        print(f"❌ FAIL: Only {len(fingerprints_seen)} unique fingerprints")

    print()
    print("=" * 70)


def test_forced_rotation() -> None:
    """Test forced rotation on contamination."""
    print()
    print("=" * 70)
    print("Testing Forced Rotation on Contamination")
    print("=" * 70)
    print()

    mgr = IdentityManager(max_requests_per_identity=10)  # High threshold

    # Get initial identity
    identity1 = mgr.get_identity()
    print(f"Initial Identity: {identity1.id}")

    # Simulate 3 requests, all failures
    for i in range(3):
        mgr.record_request(success=False)

    # Identity should be marked as contaminated
    print(f"Is Contaminated: {identity1.is_contaminated}")

    # Next get_identity should rotate
    identity2 = mgr.get_identity()
    print(f"New Identity: {identity2.id}")

    if identity1.id != identity2.id:
        print("✅ PASS: Identity rotated after contamination")
    else:
        print("❌ FAIL: Identity did not rotate")

    print()
    print("=" * 70)


def test_proxy_rotation() -> None:
    """Test proxy rotation with identities."""
    print()
    print("=" * 70)
    print("Testing Proxy Rotation")
    print("=" * 70)
    print()

    proxy_list = [
        "http://proxy1.example.com:8080",
        "http://proxy2.example.com:8080",
        "http://proxy3.example.com:8080",
    ]

    mgr = IdentityManager(
        max_requests_per_identity=3,
        enable_proxy_rotation=True,
        proxy_list=proxy_list,
    )

    proxies_seen = set()

    # Simulate 9 requests (should use all 3 proxies)
    for i in range(1, 10):
        identity = mgr.get_identity()
        mgr.record_request(success=True)

        if identity.proxy:
            proxies_seen.add(identity.proxy)
            print(f"Request {i}: Identity {identity.id} using {identity.proxy}")
        else:
            print(f"Request {i}: Identity {identity.id} (no proxy)")

    print()
    print(f"Unique Proxies Used: {len(proxies_seen)}")

    if len(proxies_seen) == len(proxy_list):
        print(f"✅ PASS: All {len(proxy_list)} proxies were used")
    else:
        print(f"❌ FAIL: Only {len(proxies_seen)}/{len(proxy_list)} proxies used")

    print()
    print("=" * 70)


if __name__ == "__main__":
    test_identity_rotation()
    test_forced_rotation()
    test_proxy_rotation()
