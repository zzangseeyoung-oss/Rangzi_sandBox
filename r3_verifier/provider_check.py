"""Stage B provider-record check (external mode): reads the PROVIDER's records of the Stage A run through the REST API with the
job's read-only token and writes PROVIDER_RECORD.json for verify.py. Stdlib only (python -I -B -S).

  python -I -B -S r3_verifier/provider_check.py --root <checkout> --stage-a-run-id ID --out PROVIDER_RECORD.json

Refuses unless: the run is the frozen Stage A workflow file (path), at THIS commit (head_sha == GITHUB_SHA of Stage B, i.e. the
same MASTER-bound snapshot commit), event workflow_dispatch, status completed / conclusion success, a different run than Stage B,
run_attempt == 1 (N4), and its job ran on a GitHub-hosted runner (runner_group_name 'GitHub Actions', label ubuntu-24.04). Records
the environment approvals, the artifact ids/digests and the git TREE of the Stage A commit (N2; verify.py compares it with the
authorization's snapshot_tree_sha1). NOTE: this check runs inside the repository-controlled workflow; the authoritative
anchor is the MASTER-side verification of the same provider records + the signed build provenance (R3_MASTER_VERIFICATION.md)."""
import argparse
import json
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--root", "--stage-a-run-id", "--out"):
        ap.add_argument(k, required=True)
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.realpath(a.root))
    from r3_stage import common as C
    repo, rid = os.environ["GITHUB_REPOSITORY"], a.stage_a_run_id
    rec = {"schema": C.SCHEMA + "/PROVIDER_RECORD/1", "stage_a_run_id": rid, "checks": {}}
    try:
        run = C.gh_get("/repos/%s/actions/runs/%s" % (repo, rid))
        jobs = C.gh_get("/repos/%s/actions/runs/%s/jobs?per_page=100" % (repo, rid))["jobs"]
        arts = C.gh_get("/repos/%s/actions/runs/%s/artifacts?per_page=100" % (repo, rid))["artifacts"]
        appr = C.gh_get("/repos/%s/actions/runs/%s/approvals" % (repo, rid))
        rec["run"] = {k: run.get(k) for k in ("id", "path", "head_sha", "head_branch", "event", "status", "conclusion", "display_title",
                                              "run_attempt", "created_at", "updated_at")}
        rec["jobs"] = [{k: j.get(k) for k in ("id", "name", "runner_name", "runner_group_name", "labels", "conclusion", "started_at")} for j in jobs]
        rec["artifacts"] = [{k: x.get(k) for k in ("id", "name", "digest", "size_in_bytes", "expired")} for x in arts]
        rec["approvals"] = [{"login": (x.get("user") or {}).get("login"), "state": x.get("state"),
                             "environments": [e.get("name") for e in x.get("environments", [])]} for x in appr]
        bad = []
        if run.get("path") != C.SCIENCE_WORKFLOW:
            bad.append("run path %r" % run.get("path"))
        if run.get("head_sha") != os.environ.get("GITHUB_SHA"):
            bad.append("Stage A commit %r != this commit %r" % (run.get("head_sha"), os.environ.get("GITHUB_SHA")))
        if run.get("event") != "workflow_dispatch" or run.get("status") != "completed" or run.get("conclusion") != "success":
            bad.append("run event/status/conclusion %r/%r/%r" % (run.get("event"), run.get("status"), run.get("conclusion")))
        if str(run.get("id")) == os.environ.get("GITHUB_RUN_ID"):
            bad.append("Stage A run is this run")
        if run.get("run_attempt") != 1:
            bad.append("Stage A run_attempt %r != 1 (a re-run is never admissible)" % run.get("run_attempt"))
        rec["commit_tree_sha1"] = C.gh_get("/repos/%s/git/commits/%s" % (repo, run.get("head_sha")))["tree"]["sha"]
        if len(jobs) != 1 or jobs[0].get("runner_group_name") != "GitHub Actions" or "ubuntu-24.04" not in (jobs[0].get("labels") or []):
            bad.append("Stage A job not a single GitHub-hosted ubuntu-24.04 job: %r" % rec["jobs"])
        names = {x["name"] for x in arts}
        if not {"r3-evidence-%s" % rid, "r3-primary-%s" % rid} <= names:
            bad.append("Stage A artifacts missing: %r" % sorted(names))
        rec["checks"]["problems"] = bad
        rec["result"] = "OK" if not bad else "FAIL_CLOSED"
    except Exception as e:
        rec["result"] = "FAIL_CLOSED"
        rec["checks"]["problems"] = ["provider records unavailable: %s: %s" % (type(e).__name__, str(e)[:200])]
    json.dump(rec, open(a.out, "x", encoding="utf-8"), indent=1)
    print(json.dumps({"provider_check": rec["result"], "problems": rec["checks"]["problems"]}))
    return 0 if rec["result"] == "OK" else 3


if __name__ == "__main__":
    raise SystemExit(main())
