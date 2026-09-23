"""World loop for Stage A (same execution semantics and record format as the R1/R2 driver: run_world over the units, RAW and
HIDDEN files kept separate, exclusive creates, failures registered, never retried). Uses only the byte-identical R1 scientific
modules in f5_q2a_r3; seeds come from f5_q2a_r3.seeds (QUAL namespace, or the one-time grant issued by stage_a)."""
import datetime
import json
import os

from f5_q2a_r3.failures import classify
from f5_q2a_r3.runner import run_world
from f5_q2a_r3.tasks import World

now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def run(mode, ns, units, auth_id, out):
    os.makedirs(out, exist_ok=False)
    json.dump({"mode": mode, "namespace": ns, "units": units, "authorization_id": auth_id, "started_utc": now(), "pid": os.getpid()},
              open(os.path.join(out, "EXECUTION_COUNTER.json"), "x"), indent=1)
    failures, done = [], []
    for u in units:
        try:
            w = World(ns, u)
            rec = run_world(w)
            json.dump(rec, open(os.path.join(out, "RAW_WORLD_%04d.json" % u), "x"), separators=(",", ":"))
            json.dump(w.hidden_truth(), open(os.path.join(out, "HIDDEN_TRUTH_%04d.json" % u), "x"), indent=1)
            for pid, pair in rec["pairs"].items():
                for c, r in pair.items():
                    if "failure" in r:
                        failures.append({"unit": u, "pair": pid, "condition": c, **r["failure"]})
            done.append(u)
        except Exception as exc:
            failures.append({"unit": u, "class": classify(exc), "repr": repr(exc)[:300]})
    json.dump({"failures": failures}, open(os.path.join(out, "FAILURE_REGISTRY.json"), "x"), indent=1)
    json.dump({"mode": mode, "namespace": ns, "units_done": done, "units_expected": units, "failures": len(failures), "finished_utc": now()},
              open(os.path.join(out, "RUN_SUMMARY.json"), "x"), indent=1)
    return done, failures
