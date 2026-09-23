"""Evidence freezer: hashes every file of a finished run directory (EVIDENCE_MANIFEST.json + SHA256SUMS) before any
analysis. Refuses if the run has not finished or if the directory was already frozen."""
import datetime
import hashlib
import json
import os
import sys

fh = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def freeze(run_dir):
    if not os.path.exists(os.path.join(run_dir, "RUN_SUMMARY.json")):
        raise RuntimeError("run not finished")
    files = {}
    for r, _, fs in os.walk(run_dir):
        for f in fs:
            p = os.path.join(r, f)
            rel = os.path.relpath(p, run_dir).replace("\\", "/")
            if rel.startswith("analysis/") or rel in ("EVIDENCE_MANIFEST.json", "SHA256SUMS"):
                continue
            files[rel] = fh(p)
    m = {"stage": "PRE_INTERPRETATION evidence freeze", "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
         "files": dict(sorted(files.items())), "file_count": len(files)}
    m["evidence_manifest_sha256"] = hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest()
    json.dump(m, open(os.path.join(run_dir, "EVIDENCE_MANIFEST.json"), "x"), indent=1, sort_keys=True)
    open(os.path.join(run_dir, "SHA256SUMS"), "x").write("".join("%s  %s\n" % (h, f) for f, h in sorted(files.items())) +
                                                        "%s  EVIDENCE_MANIFEST.json\n" % fh(os.path.join(run_dir, "EVIDENCE_MANIFEST.json")))
    return m["evidence_manifest_sha256"]


if __name__ == "__main__":
    print(freeze(sys.argv[1]))
