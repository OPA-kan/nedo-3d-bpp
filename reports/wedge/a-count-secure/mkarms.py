"""mkarms.py: the arm files for the short-budget measurement."""
R = "/home/user/nedo-3d-bpp/.claude/worktrees/agent-afceb3611e7dfc390/reports/bench/arms/"
D = "/tmp/claude-0/-home-user-nedo-3d-bpp/c555f0d0-1382-515f-857e-e77257cc9f93/scratchpad/acount/"
ship = open(R + "arm_ship_a.txt").read().strip()
v51 = open(R + "arm_acount0_a.txt").read().strip()
fix = ship + (",plan_count_secure=true,plan_count_secure_choice=true,plan_count_secure_race_chosen=true,"
              "plan_count_secure_margin=0,plan_count_secure_early=true,plan_count_secure_blocks=plain")
open(R + "arm_acountfix_a.txt", "w").write(fix + "\n")
for name, arm in (("ship", ship), ("v51", v51), ("fix", fix)):
    for b in (40, 60):
        open(D + f"arm_{name}{b}.txt", "w").write(arm + f",offline_budget_seconds={b}\n")
print("ok")
