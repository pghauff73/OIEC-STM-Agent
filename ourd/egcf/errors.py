class EGCFError(RuntimeError):
    """Base EGCF refusal or consistency error."""


class SchemaError(EGCFError):
    """Raised when a typed EGCF object is invalid."""


class CapabilityError(EGCFError):
    """Raised when effective authority does not cover requirements."""


class QualificationError(EGCFError):
    """Raised when no context-qualified algorithm is available."""


class CompilationError(EGCFError):
    """Raised when a semantic command or workflow cannot compile safely."""


class ApprovalError(EGCFError):
    """Raised when execution lacks a current exact-plan approval."""
