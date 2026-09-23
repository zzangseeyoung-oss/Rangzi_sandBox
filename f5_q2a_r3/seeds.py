"""R3 seeds (same derivation rule as R1/R2). The QUAL namespace is always allowed. Any other namespace needs an in-process
GRANT that only r3_stage.stage_a issues, on the external runner, AFTER it has verified the source manifest, the runtime identity,
the dependency lock, the MASTER authorization and the external run-count record. A NON_SCIENCE_MOCK authorization can only
grant NS_AUTHMOCK; a declared science namespace requires a non-mock authorization. The trust root is the externally supplied,
content-addressed runtime + the external run records, NOT this module (R2 B1 showed in-process gates cannot be a trust root)."""
import hashlib

from .design import NS_AUTHMOCK, NS_QUAL, NS_SCIENCE_DECLARED

_GRANT = None


class SeedNamespaceViolation(RuntimeError):
    pass


def grant(namespace, units, mock):
    """Called exactly once by r3_stage.stage_a after all external checks passed."""
    global _GRANT
    if _GRANT is not None:
        raise SeedNamespaceViolation("seed grant already issued in this process")
    if mock and namespace != NS_AUTHMOCK:
        raise SeedNamespaceViolation("a mock authorization can only grant the AUTHMOCK namespace")
    if not mock and namespace not in NS_SCIENCE_DECLARED:
        raise SeedNamespaceViolation("undeclared science namespace")
    _GRANT = (namespace, frozenset(units))


def unit_seed(namespace, unit, purpose):
    if namespace != NS_QUAL:
        if _GRANT is None or namespace != _GRANT[0] or unit not in _GRANT[1]:
            raise SeedNamespaceViolation("seed refused: no external grant for %s/%s" % (namespace, unit))
    return int.from_bytes(hashlib.sha256((namespace + ":" + "%04d" % unit + ":" + purpose).encode()).digest()[:8], "big")
