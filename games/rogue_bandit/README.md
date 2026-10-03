# Rogue Bandit math

PRD implementation: 6x8 cluster pays, tumbles, Rogue Steal, persistent Heat,
natural/paid free spins, five selectable modes, 10,000x hard cap.

Generate 10,000 complete books per mode from the math-sdk root:

```bash
python3 -m games.rogue_bandit.run --books 10000 --threads 4 --batch-size 250 --seed 20261002
```

Output: `games/rogue_bandit/library/publish_files/`.

Candidate quotas are coverage strata, not live odds. Published LUTs lock 96.00%
RTP in every mode, base/ante hit and trigger rates, superspin 10x/100x thresholds, and a
1-in-10,000,000 max-win route. A 10k build is preliminary integration math,
not high-volatility sign-off; use multi-million fresh simulations before release.
