# F5-Q2A-R3: MASTER-side verification procedure (the external anchor; runs no repository code)

## Why this procedure exists

Every check inside the workflows runs in code that the repository controls. That covers the bootstrap literal, the manifest hash, the authorization bindings, the commit binding, the provider-record check and the verifier. The repository owner can edit the workflows, so those in-run checks are **consistency checks**. They are not the trust anchor (Avengers R3 PRE B-H1).

The anchor is this procedure. GPT MASTER, or its human operator, performs it from an environment the executor does not control, using **provider records and provider-signed provenance only**.

## A. Prerequisites (before any authorized run)

1. **Repository.** The GitHub repository that holds the snapshot must support both of the following:
   - environment **required reviewers** and **artifact attestations**. That means either a **public** repository, or a private repository on **GitHub Enterprise Cloud**. On Free, Pro and Team plans, private repositories get neither feature.
   - branch protection on `main` (no force-push, no deletion).

   The repository content at the bound commit must be **exactly** the snapshot: the tree listing equals the `R3_SOURCE_MANIFEST.json` files plus the manifest itself.

   **Content binding (N2).** A commit ID alone is not enough; bind the content. From MASTER's environment:
   - `GET /repos/{repo}/git/commits/{commit}` → `tree.sha`;
   - `GET /repos/{repo}/tarball/{commit}` → the tarball;
   - `python -I -B -S r3_tools/master_verify.py commit --content <tarball> --expected-source-sha <R3_SOURCE_MANIFEST sha256> --expected-tree <snapshot_tree_sha1> --provider-tree <tree.sha>`.

   This must return OK. The tool imports no repository code. It fails closed on any of the following:
   - a file outside the manifest, or a manifest file missing;
   - a hash differing from the manifest;
   - a manifest sha differing from the MASTER-bound value;
   - a mode other than 100644;
   - a recomputed git tree different from `snapshot_tree_sha1`;
   - a provider tree different from `snapshot_tree_sha1`.

   `snapshot_tree_sha1` is computed by MASTER from the snapshot archive it holds, with `master_verify.git_tree`.
2. **Environment `r3-science`.**
   - required reviewer(s): the MASTER operator account(s), listed as `approver_logins` in the authorization;
   - "prevent self-review" on;
   - admins may **not** bypass;
   - deployment branch: `main` only.

   **F-M2 (residual kept explicit).** Required reviewers exist only on a public repository or on Enterprise Cloud. Without them, the in-run approval check (non-mock) can never pass, so that configuration **must not** be used for science. The in-run check is a consistency check only. The approval anchor is MASTER's own reading of the deployment-review record (C.2).
3. **Executor permissions (N3; residual kept explicit).** GitHub cannot express a dispatch-only right.
   - Actions: write, which a token needs in order to dispatch, also permits cancelling runs, re-running them, and deleting runs, logs and artifacts.
   - **Recommended: MASTER dispatches every authorized Stage A and Stage B run itself.** The executor holds no write token for the repository.
   - If the executor must dispatch, the residual **N3** applies and cannot be closed on GitHub. The executor can delete or cancel runs.

   N3 is mitigated only by MASTER-side controls, never removed:
   - MASTER's own exports of the run list, with pagination, hashed into the receipt (C.3);
   - the rule that any run carrying the token counts as consumed, whatever its status (C.3);
   - the rule that any re-run is inadmissible (C.1).
4. **Pre-dispatch record.** MASTER records the following in the MASTER document before any dispatch:
   - the snapshot commit SHA;
   - the tree SHA;
   - the `R3_SOURCE_MANIFEST.json` sha256;
   - the `EXPECTED_OUTCOMES.json` sha256;
   - the workflow blob SHAs.
5. **Image baseline (N1).** MASTER independently rebuilds the frozen census baseline from the registry. From its own environment, with `python -I -B r3_tools/build_image_baseline.py <out.json>`, it follows the digest chain:
   - pinned index digest;
   - linux/amd64 manifest;
   - config and layer blobs;
   - the whiteout-applied file census;
   - the file sets of the hash-locked wheels.

   The output must be **byte-identical** to the snapshot's `r3_stage/IMAGE_BASELINE.json`. A baseline edited in the repository therefore fails in two places:
   - the manifest hash bound by MASTER (bootstrap);
   - this rebuild.

## B. Authorization (science; future)

The MASTER bytes bind:
- `snapshot_commit_sha`;
- `snapshot_tree_sha1` (the content-bound git tree; N2);
- `source_manifest_sha256`;
- `runtime_image_digest`;
- `dependency_lock_sha256`;
- `science_workflow_sha256`;
- `verifier_workflow_sha256`;
- n = 32, with units 0..31;
- namespace F5_Q2A_R3_DEV_V1;
- allowance = 1;
- `approver_logins`.

MASTER computes the SHA with a real hash tool and records it before dispatch.

## C. After Stage A, before any Stage B dispatch (the R-6 receipt)

Using the GitHub REST API or `gh`, from MASTER's own environment, MASTER checks the following.

1. **The Stage A run itself:** `path == .github/workflows/r3_stage_a_science.yml`, `head_sha == snapshot_commit_sha`, `event == workflow_dispatch`, `conclusion == success`, and a single job with `runner_group_name == "GitHub Actions"` and label `ubuntu-24.04`. Two further conditions:
   - **`run_attempt == 1`** (N4). A run that shows any re-run attempt is inadmissible, even if attempt 1 succeeded, and the outcome is DESIGN_NO_INFERENCE.
   - The tree of `head_sha` (`/git/commits/{sha}` → `tree.sha`) equals `snapshot_tree_sha1`.
2. **Deployment review:** an approved review of `r3-science` by an `approver_logins` account, and no self-approval by the dispatcher.
3. **One-shot history (N4):** the complete run list of the Stage A workflow (**all pages**). MASTER exports the list and hashes it into the receipt; run records can be deleted, so the export is the record. MASTER then runs `python -I -B -S r3_tools/master_verify.py one-shot --runs <export> --auth-id <ID> --stage-a-run-id <run>`. The accounting rules:
   - consumption is counted per **distinct run id** carrying the exact token `auth=<ID> `, so a run listed twice across pages counts once;
   - every status counts: queued, waiting, cancelled, failed, or unapproved;
   - the result must be ADMISSIBLE, meaning exactly one consuming run, that run is this Stage A run, and it is attempt 1.
4. **Provider-signed provenance.** Run:

   `gh attestation verify HANDOFF_MANIFEST.json --repo <owner>/<repo> --signer-workflow <owner>/<repo>/.github/workflows/r3_stage_a_science.yml --source-digest <snapshot_commit_sha>`

   Do the same for `PRIMARY_MANIFEST.json`. The certificate binds the workflow path, the ref and the commit, so a workflow edited on another commit cannot produce a matching attestation.
5. **Artifact provenance:** the artifact ids and digests of `r3-evidence-<run>` and `r3-primary-<run>`, from the provider's API.
6. **Record the receipt:** the evidence-manifest sha256, handoff sha256 and primary sha256. The handoff and primary values must equal the attested subject digests.

## D. Stage B dispatch and result acceptance

1. MASTER dispatches Stage B with the receipted values. Stage B re-checks the provider records in-run, as a consistency check.
2. **Accept Stage B** only if all of the following hold:
   - the Stage B run is at the same commit and is the frozen verifier workflow;
   - both jobs ran on GitHub-hosted runners;
   - the verifier job's run id is not the Stage A run id;
   - `VERIFIER_RESULT.json` has `verifier_status == OK`, with `provider_record_sha256` present and a `stage_separation` that shows different boot ids;
   - `ADJUDICATION.json` exists.
3. **Apply R-1.** If the verifier FAILED CLOSED, disagreed, or any provider check above fails, the outcome is DESIGN_NO_INFERENCE. There is no repair and no rerun.

## E. What this procedure does not cover (residual trust)

- GitHub/Microsoft, the runner images and agent, Docker Hub, PyPI, Sigstore, and the pinned actions at their commit SHAs;
- the host kernel and hardware.

Those are trusted.
