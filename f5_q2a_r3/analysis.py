"""F5-Q2A-R1 analysis (FINAL pre-science freeze). Consumes ONLY a frozen run directory (verifies SHA256SUMS first).

SCOPE: CALIBRATION / SELECTIVE-CONTROL-OPPORTUNITY GATE (design.SCOPE). No P-Space credit, no novelty, no equivalence.
Unit = WORLD (anchor + R_POS/R_ZERO/R_NEG partners; all six conditions paired within the world); n = number of worlds.
Across worlds: t 95% CI (df = n-1); Holm within each family. Detection-only: PRACTICAL_MARGIN = None.
NOT SIGNIFICANT != EQUIVALENT: a non-detection is labelled NO_DETECTED_* and never read as neutrality or retention.

Frozen estimands (sign: positive = the prior task HELPED the target / relation contrast favours the first class)
  INITIALIZATION  JUMPSTART_A_TO_B, JUMPSTART_B_TO_A        (target NMSE at phase start: scratch - after prior task)
  LEARNING        LEARN_AULC_A_TO_B, LEARN_AULC_B_TO_A      (AULC over checkpoints 1..end: scratch - after prior task)
  TOTAL           AULC_A_TO_B, AULC_B_TO_A                  (AULC incl. step 0; = metrics FT_*; reported, not a subtype)
  ABSOLUTE_BI     BI_B_ON_A, BI_A_ON_B                      DESCRIPTIVE ONLY (a rise after a task switch; NOT a generic
                                                            forgetting mechanism: no continuation arm exists)
  PRIMARY BI      dBI = BI_r - BI_r' for (R_POS,R_ZERO), (R_NEG,R_ZERO), (R_POS,R_NEG), both directions (paired in world)

Frozen absolute labels per stratum (both directions required for a named label)
  JUMPSTART : INITIALIZATION_BENEFIT | INITIALIZATION_INTERFERENCE | NO_DETECTED_TRANSFER | DIRECTION_ASYMMETRIC
  LEARN_AULC: LEARNING_BENEFIT | LEARNING_INTERFERENCE | NO_DETECTED_TRANSFER | DIRECTION_ASYMMETRIC
  AULC      : POSITIVE_TRANSFER | NEGATIVE_TRANSFER | NO_DETECTED_TRANSFER | DIRECTION_ASYMMETRIC
  ABS BI    : ABSOLUTE_BI_RISE_DETECTED | ABSOLUTE_BI_RISE_NOT_DETECTED | ABSOLUTE_BI_ASYMMETRIC   (descriptive)

Frozen SELECTIVE-CONTROL-OPPORTUNITY rule (pre-result; see selective_control_opportunity)
  A  integrity/difficulty/resource gates pass (else DESIGN_NO_INFERENCE)
  C  the gates include marginal difficulty balance, equal exposure, identical evaluator schedule, no task-ID relation
     tokens, hidden-truth verification, determinism and zero failures
  per subtype S in {INITIALIZATION (JUMPSTART), LEARNING (LEARN_AULC), BACKWARD_INTERFERENCE (dBI)}; S qualifies iff in
  BOTH directions:
     B  at least one paired relation contrast of S is detected (Holm within the direction's 3-contrast family), and
     D  (INITIALIZATION / LEARNING) the absolute estimand is detected POSITIVE in one relation class and detected
        NEGATIVE in another: prior experience helps in one class and harms in another, so neither "always use" nor
        "never use" prior experience is harmless -> a control problem exists;
        (BACKWARD_INTERFERENCE) the same relation contrast is detected in both directions with the same sign: protection
        from interference would need to depend on the relation -> a control problem exists.
  OVERALL = DESIGN_NO_INFERENCE (A/C fail) | SELECTIVE_CONTROL_OPPORTUNITY_PRESENT (>=1 subtype; SUBTYPE = that subtype or
            MULTIPLE) | SELECTIVE_CONTROL_OPPORTUNITY_NOT_DETECTED.
  COARSE_RELEVANCE_CHALLENGE (descriptive flag per subtype): the R_POS vs R_NEG contrast is detected in both directions.
  R_POS and R_NEG share the latent subspace, so coarse shared-subspace relevance cannot separate them. The readout
  alignment is ORACLE truth; Q2A does not define what Q2B may observe and does not show a bounded controller can infer it.
"""
import glob
import hashlib
import json
import math
import os
import sys

from scipy import stats

sys.path.insert(0, r"D:\pspace_lab")
from f5_q2a import design  # noqa: E402
from f5_q2a.metrics import pair_estimands  # noqa: E402

REL = ("R_POS", "R_ZERO", "R_NEG")
CONTRASTS = (("R_POS", "R_ZERO"), ("R_NEG", "R_ZERO"), ("R_POS", "R_NEG"))
DIRS = {"INITIALIZATION": ("JUMPSTART_A_TO_B", "JUMPSTART_B_TO_A"), "LEARNING": ("LEARN_AULC_A_TO_B", "LEARN_AULC_B_TO_A"),
        "TOTAL": ("FT_A_TO_B", "FT_B_TO_A"), "BACKWARD_INTERFERENCE": ("BI_B_ON_A", "BI_A_ON_B")}
TOTAL_NAME = {"FT_A_TO_B": "AULC_A_TO_B", "FT_B_TO_A": "AULC_B_TO_A"}
LABELS = {"INITIALIZATION": ("INITIALIZATION_BENEFIT", "INITIALIZATION_INTERFERENCE"), "LEARNING": ("LEARNING_BENEFIT", "LEARNING_INTERFERENCE"),
          "TOTAL": ("POSITIVE_TRANSFER", "NEGATIVE_TRANSFER"), "BACKWARD_INTERFERENCE": ("ABSOLUTE_BI_RISE_DETECTED", None)}
fh = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def tci(v):
    n = len(v)
    m = sum(v) / n
    if n < 2:
        return {"n": n, "mean": m, "ci95": [float("nan")] * 2, "p": float("nan")}
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
    se = sd / math.sqrt(n)
    q = float(stats.t.ppf(0.975, n - 1))
    p = float(2 * stats.t.sf(abs(m) / se, n - 1)) if se > 0 else (0.0 if m != 0 else 1.0)
    return {"n": n, "mean": m, "ci95": [m - q * se, m + q * se], "p": p}


def holm(cells):
    keys = sorted(cells, key=lambda k: (math.isnan(cells[k]["p"]), cells[k]["p"]))
    stop = False
    for i, k in enumerate(keys):
        c = cells[k]
        ok = (not stop) and not math.isnan(c["p"]) and c["p"] <= 0.05 / (len(keys) - i)
        stop = stop or not ok
        c["holm"] = ok
        c["class"] = "POSITIVE" if ok and c["ci95"][0] > 0 else "NEGATIVE" if ok and c["ci95"][1] < 0 else "NOT_DETECTED"
    return cells


def stratum_label(subtype, c1, c2):
    pos, neg = LABELS[subtype]
    if subtype == "BACKWARD_INTERFERENCE":
        if c1 == c2 == "POSITIVE":
            return "ABSOLUTE_BI_RISE_DETECTED"
        return "ABSOLUTE_BI_RISE_NOT_DETECTED" if "POSITIVE" not in (c1, c2) else "ABSOLUTE_BI_ASYMMETRIC"
    if c1 == c2 == "POSITIVE":
        return pos
    if c1 == c2 == "NEGATIVE":
        return neg
    return "NO_DETECTED_TRANSFER" if c1 == c2 == "NOT_DETECTED" else "DIRECTION_ASYMMETRIC"


def selective_control_opportunity(gates_ok, abs_classes, contrast_classes):
    """Pure frozen rule.
    abs_classes[subtype][direction][stratum]        in {POSITIVE, NEGATIVE, NOT_DETECTED}
    contrast_classes[subtype][direction][contrast]  in {POSITIVE, NEGATIVE, NOT_DETECTED}; contrast keys 'R_POS-R_ZERO', ...
    Returns (overall, subtype_label, per_subtype_detail)."""
    if not gates_ok:
        return "DESIGN_NO_INFERENCE", None, {}
    detail = {}
    for s in ("INITIALIZATION", "LEARNING", "BACKWARD_INTERFERENCE"):
        dirs = list(contrast_classes[s])
        per = {}
        for d in dirs:
            cc = contrast_classes[s][d]
            B = any(v != "NOT_DETECTED" for v in cc.values())
            if s == "BACKWARD_INTERFERENCE":
                D = None                         # evaluated across directions below
            else:
                ac = abs_classes[s][d].values()
                D = "POSITIVE" in ac and "NEGATIVE" in ac
            per[d] = {"B_relation_contrast_detected": B, "D_help_and_harm_across_classes": D}
        if s == "BACKWARD_INTERFERENCE":
            d1, d2 = dirs
            same = [k for k in contrast_classes[s][d1]
                    if contrast_classes[s][d1][k] != "NOT_DETECTED" and contrast_classes[s][d1][k] == contrast_classes[s][d2][k]]
            qualifies = all(per[d]["B_relation_contrast_detected"] for d in dirs) and bool(same)
            per["D_same_sign_relation_contrast_both_directions"] = same
        else:
            qualifies = all(per[d]["B_relation_contrast_detected"] and per[d]["D_help_and_harm_across_classes"] for d in dirs)
        coarse = all(contrast_classes[s][d].get("R_POS-R_NEG", "NOT_DETECTED") != "NOT_DETECTED" for d in dirs)
        detail[s] = {"qualifies": qualifies, "per_direction": per, "COARSE_RELEVANCE_CHALLENGE_R_POS_vs_R_NEG_detected_both_directions": coarse}
    q = [s for s, v in detail.items() if v["qualifies"]]
    if not q:
        return "SELECTIVE_CONTROL_OPPORTUNITY_NOT_DETECTED", None, detail
    return "SELECTIVE_CONTROL_OPPORTUNITY_PRESENT", (q[0] if len(q) == 1 else "MULTIPLE"), detail


def main(run_dir):
    sums = [l.rstrip("\n").split("  ", 1) for l in open(os.path.join(run_dir, "SHA256SUMS")) if l.strip()]
    if not all(fh(os.path.join(run_dir, f)) == h for h, f in sums):
        raise RuntimeError("frozen evidence changed or not frozen")
    worlds, truths = {}, {}
    for p in sorted(glob.glob(os.path.join(run_dir, "RAW_WORLD_*.json"))):
        u = int(os.path.basename(p)[10:14])
        worlds[u] = json.load(open(p))
        truths[u] = json.load(open(os.path.join(run_dir, "HIDDEN_TRUTH_%04d.json" % u)))
    fails = json.load(open(os.path.join(run_dir, "FAILURE_REGISTRY.json")))["failures"]
    res = {"scope": design.SCOPE, "claim_ceiling": design.CLAIM_CEILING, "worlds": len(worlds), "failures": len(fails),
           "practical_margin": design.PRACTICAL_MARGIN, "equivalence_claim_allowed": design.EQUIVALENCE_CLAIM_ALLOWED}
    est, det_ok, truth_ok, expo_ok, eval_ok, id_ok = {r: [] for r in REL}, True, True, True, True, True
    n_ck = design.T_PHASE // design.CKPT_EVERY + 1
    for u, w in worlds.items():
        rel = truths[u]["relations"]
        by_r = {}
        for pid, pair in w["pairs"].items():
            id_ok &= not any(t in pid.lower() for t in ("pos", "neg", "zero", "r_"))
            e = pair_estimands(pair)
            if e is None:
                det_ok = False
                continue
            det_ok &= all(e["DETERMINISM"].values())
            ex = {c: sum(p["train_examples"] for p in r["phases"]) for c, r in pair.items()}
            expo_ok &= ex["S1"] == ex["S2"] == 2 * ex["S0A"] == 2 * ex["S0B"] and ex["S3"] == ex["S4"] == 3 * ex["S0A"]
            eval_ok &= all(len(p["curve"][k]) == n_ck for r in pair.values() for p in r["phases"] for k in ("A", "B"))
            m = truths[u]["measured"][pid]
            shared = all(abs(c - 1) < 1e-9 for c in m["principal_cosines"])
            truth_ok &= {"R_POS": shared and m["head_cosine_if_shared"] > 0.8, "R_NEG": shared and m["head_cosine_if_shared"] < -0.8,
                         "R_ZERO": not shared}[rel[pid]]
            by_r[rel[pid]] = e
        if set(by_r) == set(REL):
            for r in REL:
                est[r].append(by_r)
    n = min(len(v) for v in est.values())
    diff = holm({"%s-%s|SCRATCH_AULC_B" % (a, b): tci([x[a]["SCRATCH_AULC"]["B"] - x[b]["SCRATCH_AULC"]["B"] for x in est["R_ZERO"]])
                 for a, b in CONTRASTS})
    gates = {"zero_failures": not fails, "determinism_and_pairing": det_ok, "hidden_truth_verified": truth_ok,
             "equal_exposure": expo_ok, "identical_evaluator_schedule": eval_ok, "no_task_id_relation_tokens": id_ok,
             "marginal_difficulty_balance_not_detected": all(c["class"] == "NOT_DETECTED" for c in diff.values()),
             "all_worlds_complete": n == len(worlds) and n >= 2}
    res["gates"], res["difficulty_balance"] = gates, diff
    absolute, contrasts, labels = {}, {}, {}
    for s, keys in DIRS.items():
        absolute[s], contrasts[s] = {}, {}
        for k in keys:
            name = TOTAL_NAME.get(k, k)
            absolute[s][name] = holm({r: tci([x[r][k] for x in est["R_ZERO"]]) for r in REL})
            contrasts[s][name] = holm({"%s-%s" % (a, b): tci([x[a][k] - x[b][k] for x in est["R_ZERO"]]) for a, b in CONTRASTS})
        d1, d2 = [TOTAL_NAME.get(k, k) for k in keys]
        labels[s] = {r: stratum_label(s, absolute[s][d1][r]["class"], absolute[s][d2][r]["class"]) for r in REL}
    res["absolute_estimands"], res["relation_contrasts_primary"], res["stratum_labels"] = absolute, contrasts, labels
    res["absolute_BI_scope"] = "DESCRIPTIVE_ONLY: a rise after a task switch; not a generic forgetting mechanism (no continuation arm)"
    abs_cls = {s: {d: {r: c["class"] for r, c in v.items()} for d, v in absolute[s].items()} for s in absolute}
    con_cls = {s: {d: {k: c["class"] for k, c in v.items()} for d, v in contrasts[s].items()} for s in contrasts}
    overall, subtype, detail = selective_control_opportunity(all(gates.values()), abs_cls, con_cls)
    res["SELECTIVE_CONTROL_OPPORTUNITY"], res["OPPORTUNITY_SUBTYPE"], res["opportunity_detail"] = overall, subtype, detail
    res["interpretation_boundary"] = ("A difference between R_POS and R_NEG does not establish novelty; it only qualifies the regime for a "
                                      "later Q2B selective-control test. Readout alignment is oracle truth. No P-Space credit.")
    res["resources"] = {r: {"work_to_criterion_B_scratch_mean": sum(x[r]["WORK_TO_CRITERION"]["B_scratch"] for x in est["R_ZERO"]) / max(1, n),
                            "work_to_criterion_B_after_A_phase_local_mean": sum(x[r]["WORK_TO_CRITERION"]["B_after_A_phase_local"] for x in est["R_ZERO"]) / max(1, n),
                            "work_to_criterion_B_after_A_fully_charged_mean": sum(x[r]["WORK_TO_CRITERION"]["B_after_A_fully_charged"] for x in est["R_ZERO"]) / max(1, n),
                            "censored_B_after_A": sum(x[r]["STEPS"]["B_after_A"] is None for x in est["R_ZERO"])} for r in REL}
    os.makedirs(os.path.join(run_dir, "analysis"), exist_ok=True)
    json.dump(res, open(os.path.join(run_dir, "analysis", "ANALYSIS.json"), "x"), indent=1)
    return res


if __name__ == "__main__":
    r = main(sys.argv[1])
    print(json.dumps({"SELECTIVE_CONTROL_OPPORTUNITY": r["SELECTIVE_CONTROL_OPPORTUNITY"], "subtype": r["OPPORTUNITY_SUBTYPE"],
                      "gates": r["gates"], "labels": r["stratum_labels"]}, indent=1))
