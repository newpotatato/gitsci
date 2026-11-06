"""Мат. модель: SPSA и SPSA с адаптивным моментом (раздел Methods).

Каждая функция, реализующая формулу статьи, помечена номером формулы.
"""

import numpy as np


def noisy_quadratic(x: np.ndarray, rng: np.random.Generator, sigma: float = 0.1) -> float:
    """Формула (1): f(x) = ||x||^2 + ξ, ξ ~ N(0, σ^2)."""
    return float(np.sum(x**2) + sigma * rng.normal())


def spsa_gradient(f, x: np.ndarray, c: float, rng: np.random.Generator) -> np.ndarray:
    """Формула (2): ĝ = (f(x + cΔ) − f(x − cΔ)) / (2c) · Δ^{-1}, Δ_i = ±1."""
    delta = rng.choice([-1.0, 1.0], size=x.shape)
    return (f(x + c * delta) - f(x - c * delta)) / (2 * c) / delta


def gains(k: int, a: float = 0.2, c: float = 0.1, alpha: float = 0.602, gamma: float = 0.101):
    """Формула (3): a_k = a / (k + 1)^α, c_k = c / (k + 1)^γ."""
    return a / (k + 1) ** alpha, c / (k + 1) ** gamma


def spsa(f, x0: np.ndarray, iters: int, rng: np.random.Generator, beta: float = 0.0) -> np.ndarray:
    """Формула (4): v_{k+1} = β v_k + ĝ_k,  x_{k+1} = x_k − a_k v_{k+1}. β = 0 — классический SPSA."""
    x, v = x0.copy(), np.zeros_like(x0)
    trace = np.empty(iters)
    for k in range(iters):
        a_k, c_k = gains(k)
        v = beta * v + spsa_gradient(f, x, c_k, rng)
        x = x - a_k * v
        trace[k] = np.sum(x**2)
    return trace
