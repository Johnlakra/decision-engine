"""Time helpers: UTC in storage, tenant timezone for display."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

TENANT_TZ = ZoneInfo("Asia/Kolkata")


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(UTC)
