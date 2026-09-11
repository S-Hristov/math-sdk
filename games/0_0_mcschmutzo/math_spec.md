# McSchmutzo math spec

## Sources

- `McSchmutzo_Slot_Game_PRD.docx`
- `McSchmutzo_Full_Expanded_Explanation.docx`
- `wheel before bonus.png`

## Locked product values

- Grid: 5 reels x 5 rows.
- Win evaluation: 50 fixed left-to-right paylines.
- One paytable for every mode. No payout scaling in enhanced or bonus modes.
- Wild substitutes only for the ten pay symbols.
- Every Base, Feature, or Free Game spin with at least one paying line starts
  Lock & Re-Spin.
- Lock & Re-Spin chooses the highest-ranked winning pay symbol.
- Wilds lock only when part of a qualifying line for that symbol.
- Chef symbols add ladder steps, not direct multiplier values.
- Multiplier ladder ends at 1000x and never falls during Free Games.
- Wheel sectors: `6+3`, `8+4`, `10+5`, `12+6`, `15+8`, `20+10`, `30+15`.
- Three collected scatters trigger the Normal Bonus.
- Four collected scatters trigger the Super Bonus.
- Scatter collection is capped at four.
- Entry step limits: Normal Bonus up to 15 steps; Super Bonus up to 30 steps.
- Normal Bonus applies the wheel's step value. Super Bonus doubles that value,
  capped at 30 steps.

## Modes

| Mode | Cost | RTP target | Round cap |
|---|---:|---:|---:|
| Base | 1x | 96.51% | 25,000x |
| Enhancer 1 | 2x | 96.51% | 25,000x |
| Lock Feature Spin | 20x | 96.51% | 25,000x |
| Bonus Buy 1 | 100x | 96.51% | 25,000x |
| Bonus Buy 2 | 500x | 96.51% | 25,000x |

## Math-owned inputs

The PRD explicitly assigns the final payline map, reel strips, symbol frequencies,
hit rate, and trigger rate to math. `math_data.py` supplies the 50-line map.
The CSV strips are the first optimization seed, not signed-off production strips.

Enhancer 1 uses a scatter-enriched re-spin strip. Lock Feature Spin guarantees
a paying initial board and therefore immediate Lock & Re-Spin. Bonus Buy 1
enters the three-scatter Normal Bonus. Bonus Buy 2 enters the four-scatter
Super Bonus.

Each mode contains an exact 25,000x optimization fence targeted at 1 in
5,000,000 rounds. Bonus Buy 2 uses low-step-biased wheel and in-feature step
weights plus explicit 5,000x/10,000x tail suppression during optimization.
Its main distribution excludes payouts above 9,999.99x; the separate exact
25,000x fence remains available at the declared hit rate.

## Required sign-off

1. Directional run: at least 1,000,000 rounds per mode.
2. Production run: at least 20,000,000 rounds per mode.
3. Verify RTP tolerance, hit frequency, bonus frequency, volatility, cap rate,
   event schema, deterministic replay, and no payout above the mode cap.
