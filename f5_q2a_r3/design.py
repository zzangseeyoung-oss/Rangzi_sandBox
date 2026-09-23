"""F5-Q2A-R3 design: EVERY scientific constant is imported unchanged from the frozen R1 design (f5_q2a/design.py).
Only the governance names listed in GOVERNANCE_OVERRIDES are redefined (experiment label, R3 namespaces, units).
R3 changes the execution TRUST BOUNDARY only; no scientific constant is redefined here."""
from f5_q2a.design import *  # noqa: F401,F403  (scientific constants, byte-frozen in R1)

GOVERNANCE_OVERRIDES = ("EXPERIMENT", "NS_QUAL", "NS_SCIENCE_DECLARED", "NS_AUTHMOCK", "QUAL_WORLDS", "QUAL_UNITS", "SCIENCE_UNITS",
                        "AUTHMOCK_UNITS", "FROZEN_IMPLEMENTATION_MANIFEST")

EXPERIMENT = "F5-Q2A-R3"
NS_QUAL = "F5_Q2A_R3_QUAL_V1"                     # external QUAL namespace (disjoint from R1/R2 and science)
NS_SCIENCE_DECLARED = ("F5_Q2A_R3_DEV_V1",)       # declared only; needs a non-mock MASTER authorization verified on the external runner
NS_AUTHMOCK = "F5_Q2A_R3_AUTHMOCK_V1"             # NON-SCIENCE namespace a NON_SCIENCE_MOCK authorization may grant (plumbing QUAL)
QUAL_WORLDS = 32
QUAL_UNITS = tuple(range(9600, 9632))
SCIENCE_UNITS = tuple(range(32))                  # n = 32 independent WORLD units (DEV_INDEPENDENT_WORLDS, unchanged)
AUTHMOCK_UNITS = tuple(range(32))
FROZEN_IMPLEMENTATION_MANIFEST = "R3_SOURCE_MANIFEST.json"   # relative to the snapshot root on the external runner
