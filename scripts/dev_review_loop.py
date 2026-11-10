#!/usr/bin/env python3
"""Development and review circle for this repository.

The control flow follows the local research loop used by QML-FF: review, one
registered candidate, a measurement taken from that attempt, then an explicit
stop reason. This file is a trusted local runner, not a sandbox and not a
second agent runtime. It does not register a tool, start a session, or submit
work to a scheduler.

Product source is intentionally outside the source fingerprint. An open
implement candidate carries the reviewed edits, and this runner applies them
inside allowed_paths before measuring. A measurement that is not kept restores
those files. This runner does not edit itself, the plan, or the scripts the
plan launches. Start the next round in a new output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SCHEDULER_COMMANDS = frozenset(
    {
        "sbatch",
        "srun",
        "salloc",
        "scancel",
        "squeue",
        "scontrol",
        "qsub",
        "qstat",
        "qdel",
        "bsub",
        "bjobs",
        "bkill",
        "msub",
        "yhbatch",
        "yhrun",
        "yhalloc",
    }
)
FINISHED = frozenset({
    "drained", "kept", "discarded", "exhausted", "planned", "requires_new_review",
})
CLEAN_EXIT = frozenset({
    "drained", "kept", "planned", "needs_implementation", "requires_new_review",
})
_FROZEN_PARTS = frozenset({"node_modules", ".dsh-home", ".dsh-module-fallback"})
_KERNEL_FILES = frozenset({"scripts/dsh-cli.mjs"})


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _finite_number(value: Any, name: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ValueError(f"{name} must be finite" + (" and nonnegative" if nonnegative else ""))
    return result


def _relative_path(value: Any, name: str) -> str:
    text = str(value)
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts or path == Path("."):
        raise ValueError(f"{name} must be a relative path without parent traversal")
    return text


def _contained_file(root: Path, relative: str) -> Path:
    path = (root / _relative_path(relative, "artifact path")).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("artifact path resolves outside this attempt")
    return path


def _command_tokens(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise ValueError("command must be a list of tokens")
    tokens = tuple(str(item) for item in raw)
    if not tokens or not tokens[0]:
        raise ValueError("command must not be empty")
    return tokens


def _format_tokens(tokens: Sequence[str], values: Mapping[str, Any]) -> list[str]:
    rendered: list[str] = []
    for token in tokens:
        text = str(token)
        for key, value in values.items():
            text = text.replace("{" + key + "}", str(value))
        if "{" in text or "}" in text:
            raise ValueError(f"unresolved placeholder in command token: {text}")
        rendered.append(text)
    return rendered


def _has_scheduler_command(tokens: Sequence[str]) -> bool:
    return any(Path(token).name in SCHEDULER_COMMANDS for token in tokens)


def _git_identity(repo_root: Path) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            return subprocess.check_output(
                ["git", *args], cwd=repo_root, stderr=subprocess.DEVNULL, text=True
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    status = run("status", "--short")
    return {
        "commit": run("rev-parse", "HEAD"),
        "branch": run("branch", "--show-current"),
        "dirty": bool(status),
    }


def _source_fingerprint(plan: DevPlan, config_path: Path) -> dict[str, Any]:
    files: dict[str, dict[str, str | None]] = {}

    def record(path: Path) -> None:
        target = path.absolute()
        files[str(target)] = {
            "sha256": _sha256_file(target) if target.is_file() else None,
        }

    record(Path(__file__))
    record(config_path)
    commands = [plan.run_command, *plan.review_commands]
    if plan.proposal_command is not None:
        commands.append(plan.proposal_command)
    for command in commands:
        for index, token in enumerate(command):
            if index and command[index - 1] in {"-c", "--command"}:
                continue
            if Path(token).suffix in {".py", ".sh"} and "{" not in token and "}" not in token:
                script = Path(token)
                record(script if script.is_absolute() else plan.repo_root / script)
    encoded = json.dumps(files, sort_keys=True).encode()
    return {"sha256": _sha256_bytes(encoded), "files": files}


@dataclass(frozen=True)
class DevPlan:
    repo_root: Path
    task_id: str
    experiment_id: str
    review_commands: tuple[tuple[str, ...], ...]
    run_command: tuple[str, ...]
    primary_metric: str
    metric_file: str
    metric_direction: str
    baseline_metric: float
    minimum_effect: float
    timeout_seconds: float | None
    budget_total: float
    currency: str
    max_rounds: int
    max_attempts: int
    max_consecutive_failures: int
    stop_on_keep: bool
    task_bound: bool
    deadline_at: datetime | None
    required_artifacts: tuple[str, ...]
    candidates: tuple[dict[str, Any], ...]
    proposal_command: tuple[str, ...] | None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, config_path: Path) -> DevPlan:
        repo_value = Path(str(raw.get("repo_root", ".")))
        repo_root = repo_value if repo_value.is_absolute() else config_path.parent / repo_value
        metric = raw.get("metric")
        resources = raw.get("resources")
        loop = raw.get("loop")
        if not isinstance(metric, Mapping) or not isinstance(resources, Mapping):
            raise ValueError("metric and resources sections are required")
        if not isinstance(loop, Mapping):
            raise ValueError("loop section is required")
        direction = str(metric.get("direction", ""))
        if direction not in {"minimize", "maximize"}:
            raise ValueError("metric.direction must be minimize or maximize")
        max_rounds = int(loop.get("max_rounds", 1))
        max_attempts = int(loop.get("max_attempts", max_rounds))
        max_failures = int(loop.get("max_consecutive_failures", 1))
        if min(max_rounds, max_attempts, max_failures) < 1:
            raise ValueError("loop limits must be >= 1")
        raw_timeout = resources.get("timeout_seconds", 0)
        timeout_seconds = (
            None
            if raw_timeout is None
            else _finite_number(raw_timeout, "timeout_seconds", nonnegative=True)
        )
        reviews = raw.get("review_commands")
        candidates = raw.get("candidates", [])
        artifacts = raw.get("required_artifacts", [])
        if not isinstance(reviews, list) or not reviews:
            raise ValueError("review_commands must be a non-empty list")
        if not isinstance(candidates, list) or not isinstance(artifacts, list):
            raise ValueError("candidates and required_artifacts must be lists")
        seen: set[str] = set()
        copied: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates, start=1):
            copied.append(_validate_candidate(candidate, index, seen))
        proposal_raw = raw.get("proposal_command")
        proposal_command = None if not proposal_raw else _command_tokens(proposal_raw)
        deadline_raw = loop.get("deadline_at")
        deadline = None
        if deadline_raw not in (None, ""):
            deadline = datetime.fromisoformat(str(deadline_raw))
            if deadline.tzinfo is None:
                raise ValueError("deadline_at must include a timezone")
        return cls(
            repo_root=repo_root.resolve(),
            task_id=str(raw["task_id"]),
            experiment_id=str(raw["experiment_id"]),
            review_commands=tuple(_command_tokens(item) for item in reviews),
            run_command=_command_tokens(raw["run_command"]),
            primary_metric=str(metric["primary"]),
            metric_file=_relative_path(metric["file"], "metric.file"),
            metric_direction=direction,
            baseline_metric=_finite_number(metric["baseline"], "baseline"),
            minimum_effect=_finite_number(metric["minimum_effect"], "minimum_effect", nonnegative=True),
            timeout_seconds=timeout_seconds,
            budget_total=_finite_number(resources["budget_total"], "budget_total", nonnegative=True),
            currency=str(resources.get("currency", "check")),
            max_rounds=max_rounds,
            max_attempts=max_attempts,
            max_consecutive_failures=max_failures,
            stop_on_keep=bool(loop.get("stop_on_keep", False)),
            task_bound=loop.get("task_bound") is True,
            deadline_at=deadline,
            required_artifacts=tuple(str(item) for item in artifacts),
            candidates=tuple(copied),
            proposal_command=proposal_command,
        )


def _validate_candidate(candidate: Any, index: int, seen: set[str]) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        raise ValueError(f"candidate {index} must be an object")
    if "metric" in candidate or "checks_failed" in candidate:
        raise ValueError(f"candidate {index} cannot carry its own metric")
    identifier = str(candidate.get("id", ""))
    if not identifier or not identifier.replace("-", "").isalnum() or identifier != identifier.lower():
        raise ValueError(f"candidate {index} id must be lowercase ascii")
    if identifier in seen:
        raise ValueError(f"duplicate candidate id {identifier}")
    seen.add(identifier)
    hypothesis = candidate.get("hypothesis")
    if not isinstance(hypothesis, str) or not hypothesis.strip():
        raise ValueError(f"candidate {identifier} needs a hypothesis")
    kind = str(candidate.get("kind", "verify"))
    status = str(candidate.get("status", "ready"))
    if kind not in {"verify", "implement"} or status not in {"ready", "open"}:
        raise ValueError(f"candidate {identifier} has an unknown kind or status")
    if kind == "verify" and status != "ready":
        raise ValueError(f"verify candidate {identifier} must be ready")
    copied = dict(candidate)
    copied["cost"] = _finite_number(candidate.get("cost", 1), f"{identifier} cost", nonnegative=True)
    edits = copied.get("edits")
    if edits is not None:
        if kind != "implement":
            raise ValueError(f"verify candidate {identifier} cannot carry edits")
        if not isinstance(edits, list):
            raise ValueError(f"candidate {identifier} edits must be a list")
        for edit_index, edit in enumerate(edits, start=1):
            if not isinstance(edit, Mapping) or not all(
                isinstance(edit.get(key), str) for key in ("path", "old", "new")
            ):
                raise ValueError(
                    f"candidate {identifier} edit {edit_index} needs path, old, and new"
                )
    return copied


def load_plan(path: str | Path) -> DevPlan:
    config_path = Path(path).expanduser().resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("plan must be a JSON object")
    return DevPlan.from_mapping(raw, config_path=config_path)


def _kernel_frozen_error(text: str) -> str | None:
    path = Path(text)
    if any(part in _FROZEN_PARTS for part in path.parts):
        return f"已安装的 DSH 运行时不改：{text}"
    if text in _KERNEL_FILES:
        return "DSH 的 runCli 入口不改。启动界面是公司账号和密码，不在这个文件里。"
    return None


def _development_order_error(candidate: Mapping[str, Any]) -> str | None:
    paths = candidate.get("allowed_paths")
    if not isinstance(paths, list) or not paths:
        return "实现候选需要填写 allowed_paths。"
    prefixes = (
        "contracts/",
        "src/",
        "packages/",
        "profiles/",
        "tests/",
        "docs/",
        "scripts/",
        "desktop/",
        "knowledge/",
        "skills/",
        "apps/",
        "view/",
    )
    code_prefixes = ("contracts/", "src/", "packages/", "profiles/", "apps/", "view/")
    normalized: list[str] = []
    for item in paths:
        text = str(item).replace("\\", "/")
        path = Path(text)
        if not text or path.is_absolute() or ".." in path.parts:
            return "allowed_paths 必须留在仓库内部。"
        if not text.startswith(prefixes):
            return f"路径不在开发圈子内：{text}"
        normalized.append(text)
    needs_test = any(item.startswith(code_prefixes) for item in normalized)
    if needs_test and not any(item.startswith("tests/") for item in normalized):
        return "合同、适配器、插件、预设或原生界面的改动必须同时写上 tests/ 路径。"
    return None


def _restore_files(repo: Path, originals: Mapping[str, str]) -> None:
    for rel, text in originals.items():
        (repo / rel).write_text(text, encoding="utf-8", newline="\n")


def _apply_candidate_edits(
    repo: Path,
    candidate: Mapping[str, Any],
    *,
    protected: set[Path],
) -> dict[str, str]:
    """Replace each unique old string. Write nothing until every edit matches."""
    edits = candidate.get("edits")
    if not isinstance(edits, list) or not edits:
        raise ValueError("实现候选没有可应用的改动。")
    allowed = {str(item).replace("\\", "/") for item in candidate.get("allowed_paths") or []}
    repo_root = repo.resolve()
    originals: dict[str, str] = {}
    updated: dict[str, str] = {}
    for index, edit in enumerate(edits, start=1):
        if not isinstance(edit, Mapping):
            raise ValueError(f"第 {index} 处改动必须是对象。")
        rel = str(edit.get("path", "")).replace("\\", "/")
        old = edit.get("old")
        new = edit.get("new")
        if rel not in allowed:
            raise ValueError(f"改动路径不在允许名单里：{rel}")
        frozen = _kernel_frozen_error(rel)
        if frozen:
            raise ValueError(frozen)
        if not isinstance(old, str) or not old or not isinstance(new, str) or old == new:
            raise ValueError(f"改动需要不相等的旧文本和新文本：{rel}")
        path = (repo / rel).resolve()
        try:
            path.relative_to(repo_root)
        except ValueError as exc:
            raise ValueError(f"改动路径越出仓库：{rel}") from exc
        if path in protected:
            raise ValueError(f"本拍不能改循环自己的程序或计划：{rel}")
        if rel not in updated:
            if not path.is_file():
                raise ValueError(f"改动目标不存在：{rel}")
            text = path.read_text(encoding="utf-8")
            originals[rel] = text
            updated[rel] = text
        count = updated[rel].count(old)
        if count != 1:
            raise ValueError(f"旧文本不是唯一匹配：{rel}（{count}）")
        updated[rel] = updated[rel].replace(old, new, 1)
    written: list[str] = []
    try:
        for rel, text in updated.items():
            (repo / rel).write_text(text, encoding="utf-8", newline="\n")
            written.append(rel)
    except OSError as exc:
        _restore_files(repo, {rel: originals[rel] for rel in written})
        raise ValueError(f"写入改动失败：{exc}") from exc
    return originals


def _decision(
    plan: DevPlan,
    *,
    metric_value: float | None,
    execution_state: str,
    artifacts: Sequence[str],
) -> dict[str, Any]:
    if execution_state != "succeeded":
        return {"action": "stop", "reason": "command failed"}
    if metric_value is None or not math.isfinite(metric_value):
        return {"action": "escalate", "reason": "primary metric is missing or non-finite"}
    available = set(artifacts) | {"attempt.json"}
    missing = [item for item in plan.required_artifacts if item not in available]
    if missing:
        return {"action": "escalate", "reason": f"required artifacts missing: {missing}"}
    if plan.metric_direction == "minimize":
        improvement = plan.baseline_metric - metric_value
    else:
        improvement = metric_value - plan.baseline_metric
    if not math.isfinite(improvement):
        return {"action": "escalate", "reason": "metric improvement is non-finite"}
    if improvement < plan.minimum_effect:
        return {
            "action": "discard",
            "reason": "minimum observable effect not reached",
            "improvement": improvement,
            "minimum_effect": plan.minimum_effect,
        }
    return {
        "action": "keep",
        "reason": "primary metric passed",
        "improvement": improvement,
        "minimum_effect": plan.minimum_effect,
    }


def _metrics_from_attempt(attempt_dir: Path, plan: DevPlan) -> tuple[float | None, str | None]:
    try:
        payload = json.loads(_contained_file(attempt_dir, plan.metric_file).read_text(encoding="utf-8"))
        value = _finite_number(payload[plan.primary_metric], "primary metric")
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        return None, f"metric extraction failed: {exc}"
    return value, None


def _kill_process(process: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, 9)
        except ProcessLookupError:
            return
        return
    if process.poll() is None:
        process.kill()


def _run_command(
    tokens: Sequence[str],
    *,
    cwd: Path,
    attempt_dir: Path,
    timeout_seconds: float | None,
    dry_run: bool,
    candidate_id: str = "",
) -> dict[str, Any]:
    command = list(tokens)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    _write_json(attempt_dir / "command.json", {"argv": command, "cwd": str(cwd)})
    if _has_scheduler_command(command):
        (attempt_dir / "stdout.log").write_text("", encoding="utf-8", newline="\n")
        withheld = "scheduler submission withheld\n"
        (attempt_dir / "stderr.log").write_text(withheld, encoding="utf-8", newline="\n")
        return {
            "state": "withheld",
            "returncode": None,
            "duration_seconds": 0.0,
            "launched": False,
            "error": "scheduler submission withheld",
        }
    if timeout_seconds is not None and timeout_seconds <= 0:
        (attempt_dir / "stdout.log").write_text("", encoding="utf-8", newline="\n")
        (attempt_dir / "stderr.log").write_text("deadline reached\n", encoding="utf-8", newline="\n")
        return {
            "state": "withheld",
            "returncode": None,
            "duration_seconds": 0.0,
            "launched": False,
            "error": "deadline reached",
        }
    if dry_run:
        return {"state": "planned", "returncode": None, "duration_seconds": 0.0, "launched": False}
    started = datetime.now(UTC)
    env = dict(os.environ)
    env["COMPANY_DEV_REVIEW_ATTEMPT_DIR"] = str(attempt_dir)
    env["COMPANY_DEV_REVIEW_CANDIDATE"] = candidate_id
    process = None
    stdout: bytes | str | None = None
    stderr: bytes | str | None = None
    error = None
    state = "failed"
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=(os.name == "posix"),
            env=env,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            state = "succeeded" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired as exc:
            _kill_process(process)
            stdout, stderr = exc.stdout, exc.stderr
            state, error = "failed", "timeout"
        except BaseException:
            _kill_process(process)
            process.wait(timeout=1)
            raise
    except OSError as exc:
        stderr, error = str(exc), str(exc)
    text_out = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else (stdout or "")
    text_err = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else (stderr or "")
    (attempt_dir / "stdout.log").write_text(text_out, encoding="utf-8", newline="\n")
    (attempt_dir / "stderr.log").write_text(text_err, encoding="utf-8", newline="\n")
    result: dict[str, Any] = {
        "state": state,
        "returncode": process.returncode if process else None,
        "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
        "launched": process is not None,
    }
    if error:
        result["error"] = error
    return result


def _queue_end(attempts: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    brief = ", ".join(f"{item['candidate_id']}={item['decision']['action']}" for item in attempts)
    actions = [str(item["decision"]["action"]) for item in attempts]
    if not attempts:
        return "exhausted", "候选队列是空的。", "exhausted"
    if all(action == "planned" for action in actions):
        return "planned", f"干跑，没有测量（{brief}）。", "planned"
    if any(action == "discard" for action in actions):
        return "discarded", f"有候选没有达到指标（{brief}）。", "discarded"
    if all(action == "keep" for action in actions):
        return "drained", f"已登记候选全部保留（{brief}）。", "drained"
    return "exhausted", brief or "候选队列已经结束。", "exhausted"


def _propose_next(
    plan: DevPlan,
    state: dict[str, Any],
    root: Path,
    finish: Callable[[str, str, str], dict[str, Any]],
    save: Callable[[], None],
    require_unchanged_source: Callable[[str], None],
    dry_run: bool,
) -> dict[str, Any] | None:
    """Fill one pending candidate, or finish when the reviewed catalog is done."""
    if plan.proposal_command is None:
        status, detail, reason = _queue_end(state["attempts"])
        return finish(status, detail, reason)
    if dry_run:
        return finish("planned", "这是干跑，没有测量。", "planned")
    index = int(state.get("proposal_count") or 0) + 1
    if not plan.task_bound and index > plan.max_rounds:
        return finish("stopped", "提议次数达到上限。", "max_rounds")
    proposal_dir = root / f"proposal-{index:03d}"
    history_path = proposal_dir / "history.json"
    output_path = proposal_dir / "candidates.json"
    history = [
        {
            "candidate_id": item.get("candidate_id"),
            "decision": {"action": item.get("decision", {}).get("action")},
        }
        for item in state["attempts"]
    ]
    _write_json(history_path, history)
    command = _format_tokens(
        plan.proposal_command,
        {
            "python": sys.executable,
            "repo_root": plan.repo_root,
            "history": history_path,
            "output": output_path,
        },
    )
    state["proposal_count"] = index
    state.update(
        phase="proposal",
        active_operation={"kind": "proposal", "path": str(proposal_dir), "command": command},
    )
    save()
    execution = _run_command(
        command,
        cwd=plan.repo_root,
        attempt_dir=proposal_dir,
        timeout_seconds=plan.timeout_seconds,
        dry_run=False,
    )
    require_unchanged_source("proposal")
    if execution["state"] == "withheld":
        return finish("escalated", "提议命令被识别成调度器提交，已拒绝执行。", "withheld")
    if execution["state"] != "succeeded":
        return finish("escalated", "提议命令没有通过。", "escalated")
    if not output_path.is_file():
        return finish("escalated", "提议命令没有写下候选名单。", "escalated")
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        return finish("escalated", "提议名单必须是数组。", "escalated")
    if not loaded:
        actions = [str(item.get("decision", {}).get("action")) for item in state["attempts"]]
        if "discard" in actions:
            brief = ", ".join(
                f"{item['candidate_id']}={item['decision']['action']}" for item in state["attempts"]
            )
            return finish(
                "discarded",
                f"目录已经用尽，且有候选没有达到指标（{brief}）。",
                "discarded",
            )
        return finish(
            "requires_new_review",
            "已审阅目录已经用尽，需要新的书面协议。",
            "requires_new_review",
        )
    seen = {str(item.get("candidate_id") or "") for item in state["attempts"]}
    seen.discard("")
    try:
        chosen = _validate_candidate(loaded[0], index, seen)
    except ValueError as exc:
        return finish("failed", str(exc), "failed")
    state["pending_candidates"] = [chosen]
    state["active_operation"] = None
    save()
    return None


def _next_action(state: Mapping[str, Any]) -> str:
    reason = str(state.get("stop_reason") or "")
    pending = state.get("pending_candidates") or []
    current = pending[0] if pending else {}
    identifier = current.get("id", "")
    paths = ", ".join(current.get("allowed_paths") or [])
    messages = {
        "drained": "已登记的验证候选都已保留，队列是空的。下一件开发工作先写入计划，再用新的输出目录开一轮。",
        "planned": "这是干跑，没有测量。去掉干跑开关后才会产生保留或放弃。",
        "kept": "计划在第一次保留后停止，后面的候选没有跑。开发审查计划应把 stop_on_keep 保持为 false。",
        "discarded": "有候选没有达到已登记的指标。看本拍的放弃项，修完后用新的输出目录再跑。",
        "needs_implementation": (
            f"下一件只改候选 {identifier}，路径：{paths}。"
            "把改动写进该候选的 edits，再用新的输出目录开一轮。"
        ),
        "development_order": (
            "实现候选的路径不符合开发顺序。"
            "合同、适配器、插件、预设或原生界面的改动要同时写上 tests/ 路径。"
        ),
        "kernel_frozen": (
            "已安装的 DSH 运行时和 runCli 入口不改。"
            "启动界面可以改：填写公司账号和密码，进入带公司风格和适配的 DSH 界面。"
        ),
        "review_failed": "审阅没有通过。先看本拍审阅记录，修完后用新的输出目录再跑。",
        "budget": "登记成本已经超过剩余预算。增大预算或拆小候选后，用新的输出目录再跑。",
        "deadline": "已经过了计划里的截止时间。这一拍没有启动新的候选。",
        "max_rounds": (
            "轮数上限到了，队列里还有候选。"
            "增大 max_rounds，或新开一轮继续，未跑的候选不能记成完成。"
        ),
        "max_attempts": "尝试上限到了，队列里还有候选。增大 max_attempts 后用新的输出目录再跑。",
        "consecutive_failures": "连续执行失败达到上限。先看失败命令，再新开一轮。",
        "interrupted": "上一轮执行意图没有对账。不要把不确定的结果改成成功，先核对产物再新开一轮。",
        "source_changed": "循环程序或它启动的脚本在本轮中变了。用新的输出目录重新审阅。",
        "exhausted": "队列是空的。有开发工作时把候选写进计划，再用新的输出目录开一轮。",
        "requires_new_review": (
            "已审阅目录已经用尽。下一份开发协议要先写成新的目录项，再用新的输出目录开一轮。"
        ),
    }
    return messages.get(reason, state.get("stop_detail") or reason)


def append_ledger(path: str | Path, state: Mapping[str, Any]) -> None:
    """Append one round. Earlier rounds stay in the file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    attempts = state.get("attempts") or []
    brief = ", ".join(
        f"`{item.get('candidate_id')}` {item.get('decision', {}).get('action')}"
        for item in attempts
    ) or "无"
    stamp = state.get("finished_at") or _utc_now()
    entry = (
        f"## {stamp} `{state.get('loop_id')}`\n"
        f"- 停止：`{state.get('stop_reason')}`\n"
        f"- 候选：{brief}\n"
    )
    if target.is_file():
        previous = target.read_text(encoding="utf-8")
        separator = "" if previous.endswith("\n") else "\n"
        target.write_text(previous + separator + "\n" + entry, encoding="utf-8", newline="\n")
        return
    target.write_text("# 开发审查循环账本\n\n" + entry, encoding="utf-8", newline="\n")


def render_status(state: Mapping[str, Any]) -> str:
    lines = [
        "# 开发审查循环状态",
        "",
        f"- 状态：`{state.get('state')}`",
        f"- 停止原因：`{state.get('stop_reason')}`",
        f"- 说明：{state.get('stop_detail')}",
        f"- 循环：`{state.get('loop_id')}`",
        "",
        "## 审阅",
        "",
    ]
    review = state.get("review") or {}
    checks = review.get("checks") or []
    if not checks:
        lines.append("本拍没有审阅记录。")
    for check in checks:
        lines.append(f"- 检查 {check.get('index')}: `{check.get('state')}`")
    lines.extend(["", "## 候选", ""])
    attempts = state.get("attempts") or []
    if not attempts:
        lines.append("本拍没有执行候选。")
    for attempt in attempts:
        metric = attempt.get("metric") or {}
        lines.append(
            f"- `{attempt.get('candidate_id')}` {attempt.get('decision', {}).get('action')}"
            f"，指标 {metric.get('value')}"
        )
    pending = state.get("pending_candidates") or []
    lines.extend(["", "## 尚未执行", ""])
    if pending:
        lines.extend(
            f"- `{item.get('id')}` {item.get('kind', 'verify')}/{item.get('status', 'ready')}"
            for item in pending
        )
    else:
        lines.append("队列里没有剩余候选。")
    lines.extend(["", "## 下一拍", "", _next_action(state), ""])
    return "\n".join(lines)


def run_dev_review_loop(
    config_path: str | Path,
    *,
    output_dir: str | Path,
    resume: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run one bounded circle. Finished work is not relaunched by resume."""

    config_path = Path(config_path).expanduser().resolve()
    plan = load_plan(config_path)
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    state_path = Path(resume).expanduser().resolve() if resume else root / "loop-state.json"
    source = _source_fingerprint(plan, config_path)
    config_sha = _sha256_file(config_path)

    if resume:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported dev review loop state schema")
        if state.get("dry_run") is not dry_run:
            raise ValueError("dry-run state cannot be resumed as real execution or vice versa")
        if state.get("config_sha256") != config_sha:
            raise ValueError("resume plan hash changed")
        if state.get("source", {}).get("sha256") != source["sha256"]:
            raise ValueError("resume source fingerprint changed; start a new output directory")
        if state.get("output_dir") != str(root):
            raise ValueError("resume output directory differs from the recorded directory")
    else:
        if state_path.exists():
            raise FileExistsError(f"loop state already exists; use --resume: {state_path}")
        state = {
            "schema_version": SCHEMA_VERSION,
            "loop_id": f"{plan.experiment_id}-{uuid.uuid4().hex[:10]}",
            "task_id": plan.task_id,
            "experiment_id": plan.experiment_id,
            "state": "running",
            "stop_reason": "initialized",
            "stop_detail": "initialized",
            "review": {},
            "attempts": [],
            "failures": [],
            "pending_candidates": [dict(item) for item in plan.candidates],
            "consecutive_failures": 0,
            "spent": 0.0,
            "reserved": 0.0,
            "budget_total": plan.budget_total,
            "currency": plan.currency,
            "git": _git_identity(plan.repo_root),
            "source": source,
            "config_path": str(config_path),
            "config_sha256": config_sha,
            "output_dir": str(root),
            "dry_run": dry_run,
            "active_operation": None,
            "started_at": _utc_now(),
            "finished_at": None,
        }

    def save() -> None:
        state["updated_at"] = _utc_now()
        _write_json(state_path, state)

    def finish(status: str, detail: str, reason: str) -> dict[str, Any]:
        state.update(state=status, stop_detail=detail, stop_reason=reason, finished_at=_utc_now())
        state["active_operation"] = None
        save()
        _write_json(root / "loop-summary.json", state)
        return state

    if state.get("active_operation"):
        return finish("escalated", "上次执行意图尚未对账。", "interrupted")
    if state.get("reserved"):
        return finish("escalated", "有一笔预算预留没有对账。", "interrupted")
    if (
        resume
        and not state.get("pending_candidates")
        and state.get("stop_reason") in FINISHED
    ):
        return state
    if plan.deadline_at is not None and datetime.now(UTC) >= plan.deadline_at:
        return finish("stopped", "已经过了计划里的截止时间。", "deadline")

    def require_unchanged_source(stage: str) -> None:
        current = _source_fingerprint(plan, config_path)
        if current["sha256"] != source["sha256"]:
            changed = [
                name
                for name, row in current["files"].items()
                if source["files"].get(name) != row
            ]
            missing = [name for name in source["files"] if name not in current["files"]]
            raise ValueError(f"source changed during {stage}: {changed or missing}")

    applied: dict[str, str] = {}
    save()
    try:
        review_dir = root / "reviews" / uuid.uuid4().hex[:12]
        state.update(phase="review", active_operation={"kind": "review", "path": str(review_dir)})
        save()
        checks: list[dict[str, Any]] = []
        for index, command in enumerate(plan.review_commands, start=1):
            record = _run_command(
                _format_tokens(command, {"python": sys.executable, "repo_root": plan.repo_root}),
                cwd=plan.repo_root,
                attempt_dir=review_dir / f"check-{index:02d}",
                timeout_seconds=plan.timeout_seconds,
                dry_run=dry_run,
            )
            record.update(index=index, argv=list(command))
            checks.append(record)
            if record["state"] not in {"succeeded", "planned"}:
                break
        passed = bool(checks) and all(item["state"] == "succeeded" for item in checks)
        planned = bool(checks) and all(item["state"] == "planned" for item in checks)
        state["review"] = {"passed": passed, "planned": planned, "checks": checks}
        state["active_operation"] = None
        save()
        require_unchanged_source("review")
        if not (passed or (dry_run and planned)):
            return finish("escalated", "审阅没有通过，或审阅命令被拒绝。", "review_failed")

        while plan.task_bound or len(state["attempts"]) < plan.max_rounds:
            if not plan.task_bound and len(state["attempts"]) >= plan.max_attempts:
                return finish("stopped", "尝试次数达到上限。", "max_attempts")
            if not state["pending_candidates"]:
                stopped = _propose_next(
                    plan, state, root, finish, save, require_unchanged_source, dry_run,
                )
                if stopped is not None:
                    return stopped
                if not state["pending_candidates"]:
                    break
            candidate = state["pending_candidates"][0]
            kind = str(candidate.get("kind", "verify"))
            status_name = str(candidate.get("status", "ready"))
            if kind == "implement":
                for item in candidate.get("allowed_paths") or []:
                    frozen = _kernel_frozen_error(str(item).replace("\\", "/"))
                    if frozen:
                        return finish("escalated", frozen, "kernel_frozen")
                order_error = _development_order_error(candidate)
                if order_error:
                    return finish("escalated", order_error, "development_order")
                edits = candidate.get("edits") or []
                if status_name != "ready" and (not isinstance(edits, list) or not edits):
                    return finish(
                        "needs_implementation",
                        f"候选 {candidate['id']} 正在等待一处已审阅的代码改动。",
                        "needs_implementation",
                    )
            require_unchanged_source("before attempt")
            cost = _finite_number(candidate["cost"], "candidate cost", nonnegative=True)
            if not plan.task_bound and cost > plan.budget_total - float(state["spent"]):
                return finish("stopped", "候选的登记成本超过剩余预算。", "budget")
            edited: list[str] = []
            reverted = False
            if kind == "implement" and status_name != "ready":
                if dry_run:
                    return finish("planned", "这是干跑，没有改文件。", "planned")
                try:
                    applied = _apply_candidate_edits(
                        plan.repo_root,
                        candidate,
                        protected={Path(name).resolve() for name in source["files"]},
                    )
                except ValueError as exc:
                    return finish("failed", str(exc), "failed")
                edited = sorted(applied)
                require_unchanged_source("edit")
            identifier = str(candidate["id"])
            round_index = len(state["attempts"]) + 1
            attempt_dir = root / f"attempt-{round_index:03d}-{identifier}"
            command = _format_tokens(
                plan.run_command,
                {
                    "python": sys.executable,
                    "repo_root": plan.repo_root,
                    "output_dir": attempt_dir,
                    "candidate_id": identifier,
                },
            )
            state["pending_candidates"].pop(0)
            state["reserved"] = 0.0 if dry_run or _has_scheduler_command(command) else cost
            state.update(
                phase="attempt",
                active_operation={
                    "kind": "attempt",
                    "attempt": round_index,
                    "candidate": candidate,
                    "path": str(attempt_dir),
                    "command": command,
                    "reserved": state["reserved"],
                },
            )
            save()
            attempt_dir.mkdir(parents=True, exist_ok=False)
            execution = _run_command(
                command,
                cwd=plan.repo_root,
                attempt_dir=attempt_dir,
                timeout_seconds=plan.timeout_seconds,
                dry_run=dry_run,
                candidate_id=identifier,
            )
            state["active_operation"]["execution"] = execution
            save()
            require_unchanged_source("execution")
            metric_value = None
            metric_error = None
            if execution["state"] == "succeeded":
                metric_value, metric_error = _metrics_from_attempt(attempt_dir, plan)
            artifacts = sorted(
                path.relative_to(attempt_dir).as_posix()
                for path in attempt_dir.rglob("*")
                if path.is_file()
            )
            if execution["state"] == "withheld":
                decision: dict[str, Any] = {
                    "action": "escalate",
                    "reason": execution.get("error", "command withheld"),
                }
            elif execution["state"] == "planned":
                decision = {"action": "planned", "reason": "dry run"}
            else:
                decision = _decision(
                    plan,
                    metric_value=metric_value,
                    execution_state=execution["state"],
                    artifacts=artifacts,
                )
            if metric_error:
                decision["metric_error"] = metric_error
            if applied and decision["action"] != "keep":
                _restore_files(plan.repo_root, applied)
                reverted = True
            applied = {}
            charged = cost if execution.get("launched") else 0.0
            record = {
                "schema_version": SCHEMA_VERSION,
                "attempt": round_index,
                "candidate_id": identifier,
                "hypothesis": candidate.get("hypothesis"),
                "command": command,
                "execution": execution,
                "metric": {"name": plan.primary_metric, "file": plan.metric_file, "value": metric_value},
                "decision": decision,
                "artifacts": artifacts,
                "cost": charged,
                "created_at": _utc_now(),
            }
            if edited:
                record["edited"] = edited
                record["reverted"] = reverted
            _write_json(attempt_dir / "attempt.json", record)
            state["attempts"].append(record)
            state["spent"] = float(state["spent"]) + charged
            state["reserved"] = 0.0
            state["active_operation"] = None
            action = decision["action"]
            if action in {"stop", "escalate", "discard"}:
                execution_failure = execution["state"] != "succeeded"
                if execution_failure:
                    state["consecutive_failures"] = int(state["consecutive_failures"]) + 1
                else:
                    state["consecutive_failures"] = 0
                state["failures"].append(
                    {
                        "attempt": round_index,
                        "candidate_id": identifier,
                        "reason": decision.get("reason"),
                        "state": execution["state"],
                    }
                )
            else:
                state["consecutive_failures"] = 0
            save()
            if action == "keep" and plan.stop_on_keep:
                detail = f"候选 {identifier} 达到了已登记的阈值。"
                return finish("kept", detail, "kept")
            if execution["state"] == "withheld":
                return finish("escalated", "命令被识别成调度器提交，已拒绝执行。", "withheld")
            if action == "escalate":
                return finish("escalated", "主指标缺失，或这次尝试的产物不完整。", "escalated")
            failed_in_a_row = int(state["consecutive_failures"])
            if action == "stop" and failed_in_a_row >= plan.max_consecutive_failures:
                return finish("stopped", "连续执行失败达到上限。", "consecutive_failures")
        if not plan.task_bound and not state["pending_candidates"] and plan.proposal_command is not None:
            stopped = _propose_next(
                plan, state, root, finish, save, require_unchanged_source, dry_run,
            )
            if stopped is not None:
                return stopped
        if state["pending_candidates"]:
            return finish("stopped", "轮数达到上限。", "max_rounds")
        status, detail, reason = _queue_end(state["attempts"])
        return finish(status, detail, reason)
    except Exception as exc:
        if applied:
            _restore_files(plan.repo_root, applied)
            applied = {}
        state["error"] = f"{type(exc).__name__}: {exc}"
        reason = "source_changed" if "source changed" in str(exc) else "failed"
        return finish("failed", state["error"], reason)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one bounded development and review circle")
    parser.add_argument("--config", required=True, help="development review plan JSON")
    parser.add_argument("--output-dir", required=True, help="new directory for this round")
    parser.add_argument("--resume", default=None, help="existing loop-state.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status-out", default=None, help="write the round snapshot markdown")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = run_dev_review_loop(
        args.config,
        output_dir=args.output_dir,
        resume=args.resume,
        dry_run=args.dry_run,
    )
    if args.status_out:
        status_path = Path(args.status_out)
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(render_status(summary), encoding="utf-8", newline="\n")
        append_ledger(status_path.with_name("LEDGER.md"), summary)
    print(json.dumps(
        {
            "state": summary["state"],
            "stop_reason": summary["stop_reason"],
            "stop_detail": summary["stop_detail"],
            "loop_id": summary["loop_id"],
            "attempts": [
                {
                    "id": item["candidate_id"],
                    "action": item["decision"]["action"],
                    "metric": item["metric"]["value"],
                }
                for item in summary["attempts"]
            ],
        },
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ))
    return 0 if summary["stop_reason"] in CLEAN_EXIT else 2


if __name__ == "__main__":
    raise SystemExit(main())
