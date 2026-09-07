"""A narrow learning problem: use up the strip along the chamfer.

The ULD's chamfered side leaves a wedge no floor placement can enter and,
above it, a strip under the small shelf that only raised placements reach.
Together they are about 0.45 m^3, a tenth of the container, and the ladder
leaves most of it empty.  This package poses that strip as a small, fast
environment so standard RL can be run on it: candidates come from a
dedicated generator, validity is rule-alpha's analytic check (physics
verified elsewhere), and the reward is the volume that ends up left of the
floor line.
"""
