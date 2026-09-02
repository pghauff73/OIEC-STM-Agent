class PolicyError(RuntimeError):
    """Raised when a deterministic governance or execution policy blocks work."""


class StateError(RuntimeError):
    """Raised when persisted evidence or state cannot be trusted."""


class ProviderError(RuntimeError):
    """Raised when a model provider cannot satisfy the requested protocol."""


class ContextBudgetError(ProviderError):
    """Raised when a provider request exceeds the configured context budget."""

    def __init__(self, message: str, *, report=None):
        super().__init__(message)
        self.report = dict(report or {})


class AgentCancelledError(RuntimeError):
    """Raised when an interactive agent turn is cooperatively stopped."""
