"""F5-Q2A-R3 adjudication (third fresh runner; comparison only, no recomputation, no science code).

  python -I -B -S r3_verifier/adjudicate.py --root <checkout> --primary DIR --expected-primary-sha HEX --verifier DIR
        --expected-verifier-sha HEX --out DIR

R-1 (ratified): verifier FAIL_CLOSED, a missing/invalid input, or any material disagreement with the primary analysis =>
FINAL_STATE = DESIGN_NO_INFERENCE. Material = state, subtype, any gate, label, qualification flag, the key SET at every level
(symmetric), any Holm decision/class/n, any CI length, or a mean/p/CI bound outside the predeclared relative tolerance 1e-9.
Every outcome, including an unexpected error, writes ADJUDICATION.json. No repair, no rerun."""
import argparse
import json
import math
import os
import sys

TOL = 1e-9


def close(a, b):
    if not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return False
    if isinstance(a, float) and isinstance(b, float) and (math.isnan(a) or math.isnan(b)):
        return math.isnan(a) and math.isnan(b)
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def compare(p, v):
    d = []
    for pk, vk in (("SELECTIVE_CONTROL_OPPORTUNITY", "state"), ("OPPORTUNITY_SUBTYPE", "subtype"), ("gates", "gates"), ("stratum_labels", "labels")):
        if pk not in p or vk not in v or p[pk] != v[vk]:
            d.append(vk)
    cells = 0

    def cc(tag, P, V):
        nonlocal cells
        if not isinstance(P, dict) or not isinstance(V, dict) or set(P) != set(V) or not P:
            d.append(tag + ":keys")
            return
        for k in P:
            cells += 1
            x, y = P[k], V[k]
            fields = ("class", "holm", "n", "mean", "p", "ci95")
            if any(f not in x or f not in y for f in fields) or len(x["ci95"]) != 2 or len(y["ci95"]) != 2:
                d.append(tag + ":" + k + ":schema")
                continue
            if x["class"] != y["class"] or x["holm"] != y["holm"] or x["n"] != y["n"] or not close(x["mean"], y["mean"]) or \
                    not close(x["p"], y["p"]) or not all(close(s, t) for s, t in zip(x["ci95"], y["ci95"])):
                d.append(tag + ":" + k)

    def lvl(tag, P, V):
        if not isinstance(P, dict) or not isinstance(V, dict) or set(P) != set(V) or not P:
            d.append(tag + ":keys")
            return None
        return P
    cc("difficulty", p.get("difficulty_balance"), v.get("difficulty_balance"))
    for name_p, name_v in (("absolute_estimands", "absolute"), ("relation_contrasts_primary", "contrasts")):
        P = lvl(name_v, p.get(name_p), v.get(name_v))
        for s in (P or {}):
            E = lvl("%s:%s" % (name_v, s), p[name_p][s], v[name_v][s])
            for e in (E or {}):
                cc("%s:%s:%s" % (name_v, s, e), p[name_p][s][e], v[name_v][s][e])
    po, vo = p.get("opportunity_detail") or {}, v.get("opportunity_detail") or {}
    if p.get("SELECTIVE_CONTROL_OPPORTUNITY") != "DESIGN_NO_INFERENCE":
        if set(po) != {"INITIALIZATION", "LEARNING", "BACKWARD_INTERFERENCE"} or set(vo) != set(po):
            d.append("opportunity_detail:keys")
        else:
            for s in po:
                if po[s].get("qualifies") != vo[s].get("qualifies"):
                    d.append("qualifies:" + s)
    if cells != 51:
        d.append("cells_compared=%d (expected 51)" % cells)
    return d, cells


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--root", "--primary", "--expected-primary-sha", "--verifier", "--expected-verifier-sha", "--out"):
        ap.add_argument(k, required=True)
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.realpath(a.root))
    os.makedirs(a.out, exist_ok=False)
    out = {"schema": "F5-Q2A-R3/ADJUDICATION/1", "rule": "R-1", "tolerance_relative": TOL}
    try:
        from r3_stage import common as C
        C.verify_manifest(a.primary, "PRIMARY_MANIFEST.json", a.expected_primary_sha, C.SCHEMA + "/PRIMARY/1")
        C.verify_manifest(a.verifier, "VERIFIER_MANIFEST.json", a.expected_verifier_sha, C.SCHEMA + "/VERIFIER/1")
        p = C.read_json(os.path.join(a.primary, "PRIMARY_ANALYSIS.json"))
        v = C.read_json(os.path.join(a.verifier, "VERIFIER_RESULT.json"))
        out["evidence"] = {"mode": v.get("mode"), "namespace_check": (v.get("checks") or {}).get("authorization"),
                           "evidence_manifest_sha256": v.get("evidence_manifest_sha256"), "science": v.get("mode") == "authorized" and
                           not ((v.get("checks") or {}).get("authorization") or {}).get("mock", True)}
        if v.get("verifier_status") != "OK":
            out.update(final_state="DESIGN_NO_INFERENCE", final_subtype=None, reason="verifier FAIL_CLOSED: %s" % v.get("fail_closed_reasons"))
        else:
            diffs, cells = compare(p, v)
            out.update(differences=diffs[:20], cells_compared=cells)
            if diffs:
                out.update(final_state="DESIGN_NO_INFERENCE", final_subtype=None, reason="material primary/verifier disagreement")
            else:
                out.update(final_state=v["state"], final_subtype=v["subtype"], reason="primary and independent verifier agree")
    except Exception as e:  # missing/invalid inputs or any unexpected error: fail closed WITH a record
        out.update(final_state="DESIGN_NO_INFERENCE", final_subtype=None, reason="adjudication input refused: %s: %s" % (type(e).__name__, str(e)[:300]))
    json.dump(out, open(os.path.join(a.out, "ADJUDICATION.json"), "x", encoding="utf-8"), indent=1)
    print(json.dumps({k: out.get(k) for k in ("final_state", "final_subtype", "reason")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
