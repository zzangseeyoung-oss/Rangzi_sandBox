# F5-Q2A-R3: external attested runtime / clean-room governance replication (protocol)

- **Authority:** CANONICAL_DEC = DEC-095; NO_NEW_DEC.
- **MASTER R3 workorder:** 1_K3yq7I2l0VKxuhf_sxQJgjwilLiWmLJkTRe9BPotXU.
- **Science:** SCIENCE_AUTHORIZATION = NO. No science execution, no science seed, no active authorization, and no authoritative local science.
- **Scope:** this document is part of the R3 source snapshot (role `docs`), so its hash is bound by `R3_SOURCE_MANIFEST.json`.

## 1. Why R3 exists, and what it changes

R2 reproduced B1. A valid, self-deleting `.pyc` in an executor-controlled local Python runtime ran before the checker's controls. It patched imported numerical code, flipped the verdict, and left the checker looking valid. The same class affects the checker, the science driver and the primary analysis.

The scientific algorithm was not refuted. What was rejected is the local Python runtime as a trust root.

R3 changes **only the execution trust boundary**. The scientific design is byte-identical to R1:
- `f5_q2a_r3/{tasks,learner,runner,metrics,failures,freezer,analysis}.py` equal the per-file hashes in the R1 FINALPRE implementation manifest (file sha256 `3ee79406…`, embedded `manifest_sha256` `7963e431…`);
- `f5_q2a/{__init__,design,metrics}.py` are unchanged;
- `f5_q2a_r3/design.py` overrides only the governance names in `GOVERNANCE_OVERRIDES`.

## 2. Architecture

1. **Immutable source snapshot.** It contains exactly the files listed in `R3_SOURCE_MANIFEST.json` (path, sha256, size and role), plus that manifest itself, and nothing else. Its `snapshot_id` is a hash over those entries, and the archive is deterministic. The snapshot must be the **only content** of the Git repository that runs the workflows.
2. **Stage A (science), `r3_stage_a_science.yml`.**
   - Runs on a GitHub-hosted `ubuntu-24.04` runner, inside the container `docker.io/library/python@sha256:0de8181…` (Python 3.13.0, Debian bookworm, linux/amd64).
   - **Before any repository Python**, the workflow checks the `bootstrap_verify.py` sha against a literal in the workflow. It checks the manifest sha against the MASTER-bound input. It then runs `bootstrap_verify` under `python -I -B -S`: every file must match, and nothing unlisted, no `__pycache__`, `.pyc`, `.pth`, native code or sitecustomize/usercustomize may be present.
   - **N1 (G1 repair): frozen-baseline census.**
     - Every Python after the literal check runs with `-X pycache_prefix=<fresh empty dir>`, so no `__pycache__` bytecode is ever read. `-B` means none is written.
     - Before the first site-enabled Python, `image_census.py` runs under `python -I -B -S`. It checks the whole interpreter tree (`usr/local/lib/python3.13/**`, `usr/local/bin/python3.13*`, `usr/local/lib/libpython3.13.so*`) against `r3_stage/IMAGE_BASELINE.json`, which must match **exactly** (paths and content hashes; symlinks by target).
     - `IMAGE_BASELINE.json` is a frozen, content-bound census of the pinned image. It is derived from the registry by digest chain and cannot be rebuilt differently without failing MASTER's independent rebuild. It is a MASTER-bound snapshot file.
     - Dependencies are then installed with `python -I -B -X pycache_prefix=… -m pip install --require-hashes --no-deps --only-binary=:all: --no-compile` from `requirements.lock`.
     - After the install, the census runs again. It expects the image baseline plus exactly the files of the hash-locked wheels, with the pip-written RECORD bound by path only.
     - Anything else fails closed: a rogue module, a `.pth`, sitecustomize or usercustomize, any `.pyc`, an extra dist-info, or a changed or deleted file. There is no allow-list for future files.
   - `stage_a.py` (`python -I -B`) then:
     1. re-verifies the source;
     2. verifies the runtime identity (pinned image, `RUNNER_ENVIRONMENT=github-hosted`, the flags, no PYTHON* environment, module origins confined to the pinned runtime and the snapshot);
     3. verifies the dependencies. The installed set must equal the lock plus pip, and every installed numpy/scipy file must equal its RECORD hash. In external mode, the post-install census against the frozen image baseline is re-run in-process, and the pycache prefix must be empty.
     4. in authorized mode:
        - verifies the exact MASTER authorization bytes and bindings, **including the snapshot git tree** computed from the verified files (N2);
        - externally, refuses unless `GITHUB_RUN_ATTEMPT == 1` (N4), the commit binding holds, and the bound commit's provider tree equals the bound tree;
        - checks the provider run-count record, using one-shot accounting per distinct run;
        - then issues the one-time seed grant;
     5. runs the 32 worlds with the frozen R1 code;
     6. freezes the raw evidence (frozen freezer) before interpretation;
     7. runs the primary analysis on a separate copy;
     8. writes two artifacts: EVIDENCE and PRIMARY.
3. **Artifact store and hash boundary.** GitHub Actions artifacts. `evidence_sha`, `handoff_sha` and `primary_sha` are written by the Stage A process itself to its job outputs, so they are *self-reported*, not provider-attested. The provider-side anchors are:
   - the artifact ids and digests the provider records;
   - GitHub's signed build provenance (artifact attestation) over `HANDOFF_MANIFEST.json` and `PRIMARY_MANIFEST.json`, whose certificate binds the workflow path, the ref and the commit.

   MASTER verifies both outside the executor, following `R3_MASTER_VERIFICATION.md`.
4. **Stage B (verifier), `r3_stage_b_verifier.yml`.**
   - A different workflow run, dispatched by MASTER after the R-6 evidence receipt, on fresh GitHub-hosted runners in the same pinned container.
   - The pinned container has no git, so `actions/checkout` delivers the full tree; sparse checkout does not work there. The job therefore **prunes** the checkout to the verifier subset (verifier, common checks, pin, lock, `f5_q2a/design.py`, workflows, manifest) **before** any verification. The bootstrap then **requires** the science roles (`science_code`, `science_stage`, `qual_fixture`) to be absent. With the science code, stage script and fixtures not present, the verifier cannot run the driver, derive seeds or regenerate data.
   - `provider_check.py` reads the provider's records of the Stage A run: workflow path, head commit, event, conclusion, a GitHub-hosted runner, artifacts and approvals. It also requires **`run_attempt == 1`** (N4) and records the git tree of the Stage A commit (N2).
   - `verify.py`:
     - verifies its own sparse source;
     - refuses if any science module is importable;
     - verifies runtime and dependencies;
     - verifies the handoff against the MASTER-verified expected hash (checked against the signed provenance), then every handoff file;
     - checks that the evidence hash equals the MASTER-receipted value and that Stage A ran the same source snapshot;
     - independently re-verifies the authorization provenance from the exact bytes Stage A consumed;
     - checks stage separation (a different boot_id, machine_id and workflow run; equal values fail closed);
     - checks that the provider record matches the Stage A run. In authorized mode it also checks:
       - the Stage A commit equals the bound snapshot commit;
       - its provider tree equals the bound `snapshot_tree_sha1`;
       - the attempt is 1;
       - the handoff's one-shot accounting is admissible;
       - for non-mock authorizations, an `r3-science` approval exists;
     - then recomputes everything with `verify_core.py`. This is generated verbatim from the frozen, differentially qualified R2 FINAL checker core.
5. **Adjudication.** A third fresh runner, comparison only (`adjudicate.py`). Under R-1, a verifier FAIL_CLOSED or any material disagreement makes FINAL_STATE = DESIGN_NO_INFERENCE, with no repair and no rerun. The predeclared relative tolerance is 1e-9.

**What the stages share:** only the snapshot at the same commit and the pinned container digest. Stage A and Stage B share no process, interpreter state, local Python, venv, pycache, site-packages or mutable environment.

## 3. What crosses from the executor side

Only the Git snapshot. Everything local to the executor machine is architecturally outside the trust boundary:
- the local python;
- venvs and site-packages;
- `__pycache__` and pycache prefixes;
- PYTHONPATH;
- sitecustomize and usercustomize;
- `.pth` files;
- environment variables;
- shadow modules.

That material is never uploaded, never installed and never imported on the runner. Contamination that someone commits is refused by the bootstrap verification, before any repository Python runs (QUAL `SOURCE_*` cases).

## 4. Authorization (future science; this task MOCK only)

GPT MASTER supplies, recorded in the MASTER document:
- the exact authorization bytes (base64 transport);
- a tool-computed SHA-256;
- the authorization ID.

These are dispatched as Stage A inputs in mode `authorized`. The bytes must bind:
- `snapshot_commit_sha` and `snapshot_tree_sha1` (N2: the git tree of exactly the snapshot files, all mode 100644, so that a same-name commit with different content is refused);
- `source_manifest_sha256`;
- `runtime_image_digest`, which must equal `RUNTIME_PIN.container_image`;
- `dependency_lock_sha256`;
- `science_workflow_sha256`;
- `verifier_workflow_sha256`;
- `dev_independent_worlds = 32`, with 32 distinct integer units;
- `namespace`: `F5_Q2A_R3_DEV_V1` for science;
- `execution_allowance = 1`.

A `NON_SCIENCE_MOCK` authorization can only grant the non-science namespace `F5_Q2A_R3_AUTHMOCK_V1`. No function constructs authorization content. The executor may only dispatch the exact bytes MASTER supplied.

## 5. One-shot governance (outside the science Python process)

1. **GitHub Environment `r3-science`.** A required reviewer (the MASTER operator) must approve every authorized Stage A job, and deployment branches are restricted to the snapshot branch. This is configured on the provider by the repository owner.
2. **Concurrency group `r3-stage-a`**, with no cancel-in-progress.
3. **Provider run records.** Stage A reads the workflow's runs through the job's read-only token. If any other run's title carries the authorization ID, Stage A refuses before any seed exists.
4. **The allowance of 1** inside the MASTER bytes.
5. **MASTER audit trail.** The provider's run list, logs and artifacts are an external record, but not an immutable one: an Actions-write principal can delete runs, and artifacts expire. So the executor gets dispatch-only rights, and MASTER exports and hashes the complete run list (all pages) at the R-6 receipt (`R3_MASTER_VERIFICATION.md`).

Two further checks run in-run:
- **Pagination and accounting (N4).**
  - Stage A reads **all pages** of the run list and matches the exact token `auth=<ID> `.
  - Consumption is counted per **distinct run id**. Every status counts: queued, waiting, cancelled or failed.
  - A run attempt other than 1 is refused before any seed exists, and any re-run makes the evidence inadmissible, at Stage B, at MASTER C.1 and under R-1.
- **Approval.** For non-mock authorizations, Stage A reads the provider's **approvals** record and requires an approved `r3-science` review by a MASTER-listed reviewer.

Required reviewers need a public repository or GitHub Enterprise Cloud; this is an external requirement (**F-M2, residual kept explicit**).

**N3 (residual kept explicit).** GitHub cannot express dispatch-only rights: Actions: write also allows cancelling, re-running and deleting runs. The recommendation is that MASTER dispatches authorized runs itself. Otherwise N3 remains, mitigated only by MASTER's own run-list exports and the N4 accounting.

## 6. Handoff schema (Stage A EVIDENCE artifact)

`HANDOFF_MANIFEST.json` lists every file's sha256. It contains:
- `AUTHORIZATION_PROVENANCE.json` (exact bytes, base64, and their sha);
- `SOURCE_MANIFEST.json`;
- `RUNTIME_MANIFEST.json` (captured identity plus pin);
- `DEPENDENCY_MANIFEST.json` (lock and RECORD verification);
- `SEED_MANIFEST.json`;
- `FAILURES.json`;
- `RUN_COUNT.json`;
- `EVIDENCE_MANIFEST.json` (the evidence-manifest sha);
- `RAW_EVIDENCE/` (the frozen run, with no analysis output).

`PRIMARY_ANALYSIS` is a **separate** artifact (`PRIMARY_MANIFEST.json`) that goes only to adjudication and never to the verifier. Stage B verifies the handoff manifest hash first. Any mismatch is FAIL_CLOSED, with no partial acceptance.

## 7. Failure policy

- Any refusal in Stage A: FAIL_CLOSED, with no handoff manifest. No retry.
- Stage B FAIL_CLOSED: DESIGN_NO_INFERENCE.
- Material disagreement: DESIGN_NO_INFERENCE (R-1).

There is no post-result repair and no rerun. A different authorization would be a new MASTER decision.

## 8. Claim boundary and residual trust assumptions

**Establishable here:** EXTERNAL_RUNTIME_IMPLEMENTABILITY only.

**Not claimed:**
- SELECTIVE_CONTROL_OPPORTUNITY;
- P-Space support;
- novelty, practical superiority, evolution;
- whole-RZETA support.

**Residual trust.** R3 does not claim immunity to any of the following, all of which are trusted:
- compromise of the cloud provider (GitHub/Microsoft), its runner images, the artifact store or its run records;
- compromise of the container registry (Docker Hub; the digest pins content but trusts the registry to serve it);
- compromise of PyPI wheels (hash-locked, but the lock hashes were taken from PyPI);
- compromise of the pinned GitHub Actions at their commit SHAs;
- kernel or hardware compromise;
- a global supply-chain compromise.

The narrower claim R3 makes is this: the authoritative runtime is externally supplied and lies outside the executor-controlled local Python environment that caused B1.

**Repository control.** Whoever can edit the workflows controls every in-run check, because all of them run in repository-controlled code. The in-run checks are therefore consistency checks only.

The anchor is the MASTER-side verification of **provider records and provider-signed provenance** (`R3_MASTER_VERIFICATION.md`). It checks the run's workflow path and head commit against the bound snapshot commit, the environment approvals, the complete run list, the artifact digests and the attestations. It runs no repository code, from an environment the executor does not control. It is supported by dispatch-only executor permissions.

Until that procedure has been exercised on a real provider run, R3 is **not** freeze-ready.

**Other residuals:**
- The runtime-identity checks in Stage A and Stage B (python version, OS release, the declared container image, `RUNNER_ENVIRONMENT`) are **consistency checks**, not measurements. Runtime attestation is provider-side.
- `r3_stage/common.py` is shared by Stage A and Stage B for the manifest, authorization, runtime and dependency checks. The recomputation core (`verify_core.py`) is independent.
