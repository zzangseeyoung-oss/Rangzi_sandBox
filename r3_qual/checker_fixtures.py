"""Synthetic science-shaped CHECKER-QUAL fixtures (non-science; namespace F5_Q2A_R2_CHECKER_FIXTURE_V1).

Each fixture is a complete 32-world evidence directory with the exact RAW_WORLD / HIDDEN_TRUTH / counter / summary /
failure-registry schema of the driver, all six conditions, all three relation strata. No learner is run: curves are
ENGINEERED so every frozen estimand takes a known value (no R1 value is used anywhere):
  scratch curve s(i) = (0.1 + 1.4 exp(-i/5)) * (1 + 0.05 z_world)                   (identical for the three partners)
  after-prior-task target curve: first checkpoint s(0) - J, later checkpoints s(i) - L   -> JUMPSTART = J, LEARN_AULC = L
  non-trained task during the second phase: end-of-phase-1 value + BI * i / 80           -> BI = BI
  a non-zero effect is multiplied by a world-level factor (1 + 0.1 z) shared by the three relations; a zero effect stays
  exactly zero, so equal effects give exactly-zero contrasts (NOT_DETECTED by the frozen tci rule).
Parameter digests follow the training path (S1 phase 1 == S0A, S3 prefix == S1, ...), one shared init per pair."""
import hashlib
import json
import os

import numpy as np

from f5_q2a.design import AWU_PER_EVAL_EXAMPLE, AWU_PER_TRAIN_EXAMPLE, BATCH, CKPT_EVERY, CONDITIONS, D_IN, K_LATENT, BETA, \
    N_EVAL, NOISE_VAR, T_PHASE

NS_FIXTURE = "F5_Q2A_R2_CHECKER_FIXTURE_V1"
REL = ("R_POS", "R_ZERO", "R_NEG")
N_CK = T_PHASE // CKPT_EVERY + 1
COS = float(np.cos(np.radians(30.0)))
_h = lambda *a: hashlib.sha256(":".join(map(str, a)).encode()).hexdigest()

# effect specs: {estimand: {relation: (A_TO_B, B_TO_A)}}; BI given as (B_ON_A, A_ON_B); SCRATCH_OFFSET_B makes a stratum easier
_Z = {r: (0.0, 0.0) for r in REL}
_J = {"R_POS": (1.0, 1.0), "R_ZERO": (0.0, 0.0), "R_NEG": (-1.0, -1.0)}
_L = {"R_POS": (0.05, 0.05), "R_ZERO": (0.0, 0.0), "R_NEG": (-0.05, -0.05)}
_BI = {"R_POS": (0.2, 0.2), "R_ZERO": (1.0, 1.0), "R_NEG": (2.0, 2.0)}
_BI_EQ = {r: (0.5, 0.5) for r in REL}
SPECS = {
    "Q_PRESENT_MULTIPLE": {"J": _J, "L": _L, "BI": _BI},
    "Q_PRESENT_INITIALIZATION_ONLY": {"J": _J, "L": _Z, "BI": _BI_EQ},
    "Q_PRESENT_LEARNING_ONLY": {"J": _Z, "L": _L, "BI": _BI_EQ},
    "Q_PRESENT_BI_ONLY": {"J": _Z, "L": _Z, "BI": _BI},
    "Q_NOT_DETECTED": {"J": {"R_POS": (1.0, 1.0), "R_ZERO": (0.0, 0.0), "R_NEG": (0.5, 0.5)},   # help-only: no harm class
                       "L": _Z, "BI": _BI_EQ},
    "Q_NULL_ALL_ZERO": {"J": _Z, "L": _Z, "BI": _Z},
    "Q_DIRECTION_ONLY_NOT_DETECTED": {"J": {"R_POS": (1.0, 0.0), "R_ZERO": (0.0, 0.0), "R_NEG": (-1.0, 0.0)},
                                      "L": {"R_POS": (0.05, 0.0), "R_ZERO": (0.0, 0.0), "R_NEG": (-0.05, 0.0)},
                                      "BI": {"R_POS": (0.2, 0.5), "R_ZERO": (1.0, 0.5), "R_NEG": (2.0, 0.5)}},
    "Q_DESIGN_NO_INFERENCE": {"J": _J, "L": _L, "BI": _BI, "SCRATCH_OFFSET_B": {"R_POS": 0.1, "R_ZERO": 0.0, "R_NEG": 0.0}},
    # BI contrasts detected in BOTH directions but with OPPOSITE signs -> the BI subtype must NOT qualify (frozen same-sign rule)
    "Q_BI_OPPOSITE_SIGN_NOT_DETECTED": {"J": _Z, "L": _Z, "BI": {"R_POS": (0.2, 2.0), "R_ZERO": (1.0, 1.0), "R_NEG": (2.0, 0.2)}},
}
# decision-boundary fixtures (classification NOT predeclared; only exact checker/primary agreement is required). NOISE =
# (sd of the world-level multiplicative factor, sd of an independent per-relation additive term), chosen so that many
# p-values fall near alpha/k and Holm step-down stops occur.
for _i, (_sm, _tau) in enumerate([(2.2, 0.0), (2.6, 0.0), (3.0, 0.0), (0.3, 0.9), (0.3, 1.2), (0.3, 1.6)]):
    SPECS["Q_BOUNDARY_%d" % (_i + 1)] = {"J": _J, "L": _L, "BI": _BI, "NOISE": (_sm, _tau)}


def _task_id(rng):
    while True:
        t = "t" + rng.bytes(6).hex()
        if not any(k in t for k in ("pos", "neg", "zero", "r_")):
            return t


def build_world(spec, unit, rng):
    anchor = _task_id(rng)
    pids = [_task_id(rng) for _ in REL]
    order = rng.permutation(3)
    rel_of = {pids[i]: REL[order[i]] for i in range(3)}
    i_ = np.arange(N_CK)
    base = 0.1 + 1.4 * np.exp(-i_ / 5.0)
    sA = base * (1 + 0.05 * rng.standard_normal())
    sB0 = base * (1 + 0.05 * rng.standard_normal())
    sm, tau = spec.get("NOISE", (0.1, 0.0))
    mult = {k: (1 + sm * rng.standard_normal(), 1 + sm * rng.standard_normal()) for k in ("J", "L", "BI", "OFF")}
    add = {(k, r, d): tau * abs(spec[k]["R_POS"][d] or 1.0) * rng.standard_normal() for k in ("J", "L", "BI") for r in REL for d in (0, 1)}
    eff = lambda k, r, d: (spec[k][r][d] * mult[k][d] if spec[k][r][d] != 0.0 else 0.0) + add[(k, r, d)]
    other = [1.0] * N_CK
    train_awu, eval_awu = T_PHASE * BATCH * AWU_PER_TRAIN_EXAMPLE, 2 * N_CK * N_EVAL * AWU_PER_EVAL_EXAMPLE
    pairs = {}
    for pid in pids:
        r = rel_of[pid]
        off = spec.get("SCRATCH_OFFSET_B", {}).get(r, 0.0)
        sB = sB0 - (off * mult["OFF"][0] if off else 0.0)
        after_B = [float(sB[0] - eff("J", r, 0))] + [float(x - eff("L", r, 0)) for x in sB[1:]]
        after_A = [float(sA[0] - eff("J", r, 1))] + [float(x - eff("L", r, 1)) for x in sA[1:]]
        biA = [float(sA[-1] + eff("BI", r, 0) * k / (N_CK - 1)) for k in range(N_CK)]
        biB = [float(sB[-1] + eff("BI", r, 1) * k / (N_CK - 1)) for k in range(N_CK)]
        scratch = {"A": [float(x) for x in sA], "B": [float(x) for x in sB]}

        def phase(path, curve):
            return {"curve": curve, "train_examples": T_PHASE * BATCH, "train_awu": train_awu, "eval_awu": eval_awu,
                    "end_param_digest": _h(unit, pid, "".join(path))[:16], "train_role": path[-1]}
        recs = {}
        for c, roles in CONDITIONS.items():
            phs = []
            for k in range(len(roles)):
                path = roles[:k + 1]
                if k == 0:
                    cur = {"A": scratch["A"], "B": other} if roles[0] == "A" else {"A": other, "B": scratch["B"]}
                elif k == 1:
                    cur = {"A": biA, "B": after_B} if roles[0] == "A" else {"A": after_A, "B": biB}
                else:
                    cur = {"A": scratch["A"], "B": other} if roles[2] == "A" else {"A": other, "B": scratch["B"]}
                phs.append(phase(path, cur))
            recs[c] = {"condition": c, "task_ids": {"A": anchor, "B": pid}, "init_digest": _h(unit, pid, "init")[:16], "phases": phs}
        pairs[pid] = recs
    raw = {"unit": unit, "anchor": anchor, "pairs": pairs}
    declared = {"d": D_IN, "k": K_LATENT, "beta": BETA, "noise_var": NOISE_VAR, "U_orthonormal": True, "w_norm": 1.0, "calib_target_var": 1.0}
    meas = {}
    for pid in pids:
        r = rel_of[pid]
        if r == "R_ZERO":
            meas[pid] = {"principal_cosines": sorted([float(x) for x in rng.uniform(0.05, 0.9, K_LATENT)], reverse=True),
                         "head_cosine_if_shared": None, "declared": declared}
        else:
            meas[pid] = {"principal_cosines": [1.0] * K_LATENT, "head_cosine_if_shared": COS if r == "R_POS" else -COS, "declared": declared}
    hidden = {"anchor": anchor, "relations": rel_of, "measured": meas}
    return raw, hidden


def build(spec_name, run_dir, units, seed, mode="fixture", authorization_id=None):
    """Writes an unfrozen fixture run directory (exclusive create). Freezing is done by the caller with the frozen freezer.
    mode 'fixture_science' writes a science-shaped counter carrying a MOCK authorization id (fixture namespace only)."""
    assert mode in ("fixture", "fixture_science")
    spec = SPECS[spec_name]
    rng = np.random.default_rng(seed)
    os.makedirs(run_dir, exist_ok=False)
    units = list(units)
    json.dump({"mode": mode, "namespace": NS_FIXTURE, "units": units, "authorization_id": authorization_id, "fixture": spec_name},
              open(os.path.join(run_dir, "EXECUTION_COUNTER.json"), "x"), indent=1)
    for u in units:
        raw, hidden = build_world(spec, u, rng)
        json.dump(raw, open(os.path.join(run_dir, "RAW_WORLD_%04d.json" % u), "x"), separators=(",", ":"))
        json.dump(hidden, open(os.path.join(run_dir, "HIDDEN_TRUTH_%04d.json" % u), "x"), indent=1)
    json.dump({"failures": []}, open(os.path.join(run_dir, "FAILURE_REGISTRY.json"), "x"), indent=1)
    json.dump({"mode": mode, "namespace": NS_FIXTURE, "units_done": units, "units_expected": units, "failures": 0},
              open(os.path.join(run_dir, "RUN_SUMMARY.json"), "x"), indent=1)
    return run_dir
