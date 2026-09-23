"""R3 external-stage common checks (stdlib only). Used by Stage A (science) and, for the source/runtime parts, by Stage B.

Trust model (R3): the authoritative runtime is the externally supplied, content-addressed container image on a provider-hosted
ephemeral runner; the source is the immutable snapshot whose R3_SOURCE_MANIFEST hash MASTER binds; dependencies are hash-locked
and re-verified file-by-file against their installed RECORD (wheels hash-checked by pip), with a site-packages census. Nothing from the local executor machine (python,
venv, site-packages, pycache, PYTHONPATH, sitecustomize, environment) is an input of the external stage: only the git snapshot
crosses, and every file of it is hash-verified with unlisted files refused."""
import base64
import csv
import hashlib
import json
import os
import platform
import sys

SCHEMA = "F5-Q2A-R3"
FORBIDDEN_NAMES = ("sitecustomize.py", "usercustomize.py")
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".pth", ".so", ".pyd", ".dll")
RUNTIME_PIN_FILE = "r3_stage/RUNTIME_PIN.json"
LOCK_FILE = "r3_stage/requirements.lock"
SCIENCE_WORKFLOW = ".github/workflows/r3_stage_a_science.yml"
VERIFIER_WORKFLOW = ".github/workflows/r3_stage_b_verifier.yml"
AUTH_REQUIRED = ("authorization_id", "source_manifest_sha256", "snapshot_commit_sha", "snapshot_tree_sha1", "runtime_image_digest", "dependency_lock_sha256",
                 "science_workflow_sha256", "verifier_workflow_sha256", "dev_independent_worlds", "namespace", "units",
                 "execution_allowance")
SCIENCE_NAMESPACE = "F5_Q2A_R3_DEV_V1"
SCIENCE_UNITS = list(range(32))
SCIENCE_ENVIRONMENT = "r3-science"
IMAGE_BASELINE_FILE = "r3_stage/IMAGE_BASELINE.json"


class StageRefused(RuntimeError):
    pass


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    with open(p, "rb") as f:
        return sha_bytes(f.read())


def read_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ source snapshot
def verify_source(root, manifest_rel, expected_sha, allow_absent_roles=(), ignore_dirs=(), must_absent_roles=()):
    """Every manifest file present with exact size+sha; nothing else in the checkout (except .git and ignore_dirs); no pyc,
    pth, native code, sitecustomize/usercustomize or __pycache__ anywhere. allow_absent_roles: roles a sparse checkout omits."""
    mp = os.path.join(root, manifest_rel)
    if not os.path.isfile(mp):
        raise StageRefused("source manifest missing")
    got = sha_file(mp)
    if got != expected_sha:
        raise StageRefused("source manifest hash %s != expected %s" % (got, expected_sha))
    m = read_json(mp)
    if m.get("schema") != SCHEMA + "/SOURCE_MANIFEST/1":
        raise StageRefused("source manifest schema")
    listed, present = {}, set()
    for e in m["files"]:
        listed[e["path"]] = e
        p = os.path.join(root, e["path"])
        if e["role"] in must_absent_roles:
            if os.path.lexists(p):
                raise StageRefused("source file of role %s must be absent from this runtime: %s" % (e["role"], e["path"]))
            continue
        if not os.path.isfile(p):
            if e["role"] in allow_absent_roles:
                continue
            raise StageRefused("source file missing: %s" % e["path"])
        if os.path.islink(p) or os.path.getsize(p) != e["size"] or sha_file(p) != e["sha256"]:
            raise StageRefused("source file altered: %s" % e["path"])
        present.add(e["path"])
    ign = {os.path.normcase(os.path.abspath(os.path.join(root, d))) for d in (".git",) + tuple(ignore_dirs)}
    extra = []
    for r, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if os.path.normcase(os.path.abspath(os.path.join(r, d))) not in ign]
        for d in ds:
            full = os.path.join(r, d)
            if d == "__pycache__" or os.path.islink(full) or os.path.isjunction(full):
                extra.append(os.path.relpath(full, root))
        for f in fs:
            rel = os.path.relpath(os.path.join(r, f), root).replace(os.sep, "/")
            if os.path.islink(os.path.join(r, f)):
                extra.append(rel)
                continue
            if rel == manifest_rel:
                continue
            if rel not in listed or f in FORBIDDEN_NAMES or f.endswith(FORBIDDEN_SUFFIXES):
                extra.append(rel)
    if extra:
        raise StageRefused("unlisted / forbidden files in the source checkout: %r" % sorted(extra)[:20])
    return {"source_manifest_sha256": got, "snapshot_id": m.get("snapshot_id"), "files_verified": len(present),
            "files_absent_by_role": sorted(set(listed) - present), "must_absent_roles": list(must_absent_roles)}


# ------------------------------------------------------------------ runtime identity
def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def capture_runtime():
    env = os.environ
    osr = {}
    for line in (_read("/etc/os-release") or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            osr[k] = v.strip('"')
    mods = {}
    for name, mod in list(sys.modules.items()):
        try:
            f = mod.__file__
        except AttributeError:
            f = None
        if isinstance(f, str):
            mods[name] = os.path.realpath(f)
    return {
        "python_version": platform.python_version(), "implementation": sys.implementation.name, "executable": sys.executable,
        "base_prefix": sys.base_prefix, "platform": platform.platform(), "machine": platform.machine(), "os_release": osr,
        "flags": {"isolated": sys.flags.isolated, "ignore_environment": sys.flags.ignore_environment, "no_user_site": sys.flags.no_user_site,
                  "safe_path": sys.flags.safe_path, "dont_write_bytecode": sys.dont_write_bytecode},
        "python_env_vars": sorted(k for k in env if k.upper().startswith("PYTHON")),
        "container_image_declared": env.get("R3_CONTAINER_IMAGE"), "pycache_prefix": sys.pycache_prefix,
        "github": {k: env.get(k) for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB", "GITHUB_SHA", "GITHUB_WORKFLOW_REF",
                                           "GITHUB_WORKFLOW_SHA", "GITHUB_REPOSITORY", "RUNNER_NAME", "RUNNER_OS", "RUNNER_ARCH",
                                           "RUNNER_ENVIRONMENT", "ImageOS", "ImageVersion")},
        "boot_id": _read("/proc/sys/kernel/random/boot_id"), "machine_id": _read("/etc/machine-id"), "hostname": platform.node(),
        "cgroup": (_read("/proc/1/cgroup") or "")[:400], "sys_path": list(sys.path), "loaded_module_files": mods}


def verify_runtime(cap, pin, workspace_root):
    """External mode CONSISTENCY checks (not an attestation): python version, machine, OS release, the container image the
    workflow declares, RUNNER_ENVIRONMENT, interpreter flags, no PYTHON* environment, module origins. The runtime ATTESTATION
    is provider-side (MASTER verification procedure: provider run/job records + signed build provenance)."""
    bad = []
    if cap["python_version"] != pin["python_version"]:
        bad.append("python %s != %s" % (cap["python_version"], pin["python_version"]))
    if cap["machine"] != pin["machine"]:
        bad.append("machine %s" % cap["machine"])
    if cap["os_release"].get("ID") != pin["os_id"] or cap["os_release"].get("VERSION_CODENAME") != pin["os_codename"]:
        bad.append("os %r" % cap["os_release"].get("PRETTY_NAME"))
    if cap["container_image_declared"] != pin["container_image"]:
        bad.append("container image %r != pinned %r" % (cap["container_image_declared"], pin["container_image"]))
    if (cap["github"].get("RUNNER_ENVIRONMENT") or "") != "github-hosted":
        bad.append("runner is not provider-hosted (RUNNER_ENVIRONMENT=%r)" % cap["github"].get("RUNNER_ENVIRONMENT"))
    if not (cap["flags"]["isolated"] == 1 and cap["flags"]["dont_write_bytecode"]):
        bad.append("interpreter not started with -I -B")
    pref = cap.get("pycache_prefix")
    if not pref or (os.path.isdir(pref) and any(fs for _, _, fs in os.walk(pref))):
        bad.append("interpreter must run with -X pycache_prefix=<empty dir> (no .pyc may be read)")
    if cap["python_env_vars"]:
        bad.append("PYTHON* environment present: %r" % cap["python_env_vars"])
    base, ws = os.path.realpath(cap["base_prefix"]), os.path.realpath(workspace_root)
    for name, f in cap["loaded_module_files"].items():
        if not (f.startswith(base + os.sep) or f.startswith(ws + os.sep)):
            bad.append("module from outside the pinned runtime/snapshot: %s %s" % (name, f))
    if bad:
        raise StageRefused("runtime identity: " + "; ".join(bad[:10]))
    return True


# ------------------------------------------------------------------ dependency lock
def parse_lock(path):
    reqs = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        spec, *hashes = line.split()
        name, ver = spec.split("==")
        reqs[name.lower()] = {"version": ver, "hashes": [h.split("sha256:")[1] for h in hashes if h.startswith("--hash=sha256:")]}
    return reqs


def verify_dependencies(lock_path, strict, allowed_extra=("pip",)):
    """Installed distributions == lock (+ image-provided pip); every installed file of each locked distribution matches its
    RECORD hash as written at install time (the wheels themselves were hash-verified by pip --require-hashes); full site-packages
    and stdlib census in strict (external) mode."""
    from importlib import metadata
    lock = parse_lock(lock_path)
    installed = {d.metadata["Name"].lower(): d for d in metadata.distributions()}
    rep = {"lock_sha256": sha_file(lock_path), "locked": {k: v["version"] for k, v in lock.items()},
           "installed": {k: d.version for k, d in installed.items()}, "record_files_verified": 0, "problems": []}
    for name, spec in lock.items():
        d = installed.get(name)
        if d is None or d.version != spec["version"]:
            rep["problems"].append("%s installed %r != locked %s" % (name, d and d.version, spec["version"]))
            continue
        for f in d.files or []:
            if f.hash is None or f.hash.mode != "sha256":
                continue
            p = f.locate()
            try:
                data = open(p, "rb").read()
            except OSError:
                rep["problems"].append("missing installed file %s" % f)
                continue
            if base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode() != f.hash.value:
                rep["problems"].append("installed file differs from wheel RECORD: %s" % f)
            rep["record_files_verified"] += 1
    extra = sorted(set(installed) - set(lock) - set(allowed_extra))
    if extra:
        rep["problems"].append("unlocked distributions installed: %r" % extra)
    if strict:
        from r3_stage import image_census
        try:                                     # the frozen baseline is the snapshot file next to the lock (r3_stage/)
            baseline = read_json(os.path.join(os.path.dirname(os.path.abspath(lock_path)), os.path.basename(IMAGE_BASELINE_FILE)))
            cen = image_census.census("/", baseline, "post")
        except (OSError, ValueError, KeyError, TypeError) as e:
            cen = {"result": "FAIL_CLOSED", "n_missing": 0, "n_added": 0, "n_changed": 0, "missing": [], "added": [], "changed": [],
                   "error": "image baseline unavailable or malformed: %s: %s" % (type(e).__name__, str(e)[:200])}
        rep["image_census"] = cen
        if cen.get("error"):
            rep["problems"].append(cen["error"])
        elif cen["result"] != "OK":
            rep["problems"].append("image census (post-install) FAIL_CLOSED: missing=%d added=%d changed=%d %r" % (
                cen["n_missing"], cen["n_added"], cen["n_changed"], (cen["added"] + cen["changed"] + cen["missing"])[:5]))
    if strict and rep["problems"]:
        raise StageRefused("dependency lock: " + "; ".join(rep["problems"][:8]))
    return rep


# ------------------------------------------------------------------ authorization (exact MASTER bytes; mock in QUAL)
def verify_authorization(raw, expected_sha, expected_id, bindings, allow_mock):
    if sha_bytes(raw) != expected_sha:
        raise StageRefused("authorization bytes do not match the MASTER SHA-256")
    try:
        a = json.loads(raw.decode("utf-8"))
    except Exception:
        raise StageRefused("authorization is not UTF-8 JSON")
    if not isinstance(a, dict) or any(k not in a for k in AUTH_REQUIRED):
        raise StageRefused("authorization missing required keys")
    mock = a.get("NON_SCIENCE_MOCK") is True
    if "NON_SCIENCE_MOCK" in a and not (mock and allow_mock):
        raise StageRefused("mock authorization refused in this mode")
    if a["authorization_id"] != expected_id:
        raise StageRefused("authorization ID mismatch")
    for k, v in bindings.items():
        if a.get(k) != v:
            raise StageRefused("authorization binding mismatch: %s" % k)
    u = a["units"]
    if type(a["dev_independent_worlds"]) is not int or a["dev_independent_worlds"] != 32 or not isinstance(u, list) or len(u) != 32 or \
            len(set(u)) != 32 or not all(type(x) is int for x in u):
        raise StageRefused("n must be exactly 32 distinct integer worlds")
    if type(a["execution_allowance"]) is not int or a["execution_allowance"] != 1:
        raise StageRefused("execution allowance must be exactly 1")
    if a["namespace"] == SCIENCE_NAMESPACE and u != SCIENCE_UNITS:
        raise StageRefused("science authorization units must be exactly the frozen science units 0..31")
    return a, mock


def git_tree_sha1(root, paths):
    """git tree object id (SHA-1) of exactly <paths> under <root>, every file mode 100644 (N2: binds CONTENT, not a commit name)."""
    tree = {}
    for rel in paths:
        node = tree
        parts = rel.split("/")
        for d in parts[:-1]:
            node = node.setdefault(d, {})
        data = open(os.path.join(root, rel), "rb").read()
        node[parts[-1]] = hashlib.sha1(b"blob %d\0" % len(data) + data).digest()

    def build(node):
        ents = []
        for name, v in node.items():
            if isinstance(v, dict):
                ents.append((name + "/", b"40000 " + name.encode() + b"\0" + build(v)))
            else:
                ents.append((name, b"100644 " + name.encode() + b"\0" + v))
        body = b"".join(e for _, e in sorted(ents, key=lambda x: x[0].encode()))
        return hashlib.sha1(b"tree %d\0" % len(body) + body).digest()
    return build(tree).hex()


def snapshot_paths(root):
    m = read_json(os.path.join(root, "R3_SOURCE_MANIFEST.json"))
    return [e["path"] for e in m["files"]] + ["R3_SOURCE_MANIFEST.json"]


def one_shot_accounting(runs, authorization_id, current_run_id=None, current_attempt=None):
    """N4. Consumption is counted per workflow RUN carrying the exact token 'auth=<ID> ' (every attempt of a run belongs to that
    run; a queued/cancelled/failed run counts - no proof that no seed was derived). Admissible ONLY if the current run is the
    first and only run with this authorization AND this is attempt 1 AND the run shows no later attempt."""
    token = "auth=%s " % authorization_id
    mine = {}
    for r in runs:
        if token in ((r.get("display_title") or "") + " "):
            rid = str(r.get("id"))
            mine[rid] = max(int(r.get("run_attempt") or 1), mine.get(rid, 0))
    others = sorted(k for k in mine if k != str(current_run_id))
    attempt = int(current_attempt or mine.get(str(current_run_id), 1))
    rerun = attempt != 1 or mine.get(str(current_run_id), 1) != 1
    return {"authorization_id": authorization_id, "runs_consuming": len(mine | ({str(current_run_id): attempt} if current_run_id else {})),
            "other_runs_with_this_authorization": others, "current_run_attempt": attempt, "rerun_detected": rerun,
            "admissible": not others and not rerun}


def verify_commit_binding(auth, env):
    """External mode: the executing workflow run must be at the MASTER-bound snapshot commit, running the frozen Stage A
    workflow file from that same commit (a workflow edited on another commit/branch cannot satisfy this), as attempt 1 (N4),
    and the commit's TREE must be the MASTER-bound snapshot tree (N2; consistency check - MASTER re-verifies externally)."""
    if str(env.get("GITHUB_RUN_ATTEMPT")) != "1":
        raise StageRefused("run attempt %r: a re-run can never be an admissible science execution (one-shot)" % env.get("GITHUB_RUN_ATTEMPT"))
    want = auth["snapshot_commit_sha"]
    got = {"GITHUB_SHA": env.get("GITHUB_SHA"), "GITHUB_WORKFLOW_SHA": env.get("GITHUB_WORKFLOW_SHA")}
    if any(v != want for v in got.values()):
        raise StageRefused("run is not at the MASTER-bound snapshot commit: %r != %s" % (got, want))
    ref = env.get("GITHUB_WORKFLOW_REF") or ""
    if not ref.split("@")[0].endswith("/" + SCIENCE_WORKFLOW):
        raise StageRefused("run is not the frozen Stage A workflow: %r" % ref)
    tree = gh_get("/repos/%s/git/commits/%s" % (env["GITHUB_REPOSITORY"], want))["tree"]["sha"]
    if tree != auth["snapshot_tree_sha1"]:
        raise StageRefused("bound commit's tree %s != MASTER-bound snapshot tree %s" % (tree, auth["snapshot_tree_sha1"]))
    return {"snapshot_commit_sha": want, "snapshot_tree_sha1": tree, "workflow_ref": ref, "run_attempt": 1}


def check_separation(a_cap, cap):
    """The verifier must run on a different fresh runtime than Stage A (different boot, machine, run)."""
    same = [k for k in ("boot_id", "machine_id") if a_cap.get(k) and a_cap.get(k) == cap.get(k)]
    ga, gb = a_cap.get("github") or {}, cap.get("github") or {}
    if ga.get("GITHUB_RUN_ID") and ga.get("GITHUB_RUN_ID") == gb.get("GITHUB_RUN_ID"):
        same.append("GITHUB_RUN_ID")
    if same:
        raise StageRefused("verifier is not on a separate fresh runtime (equal %s)" % ",".join(same))
    return True


# ------------------------------------------------------------------ external run-count record
def run_count_check(authorization_id, current_run_id, runs):
    """runs: the provider's workflow-run records for the science workflow (GitHub REST /actions/workflows/<file>/runs, ALL
    pages). Any OTHER run whose display title carries the exact token 'auth=<ID> ' -> refuse (allowance 1). Run records can be
    deleted by an Actions-write principal: MASTER exports and hashes the run list at the R-6 receipt (procedure)."""
    acc = one_shot_accounting(runs, authorization_id, current_run_id, os.environ.get("GITHUB_RUN_ATTEMPT"))
    if acc["other_runs_with_this_authorization"]:
        raise StageRefused("run-count: authorization %s already used by run(s) %r" % (authorization_id, acc["other_runs_with_this_authorization"][:5]))
    if acc["rerun_detected"]:
        raise StageRefused("run-count: re-run attempt %s of an authorized run is never admissible" % acc["current_run_attempt"])
    acc.update(current_run_id=current_run_id, runs_examined=len(runs))
    return acc


def gh_get(path):
    import urllib.request
    token = os.environ["R3_GITHUB_TOKEN"]
    req = urllib.request.Request("https://api.github.com" + path, headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def fetch_runs_github(workflow_file):
    """External mode only: ALL pages of the provider's run records, read with the job's read-only GITHUB_TOKEN (actions: read)."""
    repo, runs, page = os.environ["GITHUB_REPOSITORY"], [], 1
    while True:
        d = gh_get("/repos/%s/actions/workflows/%s/runs?per_page=100&page=%d" % (repo, os.path.basename(workflow_file), page))
        runs += d["workflow_runs"]
        if len(d["workflow_runs"]) < 100 or len(runs) >= d.get("total_count", 0):
            return runs
        page += 1


def check_environment_approval(run_id, approver_logins):
    """External, non-mock authorized mode: the provider must record an APPROVED deployment review of environment r3-science for
    THIS run by one of the MASTER-listed reviewer accounts (the environment's required reviewer is the primary one-shot control)."""
    repo = os.environ["GITHUB_REPOSITORY"]
    appr = gh_get("/repos/%s/actions/runs/%s/approvals" % (repo, run_id))
    ok = [a for a in appr if a.get("state") == "approved" and (a.get("user") or {}).get("login") in approver_logins
          and any(e.get("name") == SCIENCE_ENVIRONMENT for e in a.get("environments", []))]
    if not ok:
        raise StageRefused("no approved %s deployment review by a MASTER-listed reviewer for run %s" % (SCIENCE_ENVIRONMENT, run_id))
    return {"approvals": [{"login": a["user"]["login"], "state": a["state"]} for a in ok]}


# ------------------------------------------------------------------ handoff manifest
def write_manifest(dirpath, name, schema):
    files = {}
    for r, _, fs in os.walk(dirpath):
        for f in fs:
            rel = os.path.relpath(os.path.join(r, f), dirpath).replace(os.sep, "/")
            if rel == name:
                continue
            files[rel] = sha_file(os.path.join(r, f))
    m = {"schema": schema, "files": dict(sorted(files.items()))}
    body = json.dumps(m, indent=1, sort_keys=True).encode()
    with open(os.path.join(dirpath, name), "xb") as f:
        f.write(body)
    return sha_bytes(body)


def verify_manifest(dirpath, name, expected_sha, schema):
    p = os.path.join(dirpath, name)
    if not os.path.isfile(p) or sha_file(p) != expected_sha:
        raise StageRefused("%s hash mismatch or missing" % name)
    m = read_json(p)
    if m.get("schema") != schema:
        raise StageRefused("%s schema" % name)
    on_disk = set()
    for r, _, fs in os.walk(dirpath):
        for f in fs:
            rel = os.path.relpath(os.path.join(r, f), dirpath).replace(os.sep, "/")
            if rel != name:
                on_disk.add(rel)
    if on_disk != set(m["files"]):
        raise StageRefused("%s: unlisted or missing files %r" % (name, sorted(on_disk ^ set(m["files"]))[:10]))
    for rel, h in m["files"].items():
        if sha_file(os.path.join(dirpath, rel)) != h:
            raise StageRefused("%s: file altered %s" % (name, rel))
    return m
