"""Named policies ("arms") the bench can run.

An arm is a factory ``(scene) -> agent`` where the agent has the official
three methods.  Arms are named so that a report can say exactly what ran.

``ladder`` is rule-alpha with its shipped config.  ``ladder@key=value,...``
overrides config fields, which is how a one-flag ablation is expressed.  The
same arm run twice must produce identical episodes; ``bench.compare``
checks that when two labels resolve to the same arm.
"""

from __future__ import annotations

import dataclasses
import pathlib

from rule_alpha.agent import RuleAlphaAgent
from rule_alpha.config import DEFAULT_CONFIG, RuleAlphaConfig


def _parse_value(field_type, raw: str):
    if field_type is bool or raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if raw.startswith("(") and raw.endswith(")"):
        return tuple(float(v) for v in raw[1:-1].split(";") if v)
    return raw


def config_from_spec(spec: str) -> RuleAlphaConfig:
    """``ladder`` or ``ladder@field=value,field=value``."""
    if "@" not in spec:
        return DEFAULT_CONFIG
    _base, _sep, overrides = spec.partition("@")
    fields = {f.name: f.type for f in dataclasses.fields(RuleAlphaConfig)}
    values = {}
    for pair in overrides.split(","):
        if not pair:
            continue
        key, _eq, raw = pair.partition("=")
        if key not in fields:
            raise KeyError(f"unknown rule-alpha config field {key!r}")
        values[key] = _parse_value(fields[key], raw)
    return dataclasses.replace(DEFAULT_CONFIG, **values)


class LadderArm:
    """rule-alpha's archetype ladder, unchanged."""

    def __init__(self, spec: str):
        self.spec = spec
        self.config = config_from_spec(spec)

    def __call__(self, scene):
        return RuleAlphaAgent(config=self.config)

    def describe(self) -> dict:
        return {"arm": self.spec, "family": "ladder", "config": self.config.to_dict()}


ALIASES = {
    # the ladder with its decisions made insensitive to sub-tolerance noise:
    # anchors clamped and given 0.5 mm of slack, comparator terms quantized to
    # 5 mm with an explicit geometric tie-break, an observed item that has
    # settled up to 2 cm into its shelf still counted as a shelf item, and
    # compaction forbidden from sliding a box off its support
    "ladder-stable": (
        "ladder@anchor_slack=0.0005,anchor_clamp=true,key_quantum=0.005,"
        "settle_sink_allowance=0.02,compaction_keeps_support=true"
    ),
}


def resolve_alias(spec: str) -> str:
    """``alias`` or ``alias@k=v,...`` -> the full ``ladder@...`` spec.

    Overrides written after an alias are appended to the alias's own, so
    ``ladder-stable@inclusion_clearance=0.008`` is the stable arm with one
    more field changed."""
    name, _sep, extra = spec.partition("@")
    if name not in ALIASES:
        return spec
    resolved = ALIASES[name]
    if extra:
        resolved = resolved + ("," if "@" in resolved else "@") + extra
    return resolved


class LearnedArm(LadderArm):
    """The stable ladder with a learned selector over its survivors.

    Spec: ``nn:<model.npz>[:margin][@field=value,...]``.  Generation, validity
    and vetoes are the ladder's; only the final pick among survivors is the
    model's, and only when it beats the ladder's pick by more than ``margin``.
    """

    def __init__(self, spec: str):
        from .ranker import LearnedSelector, file_sha

        body, _at, overrides = spec.partition("@")
        _nn, _colon, rest = body.partition(":")
        path, _c2, margin = rest.partition(":")
        base = resolve_alias("ladder-stable") + ("," + overrides if overrides else "")
        super().__init__(base)
        self.spec = spec
        self.model_path = path
        self.model_sha = file_sha(path)
        self.margin = float(margin) if margin else 0.0
        self.selector = LearnedSelector(path, margin=self.margin)

    def __call__(self, scene):
        return RuleAlphaAgent(config=self.config, selector=self.selector)

    def describe(self) -> dict:
        return {"arm": self.spec, "family": "nn", "model": self.model_path,
                "model_sha": self.model_sha, "margin": self.margin,
                "model_meta": self.selector.meta, "config": self.config.to_dict()}


class ValueArm(LadderArm):
    """The stable ladder with survivors ranked by a value network over the
    board each would leave.  Spec: ``vnet:<model.npz>[:margin][@field=value,...]``."""

    def __init__(self, spec: str):
        from .ranker import file_sha
        from .valuenet import ValueSelector

        body, _at, overrides = spec.partition("@")
        _v, _colon, rest = body.partition(":")
        path, _c2, margin = rest.partition(":")
        base = resolve_alias("ladder-stable") + ("," + overrides if overrides else "")
        super().__init__(base)
        self.spec = spec
        self.model_path = path
        self.model_sha = file_sha(path)
        self.margin = float(margin) if margin else 0.0
        self.selector = ValueSelector(path, margin=self.margin)

    def __call__(self, scene):
        return RuleAlphaAgent(config=self.config, selector=self.selector)

    def describe(self) -> dict:
        return {"arm": self.spec, "family": "vnet", "model": self.model_path,
                "model_sha": self.model_sha, "margin": self.margin,
                "model_spec": self.selector.net.spec, "config": self.config.to_dict()}


class WedgeArm(LadderArm):
    """The stable ladder with the learned wedge option asked before it.
    Spec: ``wedge:<policy dir>[@field=value,...]``; the directory holds
    ``policy.pt`` from ``wedge_rl train``."""

    def __init__(self, spec: str):
        from .ranker import file_sha

        body, _at, overrides = spec.partition("@")
        _w, _colon, path = body.partition(":")
        base = resolve_alias("ladder-stable") + ("," + overrides if overrides else "")
        super().__init__(base)
        self.spec = spec
        self.policy_dir = path
        self.model_sha = file_sha(str(pathlib.Path(path) / "policy.pt"))

    def __call__(self, scene):
        from wedge_rl.option import WedgeOption

        # one option per episode: it counts the items it has been offered
        return RuleAlphaAgent(config=self.config, wedge_option=WedgeOption(self.policy_dir, self.config))

    def describe(self) -> dict:
        return {"arm": self.spec, "family": "wedge", "model": self.policy_dir,
                "model_sha": self.model_sha, "config": self.config.to_dict()}


class StackArm(LadderArm):
    """The stable ladder with the learned stack option after it: once the
    ladder has nothing for an item, the stack policy places it on the boxes
    already there.  Spec: ``stack:<policy dir>[@field=value,...]``; add
    ``+wedge:<policy dir>`` to ask the wedge option before the ladder too."""

    def __init__(self, spec: str):
        from .ranker import file_sha

        body, _at, overrides = spec.partition("@")
        parts = body.split("+")
        self.policy_dir = ""
        self.wedge_dir = ""
        self.lookahead = None
        for part in parts:
            kind, _colon, path = part.partition(":")
            if kind == "stack":
                self.policy_dir = path
            elif kind == "stackla":
                # the stack option with its look-ahead over imagined futures
                self.policy_dir = path
                # two imagined streams, the value head past a short horizon:
                # on the held-out boards this keeps most of the true-future
                # search's gain (0.285 against 0.289 at the same deadline)
                self.lookahead = {"k": 3, "deadline": 2.5, "samples": 2, "length": 6, "horizon": 4}
            elif kind == "wedge":
                self.wedge_dir = path
            else:
                raise KeyError(f"unknown option {kind!r} in {spec!r}")
        base = resolve_alias("ladder-stable") + ("," + overrides if overrides else "")
        super().__init__(base)
        self.spec = spec
        self.model_sha = file_sha(str(pathlib.Path(self.policy_dir) / "policy.pt"))
        self.wedge_sha = file_sha(str(pathlib.Path(self.wedge_dir) / "policy.pt")) if self.wedge_dir else ""

    def __call__(self, scene):
        from wedge_rl.option import StackOption, WedgeOption

        wedge = WedgeOption(self.wedge_dir, self.config) if self.wedge_dir else None
        return RuleAlphaAgent(config=self.config, wedge_option=wedge,
                              stack_option=StackOption(self.policy_dir, self.config, lookahead=self.lookahead))

    def describe(self) -> dict:
        return {"arm": self.spec, "family": "stack", "model": self.policy_dir, "model_sha": self.model_sha,
                "wedge_model": self.wedge_dir, "wedge_sha": self.wedge_sha, "lookahead": self.lookahead,
                "config": self.config.to_dict()}


class SearchArm(LadderArm):
    """Search at play time over the ladder's survivors (``bench/search.py``):
    ``search:<k>+stack:<dir>``.  The inner arm (the same ladder with the
    stack option) continues every survivor to the end on the analytic model;
    the best continuation is taken.  A ceiling measurement, analytic only."""

    def __init__(self, spec: str):
        body, _at, overrides = spec.partition("@")
        head, _plus, rest = body.partition("+")
        _s, _colon, params = head.partition(":")
        # ``search:<k>[/<streams>/<horizon>]``: with streams the continuations
        # run over imagined futures of ``horizon`` items instead of the true stream
        parts = [p for p in params.split("/") if p]
        self.k = int(parts[0]) if parts else 6
        # ``search:<k>/pool``: the continuation over the visible pool alone
        self.pool_only = len(parts) > 1 and parts[1] == "pool"
        self.streams = int(parts[1]) if len(parts) > 1 and not self.pool_only else 0
        self.horizon = int(parts[2]) if len(parts) > 2 else 999
        # the overrides after the "@" belong to the inner arm as well (they
        # are the ladder's settings; the outer agent is the inner arm's agent)
        self.inner_spec = (rest or "ladder-stable") + ("@" + overrides if overrides and "@" not in (rest or "") else "")
        base = resolve_alias("ladder-stable") + ("," + overrides if overrides else "")
        super().__init__(base)
        self.spec = spec
        self.inner = make_arm(self.inner_spec)

    def __call__(self, scene):
        from .search import SearchSelector

        inner = self.inner
        agent = inner(scene)  # the same lower level, with its options, decides and continues
        selector = SearchSelector(scene, inner, k=self.k, log=lambda line: print(line, flush=True),
                                  streams=self.streams, horizon=self.horizon, pool_only=self.pool_only)
        agent.selector = selector
        agent.search = selector
        if self.pool_only:
            # the selector sees the pool the agent sees, before every decision
            inner_policy = agent.policy

            def policy(observation, _inner=inner_policy, _sel=selector):
                _sel.pool = [dict(i) for i in observation.get("pool_list", [])]
                return _inner(observation)

            agent.policy = policy
        return agent

    def describe(self) -> dict:
        return {"arm": self.spec, "family": "search", "k": self.k, "streams": self.streams,
                "horizon": self.horizon, "pool_only": self.pool_only, "inner": self.inner.describe(),
                "config": self.config.to_dict()}


class OfficialArm:
    """Any agent in the official format, by the path of its ``agent.py``:
    ``official:<path/to/agent.py>``.  Loaded the way the official app loads
    it (``Agent(module_path=<its directory>)``), one instance per scene.
    Physics only: the analytic runner needs rule-alpha's decisions."""

    def __init__(self, spec: str):
        import hashlib

        _o, _colon, path = spec.partition(":")
        self.spec = spec
        self.path = pathlib.Path(path).resolve()
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.sha = hashlib.sha256(self.path.read_bytes()).hexdigest()[:12]
        self.config = config_from_spec(resolve_alias("ladder-stable"))
        self._module = None

    def _load(self):
        if self._module is None:
            import importlib.util
            import sys

            name = f"_official_agent_{self.sha}"
            spec = importlib.util.spec_from_file_location(name, self.path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            self._module = module
        return self._module

    def __call__(self, scene):
        return self._load().Agent(module_path=str(self.path.parent))

    def describe(self) -> dict:
        return {"arm": self.spec, "family": "official", "path": str(self.path), "sha": self.sha}


class DenseArm(LadderArm):
    """The dense layer-building core asked first for every item, the ladder
    behind it, optionally the stack option after the ladder:
    ``dense[+stack:<dir>][@field=value,...]``."""

    def __init__(self, spec: str):
        body, _at, overrides = spec.partition("@")
        parts = body.split("+")
        self.stack_dir = ""
        for part in parts[1:]:
            kind, _colon, path = part.partition(":")
            if kind == "stack":
                self.stack_dir = path
            else:
                raise KeyError(f"unknown option {kind!r} in {spec!r}")
        base = resolve_alias("ladder-stable") + ("," + overrides if overrides else "")
        super().__init__(base)
        self.spec = spec

    def __call__(self, scene):
        from wedge_rl.dense import DenseOption
        from wedge_rl.option import StackOption

        stack = StackOption(self.stack_dir, self.config) if self.stack_dir else None
        return RuleAlphaAgent(config=self.config, wedge_option=DenseOption(self.config), stack_option=stack)

    def describe(self) -> dict:
        return {"arm": self.spec, "family": "dense", "stack": self.stack_dir, "config": self.config.to_dict()}


def make_arm(spec: str):
    if spec.startswith("official:"):
        return OfficialArm(spec)
    if spec == "dense" or spec.startswith("dense+") or spec.startswith("dense@"):
        return DenseArm(spec)
    if spec.startswith("search:"):
        return SearchArm(spec)
    if spec.startswith("nn:"):
        return LearnedArm(spec)
    if spec.startswith("vnet:"):
        return ValueArm(spec)
    if spec.startswith("wedge:"):
        return WedgeArm(spec)
    if spec.startswith("stack:") or spec.startswith("stackla:"):
        return StackArm(spec)
    resolved = resolve_alias(spec)
    base = resolved.partition("@")[0]
    if base == "ladder":
        arm = LadderArm(resolved)
        arm.spec = spec
        return arm
    raise KeyError(f"unknown arm {spec!r}; known: ladder[@field=value,...], nn:<model.npz>, "
                   + ", ".join(ALIASES))
