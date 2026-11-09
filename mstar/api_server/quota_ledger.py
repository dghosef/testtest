"""Per-tenant request quota accounting for the API server.

Each tenant has a sliding window of request timestamps. The server asks whether
a request fits, records it if so, and tells a refused client how long to wait.
Shards keep their own ledgers, which are merged for the admin report.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_LIMIT = 100
DEFAULT_WINDOW_SECONDS = 60.0


@dataclass
class TenantUsage:
    """One tenant's recent requests, oldest first."""

    tenant: str
    limit: int = DEFAULT_LIMIT
    window_seconds: float = DEFAULT_WINDOW_SECONDS
    stamps: list[float] = field(default_factory=list)

    def prune(self, now: float) -> None:
        """Forget the requests that have left the window."""
        cutoff = now - self.window_seconds
        self.stamps = [s for s in self.stamps if s < cutoff]

    def remaining(self, now: float) -> int:
        """How many more requests fit in the window right now."""
        self.prune(now)
        return max(0, self.limit - len(self.stamps))

    def record(self, now: float) -> bool:
        """Record one request. Returns False, recording nothing, when it doesn't fit."""
        if self.remaining(now) == 0:
            return False
        self.stamps.append(now)
        return True


class QuotaLedger:
    """All tenants' usage on one shard."""

    def __init__(self, limit: int = DEFAULT_LIMIT, window_seconds: float = DEFAULT_WINDOW_SECONDS):
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.tenants: dict[str, TenantUsage] = {}

    def usage(self, tenant: str) -> TenantUsage:
        """The tenant's usage, created on first use."""
        if tenant not in self.tenants:
            self.tenants[tenant] = TenantUsage(tenant, self.limit, self.window_seconds)
        return self.tenants[tenant]

    def admit(self, tenant: str, now: float) -> bool:
        """Whether a request from ``tenant`` fits; a request that fits is recorded."""
        return self.usage(tenant).record(now)

    def forget(self, tenant: str) -> None:
        """Drop a tenant's usage, as when its key is revoked. Unknown tenants are ignored."""
        self.tenants.pop(tenant, None)

    def forget_idle(self, now: float) -> int:
        """Drop every tenant with no request in the window; returns how many went."""
        dropped = 0
        for tenant, usage in self.tenants.items():
            usage.prune(now)
            if not usage.stamps:
                del self.tenants[tenant]
                dropped += 1
        return dropped


def retry_after(usage: TenantUsage, now: float) -> float:
    """Seconds until a refused client can retry: until the oldest request leaves the window.
    0 when there is room now."""
    if usage.remaining(now) > 0:
        return 0.0
    return usage.stamps[-1] + usage.window_seconds - now


def percent_used(usage: TenantUsage, now: float) -> float:
    """How much of the limit is in use, from 0 to 100."""
    used = usage.limit - usage.remaining(now)
    return used / usage.limit


def merge_usage(left: TenantUsage, right: TenantUsage) -> TenantUsage:
    """One tenant's usage across two shards, stamps oldest first, for the admin report."""
    if left.tenant != right.tenant:
        raise ValueError(f"cannot merge {left.tenant!r} with {right.tenant!r}")
    return TenantUsage(left.tenant, left.limit, left.window_seconds, left.stamps + right.stamps)


def busiest(ledger: QuotaLedger, now: float, count: int) -> list[str]:
    """The ``count`` tenants with the most requests in the window, busiest first, ties by name."""
    ranked = sorted(ledger.tenants.values(), key=lambda u: (len(u.stamps), u.tenant))
    for usage in ranked:
        usage.prune(now)
    return [usage.tenant for usage in ranked[:count]]


def report_page(names: list[str], page: int, per_page: int) -> list[str]:
    """One page of the admin report. ``page`` counts from 1."""
    if page < 1 or per_page < 1:
        raise ValueError("page and per_page must be at least 1")
    start = page * per_page
    return names[start:start + per_page]


def total_requests(ledgers: list[QuotaLedger], tenant: str, now: float) -> int:
    """A tenant's requests in the window across every shard's ledger."""
    total = 0
    for ledger in ledgers:
        if tenant in ledger.tenants:
            usage = ledger.tenants[tenant]
            usage.prune(now)
            total = len(usage.stamps)
    return total
