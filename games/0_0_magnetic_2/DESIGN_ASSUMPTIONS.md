# Magnetic 2: Mothership — provisional math assumptions

Implemented from the 2026-08-31 concept brief. Values below need product/math sign-off before production books.

- Inherited from Magnetic 1: 7x7 grid, orthogonal 5+ cluster pays, 10-spin bonuses, 96.10% target RTP, 20,000x cap, and existing paytable/magnet values.
- Mode costs: Base 1x, Chance 2x, Feature 50x, Gravity Breach 100x, Mothership Protocol 300x, Core Overload 500x.
- Zero Point Protocol inherits the persistent Core Overload cluster behavior (signed off). Its first spin always contains a Multiplier Magnet (strictly greater than 1x).
- Mothership Protocol selection is seeded and exact-weighted: 70% Gravity Breach, 25% Core Overload, 5% Zero Point Protocol. The lookup is weighted per awarded tier, so those weighted shares and each tier's own mean are held exactly rather than falling out of a single mode-wide RTP tilt.
- Each Mothership Protocol tier pays the same mean as the bonus it awards, because the reveal promises the real bonus: Gravity Breach 96.10x, Core Overload 480.50x, Zero Point Protocol 2018.10x.
- Zero Point Protocol's mean is derived, not chosen: it is whatever makes the advertised 300x Mothership Protocol price honest at 70/25/5 once the other two tiers are pinned to their bought-mode means. It is also the mean used for a natural 5-scatter trigger, so the rarest tier pays the most. Moving the 300x price or the 70/25/5 mix moves this number; `math_targets.py` derives it and refuses a value at or below Core Overload's.
- A Polarity Shifter can activate only while an active magnetic cluster exists. It selects LEFT/RIGHT/UP/DOWN uniformly.
- Polarity wall-packs the locked cluster and every loose symbol of its active type together. A symbol never changes lane: rows are fixed for LEFT/RIGHT, reels for UP/DOWN. Non-matching symbols close behind the movers. Scatter and the firing Polarity Shifter stay fixed during the slam; the shifter is then consumed and refilled. A Magnet/Wild already in the cluster travels with it and remains attached as a Wild.
- After the slam all relocated cluster cells stay locked. Loose matching symbols are absorbed only when connected to one of those relocated anchors.
- `polarityShift.moves` tags each entry `cluster`, `symbol` (a loose matching symbol joining the slam) or `filler` (a non-matching symbol pushed back), so playback can stage the three groups separately.
- Polarity occurrence rates, hidden natural-trigger rates, multiplier distribution, volatility, hit rate, and mode RTP splits are provisional tuning inputs. Full simulation/reweighting is mandatory after sign-off.
- Frontend is playback-only. `polarityShift.board`, `moves`, and series snapshots are authoritative book events.
- Pinning Zero Point Protocol at 2018.10x pushes Chance's feature groups to 87.9% of mode RTP, which leaves its base-game group a 0.65x mean (Base is unaffected at 1.20x). Held as-is pending playtest; the natural hidden frequencies (1/30,000 Base, 1/10,000 Chance) are the knob if Chance reads too dry.
- Open compliance question: the Zero Point Protocol book pool needs roughly 5% of its weight at or above 10,000x to average 2018.10x. Only Core Overload currently enforces the 0.2% tail cap; the tier's realised tail share is logged per weighting run.
- Every route to a bonus pays the same mean: a natural scatter trigger, an outright buy and a Mothership Protocol roll. `BONUS_TIER_MEANS` in `math_targets.py` is the single source, and `assert_natural_matches_bought` checks each route and the spread between them against the published artifacts.
- A persistent bonus values and awards its final cluster once, after the last feature spin. Intermediate growth does not emit a payout.
