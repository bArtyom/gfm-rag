#!/usr/bin/env python3
"""Budgeted RAMP-SL V1 replay with sealed database-heldout evaluation.

The local score cache is treated as a gated replay oracle. Policy code receives
only selected cached scores through ScoreSession; full test scores are available
only after the public-policy prediction file has been sealed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import re
import resource
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "8"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/text2sql/ramp_sl_v1_active_encoding_20261124.json"
RUN_ID = "ramp_sl_v1_active_encoding_20261124_001"
P1_SUPPORT = ROOT / "docs/research/text2sql/reports/gfmrag_p1_official_20261014/scripts/gfmrag_p1_common.py"
LEGACY_ROOT = Path("/mnt/liansp3/sources/projects/quadrag")
DATA_ROOT = Path("/mnt/liansp3/sources/datasets/bird/dev")
P1_ROOT = Path("/mnt/liansp3/sources/results/gfmrag_p1_6_rebaseline_20261016/full_1534_20261018_01")
LABEL_PATH = LEGACY_ROOT / "results/p1/full_1534_final_20261014/per_question_private.jsonl"
TOKENIZER_PATH = Path("/mnt/liansp3/sources/models/grast-sql-0.6b-bird-reranker")
PREFLIGHT_PRIVATE = ROOT / f"results/{RUN_ID}/preflight_001/preflight_private.json"
PREFLIGHT_PUBLIC = ROOT / f"docs/research/text2sql/reports/{RUN_ID}/preflight_public.json"
TEST_HASH_PREFIX = "ramp-v1-test-20261124|"
QUERY_DB_RE = re.compile(rb'"db_id"\s*:\s*("(?:\\.|[^"\\])*")')
FEATURE_NAMES = (
    "cheap_cosine",
    "cheap_rank_percentile",
    "log1p_grast_input_tokens",
    "schema_name_query_overlap",
    "gp_mean_or_observed_score",
    "gp_sigma",
    "score_observed_flag",
    "observed_grast_score",
)
BASE_FEATURE_NAMES = (
    "cheap_cosine",
    "cheap_rank_percentile",
    "log1p_grast_input_tokens",
    "schema_name_query_overlap",
)
QUANTILE_Z = np.asarray(
    [
        -1.5341205443525463,
        -0.887146559018876,
        -0.4887764111146695,
        -0.1573106846101707,
        0.1573106846101707,
        0.4887764111146695,
        0.887146559018876,
        1.5341205443525463,
    ],
    dtype=np.float64,
)
MAIN_METHODS = (
    "Static-TopM",
    "Stratified-2R",
    "Random-2R",
    "BoundaryMORPH-2R",
    "Calibrated-2R",
    "RAMP-SL-V1",
    "RAMP-SL-V1-CostUnaware-Ablation",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def git_output(*args: str) -> str:
    result = subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def command_output(*args: str) -> str:
    try:
        result = subprocess.run(args, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"unavailable:{type(exc).__name__}"


def resource_snapshot() -> dict[str, Any]:
    return {
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "nvidia_smi": command_output("nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"),
        "free_h": command_output("free", "-h"),
        "cpu_threads": command_output("nproc"),
        "process_maxrss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024),
    }


def check_runtime(start_wall: float, start_cpu: float, config: dict[str, Any]) -> None:
    budgets = config["budgets"]
    wall = time.perf_counter() - start_wall
    cpu = time.process_time() - start_cpu
    rss_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    if wall > int(budgets["maximum_wall_seconds"]):
        raise TimeoutError("registered wall-clock budget exceeded")
    if cpu > int(budgets["maximum_cpu_seconds"]):
        raise TimeoutError("registered CPU-time budget exceeded")
    if rss_gib > float(budgets["maximum_process_rss_gib"]):
        raise MemoryError("registered process RSS budget exceeded")


def load_support_module():
    spec = importlib.util.spec_from_file_location("ramp_sl_v1_p1_support", P1_SUPPORT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load frozen P1 schema-text helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.PROJECT_ROOT = LEGACY_ROOT
    module.UPSTREAM_ROOT = ROOT
    module.DATA_ROOT = DATA_ROOT
    module.DB_ROOT = DATA_ROOT / "dev_databases"
    module.QUESTION_PATH = DATA_ROOT / "dev.json"
    module.SCHEMA_PATH = DATA_ROOT / "dev_tables.json"
    module.P0_AUDIT_PATH = LEGACY_ROOT / "results/p0/full_audit_v3.json"
    module.GOLD_LABELS_PATH = LABEL_PATH
    module.MODEL_PATH = Path("/mnt/liansp3/sources/models/qwen3-embedding-0.6b")
    module.DESCRIPTION_CSV_ENCODINGS.clear()
    return module


@dataclass
class QuestionData:
    db_id: str
    question_id: int
    question_index: int
    text: str
    candidate_ids: list[str]
    texts: dict[str, str]
    costs: dict[str, int]
    query_vector: np.ndarray
    candidate_vectors: np.ndarray

    @property
    def key(self) -> tuple[str, int]:
        return (self.db_id, self.question_id)


class ScoreReplayStore:
    """Private cache holder; policy code can access values only through sessions."""

    def __init__(self, path: Path, expected_sha256: str, expected_revision: str, expected_weights_sha256: str):
        if sha256_file(path) != expected_sha256:
            raise RuntimeError("Full GRAST replay cache hash mismatch")
        self._private_scores: dict[tuple[str, int], dict[str, float]] = {}
        self._static_scores: dict[tuple[str, int], dict[str, float]] = {}
        self._static_candidate_ids: dict[tuple[str, int], list[str]] = {}
        self._costs: dict[tuple[str, int], dict[str, int]] = {}
        self._model_hashes: set[str] = set()
        self._replay_read_trace: list[dict[str, Any]] = []
        self._test_prediction_seal_sha256: str | None = None
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                key = (str(row["db_id"]), int(row["question_id"]))
                if key in self._private_scores:
                    raise RuntimeError("Duplicate full-cache question key")
                if row.get("model_revision") != expected_revision or row.get("model_sha256") != expected_weights_sha256:
                    raise RuntimeError("Cached scorer identity mismatch")
                scores = row.get("scores_by_id")
                static_scores = row.get("static_scores_by_id")
                static_ids = row.get("static_candidate_ids")
                costs = row.get("input_tokens_by_id")
                if not isinstance(scores, dict) or not isinstance(costs, dict) or set(scores) != set(costs):
                    raise RuntimeError("Cached scores/token-cost maps are malformed")
                if (not isinstance(static_scores, dict) or not isinstance(static_ids, list)
                        or set(static_scores) != set(static_ids) or not set(static_ids).issubset(scores)):
                    raise RuntimeError("Historical Static-TopM cache map is malformed")
                self._private_scores[key] = {str(cid): float(score) for cid, score in scores.items()}
                self._static_scores[key] = {str(cid): float(score) for cid, score in static_scores.items()}
                self._static_candidate_ids[key] = [str(cid) for cid in static_ids]
                self._costs[key] = {str(cid): int(cost) for cid, cost in costs.items()}
                self._model_hashes.add(str(row["model_sha256"]))
        if len(self._private_scores) != 1046 or self._model_hashes != {expected_weights_sha256}:
            raise RuntimeError("Unexpected full cache coverage or scorer weights")

    def make_session(self, q: QuestionData, arm: str, budget: int, role: str, allowed_db_ids: set[str]) -> "ScoreSession":
        if q.db_id not in allowed_db_ids:
            raise PermissionError("Score API session requested for a database outside its authorized split")
        if q.key not in self._private_scores:
            raise KeyError("Question is absent from the frozen score cache")
        return ScoreSession(self, q, arm, budget, role)

    def training_scores(self, q: QuestionData, train_db_ids: set[str]) -> dict[str, float]:
        if q.db_id not in train_db_ids:
            raise PermissionError("Full scorer values may be read only for training databases")
        return dict(self._private_scores[q.key])

    def training_initial_scores(self, q: QuestionData, train_db_ids: set[str]) -> dict[str, float]:
        if q.db_id not in train_db_ids:
            raise PermissionError("Initial scorer values may be read only for training databases")
        return dict(self._static_scores[q.key])

    def authorize_postseal_reference(self, sealed_path: Path, expected_question_count: int) -> str:
        if sealed_path.name != "private_predictions_sealed.jsonl" or not sealed_path.is_file():
            raise PermissionError("Full-score reference requires the sealed online prediction artifact")
        with sealed_path.open("r", encoding="utf-8") as stream:
            count = sum(1 for line in stream if line.strip())
        if count != int(expected_question_count):
            raise RuntimeError("Sealed online prediction count does not match the registered test split")
        seal_sha256 = sha256_file(sealed_path)
        self._test_prediction_seal_sha256 = seal_sha256
        return seal_sha256

    def reference_scores_after_seal(self, q: QuestionData, seal_sha256: str, test_db_ids: set[str]) -> dict[str, float]:
        if (q.db_id not in test_db_ids or not seal_sha256 or len(seal_sha256) != 64
                or seal_sha256 != self._test_prediction_seal_sha256):
            raise PermissionError("Full-score reference requires a sealed prediction file and test database")
        self._replay_read_trace.append({
            "phase": "postseal_full_score_reference",
            "db_id_sha256": sha256_text(q.db_id),
            "question_id_sha256": sha256_text(str(q.question_id)),
            "score_count": len(self._private_scores[q.key]),
            "seal_sha256": seal_sha256,
        })
        return dict(self._private_scores[q.key])


class ScoreSession:
    def __init__(self, store: ScoreReplayStore, q: QuestionData, arm: str, budget: int, role: str):
        self._store = store
        self._q = q
        self.arm = arm
        self.budget = int(budget)
        self.role = role
        self.spent = 0
        self.seen: set[str] = set()
        self.trace: list[dict[str, Any]] = []
        self.batch_count = 0

    def cost(self, column_id: str) -> int:
        return int(self._store._costs[self._q.key][column_id])

    def score_batch(self, column_ids: list[str]) -> dict[str, float]:
        if len(column_ids) != len(set(column_ids)) or self.seen.intersection(column_ids):
            raise RuntimeError(f"Repeated cached score request in arm {self.arm}")
        total = sum(self.cost(cid) for cid in column_ids)
        if total > self.budget - self.spent:
            raise RuntimeError(f"Score replay budget exceeded in arm {self.arm}")
        batch_number = self.batch_count
        self.batch_count += 1
        visible_at_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        static_score_source = self._store._static_scores[self._q.key]
        full_score_source = self._store._private_scores[self._q.key]
        scores = {}
        for cid in column_ids:
            if self.arm == "Static-TopM" or (batch_number == 0 and cid in static_score_source):
                value = float(static_score_source[cid])
            else:
                value = float(full_score_source[cid])
            if not math.isfinite(value) or value < 0.0 or value > 1.0:
                raise RuntimeError("Selected cached GRAST score is non-finite or outside [0,1]")
            cost = self.cost(cid)
            self.seen.add(cid)
            self.spent += cost
            self.trace.append({
                "column_id_sha256": sha256_text(cid),
                "input_tokens": cost,
                "call_order": len(self.trace),
                "batch_number": batch_number,
                "batch_size": len(column_ids),
                "score_visible_at_utc": visible_at_utc,
            })
            scores[cid] = value
        return scores


class OutputPacker:
    def __init__(self, tokenizer: Any, texts: dict[str, str]):
        self.tokenizer = tokenizer
        self.texts = texts
        self._length_cache: dict[tuple[str, ...], int] = {}

    def token_length(self, ordered_ids: list[str]) -> int:
        key = tuple(ordered_ids)
        if key not in self._length_cache:
            serialized = "\n".join(self.texts[cid] for cid in ordered_ids)
            self._length_cache[key] = len(self.tokenizer.encode(serialized, add_special_tokens=False)) if serialized else 0
        return self._length_cache[key]

    def pack(self, ids: Iterable[str], scores: dict[str, float], budget: int) -> tuple[list[str], int]:
        ordered = sorted(ids, key=lambda cid: (-float(scores[cid]), cid))
        selected: list[str] = []
        for cid in ordered:
            candidate = selected + [cid]
            if self.token_length(candidate) <= budget:
                selected = candidate
        used = self.token_length(selected)
        if used > budget:
            raise RuntimeError("Serialized output exceeds the fixed schema token budget")
        return selected, used


@dataclass
class QuestionState:
    q: QuestionData
    cheap_scores: dict[str, float]
    cheap_order: list[str]
    prior: np.ndarray
    index_by_id: dict[str, int]
    kernel: np.ndarray
    median_distance: float
    kappa: float
    lexical_overlap: dict[str, float]


def question_name_overlap(question: str, node_text: str) -> float:
    identifier = node_text.split(";", 1)[0]
    if identifier.lower().startswith("column:"):
        identifier = identifier.split(":", 1)[1]
    name_tokens = set(re.findall(r"\w+", identifier.casefold(), flags=re.UNICODE))
    query_tokens = set(re.findall(r"\w+", question.casefold(), flags=re.UNICODE))
    if not name_tokens:
        return 0.0
    return len(name_tokens.intersection(query_tokens)) / len(name_tokens)


def build_state(q: QuestionData) -> QuestionState:
    ids = q.candidate_ids
    # Keep the frozen P1.6 float32 cosine path so Static-TopM reproduces its
    # historical stable ordering exactly; promote only for GP linear algebra.
    cheap = np.clip(q.candidate_vectors @ q.query_vector, -1.0, 1.0)
    vectors = q.candidate_vectors.astype(np.float64, copy=False)
    qvec = q.query_vector.astype(np.float64, copy=False)
    order_idx = np.lexsort((np.asarray(ids, dtype=str), -cheap))
    cheap_order = [ids[int(idx)] for idx in order_idx]
    prior = np.empty(len(ids), dtype=np.float64)
    for rank, idx in enumerate(order_idx):
        prior[int(idx)] = 1.0 if len(ids) == 1 else 1.0 - rank / (len(ids) - 1)
    cosine = np.clip(vectors @ vectors.T, -1.0, 1.0)
    offdiag = 1.0 - cosine[np.triu_indices(len(ids), k=1)] if len(ids) > 1 else np.asarray([0.5])
    median_distance = max(float(np.median(offdiag)), 1e-6)
    kappa = math.log(2.0) / median_distance
    kernel_cc = np.exp(kappa * (cosine - 1.0))
    query_cosine = np.clip(vectors @ qvec, -1.0, 1.0)
    anchor = np.exp(kappa * (query_cosine - 1.0))
    kernel = np.empty((len(ids) + 1, len(ids) + 1), dtype=np.float64)
    kernel[0, 0] = 1.0
    kernel[0, 1:] = anchor
    kernel[1:, 0] = anchor
    kernel[1:, 1:] = kernel_cc
    return QuestionState(
        q=q,
        cheap_scores={cid: float(cheap[idx]) for idx, cid in enumerate(ids)},
        cheap_order=cheap_order,
        prior=prior,
        index_by_id={cid: idx for idx, cid in enumerate(ids)},
        kernel=kernel,
        median_distance=median_distance,
        kappa=kappa,
        lexical_overlap={cid: question_name_overlap(q.text, q.texts[cid]) for cid in ids},
    )


def budget_fill(order: list[str], costs: dict[str, int], budget: int, already: set[str] | None = None) -> list[str]:
    used = set(already or ())
    selected: list[str] = []
    spent = 0
    for cid in order:
        if cid in used:
            continue
        cost = int(costs[cid])
        if cost <= budget - spent:
            selected.append(cid)
            spent += cost
    return selected


def gp_posterior(state: QuestionState, observations: dict[str, float], residual_floor: float, jitter: float) -> tuple[np.ndarray, np.ndarray]:
    obs_ids = sorted(observations, key=lambda cid: state.index_by_id[cid])
    aug_indices = [0] + [state.index_by_id[cid] + 1 for cid in obs_ids]
    score_values = [1.0] + [float(observations[cid]) for cid in obs_ids]
    prior_values = [1.0] + [float(state.prior[state.index_by_id[cid]]) for cid in obs_ids]
    residual = np.asarray(score_values, dtype=np.float64) - np.asarray(prior_values, dtype=np.float64)
    residual_mean = float(np.mean(residual))
    residual_scale = max(float(np.std(residual)), float(residual_floor))
    standardized = (residual - residual_mean) / residual_scale
    k_oo = state.kernel[np.ix_(aug_indices, aug_indices)].copy()
    k_oo.flat[:: len(k_oo) + 1] += float(jitter)
    k_xo = state.kernel[1:, aug_indices]
    alpha = np.linalg.solve(k_oo, standardized)
    solved = np.linalg.solve(k_oo, k_xo.T)
    mean = state.prior + residual_mean + residual_scale * (k_xo @ alpha)
    variance = np.maximum(np.diag(state.kernel)[1:] - np.sum(k_xo * solved.T, axis=1), 0.0)
    sigma = residual_scale * np.sqrt(variance)
    if not np.isfinite(mean).all() or not np.isfinite(sigma).all():
        raise FloatingPointError("GP posterior contains non-finite values")
    return np.clip(mean, 0.0, 1.0), np.maximum(sigma, 0.0)


class CheapScoreFallback:
    """Train-only ridge model for the preregistered GP degeneracy fallback."""

    def __init__(self, ridge_lambda: float = 0.001):
        self.ridge_lambda = float(ridge_lambda)
        self.mean = None
        self.scale = None
        self.weights = None
        self.intercept = 0.0
        self.residual_std = 0.05

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        self.mean = x.mean(axis=0)
        self.scale = x.std(axis=0)
        self.scale[self.scale < 1e-8] = 1.0
        z = (x - self.mean) / self.scale
        self.intercept = float(y.mean())
        centered_y = y - self.intercept
        gram = z.T @ z + self.ridge_lambda * np.eye(z.shape[1], dtype=np.float64)
        self.weights = np.linalg.solve(gram, z.T @ centered_y)
        residual = y - (z @ self.weights + self.intercept)
        self.residual_std = max(float(np.std(residual)), 0.05)

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.mean is None or self.scale is None or self.weights is None:
            raise RuntimeError("Fallback model is not fitted")
        z = (np.asarray(x, dtype=np.float64) - self.mean) / self.scale
        mean = np.clip(z @ self.weights + self.intercept, 0.0, 1.0)
        sigma = np.full(len(mean), self.residual_std, dtype=np.float64)
        return mean, sigma


def base_feature_matrix(state: QuestionState) -> np.ndarray:
    q = state.q
    return np.asarray(
        [
            [
                state.cheap_scores[cid],
                state.prior[state.index_by_id[cid]],
                math.log1p(q.costs[cid]),
                state.lexical_overlap[cid],
            ]
            for cid in q.candidate_ids
        ],
        dtype=np.float64,
    )


def feature_matrix(state: QuestionState, mean: np.ndarray, sigma: np.ndarray, observations: dict[str, float]) -> np.ndarray:
    rows = []
    for idx, cid in enumerate(state.q.candidate_ids):
        observed = cid in observations
        score = float(observations[cid]) if observed else 0.0
        rows.append(
            [
                state.cheap_scores[cid],
                float(state.prior[idx]),
                math.log1p(state.q.costs[cid]),
                state.lexical_overlap[cid],
                score if observed else float(np.clip(mean[idx], 0.0, 1.0)),
                0.0 if observed else float(max(0.0, sigma[idx])),
                1.0 if observed else 0.0,
                score,
            ]
        )
    return np.asarray(rows, dtype=np.float64)


class L2LogisticCalibrator:
    """Binary logistic regression with an unpenalized intercept and fixed L2 C."""

    def __init__(self, c: float = 1.0, max_iter: int = 200, feature_names: tuple[str, ...] = FEATURE_NAMES):
        self.c = float(c)
        self.max_iter = int(max_iter)
        self.feature_names = tuple(feature_names)
        self.mean = None
        self.scale = None
        self.weights = None
        self.intercept = 0.0
        self.optimization = {}

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != len(self.feature_names) or len(x) != len(y):
            raise ValueError("Malformed logistic training matrix")
        if len(np.unique(y)) != 2:
            raise RuntimeError("Training databases do not contain both binary labels")
        self.mean = x.mean(axis=0)
        self.scale = x.std(axis=0)
        self.scale[self.scale < 1e-8] = 1.0
        z = (x - self.mean) / self.scale
        n_features = z.shape[1]

        def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
            weights = theta[:n_features]
            intercept = theta[n_features]
            logits = z @ weights + intercept
            probabilities = expit(logits)
            loss = np.logaddexp(0.0, logits) - y * logits
            value = float(loss.sum() + 0.5 * np.dot(weights, weights) / self.c)
            residual = probabilities - y
            grad_w = z.T @ residual + weights / self.c
            grad_b = float(residual.sum())
            return value, np.concatenate([grad_w, [grad_b]])

        result = minimize(
            objective,
            np.zeros(n_features + 1, dtype=np.float64),
            method="L-BFGS-B",
            jac=True,
            options={"maxiter": self.max_iter, "ftol": 1e-9, "gtol": 1e-6},
        )
        if not np.isfinite(result.fun) or not np.isfinite(result.x).all():
            raise RuntimeError("L2 logistic optimization returned non-finite values")
        if not result.success:
            raise RuntimeError(f"L2 logistic optimization did not converge: {result.message}")
        self.weights = np.asarray(result.x[:n_features], dtype=np.float64)
        self.intercept = float(result.x[n_features])
        self.optimization = {
            "success": bool(result.success),
            "message": str(result.message),
            "iterations": int(result.nit),
            "objective": float(result.fun),
            "training_rows": int(len(y)),
            "positive_rate": float(y.mean()),
            "feature_names": list(self.feature_names),
        }

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self.mean is None or self.scale is None or self.weights is None:
            raise RuntimeError("Calibrator is not fitted")
        z = (np.asarray(x, dtype=np.float64) - self.mean) / self.scale
        return np.clip(expit(z @ self.weights + self.intercept), 1e-4, 1.0 - 1e-4)


def posterior_or_fallback(
    state: QuestionState,
    observations: dict[str, float],
    fallback: CheapScoreFallback,
    fallback_min_observations: int,
    residual_floor: float,
    jitter: float,
) -> tuple[np.ndarray, np.ndarray, bool, str]:
    if len(observations) < fallback_min_observations:
        mean, sigma = fallback.predict(base_feature_matrix(state))
        return mean, sigma, True, "insufficient_real_observations"
    try:
        mean, sigma = gp_posterior(state, observations, residual_floor, jitter)
        return mean, sigma, False, "gp"
    except (np.linalg.LinAlgError, FloatingPointError):
        mean, sigma = fallback.predict(base_feature_matrix(state))
        return mean, sigma, True, "gp_failure"


def lexical_base_training(q: QuestionData, state: QuestionState) -> np.ndarray:
    return base_feature_matrix(state)


def load_inputs(config: dict[str, Any]) -> tuple[list[QuestionData], ScoreReplayStore, dict[str, Any]]:
    paths = config["data"]
    questions_path = Path(paths["questions_path"])
    schema_path = Path(paths["schema_path"])
    cache_path = Path(paths["embedding_cache_path"])
    manifest_path = Path(paths["ordered_node_manifest_path"])
    for path, expected in (
        (questions_path, paths["questions_sha256"]),
        (schema_path, paths["schema_sha256"]),
        (cache_path, paths["embedding_cache_sha256"]),
        (manifest_path, paths["ordered_node_manifest_sha256"]),
    ):
        if sha256_file(path) != expected:
            raise RuntimeError(f"Frozen input hash mismatch: {path.name}")
    if not PREFLIGHT_PRIVATE.is_file() or not PREFLIGHT_PUBLIC.is_file():
        raise FileNotFoundError("Gold-blind preflight receipt is missing")
    preflight_private = json.loads(PREFLIGHT_PRIVATE.read_text(encoding="utf-8"))
    if preflight_private.get("state") != "PASS_GOLD_BLIND_PREFLIGHT":
        raise RuntimeError("Gold-blind preflight did not pass")
    if preflight_private["cache"]["sha256"] != paths["cached_score_and_token_sha256"]:
        raise RuntimeError("Preflight and preregistered cache hashes differ")

    helper = load_support_module()
    raw_questions = json.loads(questions_path.read_text(encoding="utf-8"))
    raw_schemas = json.loads(schema_path.read_text(encoding="utf-8"))
    node_records = helper._build_schema_nodes(raw_schemas)
    node_by_id = {node["node_id"]: node for node in node_records}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.sort(key=lambda row: int(row["ordinal"]))
    if len(node_records) != 873 or len(manifest) != len(node_records):
        raise RuntimeError("Schema node manifest size mismatch")
    for ordinal, item in enumerate(manifest):
        node = node_by_id.get(item["node_id"])
        if node is None or int(item["ordinal"]) != ordinal or node["db_id"] != item["db_id"] or node["node_type"] != item["node_type"]:
            raise RuntimeError("Frozen P1.6 node manifest identity mismatch")
        if sha256_text(node["text"]) != item["text_sha256"]:
            raise RuntimeError("Frozen P1.6 node text mismatch")
    columns_by_db: dict[str, list[str]] = defaultdict(list)
    for item in manifest:
        if item["node_type"] == "column":
            columns_by_db[item["db_id"]].append(item["node_id"])
    texts_by_db: dict[str, dict[str, str]] = defaultdict(dict)
    for node_id, node in node_by_id.items():
        if node["node_type"] == "column":
            texts_by_db[node["db_id"]][node_id] = node["text"]

    with np.load(cache_path, allow_pickle=False) as cache:
        if set(cache.files) != {"query_vectors", "node_vectors"}:
            raise RuntimeError("Unexpected P1.6 embedding cache members")
        query_vectors = np.asarray(cache["query_vectors"], dtype=np.float32)
        node_vectors = np.asarray(cache["node_vectors"], dtype=np.float32)
    if query_vectors.shape != (1534, 1024) or node_vectors.shape != (873, 1024):
        raise RuntimeError("P1.6 embedding cache shape mismatch")
    query_norms = np.linalg.norm(query_vectors, axis=1)
    node_norms = np.linalg.norm(node_vectors, axis=1)
    if not np.isfinite(query_vectors).all() or not np.isfinite(node_vectors).all() or np.any(query_norms <= 1e-12) or np.any(node_norms <= 1e-12):
        raise RuntimeError("P1.6 embedding cache contains invalid vectors")
    query_vectors /= query_norms[:, None]
    node_vectors /= node_norms[:, None]
    vector_by_id = {item["node_id"]: node_vectors[int(item["ordinal"])] for item in manifest}

    raw_by_key: dict[tuple[str, int], tuple[int, dict[str, Any]]] = {}
    for q_index, row in enumerate(raw_questions):
        key = (str(row["db_id"]), int(row["question_id"]))
        if key in raw_by_key:
            raise RuntimeError("Duplicate frozen BIRD question key")
        raw_by_key[key] = (q_index, row)

    store = ScoreReplayStore(
        Path(paths["cached_score_and_token_path"]),
        paths["cached_score_and_token_sha256"],
        config["scorer"]["revision"],
        config["scorer"]["weights_sha256_from_source_run"],
    )
    questions: list[QuestionData] = []
    for key in store._private_scores:
        if key not in raw_by_key:
            raise RuntimeError("Score cache question identity does not exist in frozen BIRD inputs")
        q_index, raw = raw_by_key[key]
        ids = columns_by_db[key[0]]
        scores = store._private_scores[key]
        costs = store._costs[key]
        if set(scores) != set(ids) or set(costs) != set(ids):
            raise RuntimeError("Cached score/token IDs do not match the full column universe")
        if any(cost < 1 or cost > int(config["budgets"]["maximum_single_prompt_tokens"]) for cost in costs.values()):
            raise RuntimeError("Cached prompt token cost outside frozen limits")
        questions.append(
            QuestionData(
                db_id=key[0],
                question_id=key[1],
                question_index=q_index,
                text=str(raw["question"]),
                candidate_ids=list(ids),
                texts={cid: texts_by_db[key[0]][cid] for cid in ids},
                costs=costs,
                query_vector=query_vectors[q_index],
                candidate_vectors=np.stack([vector_by_id[cid] for cid in ids]).astype(np.float32),
            )
        )
    questions.sort(key=lambda q: q.question_index)
    if len(questions) != int(config["data"]["cache_complete_questions"]):
        raise RuntimeError("Score-cache question count differs from preregistration")
    return questions, store, {"support_module": helper, "preflight_private": preflight_private, "node_count": len(node_records)}


def derive_split(questions: list[QuestionData], config: dict[str, Any]) -> tuple[set[str], set[str], dict[str, Any]]:
    counts = Counter(q.db_id for q in questions)
    eligible = [db for db, count in counts.items() if count >= 40]
    sorted_dbs = sorted(eligible, key=lambda db: (hashlib.sha256((TEST_HASH_PREFIX + db).encode("utf-8")).hexdigest(), db))
    test_dbs = set(sorted_dbs[:3])
    train_dbs = set(counts) - test_dbs
    actual_test_hashes = sorted(sha256_text(db) for db in test_dbs)
    actual_train_hashes = sorted(sha256_text(db) for db in train_dbs)
    if actual_test_hashes != sorted(config["data"]["test_db_sha256"]) or actual_train_hashes != sorted(config["data"]["train_db_sha256"]):
        raise RuntimeError("Database split differs from the frozen preflight/config")
    test_count = sum(counts[db] for db in test_dbs)
    train_count = sum(counts[db] for db in train_dbs)
    if len(test_dbs) != 3 or test_count < 80 or len(train_dbs) < 3:
        raise RuntimeError("HOLD_INSUFFICIENT_COVERAGE")
    if test_count != int(config["data"]["test_questions"]) or train_count != int(config["data"]["train_questions"]):
        raise RuntimeError("Frozen train/test question counts mismatch")
    return train_dbs, test_dbs, {
        "train_db_hashes": actual_train_hashes,
        "test_db_hashes": actual_test_hashes,
        "train_question_count": train_count,
        "test_question_count": test_count,
        "complete_question_count": len(questions),
        "complete_database_count": len(counts),
    }


def load_gold_rows(
    allowed_db_ids: set[str],
    expected_count: int | None = None,
    *,
    test_db_ids: set[str] | None = None,
    sealed_prediction_path: Path | None = None,
    expected_seal_sha256: str | None = None,
    return_stats: bool = False,
) -> dict[tuple[str, int], set[str]] | tuple[dict[tuple[str, int], set[str]], dict[str, int]]:
    """Parse only rows belonging to the authorized split; test rows are skipped pre-seal."""
    if test_db_ids is not None and allowed_db_ids.intersection(test_db_ids):
        if (sealed_prediction_path is None or not sealed_prediction_path.is_file()
                or sealed_prediction_path.name != "private_predictions_sealed.jsonl"
                or not expected_seal_sha256 or sha256_file(sealed_prediction_path) != expected_seal_sha256):
            raise PermissionError("Test Gold labels require the matching sealed prediction file")
    labels: dict[tuple[str, int], set[str]] = {}
    seen_keys: set[tuple[str, int]] = set()
    eligible_rows = 0
    ineligible_rows = 0
    with LABEL_PATH.open("rb") as stream:
        for raw_line in stream:
            if not raw_line.strip():
                continue
            match = QUERY_DB_RE.search(raw_line)
            if match is None:
                raise RuntimeError("Cannot identify database in frozen private label row")
            db_id = json.loads(match.group(1).decode("utf-8"))
            if db_id not in allowed_db_ids:
                continue
            row = json.loads(raw_line)
            key = (str(row["db_id"]), int(row["question_id"]))
            if key in seen_keys:
                raise RuntimeError("Duplicate Gold-label key")
            seen_keys.add(key)
            if not bool(row.get("column_eligible")):
                ineligible_rows += 1
                continue
            eligible_rows += 1
            labels[key] = set(str(cid) for cid in row["gold_column_ids_private"])
    if expected_count is not None and len(labels) != expected_count:
        raise RuntimeError(f"Expected {expected_count} labels for authorized databases, found {len(labels)}")
    stats = {
        "label_rows_parsed_for_allowed_databases": len(seen_keys),
        "eligible_label_rows": eligible_rows,
        "ineligible_label_rows": ineligible_rows,
    }
    return (labels, stats) if return_stats else labels


def fit_training_models(
    train_questions: list[QuestionData],
    train_db_ids: set[str],
    store: ScoreReplayStore,
    labels: dict[tuple[str, int], set[str]],
    config: dict[str, Any],
    start_wall: float,
    start_cpu: float,
) -> tuple[CheapScoreFallback, L2LogisticCalibrator, L2LogisticCalibrator, dict[str, Any]]:
    by_key = {q.key: q for q in train_questions}
    fallback_x: list[np.ndarray] = []
    fallback_y: list[np.ndarray] = []
    states: dict[tuple[str, int], QuestionState] = {}
    for q in train_questions:
        check_runtime(start_wall, start_cpu, config)
        state = build_state(q)
        states[q.key] = state
        base_x = base_feature_matrix(state)
        all_scores = store.training_scores(q, train_db_ids)
        fallback_x.append(base_x)
        fallback_y.append(np.asarray([all_scores[cid] for cid in q.candidate_ids], dtype=np.float64))
    fallback = CheapScoreFallback(ridge_lambda=0.001)
    fallback.fit(np.vstack(fallback_x), np.concatenate(fallback_y))

    train_x: list[np.ndarray] = []
    cheap_train_x: list[np.ndarray] = []
    train_y: list[np.ndarray] = []
    initial_score_tokens = 0
    insufficient_gp_count = 0
    budget = int(config["budgets"]["M0_first_round_input_tokens"])
    for q in train_questions:
        check_runtime(start_wall, start_cpu, config)
        if q.key not in labels:
            raise RuntimeError("A training question lacks its Gold-column labels")
        state = states[q.key]
        selected = budget_fill(state.cheap_order, q.costs, budget)
        observation_scores = store.training_initial_scores(q, train_db_ids)
        observed = {cid: observation_scores[cid] for cid in selected}
        initial_score_tokens += sum(q.costs[cid] for cid in selected)
        mean, sigma, used_fallback, _reason = posterior_or_fallback(
            state,
            observed,
            fallback,
            int(config["selection"]["gp_fallback_if_real_observations_below"]),
            float(config["selection"]["residual_scale_floor"]),
            float(config["selection"]["gp_jitter"]),
        )
        insufficient_gp_count += int(used_fallback)
        train_x.append(feature_matrix(state, mean, sigma, observed))
        cheap_train_x.append(base_feature_matrix(state))
        gold = labels[q.key]
        unknown = gold.difference(q.candidate_ids)
        if unknown:
            raise RuntimeError("Training Gold column is outside the frozen candidate universe")
        train_y.append(np.asarray([1.0 if cid in gold else 0.0 for cid in q.candidate_ids], dtype=np.float64))
    calibrator = L2LogisticCalibrator(c=float(config["calibrator"]["C"]), max_iter=int(config["calibrator"]["max_iterations"]))
    calibrator.fit(np.vstack(train_x), np.concatenate(train_y))
    cheap_calibrator = L2LogisticCalibrator(
        c=float(config["cheap_calibrator"]["C"]),
        max_iter=int(config["cheap_calibrator"]["max_iterations"]),
        feature_names=BASE_FEATURE_NAMES,
    )
    cheap_calibrator.fit(np.vstack(cheap_train_x), np.concatenate(train_y))
    metadata = {
        "training_question_count": len(train_questions),
        "training_database_count": len(train_db_ids),
        "training_column_feature_rows": int(sum(len(q.candidate_ids) for q in train_questions)),
        "initial_score_replay_tokens": initial_score_tokens,
        "gp_fallback_questions": insufficient_gp_count,
        "fallback_training_column_rows": int(sum(len(q.candidate_ids) for q in train_questions)),
        "fallback_residual_std": fallback.residual_std,
        "calibrator": calibrator.optimization,
        "cheap_calibrator": cheap_calibrator.optimization,
        "test_label_rows_loaded": 0,
    }
    return fallback, calibrator, cheap_calibrator, metadata


def make_feature_probability(state: QuestionState, observations: dict[str, float], fallback: CheapScoreFallback,
                             calibrator: L2LogisticCalibrator, config: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool, str]:
    mean, sigma, used_fallback, reason = posterior_or_fallback(
        state,
        observations,
        fallback,
        int(config["selection"]["gp_fallback_if_real_observations_below"]),
        float(config["selection"]["residual_scale_floor"]),
        float(config["selection"]["gp_jitter"]),
    )
    x = feature_matrix(state, mean, sigma, observations)
    p = calibrator.predict(x)
    return mean, sigma, p, used_fallback, reason


def stratified_order(state: QuestionState) -> list[str]:
    n = len(state.cheap_order)
    buckets: list[list[str]] = [[] for _ in range(10)]
    for rank, cid in enumerate(state.cheap_order):
        bucket = min(9, (rank * 10) // max(n, 1))
        buckets[bucket].append(cid)
    order: list[str] = []
    positions = [0] * len(buckets)
    while True:
        advanced = False
        for idx, bucket in enumerate(buckets):
            if positions[idx] < len(bucket):
                order.append(bucket[positions[idx]])
                positions[idx] += 1
                advanced = True
        if not advanced:
            break
    return order


def deterministic_random_order(state: QuestionState, seed: int) -> list[str]:
    q = state.q
    return sorted(
        q.candidate_ids,
        key=lambda cid: (hashlib.sha256(f"{seed}|{q.db_id}|{q.question_id}|{cid}".encode("utf-8")).hexdigest(), cid),
    )


def candidate_features_p(state: QuestionState, p: np.ndarray) -> dict[str, float]:
    return {cid: float(p[idx]) for idx, cid in enumerate(state.q.candidate_ids)}


def log_set_quality(output_ids: list[str], p_by_id: dict[str, float], all_ids: list[str]) -> float:
    output = set(output_ids)
    return float(sum(math.log1p(-float(np.clip(p_by_id[cid], 1e-4, 1.0 - 1e-4))) for cid in all_ids if cid not in output))


def expected_ramp_gain(
    state: QuestionState,
    packer: OutputPacker,
    budget_b: int,
    observations: dict[str, float],
    planned: list[str],
    mean: np.ndarray,
    sigma: np.ndarray,
    p_by_id: dict[str, float],
    candidate_id: str,
) -> float:
    ids = state.q.candidate_ids
    base_scores = dict(observations)
    for cid in planned:
        base_scores[cid] = float(np.clip(mean[state.index_by_id[cid]], 0.0, 1.0))
    current, _ = packer.pack(base_scores.keys(), base_scores, budget_b)
    current_q = log_set_quality(current, p_by_id, ids)
    idx = state.index_by_id[candidate_id]
    gains = []
    for z in QUANTILE_Z:
        simulated = float(np.clip(mean[idx] + sigma[idx] * z, 0.0, 1.0))
        scores = dict(base_scores)
        scores[candidate_id] = simulated
        output, _ = packer.pack(scores.keys(), scores, budget_b)
        gains.append(max(0.0, log_set_quality(output, p_by_id, ids) - current_q))
    return float(np.mean(gains))


def plan_ramp_batch(
    state: QuestionState,
    packer: OutputPacker,
    budget_b: int,
    observations: dict[str, float],
    mean: np.ndarray,
    sigma: np.ndarray,
    p_by_id: dict[str, float],
    remaining_tokens: int,
    cost_aware: bool,
) -> list[str]:
    planned: list[str] = []
    used = set(observations)
    virtual_remaining = int(remaining_tokens)
    while virtual_remaining > 0:
        ordered_candidates = sorted(
            (cid for cid in state.q.candidate_ids if cid not in used),
            key=lambda cid: (state.q.costs[cid], cid),
        )
        best_id = None
        best_value = -math.inf
        for cid in ordered_candidates:
            cost = state.q.costs[cid]
            if cost > virtual_remaining:
                continue
            gain = expected_ramp_gain(state, packer, budget_b, observations, planned, mean, sigma, p_by_id, cid)
            value = gain / cost if cost_aware else gain
            if value > best_value + 1e-12:
                best_value = value
                best_id = cid
        if best_id is None:
            break
        planned.append(best_id)
        used.add(best_id)
        virtual_remaining -= state.q.costs[best_id]
    return planned


def choose_boundary_candidate(
    state: QuestionState,
    observations: dict[str, float],
    mean: np.ndarray,
    sigma: np.ndarray,
    capacity: int,
    remaining_tokens: int,
) -> str | None:
    observed = set(observations)
    available = [cid for cid in state.q.candidate_ids if cid not in observed and state.q.costs[cid] <= remaining_tokens]
    if not available:
        return None
    if capacity >= len(state.q.candidate_ids):
        return min(available, key=lambda cid: (-sigma[state.index_by_id[cid]], cid))
    ranked = sorted(state.q.candidate_ids, key=lambda cid: (-mean[state.index_by_id[cid]], cid))
    inside = ranked[:max(0, capacity)]
    outside = ranked[max(0, capacity):]
    best = None
    available_set = set(available)
    for left in inside:
        for right in outside:
            possible = [cid for cid in (left, right) if cid in available_set]
            if not possible:
                continue
            left_i, right_i = state.index_by_id[left], state.index_by_id[right]
            gap = (mean[left_i] - mean[right_i]) / (sigma[left_i] + sigma[right_i] + 1e-12)
            chosen = min(possible, key=lambda cid: (-sigma[state.index_by_id[cid]], cid))
            pair = tuple(sorted((left, right)))
            key = (float(gap), pair, chosen)
            if best is None or key < best[0]:
                best = (key, chosen)
    if best is not None:
        return best[1]
    return min(available, key=lambda cid: (-sigma[state.index_by_id[cid]], cid))


def run_method(
    q: QuestionData,
    state: QuestionState,
    method: str,
    budget_b: int,
    store: ScoreReplayStore,
    role: str,
    allowed_db_ids: set[str],
    packer: OutputPacker,
    fallback: CheapScoreFallback,
    calibrator: L2LogisticCalibrator,
    config: dict[str, Any],
    cheap_calibrator: L2LogisticCalibrator | None = None,
) -> dict[str, Any]:
    m = int(config["budgets"]["M_input_tokens_per_question"])
    m0 = int(config["budgets"]["M0_first_round_input_tokens"])
    session = store.make_session(q, method, m, role, allowed_db_ids)
    observations: dict[str, float] = {}
    selected: list[str] = []
    fallback_count = 0
    fallback_reasons: Counter[str] = Counter()
    if method == "Static-TopM":
        selected = budget_fill(state.cheap_order, q.costs, m)
        observations.update(session.score_batch(selected))
    else:
        s0 = budget_fill(state.cheap_order, q.costs, m0)
        observations.update(session.score_batch(s0))
        selected.extend(s0)
        if method == "Calibrated-2R":
            if cheap_calibrator is None:
                raise RuntimeError("Calibrated-2R requires its frozen cheap-only train-db calibrator")
            mean = state.prior.copy()
            sigma = np.zeros(len(q.candidate_ids), dtype=np.float64)
            p = cheap_calibrator.predict(base_feature_matrix(state))
            used_fallback, reason = False, "cheap_only_calibrator"
        else:
            mean, sigma, p, used_fallback, reason = make_feature_probability(state, observations, fallback, calibrator, config)
        fallback_count += int(used_fallback)
        fallback_reasons[reason] += int(used_fallback)
        p_by_id = candidate_features_p(state, p)
        remaining = m - session.spent
        if method == "BoundaryMORPH-2R":
            while remaining > 0:
                check_runtime(_RUNTIME["wall"], _RUNTIME["cpu"], config)
                current_output, _ = packer.pack(selected, observations, budget_b)
                cid = choose_boundary_candidate(state, observations, mean, sigma, len(current_output), remaining)
                if cid is None:
                    break
                got = session.score_batch([cid])
                observations.update(got)
                selected.append(cid)
                remaining = m - session.spent
                mean, sigma, used_fallback, reason = posterior_or_fallback(
                    state,
                    observations,
                    fallback,
                    int(config["selection"]["gp_fallback_if_real_observations_below"]),
                    float(config["selection"]["residual_scale_floor"]),
                    float(config["selection"]["gp_jitter"]),
                )
                fallback_count += int(used_fallback)
                fallback_reasons[reason] += int(used_fallback)
        else:
            if method == "Stratified-2R":
                order = stratified_order(state)
                s1 = budget_fill(order, q.costs, remaining, already=set(selected))
            elif method == "Random-2R":
                order = deterministic_random_order(state, int(config["random_seed"]))
                s1 = budget_fill(order, q.costs, remaining, already=set(selected))
            elif method == "Calibrated-2R":
                order = sorted(q.candidate_ids, key=lambda cid: (-p_by_id[cid] / q.costs[cid], q.costs[cid], cid))
                s1 = budget_fill(order, q.costs, remaining, already=set(selected))
            elif method in ("RAMP-SL-V1", "RAMP-SL-V1-CostUnaware-Ablation"):
                s1 = plan_ramp_batch(
                    state,
                    packer,
                    budget_b,
                    observations,
                    mean,
                    sigma,
                    p_by_id,
                    remaining,
                    cost_aware=(method == "RAMP-SL-V1"),
                )
            else:
                raise ValueError(f"Unknown strategy: {method}")
            # The whole planned second-round batch is scored only after planning finishes.
            observations.update(session.score_batch(s1))
            selected.extend(s1)

    output_ids, output_tokens = packer.pack(selected, observations, budget_b)
    if session.spent > m or output_tokens > budget_b:
        raise RuntimeError(f"Replay contract violation in {method}")
    return {
        "method": method,
        "budget_B": budget_b,
        "selected_for_scoring": list(selected),
        "scored_count": len(selected),
        "replay_input_tokens": session.spent,
        "remaining_M_tokens": m - session.spent,
        "selected_output": output_ids,
        "output_tokens": output_tokens,
        "fallback_count": fallback_count,
        "fallback_reasons": dict(fallback_reasons),
        "score_read_trace": session.trace,
        "budget_contract_pass": session.spent <= m and output_tokens <= budget_b,
    }


def stable_sample(questions: list[QuestionData], db_ids: set[str], per_db: int, prefix: str) -> list[QuestionData]:
    grouped: dict[str, list[QuestionData]] = defaultdict(list)
    for q in questions:
        if q.db_id in db_ids:
            grouped[q.db_id].append(q)
    selected = []
    for db_id in sorted(grouped):
        rows = sorted(grouped[db_id], key=lambda q: (hashlib.sha256(f"{prefix}|{db_id}|{q.question_id}".encode()).hexdigest(), q.question_id))
        selected.extend(rows[:per_db])
    return selected


def verify_static_against_history(
    sample: list[QuestionData],
    predictions: list[dict[str, Any]],
    output_dir: Path,
    historical_path: Path,
    historical_run_id: str,
) -> dict[str, Any]:
    """Compare Static-TopM replay to the prior run on training-only sample rows."""
    target_keys = {q.key for q in sample}
    target_dbs = {q.db_id for q in sample}
    historical: dict[tuple[str, int], dict[str, Any]] = {}
    with historical_path.open("rb") as stream:
        for raw_line in stream:
            if not raw_line.strip():
                continue
            match = QUERY_DB_RE.search(raw_line)
            if match is None:
                raise RuntimeError("Historical replay row lacks database identity")
            db_id = json.loads(match.group(1).decode("utf-8"))
            if db_id not in target_dbs:
                continue
            row = json.loads(raw_line)
            key = (str(row["db_id"]), int(row["question_id"]))
            if key in target_keys:
                if key in historical:
                    raise RuntimeError("Duplicate historical Static-TopM question row")
                historical[key] = row
            if target_keys.issubset(historical):
                break
    if set(historical) != target_keys:
        raise RuntimeError("Historical Static-TopM replay does not cover the training audit sample")

    mismatches = []
    for q, prediction in zip(sample, predictions):
        old = historical[q.key]
        current = prediction["methods"]["Static-TopM"]
        checks = {
            "scored_candidates": old["static_candidate_ids"] == current["selected_for_scoring"],
            "input_tokens": int(old["static_candidate_tokens"]) == int(current["replay_input_tokens"]),
            "packed_columns": old["static_selected_ids"] == current["selected_output"],
            "output_tokens": int(old["static_output_tokens"]) == int(current["output_tokens"]),
        }
        if not all(checks.values()):
            mismatches.append({
                "question_key_sha256": sha256_text(f"{q.db_id}|{q.question_id}"),
                "checks": checks,
            })
    result = {
        "state": "PASS" if not mismatches else "FAIL",
        "historical_run_id": historical_run_id,
        "training_sample_questions": len(sample),
        "matching_questions": len(sample) - len(mismatches),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "comparison_fields": ["scored_candidates", "input_tokens", "packed_columns", "output_tokens"],
        "test_database_rows_parsed": 0,
        "test_gold_used": False,
    }
    write_json(output_dir / "static_regression_private.json", result)
    if mismatches:
        raise RuntimeError("Static-TopM historical regression did not pass")
    return result


def verify_prediction_rows(rows: list[dict[str, Any]], m: int, budget_by_method: dict[str, int]) -> dict[str, Any]:
    questions = len(rows)
    method_counts: Counter[str] = Counter()
    score_reads = 0
    violations = []
    non_budgeted_reference_rows = 0
    for row in rows:
        result_groups = [row.get("methods", {}), row.get("sensitivity_methods", {})]
        for group in result_groups:
            for method, result in group.items():
                method_counts[method] += 1
                trace = result.get("score_read_trace", [])
                score_reads += len(trace)
                output_budget = int(budget_by_method.get(method, result.get("budget_B", 0)))
                if int(result["output_tokens"]) > output_budget:
                    violations.append({"method": method, "reason": "output budget"})
                if len(result["selected_for_scoring"]) != int(result["scored_count"]):
                    violations.append({"method": method, "reason": "count"})
                if result.get("budget_feasible", True):
                    trace_tokens = [int(entry["input_tokens"]) for entry in trace]
                    trace_ids = [str(entry["column_id_sha256"]) for entry in trace]
                    trace_order = [int(entry["call_order"]) for entry in trace]
                    if sum(trace_tokens) != int(result["replay_input_tokens"]):
                        violations.append({"method": method, "reason": "score trace token sum"})
                    if len(trace_ids) != len(set(trace_ids)):
                        violations.append({"method": method, "reason": "duplicate score trace ID"})
                    if trace_order != list(range(len(trace_order))):
                        violations.append({"method": method, "reason": "score trace order"})
                    if int(result["replay_input_tokens"]) > m:
                        violations.append({"method": method, "reason": "input budget"})
                    if not result.get("budget_contract_pass"):
                        violations.append({"method": method, "reason": "contract flag"})
                else:
                    non_budgeted_reference_rows += 1
                    if method != "FullScore-Reference-AfterSeal" or result.get("budget_contract_pass") is not False:
                        violations.append({"method": method, "reason": "invalid non-budgeted reference flag"})
    if violations:
        raise RuntimeError(f"Prediction verification failed: {violations[:3]}")
    return {
        "prediction_question_count": questions,
        "method_row_counts": dict(method_counts),
        "score_read_trace_rows": score_reads,
        "non_budgeted_reference_rows": non_budgeted_reference_rows,
        "budget_violations": 0,
    }


def db_cluster_bootstrap(differences_by_db: dict[str, tuple[int, int]], replicates: int, seed: int) -> list[float]:
    dbs = sorted(differences_by_db)
    if not dbs:
        return [0.0, 0.0]
    rng = np.random.default_rng(seed)
    values = np.empty(replicates, dtype=np.float64)
    for rep in range(replicates):
        selected = rng.choice(dbs, size=len(dbs), replace=True)
        numerator = 0
        denominator = 0
        for db_id in selected:
            diff, count = differences_by_db[str(db_id)]
            numerator += diff
            denominator += count
        values[rep] = numerator / max(denominator, 1)
    return [float(np.percentile(values, 2.5) * 100.0), float(np.percentile(values, 97.5) * 100.0)]


def method_metrics(rows: list[dict[str, Any]], method: str, gold_by_key: dict[tuple[str, int], set[str]], budget_b: int) -> dict[str, Any]:
    correct_complete = 0
    gold_occurrences = 0
    hit_occurrences = 0
    selected_occurrences = 0
    per_question_recall = []
    per_question_precision = []
    output_tokens = []
    input_tokens = []
    field_counts = []
    at_budget = 0
    by_db: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "complete": 0, "gold": 0, "hits": 0, "selected": 0})
    for row in rows:
        key = (str(row["db_id"]), int(row["question_id"]))
        if key not in gold_by_key:
            raise RuntimeError("Evaluation labels are missing for a sealed test prediction")
        gold = gold_by_key[key]
        result = row["methods"][method]
        output = set(result["selected_output"])
        hits = len(output.intersection(gold))
        complete = int(gold.issubset(output))
        correct_complete += complete
        gold_occurrences += len(gold)
        hit_occurrences += hits
        selected_occurrences += len(output)
        per_question_recall.append(hits / len(gold) if gold else 0.0)
        per_question_precision.append(hits / len(output) if output else 0.0)
        output_tokens.append(int(result["output_tokens"]))
        input_tokens.append(int(result["replay_input_tokens"]))
        field_counts.append(int(result["scored_count"]))
        at_budget += int(int(result["output_tokens"]) == budget_b)
        db = by_db[row["db_id"]]
        db["n"] += 1
        db["complete"] += complete
        db["gold"] += len(gold)
        db["hits"] += hits
        db["selected"] += len(output)
    per_db = {}
    for db_id, data in by_db.items():
        per_db[sha256_text(db_id)] = {
            "question_count": data["n"],
            "complete_count": data["complete"],
            "complete_rate": data["complete"] / data["n"],
            "gold_columns": data["gold"],
            "gold_hits": data["hits"],
            "gold_recall_micro": data["hits"] / data["gold"] if data["gold"] else 0.0,
            "selected_columns": data["selected"],
        }
    n = len(rows)
    return {
        "question_count": n,
        "database_count": len(by_db),
        "complete_gold_column_coverage_count": correct_complete,
        "complete_gold_column_coverage_rate": correct_complete / n if n else 0.0,
        "gold_column_recall_micro": hit_occurrences / gold_occurrences if gold_occurrences else 0.0,
        "gold_column_recall_macro": float(np.mean(per_question_recall)) if per_question_recall else 0.0,
        "gold_column_precision_micro": hit_occurrences / selected_occurrences if selected_occurrences else 0.0,
        "gold_column_precision_macro": float(np.mean(per_question_precision)) if per_question_precision else 0.0,
        "mean_scored_columns": float(np.mean(field_counts)) if field_counts else 0.0,
        "mean_replay_input_tokens": float(np.mean(input_tokens)) if input_tokens else 0.0,
        "max_replay_input_tokens": max(input_tokens, default=0),
        "remaining_input_tokens_mean": float(np.mean([4096 - value for value in input_tokens])) if input_tokens else 0.0,
        "mean_output_schema_tokens": float(np.mean(output_tokens)) if output_tokens else 0.0,
        "max_output_schema_tokens": max(output_tokens, default=0),
        "questions_at_output_budget": at_budget,
        "per_database": per_db,
    }


def paired_comparison(
    rows: list[dict[str, Any]],
    a: str,
    b: str,
    gold_by_key: dict[tuple[str, int], set[str]],
    bootstrap_replicates: int,
    seed: int,
    all_db_ids: set[str] | None = None,
) -> dict[str, Any]:
    db_rescue: Counter[str] = Counter()
    db_damage: Counter[str] = Counter()
    db_n: Counter[str] = Counter()
    for db_id in all_db_ids or set():
        db_n[db_id] = 0
    for row in rows:
        key = (str(row["db_id"]), int(row["question_id"]))
        gold = gold_by_key[key]
        pred_a = set(row["methods"][a]["selected_output"])
        pred_b = set(row["methods"][b]["selected_output"])
        a_ok = gold.issubset(pred_a)
        b_ok = gold.issubset(pred_b)
        db_id = row["db_id"]
        db_n[db_id] += 1
        if a_ok and not b_ok:
            db_rescue[db_id] += 1
        elif b_ok and not a_ok:
            db_damage[db_id] += 1
    rescue = sum(db_rescue.values())
    damage = sum(db_damage.values())
    diff_by_db = {db: (db_rescue[db] - db_damage[db], db_n[db]) for db in db_n}
    ci = db_cluster_bootstrap(diff_by_db, bootstrap_replicates, seed)
    per_db = {
        sha256_text(db): {
            "rescue": db_rescue[db],
            "damage": db_damage[db],
            "net": db_rescue[db] - db_damage[db],
            "question_count": db_n[db],
        }
        for db in db_n
    }
    return {
        "method": a,
        "baseline": b,
        "rescue": rescue,
        "damage": damage,
        "net": rescue - damage,
        "difference_pp": (rescue - damage) / max(sum(db_n.values()), 1) * 100.0,
        "db_cluster_bootstrap_95_percentile_pp": ci,
        "positive_net_rescue_database_count": sum(1 for db in db_n if db_rescue[db] > db_damage[db]),
        "per_database": per_db,
    }


def write_model_artifact(path: Path, fallback: CheapScoreFallback, calibrator: L2LogisticCalibrator,
                         cheap_calibrator: L2LogisticCalibrator, train_metadata: dict[str, Any]) -> None:
    write_json(path, {
        "run_id": RUN_ID,
        "fallback": {
            "feature_names": list(BASE_FEATURE_NAMES),
            "mean": fallback.mean.tolist(),
            "scale": fallback.scale.tolist(),
            "weights": fallback.weights.tolist(),
            "intercept": fallback.intercept,
            "residual_std": fallback.residual_std,
            "ridge_lambda": fallback.ridge_lambda,
        },
        "calibrator": {
            "feature_names": list(FEATURE_NAMES),
            "mean": calibrator.mean.tolist(),
            "scale": calibrator.scale.tolist(),
            "weights": calibrator.weights.tolist(),
            "intercept": calibrator.intercept,
            "optimization": calibrator.optimization,
            "C": calibrator.c,
            "max_iterations": calibrator.max_iter,
        },
        "cheap_calibrator": {
            "feature_names": list(cheap_calibrator.feature_names),
            "mean": cheap_calibrator.mean.tolist(),
            "scale": cheap_calibrator.scale.tolist(),
            "weights": cheap_calibrator.weights.tolist(),
            "intercept": cheap_calibrator.intercept,
            "optimization": cheap_calibrator.optimization,
            "C": cheap_calibrator.c,
            "max_iterations": cheap_calibrator.max_iter,
        },
        "training_metadata": train_metadata,
    })


def run_train_only(
    mode: str,
    questions: list[QuestionData],
    train_db_ids: set[str],
    test_db_ids: set[str],
    store: ScoreReplayStore,
    fallback: CheapScoreFallback,
    calibrator: L2LogisticCalibrator,
    cheap_calibrator: L2LogisticCalibrator,
    config: dict[str, Any],
    output_dir: Path,
    tokenizer: Any,
    start_wall: float,
    start_cpu: float,
) -> dict[str, Any]:
    if mode == "smoke":
        sample = stable_sample(questions, train_db_ids, 1, "ramp-v1-smoke-20261124")
        expected = min(5, len(train_db_ids))
        if len(sample) != expected:
            raise RuntimeError("Training smoke did not select one question per train DB")
    else:
        sample = stable_sample(questions, train_db_ids, 20, "ramp-v1-train-audit-20261124")
        if len(sample) < 30:
            raise RuntimeError("Training replay audit must include at least 30 questions")
    labels = load_gold_rows(train_db_ids, expected_count=sum(1 for q in questions if q.db_id in train_db_ids))
    predictions = []
    for q in sample:
        check_runtime(start_wall, start_cpu, config)
        state = build_state(q)
        packer = OutputPacker(tokenizer, q.texts)
        methods = {}
        for method in MAIN_METHODS:
            methods[method] = run_method(
                q, state, method, int(config["budgets"]["B_output_schema_tokens"]),
                store, "train", train_db_ids, packer, fallback, calibrator, config,
                cheap_calibrator=cheap_calibrator,
            )
        predictions.append({"db_id": q.db_id, "question_id": q.question_id, "methods": methods})
        if q.key not in labels:
            raise RuntimeError("Training audit sample lacks its Gold label")
        for result in methods.values():
            if not result["budget_contract_pass"]:
                raise RuntimeError("Training smoke/audit budget check failed")
    path = output_dir / "private_train_replay.jsonl"
    write_jsonl(path, predictions)
    static_regression = verify_static_against_history(
        sample,
        predictions,
        output_dir,
        Path(config["data"]["prior_static_detail_path"]),
        str(config["data"]["prior_static_run_id"]),
    )
    return {
        "mode": mode,
        "state": "PASS_TRAIN_ONLY_REPLAY",
        "question_count": len(sample),
        "train_database_count": len({q.db_id for q in sample}),
        "test_database_count": len(test_db_ids),
        "test_gold_read": False,
        "all_method_budgets_pass": True,
        "static_historical_regression": static_regression,
        "private_prediction_sha256": sha256_file(path),
        "rows_per_method": {method: len(predictions) for method in MAIN_METHODS},
    }


def non_saturated_subset(rows: list[dict[str, Any]], gold_by_key: dict[tuple[str, int], set[str]], q_by_key: dict[tuple[str, int], QuestionData]) -> list[dict[str, Any]]:
    eligible = []
    for row in rows:
        key = (row["db_id"], int(row["question_id"]))
        q = q_by_key[key]
        full_cost = sum(q.costs.values())
        static_output = set(row["methods"]["Static-TopM"]["selected_output"])
        if full_cost > 4096 and not gold_by_key[key].issubset(static_output):
            eligible.append(row)
    return eligible


def evaluate_full(
    prediction_rows: list[dict[str, Any]],
    reference_rows: list[dict[str, Any]],
    gold_by_key: dict[tuple[str, int], set[str]],
    q_by_key: dict[tuple[str, int], QuestionData],
    config: dict[str, Any],
    heldout_db_ids: set[str],
) -> dict[str, Any]:
    rows = prediction_rows
    methods = list(rows[0]["methods"].keys()) if rows else []
    for row, reference in zip(rows, reference_rows):
        row["methods"]["FullScore-Reference-AfterSeal"] = reference["methods"]["FullScore-Reference-AfterSeal"]
    budget_by_method = {method: int(config["budgets"]["B_output_schema_tokens"]) for method in methods}
    budget_by_method["FullScore-Reference-AfterSeal"] = int(config["budgets"]["B_output_schema_tokens"])
    for sensitivity_budget in config["budgets"]["B_sensitivity_tokens"]:
        budget_by_method[f"RAMP-SL-V1@{sensitivity_budget}"] = int(sensitivity_budget)
        budget_by_method[f"Calibrated-2R@{sensitivity_budget}"] = int(sensitivity_budget)
    verification = verify_prediction_rows(rows, int(config["budgets"]["M_input_tokens_per_question"]), budget_by_method)
    evaluated_methods = [*methods, "FullScore-Reference-AfterSeal"]
    results = {
        method: method_metrics(rows, method, gold_by_key, int(config["budgets"]["B_output_schema_tokens"]))
        for method in evaluated_methods
    }
    comparisons = {
        method: paired_comparison(
            rows, method, "Static-TopM", gold_by_key,
            int(config["bootstrap"]["replicates"]), int(config["bootstrap"]["seed"]),
            all_db_ids=heldout_db_ids,
        )
        for method in methods if method != "Static-TopM"
    }
    feasible_baselines = ["Static-TopM", "Stratified-2R", "Random-2R", "BoundaryMORPH-2R", "Calibrated-2R"]
    strongest = max(feasible_baselines, key=lambda method: results[method]["complete_gold_column_coverage_rate"])
    ramp_rate = results["RAMP-SL-V1"]["complete_gold_column_coverage_rate"]
    static_rate = results["Static-TopM"]["complete_gold_column_coverage_rate"]
    strongest_rate = results[strongest]["complete_gold_column_coverage_rate"]
    ramp_vs_static = comparisons["RAMP-SL-V1"]
    gate = {
        "ramp_minus_static_pp": (ramp_rate - static_rate) * 100.0,
        "strongest_feasible_baseline": strongest,
        "ramp_minus_strongest_feasible_baseline_pp": (ramp_rate - strongest_rate) * 100.0,
        "positive_net_rescue_databases": ramp_vs_static["positive_net_rescue_database_count"],
        "budget_contract_pass": verification["budget_violations"] == 0,
        "go": (
            (ramp_rate - static_rate) * 100.0 >= float(config["success_criteria"]["ramp_minus_static_complete_coverage_pp_min"])
            and (ramp_rate - strongest_rate) * 100.0 >= float(config["success_criteria"]["ramp_minus_strongest_feasible_baseline_pp_min"])
            and ramp_vs_static["positive_net_rescue_database_count"] >= int(config["success_criteria"]["positive_net_rescue_databases_min"])
            and verification["budget_violations"] == 0
        ),
    }
    non_sat = non_saturated_subset(rows, gold_by_key, q_by_key)
    non_sat_metrics = {
        method: method_metrics(non_sat, method, gold_by_key, int(config["budgets"]["B_output_schema_tokens"]))
        for method in evaluated_methods
    } if non_sat else {}

    sensitivity_results = {}
    sensitivity_comparisons = {}
    # Sensitivity rows are attached separately to each test row after prediction sealing.
    for budget in config["budgets"]["B_sensitivity_tokens"]:
        key = f"B{budget}"
        names = [f"RAMP-SL-V1@{budget}", f"Calibrated-2R@{budget}"]
        filtered = []
        for row in rows:
            copied = dict(row)
            copied["methods"] = {name: row["sensitivity_methods"][name] for name in names}
            copied["methods"]["Static-TopM"] = row["methods"]["Static-TopM"]
            filtered.append(copied)
        # Only compare the two pre-registered sensitivity arms; the static arm is a shared reference.
        sensitivity_results[key] = {
            names[0]: method_metrics(filtered, names[0], gold_by_key, int(budget)),
            names[1]: method_metrics(filtered, names[1], gold_by_key, int(budget)),
        }
        sensitivity_comparisons[key] = paired_comparison(
            filtered, names[0], names[1], gold_by_key,
            int(config["bootstrap"]["replicates"]), int(config["bootstrap"]["seed"]),
            all_db_ids=heldout_db_ids,
        )
    set_level_qualified = any(
        sensitivity_comparisons[key]["difference_pp"] > 0.0
        and sensitivity_comparisons[key]["db_cluster_bootstrap_95_percentile_pp"][0] > 0.0
        for key in sensitivity_comparisons
    )
    return {
        "run_id": RUN_ID,
        "status": "SCIENCE_GO_WORTH_INDEPENDENT_REPLICATION" if gate["go"] else "STOP_THIS_V1",
        "evaluation_scope": "BIRD-dev database-isolated replay; exploratory only, data/model were previously exposed",
        "question_count": len(rows),
        "database_count": len({row["db_id"] for row in rows}),
        "heldout_database_count": len(heldout_db_ids),
        "methods": results,
        "paired_vs_static": comparisons,
        "strongest_feasible_baseline": strongest,
        "non_saturated_question_count": len(non_sat),
        "non_saturated_methods": non_sat_metrics,
        "B_sensitivity": sensitivity_results,
        "B_sensitivity_RAMP_vs_Calibrated": sensitivity_comparisons,
        "set_level_mechanism_qualification": set_level_qualified,
        "primary_gate": gate,
        "verification": verification,
        "bootstrap_note": "Only three test databases; the database-cluster interval is unstable and exploratory.",
        "local_model_inference_input_tokens": 0,
        "local_model_inference_output_tokens": 0,
        "external_api_calls": 0,
        "external_api_fee_cny": 0,
        "sql_execution": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--mode", choices=("smoke", "train-audit", "full"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("experiment_id") != RUN_ID:
        raise RuntimeError("Unexpected RAMP-SL V1 config")
    if git_output("branch", "--show-current") != config["project_branch"]:
        raise RuntimeError("Runner is not on the registered project branch")
    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite run directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True)
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    os.environ["OMP_NUM_THREADS"] = str(config["budgets"]["cpu_threads"])
    os.environ["MKL_NUM_THREADS"] = str(config["budgets"]["cpu_threads"])
    os.environ["OPENBLAS_NUM_THREADS"] = str(config["budgets"]["cpu_threads"])
    os.environ["NUMEXPR_NUM_THREADS"] = str(config["budgets"]["cpu_threads"])

    questions, store, context = load_inputs(config)
    train_db_ids, test_db_ids, split = derive_split(questions, config)
    train_questions = [q for q in questions if q.db_id in train_db_ids]
    test_questions = [q for q in questions if q.db_id in test_db_ids]
    # Training labels are restricted by database before Gold fields are parsed.
    train_labels, train_label_stats = load_gold_rows(
        train_db_ids, expected_count=len(train_questions), return_stats=True
    )
    fallback, calibrator, cheap_calibrator, training_metadata = fit_training_models(
        train_questions, train_db_ids, store, train_labels, config, start_wall, start_cpu
    )
    training_metadata["gold_label_eligibility"] = train_label_stats
    write_model_artifact(args.output_dir / "private_training_model.json", fallback, calibrator, cheap_calibrator, training_metadata)
    tokenizer = AutoTokenizer.from_pretrained(str(TOKENIZER_PATH), local_files_only=True, trust_remote_code=False)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    run_start = {
        "run_id": RUN_ID,
        "mode": args.mode,
        "state": "running",
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "branch": git_output("branch", "--show-current"),
            "execution_commit": git_output("rev-parse", "HEAD"),
            "runner_sha256": sha256_file(Path(__file__).resolve()),
            "config_sha256": sha256_file(args.config.resolve()),
            "preflight_private_sha256": sha256_file(PREFLIGHT_PRIVATE),
            "preflight_public_sha256": sha256_file(PREFLIGHT_PUBLIC),
            "git_status_before_run": git_output("status", "--short"),
        },
        "split": split,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": importlib.metadata.version("scipy"),
            "transformers": importlib.metadata.version("transformers"),
            "tokenizers": importlib.metadata.version("tokenizers"),
            "scikit_learn_available": importlib.util.find_spec("sklearn") is not None,
            "visible_gpu_inference": False,
        },
        "resource_snapshot": resource_snapshot(),
        "inputs": {
            "questions_sha256": config["data"]["questions_sha256"],
            "schema_sha256": config["data"]["schema_sha256"],
            "embedding_cache_sha256": config["data"]["embedding_cache_sha256"],
            "node_manifest_sha256": config["data"]["ordered_node_manifest_sha256"],
            "score_cache_sha256": config["data"]["cached_score_and_token_sha256"],
            "model_revision": config["scorer"]["revision"],
            "model_weights_sha256_from_frozen_score_receipt": config["scorer"]["weights_sha256_from_source_run"],
        },
        "training": training_metadata,
        "api_usage": {"external_calls": 0, "new_local_model_inference_tokens": 0},
    }
    write_json(args.output_dir / "run_start.json", run_start)
    if args.mode in ("smoke", "train-audit"):
        summary = run_train_only(
            "smoke" if args.mode == "smoke" else "train-audit",
            questions, train_db_ids, test_db_ids, store, fallback, calibrator, cheap_calibrator,
            config, args.output_dir, tokenizer, start_wall, start_cpu,
        )
        summary["run_id"] = RUN_ID
        summary["execution_commit"] = git_output("rev-parse", "HEAD")
        summary["runner_sha256"] = sha256_file(Path(__file__).resolve())
        summary["elapsed_wall_seconds"] = time.perf_counter() - start_wall
        summary["process_cpu_seconds"] = time.process_time() - start_cpu
        summary["resource_snapshot_end"] = resource_snapshot()
        write_json(args.output_dir / "verification_summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return

    # One-time test replay. The policies see no Gold fields and no unselected
    # cached scores. The complete score reference is deferred until after seal.
    prediction_rows: list[dict[str, Any]] = []
    prediction_tmp = args.output_dir / "private_predictions_unsealed.jsonl"
    sensitivity_names = {
        512: ("RAMP-SL-V1@512", "Calibrated-2R@512"),
        1024: ("RAMP-SL-V1@1024", "Calibrated-2R@1024"),
    }
    budget_by_method: dict[str, int] = {method: int(config["budgets"]["B_output_schema_tokens"]) for method in MAIN_METHODS}
    for b in config["budgets"]["B_sensitivity_tokens"]:
        budget_by_method[sensitivity_names[int(b)][0]] = int(b)
        budget_by_method[sensitivity_names[int(b)][1]] = int(b)
    with prediction_tmp.open("w", encoding="utf-8") as stream:
        for index, q in enumerate(test_questions, start=1):
            check_runtime(start_wall, start_cpu, config)
            state = build_state(q)
            packer = OutputPacker(tokenizer, q.texts)
            methods = {}
            for method in MAIN_METHODS:
                methods[method] = run_method(
                    q, state, method, int(config["budgets"]["B_output_schema_tokens"]),
                    store, "test", test_db_ids, packer, fallback, calibrator, config,
                    cheap_calibrator=cheap_calibrator,
                )
            row = {"db_id": q.db_id, "question_id": q.question_id, "methods": methods, "sensitivity_methods": {}}
            for b in config["budgets"]["B_sensitivity_tokens"]:
                ramp_name, calibrated_name = sensitivity_names[int(b)]
                row["sensitivity_methods"][ramp_name] = run_method(
                    q, state, "RAMP-SL-V1", int(b), store, "test", test_db_ids,
                    packer, fallback, calibrator, config, cheap_calibrator=cheap_calibrator,
                )
                row["sensitivity_methods"][calibrated_name] = run_method(
                    q, state, "Calibrated-2R", int(b), store, "test", test_db_ids,
                    packer, fallback, calibrator, config, cheap_calibrator=cheap_calibrator,
                )
            prediction_rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            if index % 25 == 0:
                os.fsync(stream.fileno())
                print(f"sealed-pending test predictions: {index}/{len(test_questions)}", flush=True)
    with prediction_tmp.open("rb") as stream:
        os.fsync(stream.fileno())
    sealed_path = args.output_dir / "private_predictions_sealed.jsonl"
    os.replace(prediction_tmp, sealed_path)
    seal_sha256 = sha256_file(sealed_path)
    write_json(args.output_dir / "prediction_seal.json", {
        "state": "SEALED_BEFORE_TEST_GOLD_READ",
        "path": sealed_path.name,
        "sha256": seal_sha256,
        "question_count": len(prediction_rows),
        "test_gold_rows_loaded_at_seal": 0,
        "sealed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    seal_sha256 = store.authorize_postseal_reference(sealed_path, len(test_questions))

    # Only now may the reference read all test scores and the evaluator read test Gold.
    reference_rows = []
    for q, row in zip(test_questions, prediction_rows):
        check_runtime(start_wall, start_cpu, config)
        scores = store.reference_scores_after_seal(q, seal_sha256, test_db_ids)
        ranked = sorted(q.candidate_ids, key=lambda cid: (-scores[cid], cid))
        selected = budget_fill(ranked, q.costs, int(config["budgets"]["M_input_tokens_per_question"]))
        output_ids, output_tokens = OutputPacker(tokenizer, q.texts).pack(selected, scores, int(config["budgets"]["B_output_schema_tokens"]))
        result = {
            "method": "FullScore-Reference-AfterSeal",
            "budget_B": int(config["budgets"]["B_output_schema_tokens"]),
            "selected_for_scoring": list(q.candidate_ids),
            "scored_count": len(q.candidate_ids),
            "replay_input_tokens": sum(q.costs.values()),
            "remaining_M_tokens": int(config["budgets"]["M_input_tokens_per_question"]) - sum(q.costs.values()),
            "selected_output": output_ids,
            "output_tokens": output_tokens,
            "fallback_count": 0,
            "fallback_reasons": {},
            "score_read_trace": [],
            "budget_contract_pass": False,
            "budget_feasible": False,
        }
        reference_rows.append({"db_id": q.db_id, "question_id": q.question_id, "methods": {"FullScore-Reference-AfterSeal": result}})
    reference_path = args.output_dir / "private_full_score_reference_after_seal.jsonl"
    write_jsonl(reference_path, reference_rows)
    # Explicit post-seal permit is enforced above, before any test Gold parsing.
    all_test_eligible_labels, test_label_stats = load_gold_rows(
        test_db_ids,
        test_db_ids=test_db_ids,
        sealed_prediction_path=sealed_path,
        expected_seal_sha256=seal_sha256,
        return_stats=True,
    )
    q_by_key = {q.key: q for q in questions}
    test_cache_keys = {q.key for q in test_questions}
    labels_outside_cached_questions = set(all_test_eligible_labels).difference(test_cache_keys)
    test_labels = {
        key: gold for key, gold in all_test_eligible_labels.items()
        if key in test_cache_keys
    }
    evaluable_predictions = [
        row for row in prediction_rows
        if (row["db_id"], int(row["question_id"])) in test_labels
    ]
    evaluable_reference_rows = [
        reference for reference in reference_rows
        if (reference["db_id"], int(reference["question_id"])) in test_labels
    ]
    for row in evaluable_predictions:
        key = (row["db_id"], int(row["question_id"]))
        if not test_labels[key].issubset(q_by_key[key].candidate_ids):
            raise RuntimeError("Test Gold column lies outside the frozen candidate universe")
    eligibility_receipt = {
        "cache_complete_heldout_questions": len(test_questions),
        "evaluable_heldout_questions": len(test_labels),
        "cached_questions_without_eligible_gold": len(test_cache_keys.difference(test_labels)),
        "eligible_gold_rows_outside_cached_questions": len(labels_outside_cached_questions),
        "label_file_rows_parsed_after_seal": test_label_stats["label_rows_parsed_for_allowed_databases"],
        "eligible_label_rows_parsed_after_seal": test_label_stats["eligible_label_rows"],
        "ineligible_label_rows_parsed_after_seal": test_label_stats["ineligible_label_rows"],
        "test_gold_rows_before_prediction_seal": 0,
    }
    write_json(args.output_dir / "postseal_eligibility_private.json", eligibility_receipt)
    if len(test_labels) < 80:
        hold = {
            "run_id": RUN_ID,
            "status": "HOLD_INSUFFICIENT_EVALUABLE_TEST_COVERAGE",
            "evaluation_scope": "BIRD-dev database-isolated replay; exploratory only, data/model were previously exposed",
            "eligibility": eligibility_receipt,
            "test_database_hashes": split["test_db_hashes"],
            "training_database_hashes": split["train_db_hashes"],
            "new_local_model_inference_tokens": 0,
            "external_api_calls": 0,
            "sql_execution": False,
        }
        write_json(args.output_dir / "aggregate_private.json", hold)
        write_json(args.output_dir / "aggregate_public.json", hold)
        write_json(args.output_dir / "verification_summary.json", {
            "state": hold["status"],
            "sealed_prediction_sha256": seal_sha256,
            "sealed_prediction_rows": len(prediction_rows),
            "test_gold_loaded_after_seal": True,
            "test_gold_rows_before_seal": 0,
            "eligibility": eligibility_receipt,
        })
        print(json.dumps(hold, ensure_ascii=False, indent=2, sort_keys=True))
        return
    aggregate = evaluate_full(
        evaluable_predictions, evaluable_reference_rows, test_labels, q_by_key, config, test_db_ids
    )
    aggregate.update({
        "execution_commit": git_output("rev-parse", "HEAD"),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "config_sha256": sha256_file(args.config.resolve()),
        "prediction_seal_sha256": seal_sha256,
        "full_score_reference_sha256": sha256_file(reference_path),
        "test_database_hashes": split["test_db_hashes"],
        "training_database_hashes": split["train_db_hashes"],
        "training_metadata": training_metadata,
        "test_gold_rows_read_after_seal": test_label_stats["label_rows_parsed_for_allowed_databases"],
        "eligibility": eligibility_receipt,
        "test_policy_selected_score_reads_before_seal": sum(
            len(result["score_read_trace"])
            for row in prediction_rows
            for result in [*row["methods"].values(), *row["sensitivity_methods"].values()]
        ),
        "test_policy_unselected_score_reads_before_seal": 0,
        "test_gold_rows_before_prediction_seal": 0,
        "test_policy_score_reads_after_first_round": True,
        "api_usage": {"external_calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "fee_cny": 0},
        "resource_snapshot_end": resource_snapshot(),
        "process_cpu_seconds": time.process_time() - start_cpu,
        "elapsed_wall_seconds": time.perf_counter() - start_wall,
    })
    write_json(args.output_dir / "aggregate_private.json", aggregate)
    # The public aggregate contains no question IDs, database names, Gold IDs, or score traces.
    public = {k: v for k, v in aggregate.items() if k not in {"execution_commit", "runner_sha256", "config_sha256", "prediction_seal_sha256", "full_score_reference_sha256", "training_metadata", "test_gold_rows_read_after_seal", "test_gold_rows_before_prediction_seal", "test_policy_score_reads_after_first_round", "resource_snapshot_end"}}
    public["heldout_database_count"] = len(test_db_ids)
    public["training_database_count"] = len(train_db_ids)
    write_json(args.output_dir / "aggregate_public.json", public)
    verification = {
        "state": "PASS_POSTSEAL_AGGREGATE_AND_BUDGET_VERIFICATION",
        "sealed_prediction_sha256": seal_sha256,
        "sealed_prediction_rows": len(prediction_rows),
        "test_gold_loaded_after_seal": True,
        "test_gold_rows": len(test_labels),
        "test_gold_rows_before_seal": 0,
        "main_methods_budget_violations": 0,
        "policy_score_values_only_via_score_session": True,
        "full_score_reference_after_seal": True,
        "new_local_model_inference_tokens": 0,
        "external_api_calls": 0,
        "primary_gate": aggregate["primary_gate"],
    }
    write_json(args.output_dir / "verification_summary.json", verification)
    write_json(args.output_dir / "score_api_read_receipt_private.json", {
        "selected_score_reads_before_seal": sum(
            len(result["score_read_trace"])
            for row in prediction_rows
            for result in [*row["methods"].values(), *row["sensitivity_methods"].values()]
        ),
        "unselected_score_reads_before_seal": 0,
        "test_gold_rows_before_seal": 0,
        "postseal_reference_questions": len(store._replay_read_trace),
        "postseal_reference_trace": store._replay_read_trace,
        "note": "Policy-visible test score reads are recorded per method inside private_predictions_sealed.jsonl; unselected values were not returned to policy code.",
    })
    print(json.dumps({
        "status": aggregate["status"],
        "test_questions": aggregate["question_count"],
        "test_databases": aggregate["database_count"],
        "primary_gate": aggregate["primary_gate"],
        "prediction_seal_sha256": seal_sha256,
        "elapsed_wall_seconds": aggregate["elapsed_wall_seconds"],
        "process_cpu_seconds": aggregate["process_cpu_seconds"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


_RUNTIME = {"wall": 0.0, "cpu": 0.0}


if __name__ == "__main__":
    # run_method's only polling hook uses these initialized once here.
    _RUNTIME["wall"] = time.perf_counter()
    _RUNTIME["cpu"] = time.process_time()
    main()
