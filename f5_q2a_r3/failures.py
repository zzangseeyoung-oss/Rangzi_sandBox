"""Failure classifier (fail-closed). Every failure is recorded; none is retried or replaced, except EXTERNAL_INFRA which a
future frozen driver may re-execute once with identical seed and configuration (original attempt retained)."""


def classify(exc):
    from .learner import NumericDivergence
    from .seeds import SeedNamespaceViolation
    if isinstance(exc, SeedNamespaceViolation):
        return "PROTOCOL_VIOLATION"
    if isinstance(exc, (NumericDivergence, FloatingPointError, ArithmeticError)):
        return "ARM_CAUSED_NUMERIC_DIVERGENCE"
    if isinstance(exc, (MemoryError, OSError, TimeoutError)):
        return "EXTERNAL_INFRA"
    return "UNCLASSIFIED"
