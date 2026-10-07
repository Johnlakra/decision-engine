"""String enums: the single source for CHECK constraints (DATA_MODEL.md, ARCHITECTURE.md §2)."""

from enum import StrEnum


class CheckedEnum(StrEnum):
    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]

    @classmethod
    def check_sql(cls, column: str) -> str:
        """SQL predicate restricting ``column`` to this enum's values."""
        quoted = ", ".join(f"'{value}'" for value in cls.values())
        return f"{column} IN ({quoted})"


class ItemStatus(CheckedEnum):
    NEW = "new"
    NORMALISED = "normalised"
    TRIAGED = "triaged"
    INFORMATIONAL = "informational"
    DISCARDED = "discarded"
    DECIDING = "deciding"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SNOOZED = "snoozed"
    AUTO_APPROVED = "auto_approved"
    ACTING = "acting"
    DONE = "done"
    NEEDS_HUMAN_TRIAGE = "needs_human_triage"
    FAILED = "failed"


class JobKind(CheckedEnum):
    PROCESS = "process"
    ACTION = "action"
    WEBHOOK = "webhook"
    POLL = "poll"
    UPLOAD = "upload"
    DIGEST = "digest"


class JobStatus(CheckedEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Sensitivity(CheckedEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class Risk(CheckedEnum):
    NORMAL = "normal"
    SPAM = "spam"
    SCAM_OR_PHISHING = "scam_or_phishing"


class Verdict(CheckedEnum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    SNOOZE = "snooze"


class DecidedBy(CheckedEnum):
    HUMAN = "human"
    AUTO = "auto"
    LLM = "llm"


class FeedbackKind(CheckedEnum):
    DECISION = "decision"
    TRIAGE_CORRECTION = "triage_correction"
    VOTE = "vote"


class LabelSource(CheckedEnum):
    HUMAN = "human"
    LLM = "llm"


class NicheSource(CheckedEnum):
    YAML = "yaml"
    DB = "db"


class DeliveryStatus(CheckedEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class ActionStatus(CheckedEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    UNDONE = "undone"
