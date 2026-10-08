"""Errors raised by the graph runner and mapped to HTTP statuses by the decision router."""


class GraphError(Exception):
    """Base class for runner errors."""


class ItemBusy(GraphError):  # noqa: N818 - name fixed by contract C7
    """Another request or worker holds the item lock (409 item-busy)."""


class NotAwaitingApproval(GraphError):  # noqa: N818 - name fixed by contract C7
    """The item has no pending approval (409 not-awaiting-approval)."""


class ItemNotFound(GraphError):  # noqa: N818
    """No such item for this tenant (404)."""


class InvalidDecision(GraphError):  # noqa: N818
    """The decision body does not fit the stored decision, e.g. unknown option (422)."""


class UnsupportedSteps(GraphError):  # noqa: N818
    """A niche declares custom ``steps:``; Phase 1 has no custom steps (ADR 0003 decision 8)."""
