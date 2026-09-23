"""F5-Q2A-R3 STAGE A (external science stage; this build executes QUAL / FIXTURE / MOCK-AUTHORIZED modes only).

  python -I -B r3_stage/stage_a.py --root <checkout> --source-sha <MASTER-bound R3_SOURCE_MANIFEST sha256> --mode qual|fixture|authorized
        --out <dir> [--fixture NAME [--inject NAME]] [--auth-file F --auth-sha HEX --auth-id ID] [--external | --local-sim]

Order (fail closed at the first failure; nothing scientific runs before step 5):
 1 verify the source snapshot (every file hash-matched, no unlisted/pyc/pth/sitecustomize files)
 2 capture + verify the runtime identity (external: pinned container digest, provider-hosted runner, -I -B, no PYTHON* env,
   every loaded module inside the pinned runtime or the verified snapshot)
 3 verify the dependency lock (installed == lock, every installed numpy/scipy file == its installed RECORD hash; external: the
   post-install census of the whole interpreter tree against the FROZEN image baseline r3_stage/IMAGE_BASELINE.json)
 4 authorized mode: verify the exact MASTER authorization bytes + bindings (incl. the snapshot git TREE computed from the verified
   files), then (external) commit+tree binding, run attempt == 1 and the run-count record; issue the one-time in-process seed grant
 5 run the 32 worlds (qual / authorized) or build the synthetic fixture (fixture), with the frozen R1 scientific code
 6 freeze the raw evidence (frozen freezer) BEFORE interpretation; evidence manifest sha256
 7 primary frozen analysis (on a separate copy); 8 write the handoff (two artifacts: EVIDENCE and PRIMARY) with manifests.
--local-sim: supporting local simulation only (runtime/dependency checks recorded but NOT enforced); never authoritative."""
import argparse
import base64
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--mode", required=True, choices=("qual", "fixture", "authorized"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--fixture")
    ap.add_argument("--inject")
    ap.add_argument("--auth-file")
    ap.add_argument("--auth-sha")
    ap.add_argument("--auth-id")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--external", action="store_true")
    g.add_argument("--local-sim", action="store_true")
    a = ap.parse_args(argv)
    root = os.path.realpath(a.root)
    sys.path.insert(0, root)
    from r3_stage import common as C
    os.makedirs(a.out, exist_ok=False)
    status = {"schema": C.SCHEMA + "/STAGE_A_STATUS/1", "mode": a.mode, "authoritative_environment": bool(a.external),
              "local_simulation_not_authoritative": bool(a.local_sim), "steps": {}}

    def done(ok, reason=None, code=0):
        status["result"] = "OK" if ok else "FAIL_CLOSED"
        status["reason"] = reason
        with open(os.path.join(a.out, "STAGE_A_STATUS.json"), "x", encoding="utf-8") as f:
            json.dump(status, f, indent=1)
        print(json.dumps({"stage_a": status["result"], "reason": reason}))
        return code

    try:
        # 1 source
        src = C.verify_source(root, "R3_SOURCE_MANIFEST.json", a.source_sha, ignore_dirs=(os.path.relpath(os.path.realpath(a.out), root),)
                              if os.path.realpath(a.out).startswith(root + os.sep) else ())
        status["steps"]["source"] = src
        # 2 runtime
        pin = C.read_json(os.path.join(root, C.RUNTIME_PIN_FILE))
        cap = C.capture_runtime()
        if a.external:
            C.verify_runtime(cap, pin, root)
        status["steps"]["runtime"] = {"verified": bool(a.external)}
        # 3 dependencies
        dep = C.verify_dependencies(os.path.join(root, C.LOCK_FILE), strict=bool(a.external))
        status["steps"]["dependencies"] = {"verified": bool(a.external), "problems": dep["problems"][:5]}
        # 4 authorization + run count + grant
        from f5_q2a_r3 import design, seeds
        auth_prov, run_count = {"mode": a.mode, "authorization": None}, {"mode": a.mode}
        if a.mode == "authorized":
            raw = open(a.auth_file, "rb").read()
            bindings = {"source_manifest_sha256": src["source_manifest_sha256"], "runtime_image_digest": pin["container_image"],
                        "snapshot_tree_sha1": C.git_tree_sha1(root, C.snapshot_paths(root)),
                        "dependency_lock_sha256": dep["lock_sha256"],
                        "science_workflow_sha256": C.sha_file(os.path.join(root, C.SCIENCE_WORKFLOW)),
                        "verifier_workflow_sha256": C.sha_file(os.path.join(root, C.VERIFIER_WORKFLOW))}
            auth, mock = C.verify_authorization(raw, a.auth_sha, a.auth_id, bindings, allow_mock=True)
            if not mock and not a.external:
                raise C.StageRefused("a non-mock authorization can only be used on the external runtime")
            if a.external:
                status["steps"]["commit_binding"] = C.verify_commit_binding(auth, os.environ)
                if not mock:
                    if not auth.get("approver_logins"):
                        raise C.StageRefused("a science authorization must list the MASTER reviewer accounts (approver_logins)")
                    status["steps"]["environment_approval"] = C.check_environment_approval(os.environ["GITHUB_RUN_ID"], auth["approver_logins"])
                runs = C.fetch_runs_github(C.SCIENCE_WORKFLOW)
                run_count = C.run_count_check(auth["authorization_id"], os.environ.get("GITHUB_RUN_ID"), runs)
            else:
                runs = C.read_json(os.environ["R3_RUNS_FIXTURE"]) if os.environ.get("R3_RUNS_FIXTURE") else []
                run_count = C.run_count_check(auth["authorization_id"], "LOCAL-SIM", runs)
                run_count["source"] = "LOCAL_SIMULATION_FIXTURE_NOT_AUTHORITATIVE"
            seeds.grant(auth["namespace"], auth["units"], mock)
            ns, units, auth_id = auth["namespace"], list(auth["units"]), auth["authorization_id"]
            auth_prov = {"mode": a.mode, "authorization_id": auth_id, "authorization_sha256": a.auth_sha, "mock": mock,
                         "bindings_verified": bindings, "authorization_bytes_b64": base64.b64encode(raw).decode()}
        elif a.mode == "qual":
            ns, units, auth_id = design.NS_QUAL, list(design.QUAL_UNITS), None
        status["steps"]["authorization"] = {k: v for k, v in auth_prov.items() if k != "authorization_bytes_b64"}
        # 5 run / build
        work = os.path.join(a.out, "_work")
        run = os.path.join(work, "RUN")
        if a.mode == "fixture":
            from r3_qual import checker_fixtures, injections
            fx = C.read_json(os.path.join(root, "r3_qual", "FIXTURE_PLAN.json"))[a.fixture]
            checker_fixtures.build(fx["spec"], run, fx["units"], seed=fx["seed"])
            if a.inject:
                injections.pre_freeze(a.inject, run, fx["units"])
            ns, units = checker_fixtures.NS_FIXTURE, fx["units"]
        else:
            from r3_stage import science_run
            science_run.run(a.mode, ns, units, auth_id, run)
        # 6 freeze
        from f5_q2a_r3.freezer import freeze
        ev_sha = freeze(run)
        # 7 primary analysis on a separate copy (the evidence handed to Stage B never contains analysis output)
        ev_dir = os.path.join(a.out, "EVIDENCE")
        pr_dir = os.path.join(a.out, "PRIMARY")
        shutil.copytree(run, os.path.join(ev_dir, "RAW_EVIDENCE"))
        prim_run = os.path.join(work, "PRIMARY_COPY")
        shutil.copytree(run, prim_run)
        from f5_q2a_r3 import analysis
        analysis.main(prim_run)
        os.makedirs(pr_dir)
        shutil.copyfile(os.path.join(prim_run, "analysis", "ANALYSIS.json"), os.path.join(pr_dir, "PRIMARY_ANALYSIS.json"))
        # 8 handoff
        wr = lambda d, n, o: json.dump(o, open(os.path.join(d, n), "x", encoding="utf-8"), indent=1, sort_keys=True)
        wr(ev_dir, "AUTHORIZATION_PROVENANCE.json", auth_prov)
        shutil.copyfile(os.path.join(root, "R3_SOURCE_MANIFEST.json"), os.path.join(ev_dir, "SOURCE_MANIFEST.json"))
        wr(ev_dir, "RUNTIME_MANIFEST.json", {"captured": cap, "pin": pin, "enforced": bool(a.external)})
        wr(ev_dir, "DEPENDENCY_MANIFEST.json", dep)
        wr(ev_dir, "SEED_MANIFEST.json", {"namespace": ns, "units": units, "rule": design.SEED_RULE,
                                          "authorization_id": auth_id if a.mode == "authorized" else None})
        shutil.copyfile(os.path.join(run, "FAILURE_REGISTRY.json"), os.path.join(ev_dir, "FAILURES.json"))
        wr(ev_dir, "RUN_COUNT.json", run_count)
        wr(ev_dir, "EVIDENCE_MANIFEST.json", {"evidence_manifest_sha256": ev_sha, "raw_evidence_dir": "RAW_EVIDENCE"})
        hand_sha = C.write_manifest(ev_dir, "HANDOFF_MANIFEST.json", C.SCHEMA + "/HANDOFF/1")
        prim_sha = C.write_manifest(pr_dir, "PRIMARY_MANIFEST.json", C.SCHEMA + "/PRIMARY/1")
        shutil.rmtree(work)
        status["outputs"] = {"evidence_manifest_sha256": ev_sha, "handoff_manifest_sha256": hand_sha, "primary_manifest_sha256": prim_sha}
        if a.external and os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write("evidence_sha=%s\nhandoff_sha=%s\nprimary_sha=%s\n" % (ev_sha, hand_sha, prim_sha))
        return done(True)
    except C.StageRefused as e:
        return done(False, str(e), 3)
    except Exception as e:  # any other failure: fail closed, no partial handoff is valid (no manifest written)
        return done(False, "%s: %s" % (type(e).__name__, str(e)[:300]), 4)


if __name__ == "__main__":
    raise SystemExit(main())
