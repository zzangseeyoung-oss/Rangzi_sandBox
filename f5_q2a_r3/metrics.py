"""Per-world metric extraction from raw curves. Pure functions; no statistics across worlds here.

Acquisition metrics of a task X in a phase (target curve = X's eval NMSE over the phase's checkpoints):
  AULC       mean NMSE over the T_PHASE/CKPT_EVERY+1 checkpoints (uncensored, primary)
  STEPS      steps to criterion (first checkpoint with NMSE <= CRITERION_NMSE); None if not reached (censored)
  EXAMPLES   STEPS * BATCH
  FINAL      NMSE at the end of the phase (final target quality guardrail)
  WORK_PHASE accounted training work spent in the phase until criterion (or the whole phase if censored)
Fully charged work to criterion additionally includes every earlier phase of the condition.

Estimands (per world, per pair; sign convention: positive = the prior experience HELPED / nothing was lost):
  FT_A_TO_B = AULC_B(S0B)  - AULC_B(S1 phase 2)
  FT_B_TO_A = AULC_A(S0A)  - AULC_A(S2 phase 2)
  BI_B_ON_A = NMSE_A(S1 end of phase 2) - NMSE_A(S1 end of phase 1)      (positive = backward interference/forgetting)
  BI_A_ON_B = NMSE_B(S2 end of phase 2) - NMSE_B(S2 end of phase 1)
  Decomposition (secondary, reported beside the primary AULC so zero-shot offset is not conflated with learning speed):
  JUMPSTART_A_TO_B = NMSE_B(S0B step 0) - NMSE_B(S1 phase 2 step 0)   (positive = the prior task gave a better start)
  LEARN_AULC_A_TO_B = mean over checkpoints 1..end (step 0 excluded) of the same difference; FINAL = end-of-phase difference
  (S3/S4 phases 1-2 are bitwise-identical to S1/S2 phases 1-2 by construction: a determinism check. S3/S4 phase 3
   gives relearning after interference: SAVINGS_A = AULC_A(S0A) - AULC_A(S3 phase 3), SAVINGS_B analogous.)
"""
from .design import AWU_PER_TRAIN_EXAMPLE, BATCH, CKPT_EVERY, CRITERION_NMSE, T_PHASE


def aulc(c):
    return sum(c) / len(c)


def steps_to_criterion(c):
    for i, v in enumerate(c):
        if v <= CRITERION_NMSE:
            return i * CKPT_EVERY
    return None


def acquisition(phase, role):
    c = phase["curve"][role]
    st = steps_to_criterion(c)
    return {"AULC": aulc(c), "STEPS": st, "CENSORED": st is None, "EXAMPLES": None if st is None else st * BATCH,
            "FINAL": c[-1], "WORK_PHASE": (T_PHASE if st is None else st) * BATCH * AWU_PER_TRAIN_EXAMPLE}


def fully_charged_work(cond_rec, phase_index, role):
    prior = sum(p["train_awu"] for p in cond_rec["phases"][:phase_index])
    return prior + acquisition(cond_rec["phases"][phase_index], role)["WORK_PHASE"]


def pair_estimands(pair):
    """pair: {condition: record}. Returns the per-world estimands or None if any condition failed (fail-closed)."""
    if any("failure" in r for r in pair.values()):
        return None
    S0A, S0B, S1, S2, S3, S4 = (pair[k] for k in ("S0A", "S0B", "S1", "S2", "S3", "S4"))
    aA0, aB0 = acquisition(S0A["phases"][0], "A"), acquisition(S0B["phases"][0], "B")
    aB1, aA2 = acquisition(S1["phases"][1], "B"), acquisition(S2["phases"][1], "A")
    aA3, aB4 = acquisition(S3["phases"][2], "A"), acquisition(S4["phases"][2], "B")
    e = {
        "FT_A_TO_B": aB0["AULC"] - aB1["AULC"], "FT_B_TO_A": aA0["AULC"] - aA2["AULC"],
        "FT_A_TO_B_FINAL": aB0["FINAL"] - aB1["FINAL"], "FT_B_TO_A_FINAL": aA0["FINAL"] - aA2["FINAL"],
        "BI_B_ON_A": S1["phases"][1]["curve"]["A"][-1] - S1["phases"][0]["curve"]["A"][-1],
        "BI_A_ON_B": S2["phases"][1]["curve"]["B"][-1] - S2["phases"][0]["curve"]["B"][-1],
        "SAVINGS_A": aA0["AULC"] - aA3["AULC"], "SAVINGS_B": aB0["AULC"] - aB4["AULC"],
        "JUMPSTART_A_TO_B": S0B["phases"][0]["curve"]["B"][0] - S1["phases"][1]["curve"]["B"][0],
        "JUMPSTART_B_TO_A": S0A["phases"][0]["curve"]["A"][0] - S2["phases"][1]["curve"]["A"][0],
        "LEARN_AULC_A_TO_B": aulc(S0B["phases"][0]["curve"]["B"][1:]) - aulc(S1["phases"][1]["curve"]["B"][1:]),
        "LEARN_AULC_B_TO_A": aulc(S0A["phases"][0]["curve"]["A"][1:]) - aulc(S2["phases"][1]["curve"]["A"][1:]),
        "STEPS": {"B_scratch": aB0["STEPS"], "B_after_A": aB1["STEPS"], "A_scratch": aA0["STEPS"], "A_after_B": aA2["STEPS"]},
        "WORK_TO_CRITERION": {"B_scratch": aB0["WORK_PHASE"], "B_after_A_phase_local": aB1["WORK_PHASE"],
                              "B_after_A_fully_charged": fully_charged_work(S1, 1, "B"),
                              "A_scratch": aA0["WORK_PHASE"], "A_after_B_phase_local": aA2["WORK_PHASE"],
                              "A_after_B_fully_charged": fully_charged_work(S2, 1, "A")},
        "FINAL_QUALITY": {"A_scratch": aA0["FINAL"], "B_scratch": aB0["FINAL"], "B_after_A": aB1["FINAL"], "A_after_B": aA2["FINAL"],
                          "A_end_S3": S3["phases"][2]["curve"]["A"][-1], "B_end_S3": S3["phases"][2]["curve"]["B"][-1],
                          "A_end_S4": S4["phases"][2]["curve"]["A"][-1], "B_end_S4": S4["phases"][2]["curve"]["B"][-1]},
        "SCRATCH_AULC": {"A": aA0["AULC"], "B": aB0["AULC"]},
        "DETERMINISM": {"S3_prefix_equals_S1": [p["end_param_digest"] for p in S3["phases"][:2]] == [p["end_param_digest"] for p in S1["phases"]],
                        "S4_prefix_equals_S2": [p["end_param_digest"] for p in S4["phases"][:2]] == [p["end_param_digest"] for p in S2["phases"]],
                        "S1_phase1_equals_S0A": S1["phases"][0]["end_param_digest"] == S0A["phases"][0]["end_param_digest"],
                        "S2_phase1_equals_S0B": S2["phases"][0]["end_param_digest"] == S0B["phases"][0]["end_param_digest"],
                        "same_init": len({r["init_digest"] for r in pair.values()}) == 1},
    }
    return e
