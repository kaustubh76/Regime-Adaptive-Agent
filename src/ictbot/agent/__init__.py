"""
The agent layer — what makes the trading core an *AI agent* for BNB Hack Track 1.

Three pillars wrap the validated regime-adaptive momentum allocator:
  - identity.py     : BNB AI Agent SDK — the agent's on-chain ERC-8004 identity.
  - strategy_spec.py: the natural-language strategy ("rules you set") -> params.
  - rationale.py    : per-tick natural-language explanation of what it sees + does.

Data (CMC) and execution (TWAK) live in ictbot.data.cmc / ictbot.exec.* respectively.
"""
