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


def make_arm(spec: str):
    base = spec.partition("@")[0]
    if base == "ladder":
        return LadderArm(spec)
    raise KeyError(f"unknown arm {spec!r}; known: ladder[@field=value,...]")
