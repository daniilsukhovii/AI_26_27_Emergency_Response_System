# AI_26_27_Emergency_Response_System

Decision-support system for emergency response: Bayesian road-status inference, HMM traffic
filtering, A* routing and CSP allocation inside an event-driven rolling-horizon simulation.
`SPEC.md` is the binding specification; design decisions are in `ASSUMPTIONS.md`.

## Install

Python ≥ 3.11 (developed on 3.14). Dependencies: numpy, pytest.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python run.py --scenario Scenarios/Scenario1
```

This writes `plan.json` and `statistics.txt` to `outputs/<scenario dir name>/` (git-ignored).

| Flag | Values (default first) | Meaning |
|---|---|---|
| `--scenario DIR` | required | scenario directory with the 7 input files |
| `--out DIR` | `outputs/<scenario>/` | output directory |
| `--planner` | `csp`, `greedy` | CSP (backtracking + MRV + FC + B&B) or greedy baseline |
| `--after-job` | `on-site`, `return` | responder stays at the incident or drives back to its start [D 2] |
| `--tau` | `0.5` | a road is removed if P(Blocked) ≥ tau [D 5] |
| `--traffic-mult` | `Low=1.0,Medium=1.2,High=1.5` | travel-time multiplier per traffic level, all ≥ 1 [D 7] (unlisted levels keep their default) |
| `--unobserved-traffic` | `initial`, `neutral`, `stationary` | traffic factor of roads without observations (OQ-2) |
| `--hmm-init` | `pi_is_t1`, `pi_is_t0` | whether `initial` is P(X_1) or P(X_0) (OQ-1) |
| `--csp-node-limit N` | `200000` | node budget of the CSP search per decision |
| `--no-validate` | off | skip the plan validator checks (the timeline is still reconstructed for the statistics) |
| `--no-bayes` | off | ablation: every road Open with P = 1 (e_mult = 1, no road removed); Bayesian inference is skipped (D06) |
| `--no-hmm` | off | ablation: f_traffic = 1 for every road, observed or not; HMM filtering is skipped and `--unobserved-traffic` has no effect (D06) |

Exit codes: `0` OK, `1` the plan has validation errors (files are still written), `2` input error.

Sensitivity analysis (one factor at a time, SPEC §5.16, including the `use_bayes` / `use_hmm`
ablations), writes `outputs/sensitivity.md`:

```bash
python experiments/sensitivity.py
```

## Results

`results/` (tracked by git) holds the reference outputs: `results/sensitivity.md` and
`results/Scenario1..3/statistics.txt` (default settings). `outputs/` is git-ignored, so
regenerate them there and copy them over:

```bash
for s in 1 2 3; do python run.py --scenario Scenarios/Scenario$s; done
python experiments/sensitivity.py
for s in 1 2 3; do mkdir -p results/Scenario$s && cp outputs/Scenario$s/statistics.txt results/Scenario$s/; done
cp outputs/sensitivity.md results/
```

## Test

```bash
python -m pytest                # all tests
python -m pytest tests/test_stats.py -q
```

Some tests call the student kernels (`erp/bayes.py`, `erp/hmm.py`, `erp/search.py`,
`erp/csp.py`, functions marked `# STUDENT:`), others inject hand-made beliefs and reference
routers so that the infrastructure is tested on its own. Reference implementations used only
by tests (Dijkstra, brute-force HMM, exhaustive CSP) live in `tests/reference.py` and are never
imported by `erp/`.

## Layout

```
run.py                     CLI entry point
erp/config.py              Config + CLI parsing
erp/model.py               data classes, natural id order, order keys
erp/io_load.py             scenario loading + input checks I001–I012
erp/bayes.py               road-status prior/posterior          (student kernels + wrapper)
erp/hmm.py                 forward filter, traffic factor        (student kernel + wrapper)
erp/roadnet.py             beliefs, edge weights, usable graph
erp/search.py              A* + heuristic                        (student kernels)
erp/routing.py             memoised route cache
erp/allocation.py          allocation problem, schedule, lexicographic cost
erp/csp.py                 CSP allocation                        (student kernels + planner wrapper)
erp/greedy.py              greedy baseline / CSP incumbent
erp/simulate.py            event-driven rolling-horizon simulation
erp/validate.py            plan validator                        (independent of the planner)
erp/stats.py, output.py    statistics and writers
experiments/sensitivity.py sensitivity analysis
tests/                     SPEC §8 tests, fixtures, reference implementations
```
