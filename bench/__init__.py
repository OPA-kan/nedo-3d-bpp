"""Measurement bench for packing policies in the official simulator.

The bench exists so that two policies can be compared on the same seeded
scenes, with the same terminal quantities, under a fixed work budget, and
with the analytic model's verdicts checked against the official validator.
It does not define a score.  See ``docs/bench/README.md``.
"""
