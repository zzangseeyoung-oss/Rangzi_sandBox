"""F5-Q2A-R1 design constants (candidate protocol; NOT frozen for science until MASTER freezes it).

All numbers below are measurement-instrument definitions fixed before any science data exists. None is a practical
margin. NUMERIC_MARGIN_STATUS = NOT_FROZEN (no result-independent basis exists at this stage)."""

EXPERIMENT = "F5-Q2A-R1"
MASTER_CANONICAL_DEC = "DEC-095"

# ---- namespaces: QUAL may be materialized; science namespaces are declared and refused
NS_QUAL = "F5_Q2A_R1_QUAL_V1"
NS_SCIENCE_DECLARED = ("F5_Q2A_R1_DEV_V1", "F5_Q2A_R1_CONFIRM_V1")
SEED_RULE = "int.from_bytes(sha256((namespace + ':' + '%04d' % unit + ':' + purpose).encode()).digest()[:8], 'big')"

# ---- sequence conditions (symmetric; each phase trains exactly one task for T_PHASE steps)
CONDITIONS = {
    "S0A": ("A",),            # A_FROM_SCRATCH
    "S0B": ("B",),            # B_FROM_SCRATCH
    "S1": ("A", "B"),         # A_TO_B
    "S2": ("B", "A"),         # B_TO_A
    "S3": ("A", "B", "A"),    # A_TO_B_TO_A
    "S4": ("B", "A", "B"),    # B_TO_A_TO_B
}
CONDITION_NAMES = {"S0A": "A_FROM_SCRATCH", "S0B": "B_FROM_SCRATCH", "S1": "A_TO_B", "S2": "B_TO_A",
                   "S3": "A_TO_B_TO_A", "S4": "B_TO_A_TO_B"}

# ---- relation strata (latent structural relation of the pair; hidden truth only)
RELATIONS = ("R_POS", "R_ZERO", "R_NEG")
RELATION_DEF = {
    "R_POS": "ALIGNED: B shares A's latent feature subspace (U_B = U_A) and its readout is aligned (w_B = +cos(phi) w_A + sin(phi) w_perp)",
    "R_ZERO": "NEUTRAL: B's subspace and readout are drawn independently of A (Haar U_B, uniform w_B)",
    "R_NEG": "CONFLICTING: B shares A's latent subspace (U_B = U_A) but its readout is anti-aligned (w_B = -cos(phi) w_A + sin(phi) w_perp)",
}
PHI_DEG = 30.0                 # |cos| = 0.866 for R_POS / R_NEG (symmetric in A<->B; marginal law of every task identical)

# ---- task family (identical for every task in every stratum)
D_IN = 16                      # input dimension, x ~ N(0, I)
K_LATENT = 4                   # latent features, U in Stiefel(4, 16) (Haar)
BETA = 1.5                     # feature nonlinearity scale: y = s * w . tanh(BETA * U x)
NOISE_VAR = 0.05               # label noise on training labels (eval targets are noiseless)
N_CALIB = 4096                 # per-world calibration inputs: s is chosen so Var(y) = 1 on them
N_EVAL = 512                   # per-world held-out evaluation inputs (disjoint stream from training)

# ---- learner (one learner, one update rule, no memory/replay/gating/regularisation path)
M_HIDDEN = 32
LR = 0.05                      # constant SGD step size, no momentum (no optimizer state carried across phases)
BATCH = 32
T_PHASE = 400                  # FIXED steps per phase for every task, condition and stratum (equal exposure per phase)
CKPT_EVERY = 5                 # evaluation checkpoints (step 0, 5, ..., 400) on every task; set to 5 (from 20) after a QUAL instrument
                               # check showed criterion at step ~40 (resolution only; learning, exposure and criterion unchanged)
CRITERION_NMSE = 0.25          # criterion = normalised eval MSE <= 0.25 (measurement definition, not a margin)

# ---- work accounting (deterministic accounted work units; wall clock is never used)
AWU_PER_TRAIN_EXAMPLE = 3 * (M_HIDDEN * D_IN + 2 * M_HIDDEN)     # forward + backward
AWU_PER_EVAL_EXAMPLE = M_HIDDEN * D_IN + 2 * M_HIDDEN            # forward only
TIMING = "wall-clock never measured or used (A13)"

# ---- QUAL fixtures (non-science)
QUAL_WORLDS = 8
QUAL_UNITS = tuple(range(9000, 9000 + QUAL_WORLDS))   # disjoint unit range inside the disjoint QUAL namespace

# ---- DEV proposal (NOT frozen; for MASTER)
DEV_PROPOSAL = {"worlds": 32, "unit": "world (anchor A + three partners R_POS/R_ZERO/R_NEG; all six conditions per pair)",  # superseded by DEV_INDEPENDENT_WORLDS below
                "status": "PROPOSED_NOT_FROZEN"}

# ==================================================================== FINAL PRE-SCIENCE SCOPE / FREEZE REPAIR (MASTER)
SCOPE = "CALIBRATION / SELECTIVE-CONTROL-OPPORTUNITY GATE"
SCOPE_STATEMENT = ("Determine whether the frozen testbed contains a clean, direction-specific and relation-specific prior-experience "
                   "effect that a later selective controller would need to distinguish. NOT a discovery that transfer exists, NOT "
                   "P-Space evidence, NOT a novelty experiment, NOT a continual-learning superiority experiment.")
CLAIM_CEILING = ("SELECTIVE_CONTROL_OPPORTUNITY_PRESENT (DEV calibration evidence that the regime qualifies for a later Q2B "
                 "selective-control test). No P-Space credit, no novelty, no equivalence, no practical-support claim.")
DEV_INDEPENDENT_WORLDS = 32
DEV_N_STATUS = "EXPLORATORY_CALIBRATION_FIXED_N"
DEV_N_NOTE = ("n=32 worlds is NOT a confirmatory powered sample size and was NOT derived from any QUAL effect magnitude. "
              "Independent replication unit = WORLD; partners/tasks/conditions inside a world are paired repeated observations.")
PRACTICAL_MARGIN = None                      # none exists; no equivalence margin exists
EQUIVALENCE_CLAIM_ALLOWED = False            # NOT SIGNIFICANT != EQUIVALENT
CONFIRM_AUTHORIZED = False
QUAL_DISCLOSURE = ("QUAL values were inspected during instrument development. Before this freeze: checkpoint spacing changed "
                   "20 -> 5 and JUMPSTART / LEARN_AULC were separated. Both happened before any science authorization, science "
                   "seed or science outcome. QUAL effect magnitudes are NOT used to define margins, success thresholds, relation "
                   "classes, estimands or n. No further estimand/generator change after this freeze.")
FROZEN_IMPLEMENTATION_MANIFEST = r"D:\pspace_lab\artifacts\f5_q2a\F5-Q2A-R1-FINALPRE-001\FREEZE\IMPLEMENTATION_MANIFEST.json"
