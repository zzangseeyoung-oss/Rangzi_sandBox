"""Task-pair builder with hidden relation truth.

A world = one anchor task A + three partner tasks, one per relation stratum (R_POS, R_ZERO, R_NEG). Every task has
the SAME marginal law (Haar U, uniform w, same BETA, same noise, same variance normalisation), so relation is
manipulated only through the JOINT law of (A, B). Relation labels exist only in the hidden-truth record; the learner and
the runner receive opaque task ids and arrays.
"""
import hashlib
import math

import numpy as np

from .design import BETA, D_IN, K_LATENT, N_CALIB, N_EVAL, NOISE_VAR, PHI_DEG, RELATIONS
from .seeds import unit_seed


def haar_stiefel(rng, k, d):
    q, r = np.linalg.qr(rng.standard_normal((d, k)))
    q = q * np.sign(np.diag(r))                     # Haar-distributed orthonormal columns
    return q.T                                        # k x d, orthonormal rows


def unit_vector(rng, k):
    v = rng.standard_normal(k)
    return v / np.linalg.norm(v)


def orthogonal_unit(rng, w):
    v = rng.standard_normal(len(w))
    v -= (v @ w) * w
    return v / np.linalg.norm(v)


class Task:
    """Latent parameters are hidden; the runner uses only .labels(X, noise_rng) and .targets(X)."""

    def __init__(self, task_id, U, w, scale):
        self.task_id, self._U, self._w, self._s = task_id, U, w, scale

    def targets(self, X):
        return self._s * (np.tanh(BETA * (X @ self._U.T)) @ self._w)

    def labels(self, X, rng):
        return self.targets(X) + math.sqrt(NOISE_VAR) * rng.standard_normal(len(X))


def _scale(U, w, Xc):
    raw = np.tanh(BETA * (Xc @ U.T)) @ w
    return 1.0 / float(np.std(raw))


class World:
    def __init__(self, namespace, unit):
        self.namespace, self.unit = namespace, unit
        s = lambda p: unit_seed(namespace, unit, p)
        rng = np.random.default_rng(s("latent"))
        self.Xc = np.random.default_rng(s("calibration")).standard_normal((N_CALIB, D_IN))
        self.Xe = np.random.default_rng(s("evaluation")).standard_normal((N_EVAL, D_IN))
        self.init_seed = s("init")                    # ONE initialisation shared by all conditions of the world
        salt = s("id_salt").to_bytes(8, "big")
        tid = lambda slot: hashlib.sha256(salt + slot.encode()).hexdigest()[:12]
        U_A, w_A = haar_stiefel(rng, K_LATENT, D_IN), unit_vector(rng, K_LATENT)
        phi = math.radians(PHI_DEG)
        latents = {}
        for r in RELATIONS:                            # fixed draw order independent of slot shuffling
            if r == "R_ZERO":
                latents[r] = (haar_stiefel(rng, K_LATENT, D_IN), unit_vector(rng, K_LATENT))
            else:
                sign = 1.0 if r == "R_POS" else -1.0
                latents[r] = (U_A.copy(), sign * math.cos(phi) * w_A + math.sin(phi) * orthogonal_unit(rng, w_A))
        order = list(RELATIONS)
        np.random.default_rng(s("slot_order")).shuffle(order)     # partner slot order carries no relation information
        self.anchor = Task(tid("anchor"), U_A, w_A, _scale(U_A, w_A, self.Xc))
        self.partners, self._hidden = [], {}
        for i, r in enumerate(order):
            U, w = latents[r]
            t = Task(tid("partner%d" % i), U, w, _scale(U, w, self.Xc))
            self.partners.append(t)
            self._hidden[t.task_id] = r
        self.stream_seed = {t.task_id: s("stream:" + t.task_id) for t in [self.anchor] + self.partners}

    # ---- hidden truth (only the harness/qual/analysis post-freeze may read it)
    def hidden_truth(self):
        out = {"anchor": self.anchor.task_id, "relations": dict(self._hidden)}
        UA, wA = self.anchor._U, self.anchor._w
        meas = {}
        for t in self.partners:
            sv = np.linalg.svd(UA @ t._U.T, compute_uv=False)
            meas[t.task_id] = {"principal_cosines": [float(x) for x in sv],
                               "head_cosine_if_shared": float(wA @ t._w) if np.allclose(sv, 1.0) else None,
                               "declared": {"d": D_IN, "k": K_LATENT, "beta": BETA, "noise_var": NOISE_VAR,
                                            "U_orthonormal": bool(np.allclose(t._U @ t._U.T, np.eye(K_LATENT))),
                                            "w_norm": float(np.linalg.norm(t._w)),
                                            "calib_target_var": float(np.var(t.targets(self.Xc)))}}
        out["measured"] = meas
        return out
