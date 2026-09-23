"""R3 QUAL case actions (non-science). Shared by the external QUAL workflow (r3_qual_external.yml) and the local supporting
simulation (r3_tools/local_sim.py). Builds NON_SCIENCE_MOCK authorization variants, mutates a CHECKOUT COPY (B1 family,
source substitution), and tampers with a Stage A handoff between stages. Never creates a non-mock authorization.

  python -I -B r3_qual/external_case.py auth <variant> <root> <out_dir>
  python -I -B r3_qual/external_case.py mutate <variant> <checkout_root>
  python -I -B r3_qual/external_case.py tamper <variant> <stage_a_out> [<other_stage_a_out>]"""
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import sys

AUTHMOCK_NS = "F5_Q2A_R3_AUTHMOCK_V1"
SCIENCE_NS = "F5_Q2A_R3_DEV_V1"
sha = lambda b: hashlib.sha256(b).hexdigest()
fsha = lambda p: sha(open(p, "rb").read())


def tree_sha1(root):
    """git tree of the snapshot files under <root>, computed by the HARNESS's own (bootstrap-verified) copy of common.py - never by
    code imported from a possibly mutated checkout."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)
    from r3_stage import common
    return common.git_tree_sha1(root, common.snapshot_paths(root))


def bindings(root):
    pin = json.load(open(os.path.join(root, "r3_stage", "RUNTIME_PIN.json"), encoding="utf-8"))
    return {"source_manifest_sha256": fsha(os.path.join(root, "R3_SOURCE_MANIFEST.json")), "runtime_image_digest": pin["container_image"],
            "snapshot_tree_sha1": tree_sha1(root),
            "dependency_lock_sha256": fsha(os.path.join(root, "r3_stage", "requirements.lock")),
            "science_workflow_sha256": fsha(os.path.join(root, ".github", "workflows", "r3_stage_a_science.yml")),
            "verifier_workflow_sha256": fsha(os.path.join(root, ".github", "workflows", "r3_stage_b_verifier.yml"))}


def make_auth(variant, root, out_dir):
    """Returns (path, sha, id) of a NON_SCIENCE_MOCK authorization variant (plus, for replay, a runs fixture)."""
    a = {"NON_SCIENCE_MOCK": True, "authorization_id": "MOCK-R3-QUAL-0001", "namespace": AUTHMOCK_NS, "units": list(range(32)),
         "dev_independent_worlds": 32, "execution_allowance": 1, "approver_logins": [],
         "snapshot_commit_sha": os.environ.get("GITHUB_SHA", "LOCAL-SIM-COMMIT")}
    a.update(bindings(root))
    claimed_sha, claimed_id = None, a["authorization_id"]
    if variant == "bad_binding_source":
        a["source_manifest_sha256"] = "0" * 64
    elif variant == "bad_binding_runtime":
        a["runtime_image_digest"] = "docker.io/library/python:3.13.0-slim"
    elif variant == "bad_binding_dependency_lock":
        a["dependency_lock_sha256"] = "1" * 64
    elif variant == "bad_binding_science_workflow":
        a["science_workflow_sha256"] = "2" * 64
    elif variant == "bad_binding_verifier_workflow":
        a["verifier_workflow_sha256"] = "3" * 64
    elif variant == "bad_binding_tree":
        a["snapshot_tree_sha1"] = "5" * 40
    elif variant == "n_31":
        a["dev_independent_worlds"], a["units"] = 31, list(range(31))
    elif variant == "allowance_2":
        a["execution_allowance"] = 2
    elif variant == "allowance_true":
        a["execution_allowance"] = True
    elif variant == "mock_claims_science_namespace":
        a["namespace"] = SCIENCE_NS
    elif variant == "bad_id":
        claimed_id = "MOCK-R3-QUAL-9999"
    b = b"authorize everything" if variant == "not_json" else json.dumps(a, indent=1, sort_keys=True).encode()
    if variant == "bad_sha":
        claimed_sha = "4" * 64
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "AUTH.bin")
    open(p, "wb").write(b)
    runs = [{"id": 111, "display_title": "r3-stageA mode=authorized auth=MOCK-R3-QUAL-0001"}] if variant == "replay_prior_run" else []
    json.dump(runs, open(os.path.join(out_dir, "RUNS.json"), "w"))
    return p, claimed_sha or sha(b), claimed_id


def _valid_pyc(src_path, payload):
    src = open(src_path, "rb").read()
    code = compile(src + payload, src_path, "exec", dont_inherit=True)
    import importlib._bootstrap_external as be
    return be._code_to_hash_pyc(code, importlib.util.source_hash(src), checked=False)


def mutate(variant, root):
    j = lambda *p: os.path.join(root, *p)
    if variant == "altered_science_source":
        open(j("f5_q2a_r3", "runner.py"), "ab").write(b"\n# altered\n")
    elif variant == "altered_verifier_source":
        open(j("r3_verifier", "verify_core.py"), "ab").write(b"\n# altered\n")
    elif variant in ("planted_valid_pyc", "planted_self_deleting_pyc"):
        payload = b"\nimport os as _o\ntry:\n    _o.remove(__cached__)\nexcept Exception:\n    pass\n" if variant == "planted_self_deleting_pyc" else b"\nPATCHED = True\n"
        os.makedirs(j("f5_q2a_r3", "__pycache__"), exist_ok=True)
        open(j("f5_q2a_r3", "__pycache__", "runner.cpython-313.pyc"), "wb").write(_valid_pyc(j("f5_q2a_r3", "runner.py"), payload))
    elif variant == "planted_pycache_dir":
        os.makedirs(j("r3_stage", "__pycache__"), exist_ok=True)
    elif variant == "planted_sitecustomize":
        open(j("sitecustomize.py"), "w").write("import scipy.stats\nscipy.stats.t.sf = lambda *a, **k: 0.5\n")
    elif variant == "planted_usercustomize":
        open(j("usercustomize.py"), "w").write("import scipy.stats\nscipy.stats.t.sf = lambda *a, **k: 0.5\n")
    elif variant == "planted_pth":
        open(j("evil.pth"), "w").write("import os; os.environ['R3_EVIL'] = '1'\n")
    elif variant == "shadow_numpy_module":
        open(j("numpy.py"), "w").write("raise SystemExit('shadow numpy')\n")
    elif variant == "shadow_scipy_package":
        os.makedirs(j("scipy"), exist_ok=True)
        open(j("scipy", "__init__.py"), "w").write("raise SystemExit('shadow scipy')\n")
    elif variant == "extra_unlisted_file":
        open(j("NOTE.txt"), "w").write("unlisted\n")
    else:
        raise KeyError(variant)


def _resign(d, name, schema):
    files = {}
    for r, _, fs in os.walk(d):
        for f in fs:
            rel = os.path.relpath(os.path.join(r, f), d).replace(os.sep, "/")
            if rel != name:
                files[rel] = fsha(os.path.join(r, f))
    body = json.dumps({"schema": schema, "files": dict(sorted(files.items()))}, indent=1, sort_keys=True).encode()
    open(os.path.join(d, name), "wb").write(body)
    return sha(body)


def tamper(variant, out, other=None):
    """Mutates the Stage A output (EVIDENCE / PRIMARY) and returns overrides for the expected hashes (None = keep)."""
    ev = os.path.join(out, "EVIDENCE")
    raw = os.path.join(ev, "RAW_EVIDENCE")
    first = sorted(f for f in os.listdir(raw) if f.startswith("RAW_WORLD_"))[0]
    ov = {}
    if variant in ("altered_artifact", "altered_artifact_resigned"):
        p = os.path.join(raw, first)
        w = json.load(open(p))
        pid = next(iter(w["pairs"]))
        w["pairs"][pid]["S1"]["phases"][1]["curve"]["B"][3] += 0.01
        json.dump(w, open(p, "w"), separators=(",", ":"))
        if variant == "altered_artifact_resigned":
            _resign(ev, "HANDOFF_MANIFEST.json", "F5-Q2A-R3/HANDOFF/1")      # attacker re-signs; provider-recorded hash still differs
    elif variant == "substituted_artifact":
        shutil.rmtree(ev)
        shutil.copytree(os.path.join(other, "EVIDENCE"), ev)              # another run's self-consistent evidence
    elif variant == "primary_in_handoff":
        shutil.copyfile(os.path.join(out, "PRIMARY", "PRIMARY_ANALYSIS.json"), os.path.join(ev, "PRIMARY_ANALYSIS.json"))
        ov["handoff_sha"] = _resign(ev, "HANDOFF_MANIFEST.json", "F5-Q2A-R3/HANDOFF/1")   # even a "consistent" handoff is refused
    elif variant == "evidence_sha_mismatch":
        ov["evidence_sha"] = "5" * 64
    elif variant == "missing_evidence_file":
        os.remove(os.path.join(raw, first))
    elif variant == "source_manifest_swapped_in_handoff":
        m = json.load(open(os.path.join(ev, "SOURCE_MANIFEST.json")))
        m["snapshot_id"] = "0" * 64
        json.dump(m, open(os.path.join(ev, "SOURCE_MANIFEST.json"), "w"), indent=1, sort_keys=True)
        ov["handoff_sha"] = _resign(ev, "HANDOFF_MANIFEST.json", "F5-Q2A-R3/HANDOFF/1")
    elif variant == "primary_disagrees":
        pp = os.path.join(out, "PRIMARY", "PRIMARY_ANALYSIS.json")
        p = json.load(open(pp))
        p["SELECTIVE_CONTROL_OPPORTUNITY"], p["OPPORTUNITY_SUBTYPE"] = "SELECTIVE_CONTROL_OPPORTUNITY_NOT_DETECTED", None
        json.dump(p, open(pp, "w"), indent=1)
        ov["primary_sha"] = _resign(os.path.join(out, "PRIMARY"), "PRIMARY_MANIFEST.json", "F5-Q2A-R3/PRIMARY/1")
    else:
        raise KeyError(variant)
    return ov


# ------------------------------------------------------------------ unified case runner (external QUAL + local simulation)
import subprocess  # noqa: E402

LOCK = "r3_stage/requirements.lock"
VERIFIER_FILES = ("R3_SOURCE_MANIFEST.json", ".gitattributes", "r3_verifier/__init__.py", "r3_verifier/verify_core.py", "r3_verifier/verify.py",
                  "r3_verifier/adjudicate.py", "r3_verifier/provider_check.py", "r3_stage/__init__.py", "r3_stage/common.py",
                  "r3_stage/bootstrap_verify.py", "r3_stage/RUNTIME_PIN.json", "r3_stage/requirements.lock", "r3_stage/image_census.py",
                  "r3_stage/IMAGE_BASELINE.json", "f5_q2a/design.py",
                  ".github/workflows/r3_stage_a_science.yml", ".github/workflows/r3_stage_b_verifier.yml", ".github/workflows/r3_qual_external.yml")


def prune_verifier(full, dst):
    """Copy ONLY the verifier subset (same list as the Stage B workflows) - the science roles are then absent."""
    for rel in VERIFIER_FILES:
        s_ = os.path.join(full, rel)
        if os.path.exists(s_):
            os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
            shutil.copyfile(s_, os.path.join(dst, rel))
    return dst
SHA_KEYS = {"handoff_sha": "handoff_manifest_sha256", "evidence_sha": "evidence_manifest_sha256", "primary_sha": "primary_manifest_sha256"}

# N6: B1 comparison by IMMUTABLE identities and outputs. Volatile fields (wall-clock stamps, pid, per-VM runtime capture, run ids)
# are excluded BY NAME; every scientific byte (each RAW_WORLD / HIDDEN_TRUTH / FAILURE_REGISTRY file, the per-file hash list of the
# freeze, the seed manifest, the primary analysis, the source manifest, the lock) is compared by content hash.
VOLATILE_KEYS = ("started_utc", "finished_utc", "frozen_utc", "pid", "evidence_manifest_sha256")
IDENTITY_EXCLUDED_FILES = ("EVIDENCE/HANDOFF_MANIFEST.json", "EVIDENCE/EVIDENCE_MANIFEST.json", "EVIDENCE/RUNTIME_MANIFEST.json",
                           "EVIDENCE/RUN_COUNT.json", "EVIDENCE/DEPENDENCY_MANIFEST.json", "PRIMARY/PRIMARY_MANIFEST.json")


STAMPED_RAW_FILES = ("EXECUTION_COUNTER.json", "RUN_SUMMARY.json", "EVIDENCE_MANIFEST.json")   # carry wall-clock stamps / pid


def _canon_json(p):
    d = json.load(open(p, encoding="utf-8"))
    if isinstance(d, dict):
        d = {k: v for k, v in d.items() if k not in VOLATILE_KEYS}
        if isinstance(d.get("files"), dict):     # the freeze's per-file hash list: stamped files are compared canonically on their own
            d["files"] = {k: v for k, v in d["files"].items() if k not in STAMPED_RAW_FILES}
    return sha(json.dumps(d, sort_keys=True).encode())


def evidence_identity(evidence_dir, primary_dir):
    """-> {key: sha256} over the immutable content of one Stage A handoff (EVIDENCE artifact) + PRIMARY artifact."""
    ident = {}
    for base, tag in ((evidence_dir, "EVIDENCE"), (primary_dir, "PRIMARY")):
        for r, _, fs in os.walk(base):
            for f in fs:
                p = os.path.join(r, f)
                key = tag + "/" + os.path.relpath(p, base).replace(os.sep, "/")
                if key in IDENTITY_EXCLUDED_FILES:
                    continue
                if key.endswith("/RAW_EVIDENCE/SHA256SUMS"):
                    lines = [x for x in open(p, encoding="utf-8").read().splitlines()
                             if not any(x.endswith("  " + n) for n in STAMPED_RAW_FILES)]
                    ident[key] = sha("\n".join(lines).encode())
                elif key.endswith((".json",)) and os.path.basename(p) in ("EVIDENCE_MANIFEST.json", "EXECUTION_COUNTER.json", "RUN_SUMMARY.json",
                                                                          "AUTHORIZATION_PROVENANCE.json"):
                    ident[key] = _canon_json(p)
                else:
                    ident[key] = fsha(p)
    dep = os.path.join(evidence_dir, "DEPENDENCY_MANIFEST.json")
    if os.path.exists(dep):
        d = json.load(open(dep, encoding="utf-8"))
        ident["EVIDENCE/DEPENDENCY_MANIFEST.json#lock"] = sha(json.dumps([d.get("lock_sha256"), d.get("locked"), d.get("installed")], sort_keys=True).encode())
    return ident


def compare_identity(a, b):
    keys = sorted(set(a) | set(b))
    diff = [k for k in keys if a.get(k) != b.get(k)]
    return {"result": "SAME" if not diff else "DIFFERENT", "compared_keys": len(keys), "differing_keys": diff}


def load_case(case_id, root):
    d = json.load(open(os.path.join(root, "r3_qual", "EXPECTED_OUTCOMES.json"), encoding="utf-8"))
    return next(c for c in d["cases"] if c["id"] == case_id)


def _run(cmd, env=None, cwd=None):
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)
    return p.returncode, p.stdout[-3000:], p.stderr[-1500:]


def clean_env(extra=None):
    e = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
    e.update(extra or {})
    return e


def pyc_prefix(tmp):
    """-X pycache_prefix=<empty dir>: no __pycache__ bytecode is ever READ (-B: none written)."""
    p = os.environ.get("R3_PYC_PREFIX") or os.path.join(tmp, "r3_nopyc")
    os.makedirs(p, exist_ok=True)
    if any(fs for _, _, fs in os.walk(p)):
        raise SystemExit("bytecode prefix %s is not empty" % p)
    return ["-X", "pycache_prefix=" + p]


def trusted_install(src, tmp, py):
    """N1 sequence used by EVERY external leg (same as the Stage A/B workflows): pre-install census of the interpreter tree against
    the FROZEN image baseline (python -I -B -S: no site, so no .pth/customize runs first) -> hash-locked pip under python -I -B with
    an empty bytecode prefix (--no-compile) -> post-install census (image + locked wheel files exactly). Returns (record, ok)."""
    X = pyc_prefix(tmp)
    cen = lambda ph: _run([py, "-I", "-B", "-S"] + X + [os.path.join(src, "r3_stage", "image_census.py"), "--root", "/",
                                                       "--baseline", os.path.join(src, "r3_stage", "IMAGE_BASELINE.json"), "--phase", ph])
    rec = {}
    rc, out, err = cen("pre")
    rec["census_pre"] = {"rc": rc, "out": out.strip()[-400:], "err": err.strip()[-200:]}
    if rc != 0:
        return rec, False
    rc, _, err = _run([py, "-I", "-B"] + X + ["-m", "pip", "install", "--no-deps", "--only-binary=:all:", "--require-hashes", "--no-compile",
                                              "--no-cache-dir", "-r", os.path.join(src, LOCK)])
    rec["install_rc"] = rc
    if rc != 0:
        rec["install_err"] = err.strip()[-300:]
        return rec, False
    rc, out, err = cen("post")
    rec["census_post"] = {"rc": rc, "out": out.strip()[-400:], "err": err.strip()[-200:]}
    return rec, rc == 0


def site_plant(spec, py):
    """External QUAL only (N1 cases): plants one foreign object into the CONTAINER's interpreter tree (never used locally)."""
    import subprocess as sp_
    info = json.loads(sp_.run([py, "-I", "-S", "-c", "import json,sysconfig;print(json.dumps(sysconfig.get_paths()))"],
                              capture_output=True, text=True).stdout)
    site, std = info["purelib"], info["stdlib"]
    kind = spec.split(":", 1)[1]
    if kind == "rogue_pth":
        open(os.path.join(site, "zz_rogue.pth"), "w").write("import os\n")
    elif kind == "sitecustomize":
        open(os.path.join(site, "sitecustomize.py"), "w").write("import scipy.stats\nscipy.stats.t.sf = lambda *a, **k: 0.5\n")
    elif kind == "stdlib_pyc":
        import py_compile
        os.makedirs(os.path.join(std, "json", "__pycache__"), exist_ok=True)
        py_compile.compile(os.path.join(std, "json", "__init__.py"),
                           cfile=os.path.join(std, "json", "__pycache__", "__init__.cpython-313.pyc"), doraise=True)
    elif kind == "rogue_module":
        open(os.path.join(site, "zz_rogue.py"), "w").write("X = 1\n")
    else:
        raise ValueError(spec)


def run_stage_a(case, src, tmp, src_sha, external, py=None):
    """One Stage A leg: optional checkout mutation, bootstrap verification, (external) locked install + dependency mutation,
    then stage_a.py. The Stage A output lands in <tmp>/r3out."""
    py = py or sys.executable
    sa = case["stage_a"]
    rec = {"case": case["id"], "external": external}
    if sa.get("checkout_mutation"):
        mutate(sa["checkout_mutation"], src)
    rc, out, err = _run([py, "-I", "-B", "-S", os.path.join(src, "r3_stage", "bootstrap_verify.py"), src, src_sha])
    rec["bootstrap"] = {"rc": rc, "out": out.strip()[-300:], "err": err.strip()[-300:]}
    if rc != 0 and external:                     # external: the workflow stops here; nothing of the checkout is executed
        rec.update(stage_a="FAIL_CLOSED", refused_by="bootstrap_verify", stage_a_self_check={"result": "NOT_RUN", "reason": None}, outputs=None)
        return rec
    env = clean_env({"R3_CONTAINER_IMAGE": os.environ.get("R3_CONTAINER_IMAGE", "")})
    if sa.get("container_env_override"):
        env["R3_CONTAINER_IMAGE"] = sa["container_env_override"]
    if sa.get("runner") == "self-hosted":
        env["RUNNER_ENVIRONMENT"] = "self-hosted"
    X = pyc_prefix(tmp)
    if external:
        if (sa.get("site_plant") or "").startswith("pre:"):
            site_plant(sa["site_plant"], py)
        rec["trusted_install"], ok = trusted_install(src, tmp, py)
        if not ok:                               # external: the workflow stops here (census/installation step fails)
            ti = rec["trusted_install"]
            why = "image census pre %s" % ti["census_pre"]["out"] if ti.get("census_pre", {}).get("rc") else \
                "install rc %s" % ti.get("install_rc") if ti.get("install_rc") else "image census post %s" % ti.get("census_post", {}).get("out")
            rec.update(stage_a="FAIL_CLOSED", refused_by="image_census", stage_a_self_check={"result": "NOT_RUN", "reason": why}, outputs=None)
            return rec
        if (sa.get("site_plant") or "").startswith("post:"):
            site_plant(sa["site_plant"], py)
        if sa.get("dependency_mutation") == "numpy_other_version":
            _run([py, "-I", "-B"] + X + ["-m", "pip", "install", "--no-deps", "--no-compile", "numpy==2.4.5"])
        elif sa.get("dependency_mutation") == "patch_scipy_stats_file":
            _run([py, "-I", "-B"] + X + ["-c", "import scipy.stats._distn_infrastructure as m; open(m.__file__, 'a').write('\\n# patched\\n')"])
    out_dir = os.path.join(tmp, "r3out")
    args = [py, "-I", "-B"] + X + [os.path.join(src, "r3_stage", "stage_a.py"), "--root", src, "--source-sha", src_sha, "--mode", sa.get("mode", "fixture"),
            "--out", out_dir, "--external" if (external or sa.get("local_claims_external")) else "--local-sim"]
    if sa.get("fixture"):
        args += ["--fixture", sa["fixture"]]
    if sa.get("inject"):
        args += ["--inject", sa["inject"]]
    if sa.get("mode") == "authorized":
        p, s, i = make_auth(sa["auth"], src, os.path.join(tmp, "auth"))
        args += ["--auth-file", p, "--auth-sha", s, "--auth-id", i]
        env["R3_RUNS_FIXTURE"] = os.path.join(tmp, "auth", "RUNS.json")
    rc3, _, err3 = _run(args, env=env)
    rec["stage_a_rc"] = rc3
    st = os.path.join(out_dir, "STAGE_A_STATUS.json")
    s = json.load(open(st)) if os.path.exists(st) else {"result": "NO_STATUS", "reason": err3[-300:]}
    rec["stage_a_self_check"] = {"result": s.get("result"), "reason": s.get("reason")}
    rec["stage_a"] = "FAIL_CLOSED" if rec["bootstrap"]["rc"] != 0 else s.get("result")
    rec["refused_by"] = "bootstrap_verify" if rec["bootstrap"]["rc"] != 0 else ("stage_a" if s.get("result") != "OK" else None)
    rec["outputs"] = s.get("outputs")
    return rec


def run_stage_b(case, vsrc, a_out, other_out, tmp, src_sha, external, py=None, stage_a_src=None):
    """One Stage B leg (+ adjudication): optional tamper, bootstrap (science roles absent), verify.py, adjudicate.py."""
    py = py or sys.executable
    rec = {"case": case["id"], "external": external}
    st_p = os.path.join(a_out, "STAGE_A_STATUS.json")
    if not os.path.exists(st_p) or json.load(open(st_p)).get("result") != "OK":
        rec["verifier"] = ["NOT_APPLICABLE_STAGE_A_REFUSED"]
        return rec
    outs = dict(json.load(open(st_p))["outputs"])
    if case["verifier"] == "science_probe":
        code = "import sys, importlib.util; sys.path.insert(0, %r); print([m for m in ('f5_q2a_r3', 'f5_q2a_r2', 'r3_qual') if importlib.util.find_spec(m)])" % vsrc
        rc, out, err = _run([py, "-I", "-B", "-c", code])
        drv = [p for p in ("r3_stage/stage_a.py", "r3_stage/science_run.py", "f5_q2a_r3/runner.py") if os.path.exists(os.path.join(vsrc, p))]
        rec["science_probe"] = {"importable_science_modules": out.strip(), "science_files_present": drv, "err": err[-200:]}
        rec["verifier"] = ["SCIENCE_UNAVAILABLE"] if out.strip() == "[]" and not drv else ["SCIENCE_AVAILABLE"]
        return rec
    if case.get("between"):
        ov = tamper(case["between"], a_out, other_out)
        outs.update({SHA_KEYS[k]: v for k, v in ov.items()})
        rec["tamper_overrides"] = ov
    root = stage_a_src if case["verifier"] == "same_workspace_as_stage_a" else vsrc
    X = pyc_prefix(tmp)
    if root == vsrc:
        rc, out, err = _run([py, "-I", "-B", "-S"] + X + [os.path.join(vsrc, "r3_stage", "bootstrap_verify.py"), vsrc, src_sha,
                             "docs", "must_absent=science_code", "must_absent=science_stage", "must_absent=qual_fixture"])
        rec["bootstrap"] = {"rc": rc, "out": out.strip()[-200:], "err": err.strip()[-200:]}
        if external and rc == 0 and not os.environ.get("R3_LEG_ALREADY_INSTALLED"):
            rec["trusted_install"], ok = trusted_install(vsrc, tmp, py)
            if not ok:
                rec["verifier"] = ["FAIL_CLOSED"]
                rec["verifier_reasons"] = ["image census / locked install failed on the verifier leg"]
                return rec
    vout = os.path.join(tmp, "verifier")
    rc, out, err = _run([py, "-I", "-B"] + X + [os.path.join(root, "r3_verifier", "verify.py"), "--root", root, "--source-sha", src_sha,
                         "--handoff", os.path.join(a_out, "EVIDENCE"), "--expected-handoff-sha", outs["handoff_manifest_sha256"],
                         "--expected-evidence-sha", outs["evidence_manifest_sha256"], "--out", vout]
                        + (["--external", "--qual-same-run"] if external else ["--local-sim"]), env=clean_env())
    vr = json.load(open(os.path.join(vout, "VERIFIER_RESULT.json")))
    rec["verifier"] = [vr["verifier_status"], vr.get("state"), vr.get("subtype")] if vr["verifier_status"] == "OK" else ["FAIL_CLOSED"]
    rec["verifier_reasons"] = vr.get("fail_closed_reasons")
    rec["stage_separation"] = vr.get("stage_separation")
    vsha = json.loads(out.strip().splitlines()[-1])["verifier_manifest_sha256"]
    aout = os.path.join(tmp, "adjudication")
    _run([py, "-I", "-B", "-S"] + X + [os.path.join(vsrc, "r3_verifier", "adjudicate.py"), "--root", vsrc, "--primary", os.path.join(a_out, "PRIMARY"),
          "--expected-primary-sha", outs["primary_manifest_sha256"], "--verifier", vout, "--expected-verifier-sha", vsha, "--out", aout],
         env=clean_env())
    adj = json.load(open(os.path.join(aout, "ADJUDICATION.json")))
    rec["final"] = [adj.get("final_state"), adj.get("final_subtype")]
    rec["adjudication_reason"] = adj.get("reason")
    rec["cells_compared"] = adj.get("cells_compared")
    return rec


def _reason_ok(e, a, b):
    """Refusal cases must be refused by the predeclared layer with the predeclared reason (no false passes)."""
    if e.get("refused_by") and a.get("refused_by") != e["refused_by"]:
        return False
    pat = e.get("reason_contains")
    if not pat:
        return True
    text = " ".join(str(x) for x in ((a.get("stage_a_self_check") or {}).get("reason"), (a.get("bootstrap") or {}).get("err"),
                                     (b or {}).get("verifier_reasons"), (b or {}).get("adjudication_reason")))
    return pat in text


def judge(case, a, b):
    e = case["expect"]
    ok = a.get("stage_a") == e["stage_a"] and _reason_ok(e, a, b)
    if e["verifier"] is None:
        return bool(ok)
    v = (b or {}).get("verifier")
    if e["verifier"] == ["DIFF_ONLY"]:
        ok = ok and bool(v) and v[0] == "OK" and b.get("final") == v[1:] and "agree" in (b.get("adjudication_reason") or "")
    else:
        ok = ok and v == e["verifier"]
        if e.get("final") is not None and e["final"] != ["AGREE"]:
            ok = ok and b.get("final") == e["final"]
    return bool(ok)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "auth":
        print(json.dumps(dict(zip(("path", "sha", "id"), make_auth(sys.argv[2], sys.argv[3], sys.argv[4])))))
    elif cmd == "mutate":
        mutate(sys.argv[2], sys.argv[3])
    elif cmd == "tamper":
        print(json.dumps(tamper(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)))
    elif cmd == "prune-verifier":
        prune_verifier(sys.argv[2], sys.argv[3])
    elif cmd in ("run-stage-a", "run-stage-b", "run-coupled"):
        case_id, src, tmp = sys.argv[2], sys.argv[3], sys.argv[4]
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        case = load_case(case_id, here)
        src_sha = os.environ["IN_SRC_SHA"]
        if cmd == "run-stage-a":
            print(json.dumps(run_stage_a(case, src, tmp, src_sha, external=True)))
        elif cmd == "run-stage-b":
            print(json.dumps(run_stage_b(case, src, os.path.join(tmp, "a_out"), os.path.join(tmp, "other_out"), tmp, src_sha, external=True)))
        else:
            a = run_stage_a(case, src, tmp, src_sha, external=True)
            vt = os.path.join(tmp, "vt")
            os.makedirs(vt)
            vsrc = prune_verifier(src, os.path.join(tmp, "vsrc"))      # verifier-only tree, SAME job/VM as Stage A
            os.environ["R3_LEG_ALREADY_INSTALLED"] = "1"                 # same job: the Stage A leg already ran the trusted install
            b = run_stage_b(case, vsrc, os.path.join(tmp, "r3out"), None, vt, src_sha, external=True)
            print(json.dumps({"a": a, "b": b, "pass": judge(case, a, b)}))
