"""Executes the six symmetric sequence conditions for every (anchor, partner) pair of a world.

Pairing (frozen): every condition of a world starts from the SAME initial parameters (world init seed). Every
acquisition phase of a task X consumes X's OWN deterministic stream from index 0 (same inputs, same label noise), so the
only difference between e.g. S0B and the second phase of S1 is the parameter state the phase starts from.
Exposure (frozen): every phase is exactly T_PHASE SGD steps of BATCH examples; no early stopping; no retry.
Evaluation (frozen): identical held-out evaluation inputs and noiseless targets at every checkpoint, for both tasks of the
pair, in every phase and condition (the evaluator never changes between phases).
"""
import numpy as np

from .design import AWU_PER_EVAL_EXAMPLE, AWU_PER_TRAIN_EXAMPLE, BATCH, CKPT_EVERY, CONDITIONS, D_IN, N_EVAL, T_PHASE
from .failures import classify
from .learner import MLP


def nmse(model, task, Xe, ye_var):
    return float(np.mean((model.predict(Xe) - task.targets(Xe)) ** 2) / ye_var)


def run_phase(model, train_task, stream_seed, eval_tasks, Xe, evvar):
    rng = np.random.default_rng([stream_seed, 0])          # identical stream for every acquisition of this task
    curve = {r: [nmse(model, t, Xe, evvar[r])] for r, t in eval_tasks.items()}
    for step in range(1, T_PHASE + 1):
        X = rng.standard_normal((BATCH, D_IN))
        y = train_task.labels(X, rng)
        model.sgd_step(X, y)
        if step % CKPT_EVERY == 0:
            for r, t in eval_tasks.items():
                curve[r].append(nmse(model, t, Xe, evvar[r]))
    return {"curve": curve, "train_examples": T_PHASE * BATCH, "train_awu": T_PHASE * BATCH * AWU_PER_TRAIN_EXAMPLE,
            "eval_awu": len(eval_tasks) * (T_PHASE // CKPT_EVERY + 1) * N_EVAL * AWU_PER_EVAL_EXAMPLE, "end_param_digest": model.digest()}


def run_condition(world, cond, A, B):
    tasks = {"A": A, "B": B}
    evvar = {r: float(np.var(t.targets(world.Xe))) for r, t in tasks.items()}
    model = MLP(world.init_seed)
    rec = {"condition": cond, "task_ids": {"A": A.task_id, "B": B.task_id}, "init_digest": model.digest(), "phases": []}
    try:
        for role in CONDITIONS[cond]:
            ph = run_phase(model, tasks[role], world.stream_seed[tasks[role].task_id], tasks, world.Xe, evvar)
            ph["train_role"] = role
            rec["phases"].append(ph)
    except Exception as exc:                                   # fail-closed: the condition is marked failed, never retried
        rec["failure"] = {"class": classify(exc), "repr": repr(exc)[:300]}
    return rec


def run_world(world):
    """All six conditions for each of the three partners. S0A (A from scratch) is computed per pair (identical by
    construction; the repetition is a determinism check, not extra data)."""
    out = {"unit": world.unit, "anchor": world.anchor.task_id, "pairs": {}}
    for B in world.partners:
        out["pairs"][B.task_id] = {c: run_condition(world, c, world.anchor, B) for c in CONDITIONS}
    return out
