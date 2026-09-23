"""The single learner: 2-layer tanh MLP trained by plain minibatch SGD on MSE. There is exactly one update path.
No replay, no regularisation toward earlier parameters, no gating, no weighting, no consolidation, no task identity input,
no optimizer state (plain SGD is stateless across phases)."""
import hashlib

import numpy as np

from .design import D_IN, LR, M_HIDDEN


class NumericDivergence(ArithmeticError):
    pass


class MLP:
    def __init__(self, init_seed):
        rng = np.random.default_rng(init_seed)
        self.W1 = rng.standard_normal((M_HIDDEN, D_IN)) / np.sqrt(D_IN)
        self.b1 = np.zeros(M_HIDDEN)
        self.v = rng.standard_normal(M_HIDDEN) / np.sqrt(M_HIDDEN)
        self.c = 0.0

    def predict(self, X):
        return np.tanh(X @ self.W1.T + self.b1) @ self.v + self.c

    def sgd_step(self, X, y):
        n = len(X)
        h = np.tanh(X @ self.W1.T + self.b1)
        e = h @ self.v + self.c - y
        gv = h.T @ e / n
        gc = float(e.mean())
        dz = (e[:, None] * self.v[None, :]) * (1.0 - h * h)
        gW1 = dz.T @ X / n
        gb1 = dz.mean(axis=0)
        self.W1 -= LR * gW1
        self.b1 -= LR * gb1
        self.v -= LR * gv
        self.c -= LR * gc
        if not (np.isfinite(self.W1).all() and np.isfinite(self.v).all() and np.isfinite(self.c)):
            raise NumericDivergence("non-finite parameters")

    def digest(self):
        return hashlib.sha256(b"".join(a.astype("<f8").tobytes() for a in (self.W1, self.b1, self.v, np.array([self.c])))).hexdigest()
