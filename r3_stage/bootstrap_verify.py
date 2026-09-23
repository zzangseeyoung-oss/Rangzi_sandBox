"""Bootstrap source verification, run by the external workflow BEFORE any other repository Python, with python -I -B -S
(no site, no user site, no environment, no bytecode writes; stdlib only). The workflow first checks this file's own sha256
against a literal in the (MASTER-bound) workflow file, and R3_SOURCE_MANIFEST.json against the MASTER-bound hash.

  python -I -B -S r3_stage/bootstrap_verify.py <checkout_root> <expected R3_SOURCE_MANIFEST sha256> [ROLE | must_absent=ROLE ...]

ROLE: files of this role may be absent. must_absent=ROLE: files of this role MUST be absent (Stage B: the science roles), so a
checkout that silently delivered the full tree (e.g. actions/checkout's REST-tarball fallback in a git-less container) is refused.
Also refused: any unlisted file, __pycache__, .pyc/.pyo/.pth/native code, sitecustomize/usercustomize, and ANY symlink/junction."""
import hashlib
import json
import os
import sys

FORBIDDEN_NAMES = ("sitecustomize.py", "usercustomize.py")
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".pth", ".so", ".pyd", ".dll")


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    root, expected = os.path.realpath(sys.argv[1]), sys.argv[2]
    absent_ok = {a for a in sys.argv[3:] if not a.startswith("must_absent=")}
    must_absent = {a.split("=", 1)[1] for a in sys.argv[3:] if a.startswith("must_absent=")}
    mp = os.path.join(root, "R3_SOURCE_MANIFEST.json")
    if sha(mp) != expected:
        sys.exit("BOOTSTRAP_REFUSED: source manifest hash mismatch")
    m = json.load(open(mp, encoding="utf-8"))
    listed = {e["path"]: e for e in m["files"]}
    for p, e in listed.items():
        fp = os.path.join(root, p)
        present = os.path.lexists(fp)
        if e["role"] in must_absent:
            if present:
                sys.exit("BOOTSTRAP_REFUSED: %s (role %s) must be absent from this runtime" % (p, e["role"]))
            continue
        if not present:
            if e["role"] in absent_ok:
                continue
            sys.exit("BOOTSTRAP_REFUSED: missing %s" % p)
        if os.path.islink(fp) or not os.path.isfile(fp) or os.path.getsize(fp) != e["size"] or sha(fp) != e["sha256"]:
            sys.exit("BOOTSTRAP_REFUSED: altered %s" % p)
    bad = []
    for r, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if not (r == root and d == ".git")]
        for d in ds:
            full = os.path.join(r, d)
            if d == "__pycache__" or os.path.islink(full) or (hasattr(os.path, "isjunction") and os.path.isjunction(full)):
                bad.append(os.path.relpath(full, root))
        for f in fs:
            full = os.path.join(r, f)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.islink(full) or (rel != "R3_SOURCE_MANIFEST.json" and (rel not in listed or f in FORBIDDEN_NAMES or f.endswith(FORBIDDEN_SUFFIXES))):
                bad.append(rel)
    if bad:
        sys.exit("BOOTSTRAP_REFUSED: unlisted/forbidden/link entries %r" % sorted(bad)[:20])
    print("BOOTSTRAP_SOURCE_VERIFIED %s files=%d must_absent=%s" % (expected, len(listed), sorted(must_absent)))


if __name__ == "__main__":
    main()
