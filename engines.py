"""Review engines for the Controls Submittal Review Agent v2.

  gemma3:4b       the local model through Ollama on this machine (default, free)
  claude-haiku    Claude Haiku 5.5 through the Anthropic API (opt-in)
  claude-sonnet   Claude Sonnet 5.5 through the Anthropic API (opt-in)

Every engine gets the same prompt text and the same reply schema, and every
reply goes through the same code checks in the agent. The Claude engines differ
only in transport: the instructions go in a cached system block (prompt caching
on), the reply format goes in output_config.format, and each call is priced
from its usage and written to a spend ledger. A hard stop refuses any call
that could take the total past the task budget.

The API key comes from the ANTHROPIC_API_KEY environment variable. It is never
printed, logged or written to any file by this code.

Privacy: v1 never sent anything off the machine. The Claude engines keep that
the default: they only run on the frozen public and synthetic test sets unless
the caller passes allow_cloud=True (the --allow-cloud flag).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import submittal_review as sr

HERE = Path(__file__).resolve().parent
DEFAULT_ENGINE = "gemma3:4b"
ENGINE_CHOICES = ("gemma3:4b", "claude-haiku", "claude-sonnet")
CLAUDE_MODELS = {"claude-haiku": "claude-haiku-5-5", "claude-sonnet": "claude-sonnet-5-5"}
# USD per million tokens, Anthropic first-party API list prices (skill reference cached 2026-11-03).
# Cache writes are 1.25x input (5 minute TTL); cache reads are 0.1x on Haiku 5.5 and 0.05x on Sonnet 5.5.
PRICES_PER_MTOK = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01,
                         "long_input": 0.50, "long_output": 2.50, "long_threshold": 100_000},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.10},
}
CLAUDE_EFFORT = "medium"  # set explicitly and logged: Haiku 5.5 defaults to medium, Sonnet 5.5 to high
CLAUDE_MAX_TOKENS = 8000  # thinking plus the JSON reply; a reply cut off here is a failed attempt
TASK_BUDGET_USD = 50.00  # hard stop for the whole v2 task, across every run
LEDGER = HERE / "validation" / "v2" / "spend_ledger.jsonl"
OLLAMA_NUM_CTX = 8192  # v2 prompts carry a whole section; v1 prompts are unchanged


class BudgetExceeded(RuntimeError):
    """The next call could take total Claude spend past the task budget; the run stops cleanly."""


# Build Guide: v2 cost control
# Decision: one ledger of every Claude call; before a call, reserve its worst case cost and refuse it if the
#           ledger total plus every open reservation plus this worst case would pass the cap
class SpendGuard:
    def __init__(self, ledger: Path = LEDGER, cap_usd: float = TASK_BUDGET_USD) -> None:
        self.ledger, self.cap = Path(ledger), float(cap_usd)
        self._lock = threading.Lock()
        self._reserved = 0.0

    def spent(self) -> float:
        if not self.ledger.is_file():
            return 0.0
        total = 0.0
        for line in self.ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                total += float(json.loads(line).get("cost_usd", 0.0))
        return total

    def remaining(self) -> float:
        return self.cap - self.spent()

    def reserve(self, worst_usd: float) -> None:
        with self._lock:
            spent = self.spent()  # re-read so spend from earlier runs always counts
            if spent + self._reserved + worst_usd > self.cap:
                raise BudgetExceeded(f"hard stop: spent ${spent:.4f} of ${self.cap:.2f}; the next call could cost up to "
                                     f"${worst_usd:.4f}, which would pass the budget")
            self._reserved += worst_usd

    def release(self, worst_usd: float) -> None:
        with self._lock:
            self._reserved = max(0.0, self._reserved - worst_usd)

    def record(self, entry: dict, worst_usd: float) -> None:
        with self._lock:
            self._reserved = max(0.0, self._reserved - worst_usd)
            self.ledger.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")


def cost_usd(model: str, usage: Any) -> float:
    """Price one call from its usage block. Unknown models cost nothing here and are refused earlier."""
    pr = PRICES_PER_MTOK[model]
    fresh = int(getattr(usage, "input_tokens", 0) or 0)
    write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    inp, outp = pr["input"], pr["output"]
    if "long_threshold" in pr and fresh + write + read > pr["long_threshold"]:
        inp, outp = pr["long_input"], pr["long_output"]
    return (fresh * inp + write * pr["cache_write"] * inp / pr["input"] + read * pr["cache_read"] * inp / pr["input"]
            + out * outp) / 1_000_000


def strict_schema(schema: dict) -> dict:
    """The same reply schema, in the subset structured outputs accept: every object closed, no length limits."""
    drop = {"title", "default", "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems"}

    def walk(node):
        if isinstance(node, dict):
            out = {k: walk(v) for k, v in node.items() if k not in drop}
            if out.get("type") == "object":
                out["additionalProperties"] = False
                out.setdefault("required", list(out.get("properties", {})))
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(json.loads(json.dumps(schema)))


# Build Guide: v2 privacy
# Decision: a cloud engine runs only on frozen public or synthetic test sets unless the person passes --allow-cloud
def frozen_public_set(folder: Path) -> bool:
    folder = Path(folder)
    if sr.run_identity(folder)["full_text_logging"]:  # a frozen v1 fixture or evaluation set
        return True
    manifest = HERE / "validation" / "v2" / "datasets_v2.json"
    if not manifest.is_file():
        return False
    man = json.loads(manifest.read_text(encoding="utf-8"))
    hashes = {}
    for name in ("spec.txt", "submittal_sequence.txt", "submittal_points.csv", "drawing_list.csv"):
        p = folder / name
        if not p.is_file():
            return False
        hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    for case in man.get("cases", {}).values():
        for twin in ("seeded", "clean"):
            if all(case["files"].get(f"{twin}/{n}") == h for n, h in hashes.items()):
                return True
    return False


def check_cloud_allowed(engine: str, folder: Path, allow_cloud: bool) -> None:
    if engine in CLAUDE_MODELS and not allow_cloud and not frozen_public_set(folder):
        raise ValueError(f"{engine} sends the package to the Anthropic API. {Path(folder).name} is not a frozen public "
                         "or synthetic test set, so it stays on this machine. Pass --allow-cloud to send it anyway.")


# ---------------------------------------------------------------------------
# Local engine: gemma3:4b through Ollama
# ---------------------------------------------------------------------------
class OllamaEngine(sr.OllamaClient):
    """The v1 Ollama client (localhost only, temperature from the config) plus a v2 generate() call."""

    engine = "gemma3:4b"

    def generate(self, system: str, user: str, schema: dict, tag: str = "") -> str:
        payload = {"model": self.config.model_name, "system": system, "prompt": user, "stream": False,
                   "format": strict_schema(schema), "options": {"temperature": self.config.temperature,
                                                                "num_ctx": OLLAMA_NUM_CTX}}
        limit = self.config.model_timeout_seconds
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self._call, "/api/generate", payload, limit + 5)
        try:
            body = future.result(timeout=limit)
            self.last_usage = {"prompt_tokens": body.get("prompt_eval_count"), "reply_tokens": body.get("eval_count"),
                               "cost_usd": 0.0}
            return body["response"]
        except FutureTimeout:
            raise TimeoutError(f"no reply within {limit} seconds") from None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------------
# Cloud engines: Claude Haiku 5.5 and Claude Sonnet 5.5
# ---------------------------------------------------------------------------
class ClaudeEngine:
    """Claude through the Anthropic SDK. The client is injectable so tests run with the API mocked."""

    def __init__(self, engine: str, config: sr.ReviewConfig, guard: Optional[SpendGuard] = None, client: Any = None,
                 effort: str = CLAUDE_EFFORT, max_tokens: int = CLAUDE_MAX_TOKENS, run_label: str = "") -> None:
        if engine not in CLAUDE_MODELS:
            raise ValueError(f"unknown Claude engine {engine}")
        self.engine, self.model = engine, CLAUDE_MODELS[engine]
        self.name = f"anthropic:{self.model}"
        self.model_digest = f"{self.model} (effort {effort}, max_tokens {max_tokens})"
        self.config, self.guard = config, guard or SpendGuard()
        self.effort, self.max_tokens, self.run_label = effort, max_tokens, run_label
        self._client = client
        self.last_usage: Optional[dict] = None
        self.context = ""  # set by the caller to the case and item being checked, for the ledger

    def preflight(self) -> None:
        if self._client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise sr.ModelUnavailableError("ANTHROPIC_API_KEY is not set in the environment. Set it in this "
                                               "shell, then run again. The key is never printed or logged.")
            import anthropic
            self._client = anthropic.Anthropic(timeout=float(self.config.model_timeout_seconds), max_retries=2)
        if self.guard.remaining() <= 0:
            raise BudgetExceeded(f"hard stop: the ${self.guard.cap:.2f} budget is already spent")

    def _worst_case(self, text: str) -> float:
        pr = PRICES_PER_MTOK[self.model]
        tokens_in = len(text.encode("utf-8"))  # bytes never undercount tokens, so the estimate fails safe
        return (tokens_in * pr.get("long_input", pr["input"]) * 1.25
                + self.max_tokens * pr.get("long_output", pr["output"])) / 1_000_000

    def generate(self, system: Optional[str], user: str, schema: dict, tag: str = "") -> str:
        if self._client is None:
            self.preflight()
        worst = self._worst_case((system or "") + user)
        self.guard.reserve(worst)
        kwargs = dict(model=self.model, max_tokens=self.max_tokens,
                      messages=[{"role": "user", "content": user}],
                      output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": strict_schema(schema)}})
        if system:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        else:
            kwargs["cache_control"] = {"type": "ephemeral"}
        started = time.monotonic()
        try:
            resp = self._client.messages.create(**kwargs)
        except BaseException:
            self.guard.release(worst)
            raise
        usage = resp.usage
        cost = cost_usd(self.model, usage)
        entry = {"at": datetime.now().isoformat(timespec="seconds"), "engine": self.engine, "model": self.model,
                 "run": self.run_label, "item": tag or self.context, "seconds": round(time.monotonic() - started, 2),
                 "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                 "cache_creation_input_tokens": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
                 "cache_read_input_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
                 "output_tokens": int(getattr(usage, "output_tokens", 0) or 0), "stop_reason": resp.stop_reason,
                 "request_id": getattr(resp, "_request_id", None) or getattr(resp, "id", None), "cost_usd": round(cost, 8)}
        self.guard.record(entry, worst)
        self.last_usage = {k: entry[k] for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                                                 "output_tokens", "cost_usd")}
        if resp.stop_reason == "refusal":
            raise RuntimeError("the model declined to answer (stop_reason refusal)")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError(f"reply cut off at max_tokens {self.max_tokens}")
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    def classify(self, item: "sr.FindingWithContext", prompt: str) -> str:
        """The v1 N7 call: the same prompt and the same reply format the Ollama client sends."""
        return self.generate(None, prompt, sr.reply_schema(sr.allowed_verdicts(item)), tag=item.finding.finding_id)


def make_engine(engine: str, config: sr.ReviewConfig, ollama_url: str = sr.DEFAULT_OLLAMA_URL,
                guard: Optional[SpendGuard] = None, client: Any = None, run_label: str = ""):
    if engine == "gemma3:4b":  # the local engine runs the configured Ollama model (gemma3:4b unless a config says otherwise)
        return OllamaEngine(config, ollama_url)
    if engine in CLAUDE_MODELS:
        return ClaudeEngine(engine, config, guard=guard, client=client, run_label=run_label)
    raise ValueError(f"unknown engine {engine}; choose one of {', '.join(ENGINE_CHOICES)}")
