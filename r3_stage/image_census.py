"""N1 runtime census against the FROZEN, content-bound baseline of the pinned image (r3_stage/IMAGE_BASELINE.json).
Stdlib only. Run on the external runner with:  python -I -B -S -X pycache_prefix=<fresh empty dir> r3_stage/image_census.py ...
(-S: no site, so no .pth/sitecustomize/usercustomize can run first; pycache_prefix: no __pycache__ .pyc is ever read; -B: none written.)

  python -I -B -S -X pycache_prefix=$EMPTY r3_stage/image_census.py --root / --baseline r3_stage/IMAGE_BASELINE.json --phase pre|post

pre : every path in scope == image_files exactly (paths AND sha256; symlinks by target), nothing missing, nothing added.
post: every path in scope == image_files + locked_wheel_install.files exactly (the pip-written RECORD bound by path only).
Anything else FAILS CLOSED: an added module, .pth, sitecustomize/usercustomize, .pyc, extra dist-info, a changed or deleted file."""
import hashlib
import json
import os
import sys

MARK = ".R3_SYMLINK"      # LOCAL_SUPPORTING tests only: a symlink extracted on Windows is stored as '<path>.R3_SYMLINK' (target text)


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def actual_scope(root, baseline, local_markers=False):
    out = {}

    def add(full, rel):
        if local_markers and rel.endswith(MARK):
            out[rel[:-len(MARK)]] = "symlink:" + open(full, encoding="utf-8").read()
        elif os.path.islink(full):
            out[rel] = "symlink:" + os.readlink(full)
        else:
            out[rel] = _sha(full)
    for d in baseline["scope"]["dirs"]:
        base = os.path.join(root, d)
        for r, ds, fs in os.walk(base):
            for x in list(ds):
                if os.path.islink(os.path.join(r, x)):          # a symlinked directory is an entry, never descended
                    ds.remove(x)
                    add(os.path.join(r, x), os.path.relpath(os.path.join(r, x), root).replace(os.sep, "/"))
            for f in fs:
                add(os.path.join(r, f), os.path.relpath(os.path.join(r, f), root).replace(os.sep, "/"))
    for pre in baseline["scope"]["file_prefixes"]:
        dd = os.path.join(root, os.path.dirname(pre))
        for f in sorted(os.listdir(dd)) if os.path.isdir(dd) else []:
            rel = os.path.dirname(pre) + "/" + f
            if rel.startswith(pre) or (local_markers and rel[:-len(MARK)].startswith(pre) and rel.endswith(MARK)):
                add(os.path.join(dd, f), rel)
    return out


def census(root, baseline, phase, local_markers=False):
    expected = dict(baseline["image_files"])
    if phase == "post":
        expected.update(baseline["locked_wheel_install"]["files"])
    elif phase != "pre":
        raise ValueError("phase")
    act = actual_scope(root, baseline, local_markers)
    missing = sorted(set(expected) - set(act))
    added = sorted(set(act) - set(expected))
    changed = sorted(k for k in set(expected) & set(act) if expected[k] != "RECORD_PATH_ONLY" and expected[k] != act[k])
    flag = lambda k: ("pth" if k.endswith(".pth") else "customize" if k.rsplit("/", 1)[-1] in ("sitecustomize.py", "usercustomize.py")
                      else "pyc" if k.endswith((".pyc", ".pyo")) else "dist-info" if ".dist-info/" in k else "module")
    ok = not (missing or added or changed)
    return {"phase": phase, "result": "OK" if ok else "FAIL_CLOSED", "expected_entries": len(expected), "actual_entries": len(act),
            "missing": missing[:25], "added": [{"path": k, "kind": flag(k)} for k in added[:25]], "changed": changed[:25],
            "n_missing": len(missing), "n_added": len(added), "n_changed": len(changed)}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--phase", required=True, choices=("pre", "post"))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    b = json.load(open(a.baseline, encoding="utf-8"))
    r = census(a.root, b, a.phase)
    r["baseline_sha256"] = _sha(a.baseline)
    r["interpreter"] = {"isolated": sys.flags.isolated, "no_site": sys.flags.no_site, "dont_write_bytecode": sys.dont_write_bytecode,
                        "pycache_prefix": sys.pycache_prefix}
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and sys.pycache_prefix):
        r["result"] = "FAIL_CLOSED"
        r["interpreter_violation"] = "census must run under python -I -B -S -X pycache_prefix=<empty dir>"
    if a.out:
        json.dump(r, open(a.out, "x", encoding="utf-8"), indent=1)
    print(json.dumps({k: r[k] for k in ("phase", "result", "n_missing", "n_added", "n_changed")}))
    return 0 if r["result"] == "OK" else 3


if __name__ == "__main__":
    raise SystemExit(main())
