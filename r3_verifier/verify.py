"""F5-Q2A-R3 STAGE B: independent verifier on a FRESH external runner.

  python -I -B r3_verifier/verify.py --root <verifier checkout> --source-sha HEX --handoff <EVIDENCE artifact dir>
        --expected-handoff-sha HEX --expected-evidence-sha HEX --out DIR (--external | --local-sim)

Receives ONLY the Stage A EVIDENCE artifact (never the PRIMARY artifact), the verifier's own sparse checkout of the source
snapshot (verifier code, stage common checks, the frozen design constants, runtime pin and lock) and the two expected hashes
recorded by the provider as Stage A job outputs. The science code (f5_q2a_r3, r3_stage science files) is NOT checked out in
Stage B, so the verifier cannot invoke the driver, materialize a seed or regenerate data (architectural non-availability, not
just a policy). Independent recomputation = the verbatim frozen checker core (verify_core.py).
Fails closed on any mismatch; no partial acceptance."""
import argparse
import base64
import json
import os
import sys

VERIFIER_MUST_ABSENT_ROLES = ("science_code", "science_stage", "qual_fixture")   # the pruned verifier checkout must NOT contain these
VERIFIER_MAY_ABSENT_ROLES = ("docs", "tooling")
NS_BY_MODE = {"qual": "F5_Q2A_R3_QUAL_V1", "fixture": "F5_Q2A_R2_CHECKER_FIXTURE_V1"}
NS_AUTHMOCK, NS_SCIENCE = "F5_Q2A_R3_AUTHMOCK_V1", "F5_Q2A_R3_DEV_V1"


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--root", "--source-sha", "--handoff", "--expected-handoff-sha", "--expected-evidence-sha", "--out"):
        ap.add_argument(k, required=True)
    ap.add_argument("--stage-a-run-id")
    ap.add_argument("--provider-record")
    ap.add_argument("--qual-same-run", action="store_true",
                    help="QUAL ONLY: Stage A legs are jobs of the same QUAL workflow run (no provider record); refused for science evidence")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--external", action="store_true")
    g.add_argument("--local-sim", action="store_true")
    a = ap.parse_args(argv)
    root = os.path.realpath(a.root)
    sys.path.insert(0, root)
    from r3_stage import common as C
    from r3_verifier import verify_core as V
    os.makedirs(a.out, exist_ok=False)
    res = {"schema": C.SCHEMA + "/VERIFIER_RESULT/1", "authoritative_environment": bool(a.external),
           "local_simulation_not_authoritative": bool(a.local_sim), "checks": {}}

    def finish(status, reasons, code):
        res["verifier_status"] = status
        res["fail_closed_reasons"] = reasons
        if status != "OK":
            res.update(state=None, subtype=None)
        with open(os.path.join(a.out, "VERIFIER_RESULT.json"), "x", encoding="utf-8") as f:
            json.dump(res, f, indent=1, default=str)
        sha = C.write_manifest(a.out, "VERIFIER_MANIFEST.json", C.SCHEMA + "/VERIFIER/1")
        if a.external and os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write("verifier_sha=%s\n" % sha)
        print(json.dumps({"verifier": status, "state": res.get("state"), "subtype": res.get("subtype"), "reasons": reasons,
                          "verifier_manifest_sha256": sha}))
        return code

    try:
        # own source (sparse) + science code must be ABSENT from this runtime
        res["checks"]["source"] = C.verify_source(root, "R3_SOURCE_MANIFEST.json", a.source_sha, allow_absent_roles=VERIFIER_MAY_ABSENT_ROLES,
                                                  must_absent_roles=VERIFIER_MUST_ABSENT_ROLES,
                                                  ignore_dirs=(os.path.relpath(os.path.realpath(a.out), root),)
                                                  if os.path.realpath(a.out).startswith(root + os.sep) else ())
        import importlib.util
        present = [m for m in ("f5_q2a_r3", "f5_q2a_r2", "r3_qual") if importlib.util.find_spec(m) is not None] + \
            [p for p in ("r3_stage/stage_a.py", "r3_stage/science_run.py") if os.path.exists(os.path.join(root, p))]
        if present:
            raise C.StageRefused("science code present in the verifier runtime: %r" % present)
        res["checks"]["science_code_available_to_verifier"] = False
        pin = C.read_json(os.path.join(root, C.RUNTIME_PIN_FILE))
        cap = C.capture_runtime()
        if a.external:
            C.verify_runtime(cap, pin, root)
        dep = C.verify_dependencies(os.path.join(root, C.LOCK_FILE), strict=bool(a.external))
        res["runtime"] = {"captured": cap, "enforced": bool(a.external)}
        res["dependencies"] = {"lock_sha256": dep["lock_sha256"], "problems": dep["problems"][:5], "enforced": bool(a.external)}
        # handoff: MASTER-verified expected hash first (attested subject digest), then every file
        hm = C.verify_manifest(a.handoff, "HANDOFF_MANIFEST.json", a.expected_handoff_sha, C.SCHEMA + "/HANDOFF/1")
        if any(f.startswith(("PRIMARY", "analysis/")) or "/analysis/" in f for f in hm["files"]):
            raise C.StageRefused("primary analysis output inside the evidence handoff")
        req = ("AUTHORIZATION_PROVENANCE.json", "SOURCE_MANIFEST.json", "RUNTIME_MANIFEST.json", "DEPENDENCY_MANIFEST.json",
               "SEED_MANIFEST.json", "FAILURES.json", "RUN_COUNT.json", "EVIDENCE_MANIFEST.json")
        miss = [f for f in req if f not in hm["files"]]
        if miss:
            raise C.StageRefused("handoff schema: missing %r" % miss)
        if C.sha_file(os.path.join(a.handoff, "SOURCE_MANIFEST.json")) != a.source_sha:
            raise C.StageRefused("Stage A ran a different source snapshot")
        emf = C.read_json(os.path.join(a.handoff, "EVIDENCE_MANIFEST.json"))
        if emf.get("evidence_manifest_sha256") != a.expected_evidence_sha:
            raise C.StageRefused("evidence manifest hash differs from the MASTER-receipted value")
        raw = os.path.join(a.handoff, emf.get("raw_evidence_dir", "RAW_EVIDENCE"))
        if os.path.lexists(os.path.join(raw, "analysis")):
            raise C.StageRefused("analysis output inside the raw evidence")
        ctr = V._load_json(os.path.join(raw, "EXECUTION_COUNTER.json"))
        mode = ctr.get("mode")
        # authorization provenance (authorized mode) - re-verified independently from the exact bytes Stage A consumed
        prov = C.read_json(os.path.join(a.handoff, "AUTHORIZATION_PROVENANCE.json"))
        if mode == "authorized":
            b = base64.b64decode(prov["authorization_bytes_b64"])
            bindings = {"source_manifest_sha256": a.source_sha, "runtime_image_digest": pin["container_image"],
                        "dependency_lock_sha256": dep["lock_sha256"],
                        "science_workflow_sha256": C.sha_file(os.path.join(root, C.SCIENCE_WORKFLOW)),
                        "verifier_workflow_sha256": C.sha_file(os.path.join(root, C.VERIFIER_WORKFLOW))}
            auth, mock = C.verify_authorization(b, prov["authorization_sha256"], prov["authorization_id"], bindings, allow_mock=True)
            expected_ns = NS_AUTHMOCK if mock else NS_SCIENCE
            if auth["namespace"] != expected_ns or auth["units"] != ctr.get("units") or auth["authorization_id"] != ctr.get("authorization_id"):
                raise C.StageRefused("evidence not bound to the authorization (namespace/units/id)")
            V.MODE_NAMESPACE["authorized"] = expected_ns
            res["checks"]["authorization"] = {"authorization_id": auth["authorization_id"], "mock": mock, "namespace": expected_ns,
                                              "snapshot_commit_sha": auth["snapshot_commit_sha"], "snapshot_tree_sha1": auth["snapshot_tree_sha1"]}
            rc_rec = C.read_json(os.path.join(a.handoff, "RUN_COUNT.json"))
            if rc_rec.get("admissible") is not True or rc_rec.get("current_run_attempt") != 1 or rc_rec.get("other_runs_with_this_authorization"):
                raise C.StageRefused("one-shot accounting in the handoff is not admissible: %r" % {k: rc_rec.get(k) for k in (
                    "admissible", "current_run_attempt", "other_runs_with_this_authorization")})
        elif mode in NS_BY_MODE:
            V.MODE_NAMESPACE[mode] = NS_BY_MODE[mode]
        else:
            raise C.StageRefused("unknown evidence mode %r" % mode)
        seed = C.read_json(os.path.join(a.handoff, "SEED_MANIFEST.json"))
        if seed.get("namespace") != V.MODE_NAMESPACE[mode] or seed.get("units") != ctr.get("units"):
            raise C.StageRefused("seed manifest inconsistent with the evidence")
        # stage separation + provider-record binding (the verifier must run on a different, fresh runtime)
        a_rt = C.read_json(os.path.join(a.handoff, "RUNTIME_MANIFEST.json"))
        a_cap = a_rt["captured"]
        sep = {k: (a_cap.get(k), cap.get(k)) for k in ("boot_id", "machine_id", "hostname")}
        sep.update({"github_" + k: (a_cap["github"].get(k), cap["github"].get(k)) for k in ("GITHUB_RUN_ID", "GITHUB_JOB", "RUNNER_NAME")})
        res["stage_separation"] = sep
        if a.provider_record:
            C.check_separation(a_cap, cap)                       # science path: different VM AND different workflow run
        else:
            C.check_separation({k: a_cap.get(k) for k in ("boot_id", "machine_id")}, {k: cap.get(k) for k in ("boot_id", "machine_id")})
        is_science = mode == "authorized" and not res["checks"]["authorization"]["mock"]
        if a.qual_same_run and (is_science or not a.external):
            raise C.StageRefused("--qual-same-run is QUAL-only (external, non-science evidence)")
        if a.external and a.qual_same_run:
            if not a_rt.get("enforced") or a_cap["github"].get("RUNNER_ENVIRONMENT") != "github-hosted":
                raise C.StageRefused("QUAL handoff was not produced by an enforced external Stage A job")
        elif a.external:
            if not a.provider_record or not a.stage_a_run_id:
                raise C.StageRefused("external verification requires the Stage A run id and the provider record")
            pr = C.read_json(a.provider_record)
            if pr.get("result") != "OK" or str(pr.get("stage_a_run_id")) != str(a.stage_a_run_id):
                raise C.StageRefused("provider record refused or for another run: %r" % (pr.get("checks") or {}).get("problems"))
            if str(a_cap["github"].get("GITHUB_RUN_ID")) != str(a.stage_a_run_id) or not a_rt.get("enforced") or \
                    a_cap["github"].get("RUNNER_ENVIRONMENT") != "github-hosted":
                raise C.StageRefused("handoff was not produced by the enforced external Stage A run %s" % a.stage_a_run_id)
            if mode == "authorized" and a_cap["github"].get("GITHUB_SHA") != res["checks"]["authorization"]["snapshot_commit_sha"]:
                raise C.StageRefused("Stage A commit differs from the MASTER-bound snapshot commit")
            if mode == "authorized" and pr.get("commit_tree_sha1") != res["checks"]["authorization"]["snapshot_tree_sha1"]:
                raise C.StageRefused("Stage A commit tree %r != MASTER-bound snapshot tree" % pr.get("commit_tree_sha1"))
            if str(a_cap["github"].get("GITHUB_RUN_ATTEMPT")) != "1" or (pr.get("run") or {}).get("run_attempt") != 1:
                raise C.StageRefused("Stage A run attempt is not 1 (re-run evidence is never admissible)")
            if mode == "authorized" and not res["checks"]["authorization"]["mock"] and not any(
                    x.get("state") == "approved" and C.SCIENCE_ENVIRONMENT in x.get("environments", []) for x in pr.get("approvals", [])):
                raise C.StageRefused("no provider-recorded r3-science approval for the Stage A run")
            res["provider_record_sha256"] = C.sha_file(a.provider_record)
        # independent recomputation (verbatim frozen checker core)
        design = V.design_constants(os.path.join(root, "f5_q2a", "design.py"))
        V.verify_evidence(raw, a.expected_evidence_sha, mode)
        worlds, fails, n_ck, _ = V.load_worlds(raw, design["DEV_INDEPENDENT_WORLDS"], mode, design)
        res.update(V.recompute(worlds, fails, n_ck, design["DEV_INDEPENDENT_WORLDS"]))
        res["evidence_manifest_sha256"] = a.expected_evidence_sha
        res["handoff_manifest_sha256"] = a.expected_handoff_sha
        res["mode"] = mode
        return finish("OK", [], 0)
    except (C.StageRefused, V.FailClosed) as e:
        return finish("FAIL_CLOSED", [str(e)], 3)
    except Exception as e:
        return finish("FAIL_CLOSED", ["malformed input: %s: %s" % (type(e).__name__, str(e)[:200])], 4)


if __name__ == "__main__":
    raise SystemExit(main())
