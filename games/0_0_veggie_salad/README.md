# Veggie Salad math prototype

Locked from GDD v1.0:

- 7x7 base; 8x8 Normal; 9x9 Super; 10x10 Hidden.
- Orthogonal clusters of 5+; simultaneous tumble removal.
- Exact seven-symbol paytable.
- Base 2x symbol multipliers; bonus 2x/4x; multiplicative; 256x cluster cap.
- 10 starting free spins; +10/+11/+12/+13/+14 retriggers for 3/4/5/6/7+ Scatters.
- 100x Normal, 300x Mystery, 400x Super; Mystery 60/30/10.
- Extra Chance 2x cost and exactly 3x natural feature probability.
- 25,000x cap; 96.10% target per published mode.

Prototype assumptions pending product lock:

- Feature Spin cost: 20x.
- Standard natural bonus rate: 1/300; Extra Chance: 1/100.
- Natural tier mix: 85% Normal / 14% Super / 1% Hidden.
- Base non-trigger paying-round rate: 30%.
- Per-mode symbol, Scatter and multiplier probabilities in `veggie_math.py`.
- Feature Spin does not independently trigger Free Spins.

Fast contract check:

```bash
python3 games/0_0_veggie_salad/validate_veggie_contract.py
```

Generated-package check:

```bash
python3 games/0_0_veggie_salad/validate_veggie_artifacts.py
```

Prototype package:

```bash
VEGGIE_SIMS=50000 VEGGIE_THREADS=4 VEGGIE_BATCH=25 \
  python3 games/0_0_veggie_salad/run.py
```

Use 10M+ Standard rounds and 250k+ per buy only after prototype tuning. Use 100M+/5M+ for tuning evidence; current output is not certification evidence.
