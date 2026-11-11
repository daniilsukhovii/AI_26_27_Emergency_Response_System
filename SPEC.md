# SPEC — Emergency Response Decision-Support System

Status: draft for review (nothing implemented yet).
Sources used: `Assignment1.pdf`, `Scenarios/README.md`, `Scenarios/Scenario1-3/*`,
`ASSUMPTIONS.md`, `CLAUDE.md`. Nothing else is normative. Where this spec cites a
rule it names the source: **[A §x]** = assignment section, **[S-README]** =
`Scenarios/README.md`, **[D n]** = ASSUMPTIONS.md decision n, **[T n]** = ASSUMPTIONS.md
trap case n, **[F]** = ASSUMPTIONS.md §2 formulas, **[C]** = CLAUDE.md.
Anything not covered by a source is marked **ENG** (engineering choice that has no effect
on the problem semantics) or **OQ-n** (open question, see §11; the stated default is
provisional and must be confirmed by the student).

---

## 0. Conventions

| Item | Rule | Source |
|---|---|---|
| Time | seconds (s), `float`, never truncated; simulation starts at t = 0 | [S-README], [T 8] |
| Distance / coordinates | metres (m) | [S-README] |
| Speed | m/s | [S-README] |
| Probabilities | `float` in [0, 1]; every distribution sums to 1 (tolerance 1e-6 on input, 1e-9 after normalisation) | ENG |
| Roads | **directed**; key `(from, to)`; reports, posteriors, traffic observations and filtering are per directed road | [D add.], [S-README] |
| Road states | static during the whole simulation; reports refer to t = 0 | [D add.] |
| Python | ≥ 3.11; stdlib + numpy + pytest only | [C] |
| Hard-coded values | no scenario-specific values (node ids, speeds, counts) in code; model parameters live in `Config` | [C] |
| Future knowledge | no component may read an incident whose `timestamp` > current simulation time. An incident is known at time t iff `timestamp ≤ t`, compared **exactly** (no EPS); the same exact comparison is used by E402 | [C], [A §3.2] |
| Student functions | functions marked `# STUDENT:` are stubs only (signature, type hints, docstring, `raise NotImplementedError`). The coding agent never writes their bodies, even if tests fail, and never weakens tests | [C] |
| Determinism | identical inputs + config ⇒ byte-identical outputs. All ties are broken by **natural id order** (`"I2" < "I10"`, key = `(alpha prefix, int suffix)`) | ENG, [T 3] |
| Float comparisons | `a ≤ b` is evaluated as `a ≤ b + EPS` with `EPS = 1e-9` s (deadlines, availability / `free_at`); never for incident timestamps (see Future knowledge) | ENG |

Priority rank (used everywhere an order over priorities is needed):
`rank(Critical)=0, rank(High)=1, rank(Medium)=2, rank(Low)=3`.

Incident order key (ENG, consistent with [T 3]):
`order_key(i) = (rank(i.priority), i.deadline, i.timestamp, natural(i.id))`.

---

## 1. Inputs

One scenario = one directory with exactly these 7 files [A §2]. PNG files are not used.

### 1.1 File formats (as observed in Scenario1-3)

| File | Format | Fields / structure |
|---|---|---|
| `city_graph.json` | JSON | `nodes: [{id, name, x, y, type}]`, `type ∈ {normal, hospital, police, fire_station}` (informational only); `roads: [{from, to, distance, road_type, speed}]`, `road_type ∈ {main, secondary}` (informational only; `speed` is used) |
| `responders.csv` | CSV, header | `responder_id, type, start_location, capabilities, availability, time_until_available`; `capabilities` is `;`-separated; `availability ∈ {Available, Busy}` |
| `incidents.csv` | CSV, header | `incident_id, location, priority, deadline, required_capability, timestamp, time_required` |
| `road_reports.csv` | CSV, header | `from, to, weather, source, reported_status`; `source ∈ {Citizen, Police, Sensor}`; `weather ∈ {Clear, Rain, Storm}` |
| `road_probabilities.json` | JSON | `weather_prior[w]`, `road_status_given_weather[w][S]`, `citizen_report[S_true][S_rep]`, `police_report[...]`, `sensor_report[...]` — **outer key = true status, inner key = reported status** [F] |
| `observed_traffic.csv` | CSV, header | `observation_nr, from, to, traffic_observation`; one sequence per directed road, ordered by `observation_nr` (not a simulation time) [S-README] |
| `traffic_probabilities.json` | JSON | `initial[L]`, `transition[L_prev][L_next]`, `emission[L_state][L_obs]` (rows sum to 1, verified on all 3 scenarios) |

Note: `traffic_probabilities.json` of Scenario2 differs from Scenario1/3 (`initial` 0.50/0.35/0.15 etc.); `road_probabilities.json` is identical in all three. Always load per scenario.

### 1.2 Parsing rules

* Blank / whitespace-only CSV lines are skipped [T 7] (they occur in S1/S2/S3 `observed_traffic.csv` and `road_reports.csv`).
* Leading/trailing whitespace around fields is stripped (ENG).
* All numeric fields parsed with `float()` [T 8]; `observation_nr` with `int()`.
* `source` mapping to CPT keys: `Citizen→citizen_report`, `Police→police_report`, `Sensor→sensor_report`.
* Responder with `availability = Busy` becomes free at `time_until_available` at its `start_location` [D 2]. `Available` ⇒ free at 0.

### 1.3 Input checks (raise `InputError(code, msg)` for errors; warnings are collected and printed)

| Code | Sev. | Check |
|---|---|---|
| I001 | error | a required file or CSV column is missing |
| I002 | error | duplicate node / responder / incident id, or duplicate directed road |
| I003 | error | a road, report, observation, responder start or incident location references an unknown node |
| I004 | error | unknown label (priority, availability, weather, source, status, traffic level) |
| I005 | error | a probability row is negative or does not sum to 1 (±1e-6) |
| I006 | error | `distance ≤ 0`, `speed ≤ 0`, negative `time_required`, `time_until_available`, `timestamp` |
| I007 | error | reports for one directed road carry different `weather` values (not present in data; the posterior needs one `w`) |
| I008 | warning | `observation_nr` of a road is not 1..n without gaps (sequence is still ordered by `observation_nr`) |
| I009 | warning | `deadline < timestamp` (incident can never be met; still planned, [D 4]) |
| I010 | warning | Euclidean distance between road endpoints > `distance` (A* heuristic may become inadmissible, §6.6). Not triggered by any scenario (max ratio 0.983) |
| I011 | warning | `Available` with `time_until_available > 0`, or `Busy` with `0` |
| I012 | warning | a report / observation refers to a road not in the graph (ignored). Not triggered by any scenario |
| I013 | error | evidence has probability 0 under the model (allowed by I005, which accepts zero entries): a road's reports have likelihood 0 for every status (posterior normaliser Z = 0, §6.1), or a road's traffic observation sequence has probability 0 under the HMM (§6.4). Raised by the infrastructure wrappers `compute_status_beliefs` / `compute_traffic_factors` when the kernel raises `ValueError`, i.e. while building the network, not in `load_scenario`; `run.py` exits with status 2. Not triggered by any scenario |

---

## 2. Outputs

`run.py` writes both files into the output directory (default `outputs/<scenario dir name>/`, ENG; `outputs/` is git-ignored).

### 2.1 `plan.json` [A §5.1]

A JSON list; each element exactly:

```json
{"responder_id": "R1", "incident_id": "I1", "path": ["N1", "H1", "N2"], "time": 0}
```

* `time` = **departure time** [D 1]: `time ≥ max(incident.timestamp, responder free time)`.
* `path` = node ids from the responder's position at departure to the incident location, consecutive nodes joined by a usable directed road.
* Only committed assignments appear (one per handled incident). Return trips are not written [D 2].
* Order: by `(time, natural(responder_id))` (ENG). Integral times are written as JSON integers, others as floats (ENG, matches the example).
* Indent 4 spaces, UTF-8, trailing newline (ENG).

### 2.2 `statistics.txt` [A §5.2]

The first block reproduces the assignment's example format exactly; a details block follows.

```
System statistics:

 * 5 incidents handled
 * 3 responders used
 * Average response time: 65.7 s
 * Deadlines met: 57.1%

Details:
 * The "Deadlines met" line above is the same value as "Deadlines met (all incidents)" below (§6.8, [D 10])
 * Time unit: seconds (s) of simulation time; response time = arrival time - incident timestamp
 * Incidents: 7 total, 5 handled (1 late), 2 unhandled: I3 (no capable responder), I6 (unreachable)
 * Deadlines met (all incidents, unhandled = missed): 57.1% (4/7)
 * Deadlines met (Critical): 50.0% (1/2)
 * Missed deadlines: Critical 1, High 1, Medium/Low 1
 * Configuration: ...
 * Roads removed (P(Blocked) >= tau): ...
 * Validation: 0 errors, 3 warnings (W401 x1, W501 x1, W502 x1)

Per incident:
 id   priority  responder  depart   arrive   deadline  response  status
 I1   High      R2         0.0      12.6     80.0      12.6      met
 ...
```

Formulas: §6.8. Numbers printed with 1 decimal (as in the example); "n/a" when the denominator is 0.

---

## 3. Architecture

### 3.1 Layout

```
run.py                     CLI entry point                                   infra
erp/__init__.py
erp/config.py              Config dataclass + CLI parsing helpers            infra
erp/model.py               immutable data classes, type aliases, order keys  infra
erp/io_load.py             load_scenario + input checks (§1.3)               infra
erp/bayes.py               road-status prior/posterior                      STUDENT kernel + infra wrapper
erp/hmm.py                 forward filtering, traffic factor                STUDENT kernel + infra wrapper
erp/roadnet.py             RoadBelief per road, edge weights, usable graph  infra
erp/search.py              A* + heuristic                                    STUDENT kernel
erp/routing.py             RouteCache (memoised A* calls)                    infra
erp/allocation.py          AllocationProblem, schedule simulation, cost     infra
erp/csp.py                 backtracking + MRV + FC + branch-and-bound       STUDENT kernel
erp/greedy.py              greedy baseline planner                          infra
erp/simulate.py            event-driven rolling-horizon simulation          infra
erp/validate.py            plan validator, timeline reconstruction, Dijkstra infra
erp/stats.py               statistics computation                           infra
erp/output.py              writers for plan.json / statistics.txt           infra
experiments/sensitivity.py tau ∈ {0.3,0.5,0.7} × scenarios × planners       infra
tests/...                  §8
```

### 3.2 Data flow

```
load_scenario ─► compute_road_beliefs (bayes.road_status_posterior / prior)
              ─► compute_traffic_factors (hmm.forward_filter)
              ─► build_network (edge weights, removal by tau)
              ─► simulate(planner = csp | greedy, router = RouteCache(search.astar))
                     at each event: AllocationProblem ─► planner ─► commit departures
              ─► plan (list[Assignment])
              ─► validate(plan) ─► Timeline ─► compute_statistics ─► write outputs
```

Dependency rule (ENG): `validate.py` and `stats.py` never import `simulate`, `csp`, `greedy`, `search`. They re-derive timelines from `plan + scenario + network` only, so the validator is an independent check of the planner. They do share `roadnet` (edge weights) — see limitation L2.

Injection rule (ENG): `simulate` takes `router` and `planner` as parameters and `build_network` accepts precomputed beliefs, so infrastructure tests can run before the student kernels exist (tests inject the validator's Dijkstra / hand-made beliefs; the production path in `run.py` always uses the student kernels).

---

## 4. Data structures (`erp/model.py`)

```python
from dataclasses import dataclass, field
from typing import Literal, Mapping, Callable

NodeId = str
RoadKey = tuple[NodeId, NodeId]                     # (from, to), directed
Status = Literal["Open", "Congested", "Blocked"]
Level = Literal["Low", "Medium", "High"]
Priority = Literal["Critical", "High", "Medium", "Low"]
Weather = Literal["Clear", "Rain", "Storm"]
Source = Literal["Citizen", "Police", "Sensor"]
Dist = dict[str, float]                             # label -> probability
CostTuple = tuple[int, int, int, float]             # §6.7

STATUSES: tuple[Status, ...] = ("Open", "Congested", "Blocked")
LEVELS: tuple[Level, ...] = ("Low", "Medium", "High")

@dataclass(frozen=True)
class Node:
    id: NodeId; name: str; x: float; y: float; type: str          # x, y in m

@dataclass(frozen=True)
class Road:
    src: NodeId; dst: NodeId
    distance: float      # m
    speed: float         # m/s
    road_type: str
    @property
    def key(self) -> RoadKey: ...

@dataclass(frozen=True)
class Responder:
    id: str; type: str; start_location: NodeId
    capabilities: frozenset[str]
    available: bool
    time_until_available: float   # s; free time at t=0 is this value if Busy, else 0

@dataclass(frozen=True)
class Incident:
    id: str; location: NodeId; priority: Priority
    deadline: float          # s, absolute arrival deadline [A §3.2]
    required_capability: str
    timestamp: float         # s, time the incident becomes known
    time_required: float     # s, on-site handling time after arrival

@dataclass(frozen=True)
class RoadReport:
    road: RoadKey; weather: Weather; source: Source; reported_status: Status

@dataclass(frozen=True)
class RoadCPTs:
    weather_prior: Mapping[Weather, float]
    status_given_weather: Mapping[Weather, Mapping[Status, float]]
    report: Mapping[Source, Mapping[Status, Mapping[Status, float]]]  # [source][true][reported]

@dataclass(frozen=True)
class HMMParams:
    initial: Mapping[Level, float]
    transition: Mapping[Level, Mapping[Level, float]]   # [prev][next]
    emission: Mapping[Level, Mapping[Level, float]]     # [state][observation]

@dataclass(frozen=True)
class Scenario:
    name: str
    nodes: Mapping[NodeId, Node]
    roads: Mapping[RoadKey, Road]
    responders: Mapping[str, Responder]                 # natural id order
    incidents: tuple[Incident, ...]                     # sorted by (timestamp, natural id)
    reports: Mapping[RoadKey, tuple[RoadReport, ...]]   # file order
    traffic_obs: Mapping[RoadKey, tuple[Level, ...]]    # ordered by observation_nr
    cpts: RoadCPTs
    hmm: HMMParams
    warnings: tuple[str, ...]

@dataclass(frozen=True)
class RoadBelief:
    road: RoadKey
    status: Mapping[Status, float]        # posterior (reports) or prior via P(W)
    has_reports: bool
    traffic: Mapping[Level, float] | None # filtered distribution, None if no observations
    f_traffic: float                      # dimensionless, ≥ 1
    e_mult: float                         # E[status multiplier | not Blocked], dimensionless, ≥ 1
    removed: bool                         # status["Blocked"] >= tau
    weight: float                         # s; math.inf if removed

@dataclass(frozen=True)
class Assignment:
    responder_id: str; incident_id: str
    path: tuple[NodeId, ...]
    time: float                           # departure, s
    def to_json(self) -> dict: ...

@dataclass
class ResponderState:                     # simulator-internal
    id: str
    position: NodeId                      # where it is / will be when free
    free_at: float                        # s

@dataclass(frozen=True)
class Route:
    path: tuple[NodeId, ...]; cost: float  # cost in s

@dataclass(frozen=True)
class AllocationProblem: ...              # §5.8
@dataclass(frozen=True)
class AllocationResult: ...               # §5.9

@dataclass(frozen=True)
class TimelineEntry:                      # validator / stats
    assignment: Assignment
    start_node: NodeId
    departure: float; arrival: float; finish: float; free_at: float   # all s
    position_after: NodeId
    deadline_met: bool
    response_time: float                  # arrival - incident.timestamp, s

@dataclass(frozen=True)
class Issue:
    code: str; severity: Literal["error", "warning"]
    entry: int | None                     # index in plan.json, None = global
    message: str
```

Helper functions in `model.py`: `natural_key(id: str) -> tuple[str, int]`, `priority_rank(p) -> int`, `order_key(inc) -> tuple`.

---

## 5. Modules and signatures

### 5.1 `erp/config.py`

```python
@dataclass(frozen=True)
class Config:
    tau: float = 0.5                                   # [D 5]
    congested_multiplier: float = 1.5                  # [A §3.3]
    traffic_multipliers: Mapping[Level, float] = {"Low": 1.0, "Medium": 1.2, "High": 1.5}  # [D 7]
    unobserved_traffic: Literal["initial", "neutral", "stationary"] = "initial"  # OQ-2
    after_job: Literal["on-site", "return"] = "on-site"   # [D 2]
    planner: Literal["csp", "greedy"] = "csp"
    csp_node_limit: int = 200_000                      # ENG, anytime B&B guard
    hmm_init_convention: Literal["pi_is_t1", "pi_is_t0"] = "pi_is_t1"  # OQ-1
    validate: bool = True
    use_bayes: bool = True   # False: every road Open with P = 1 (e_mult = 1, nothing removed); ablation
    use_hmm: bool = True     # False: f_traffic = 1 for every road; ablation

def config_from_args(argv: list[str] | None = None) -> tuple[Path, Path, Config]: ...
```
`traffic_multipliers` must all be ≥ 1 (otherwise the heuristic of §6.6 may be inadmissible → `ValueError`).

### 5.2 `erp/io_load.py`

```python
class InputError(Exception):
    code: str
def load_scenario(directory: Path) -> Scenario
def read_csv_rows(path: Path, required: Sequence[str]) -> list[dict[str, str]]   # skips blank lines [T 7]
def check_scenario(s: Scenario) -> list[str]                                     # §1.3 warnings
```

### 5.3 `erp/bayes.py`

```python
# STUDENT:
def road_status_prior(cpts: RoadCPTs) -> dict[Status, float]:
    """P(S) = Σ_w P(w)·P(S|w)  (§6.2). Used for roads without reports [D 6]."""

# STUDENT:
def road_status_posterior(cpts: RoadCPTs, weather: Weather,
                          reports: Sequence[RoadReport]) -> dict[Status, float]:
    """P(S | w, r_1..r_k) ∝ P(S|w)·Π_k P(r_k|S)  (§6.1). Normalised; order-invariant.
    With an empty report list it returns P(S|w)."""

# infra:
def compute_status_beliefs(s: Scenario) -> dict[RoadKey, tuple[dict[Status, float], bool]]
    """For every graph road: posterior if it has reports (weather taken from its reports),
    else the prior. Returns (distribution, has_reports)."""
```

### 5.4 `erp/hmm.py`

```python
# STUDENT:
def forward_filter(params: HMMParams, observations: Sequence[Level],
                   convention: str = "pi_is_t1") -> list[dict[Level, float]]:
    """Normalised forward messages α_1..α_T (§6.4). Returns one distribution per observation;
    the last one is the filtered state [D 8]. Raises ValueError on an empty sequence."""

# infra:
def expected_traffic_factor(dist: Mapping[Level, float], mult: Mapping[Level, float]) -> float  # §6.5
def stationary_distribution(params: HMMParams) -> dict[Level, float]   # numpy eig; only for OQ-2 "stationary"
def compute_traffic_factors(s: Scenario, cfg: Config) -> dict[RoadKey, tuple[dict[Level, float] | None, float]]
    """Per graph road: (filtered distribution or None, f_traffic). Roads without observations get
    f_traffic according to cfg.unobserved_traffic (OQ-2)."""
```

### 5.5 `erp/roadnet.py`

```python
def expected_status_multiplier(status: Mapping[Status, float], congested_mult: float) -> float  # §6.3
def edge_weight(road: Road, e_mult: float, f_traffic: float) -> float                         # §6.5, s
def compute_road_beliefs(s: Scenario, cfg: Config) -> dict[RoadKey, RoadBelief]

class RoadNetwork:
    def __init__(self, s: Scenario, beliefs: Mapping[RoadKey, RoadBelief], cfg: Config): ...
    nodes: Mapping[NodeId, Node]
    v_max: float                                      # max road speed in the graph (OQ-3)
    def neighbours(self, u: NodeId) -> list[tuple[NodeId, float]]   # usable roads only, natural order of v
    def is_usable(self, u: NodeId, v: NodeId) -> bool
    def weight(self, u: NodeId, v: NodeId) -> float   # inf if missing or removed
    def path_cost(self, path: Sequence[NodeId]) -> float   # Σ weights; 0 for a 1-node path; inf if any edge unusable
    def removed_roads(self) -> list[tuple[RoadKey, float]]  # with P(Blocked)

def build_network(s: Scenario, cfg: Config,
                  beliefs: Mapping[RoadKey, RoadBelief] | None = None) -> RoadNetwork
```

### 5.6 `erp/search.py`

```python
# STUDENT:
def euclidean_heuristic(net: RoadNetwork, goal: NodeId) -> Callable[[NodeId], float]:
    """h(n) = euclid(n, goal) / v_max  (§6.6), seconds."""

# STUDENT:
def astar(net: RoadNetwork, start: NodeId, goal: NodeId,
          h: Callable[[NodeId], float] | None = None) -> Route | None:
    """A* over usable roads. Returns Route(path, cost) with path[0]=start, path[-1]=goal,
    cost = net.path_cost(path); Route((start,), 0.0) if start == goal; None if unreachable.
    Must terminate on every finite graph. Deterministic tie-break on equal f: smaller h, then
    natural node id (ENG; the student may change the rule but must keep it deterministic)."""
```

Optional (STUDENT, for the report): an expansion counter returned via a module-level stats object or an extra function `astar_with_stats(...) -> tuple[Route | None, int]`.

### 5.7 `erp/routing.py`

```python
class RouteCache:
    def __init__(self, net: RoadNetwork, search: Callable[..., Route | None] = astar): ...
    def route(self, u: NodeId, v: NodeId) -> Route | None     # memoised; road states are static [D add.]
    def travel_time(self, u: NodeId, v: NodeId) -> float      # inf if None
```

### 5.8 `erp/allocation.py` (infra; shared by CSP, greedy, tests)

```python
@dataclass(frozen=True)
class ResponderSnapshot:
    id: str; capabilities: frozenset[str]; start_location: NodeId
    position: NodeId          # current node, or node where it will become free
    free_at: float            # s; ≤ now means free now

@dataclass(frozen=True)
class AllocationProblem:
    now: float                                         # s
    incidents: tuple[Incident, ...]                    # pending, all with timestamp <= now (asserted), sorted by order_key
    responders: tuple[ResponderSnapshot, ...]          # natural id order
    domains: Mapping[str, tuple[str, ...]]             # incident id -> capable responder ids that can reach it
                                                       #   from their position; sorted by (arrival estimate, natural id)
    travel: Callable[[NodeId, NodeId], float]          # RouteCache.travel_time, s
    after_job: Literal["on-site", "return"]

def build_problem(now: float, pending: Sequence[Incident],
                  states: Mapping[str, ResponderState], s: Scenario,
                  router: RouteCache, cfg: Config) -> AllocationProblem

def simulate_schedule(p: AllocationProblem, assignment: Mapping[str, str]
                      ) -> dict[str, tuple[float, float]] | None
    """For a (partial) mapping incident->responder returns incident -> (departure, arrival) in s,
    or None if some chained leg is unreachable. Per responder the assigned incidents are served in
    order_key order (OQ-4), §6.7."""

def schedule_cost(p: AllocationProblem, assignment: Mapping[str, str]) -> CostTuple | None
    """Lexicographic cost §6.7 over the incidents in `assignment`. Monotone: adding an incident
    to a partial assignment never decreases any component ⇒ valid lower bound for B&B."""
```

Planner protocol: `Planner = Callable[[AllocationProblem], Mapping[str, str]]` (incident id → responder id; incidents may be omitted only if their domain is empty, or — greedy only — if no capable responder is free now).

### 5.9 `erp/csp.py`

CSP formulation (default; see OQ-4):

* **Variables**: the pending incidents of the current event (`p.incidents`).
* **Domains**: `p.domains[i]` — responders that have `i.required_capability` [A §3.1] and from whose `position` a route to `i.location` exists. Busy responders are included (their departure is `free_at`).
* **Hard constraints**: capability, reachability (unary, already in the domain); chained reachability (incidents on the same responder must be reachable one after another — checked by `simulate_schedule`); one responder per incident (inherent: each variable has one value) [D add.]; no overlapping jobs (inherent: a responder's incidents are served sequentially).
* **Soft constraints / objective**: lexicographic cost §6.7 [D 11]. Deadlines are soft [D 4].
* **Search**: backtracking; variable choice **MRV** (smallest current domain; ties by `order_key`); **value order**: increasing partial schedule cost `schedule_cost(partial ∪ {Y: r})` (values that make the partial schedule infeasible are skipped), ties by natural responder id — since the values are tried in increasing order of this lower bound, the first value whose cost is ≥ the incumbent ends the loop for all remaining values (branch-and-bound break, D08); **forward checking** after each assignment: for every unassigned variable remove values that make `simulate_schedule` infeasible or whose `schedule_cost(partial ∪ {Y: r})` is ≥ the incumbent (cost-based FC); empty domain ⇒ backtrack; **branch-and-bound**: prune when `schedule_cost(partial) ≥ incumbent`.
* **Incumbent**: the greedy solution of the same problem (`greedy.greedy_assignment(p)`) if feasible, else +∞.

```python
@dataclass(frozen=True)
class AllocationResult:
    assignment: Mapping[str, str]   # incident id -> responder id (all variables with non-empty domain)
    cost: CostTuple | None
    nodes_expanded: int
    optimal: bool                   # False if csp_node_limit was hit (best found so far returned)

# STUDENT:
def select_unassigned_variable(p: AllocationProblem, domains: Mapping[str, Sequence[str]],
                               assignment: Mapping[str, str]) -> str          # MRV

# STUDENT:
def forward_check(p: AllocationProblem, domains: Mapping[str, Sequence[str]],
                  assignment: Mapping[str, str], incumbent: CostTuple | None
                  ) -> dict[str, tuple[str, ...]] | None                       # None = wipe-out

# STUDENT:
def solve_allocation(p: AllocationProblem, node_limit: int,
                     incumbent: Mapping[str, str] | None = None) -> AllocationResult
    """Backtracking + MRV + FC + B&B. Returns the lexicographically optimal complete assignment
    (or best found under node_limit). Variables with empty initial domain are left out."""

# infra:
def csp_planner(cfg: Config) -> Planner    # wraps solve_allocation; logs nodes_expanded / optimal
```

If `solve_allocation` returns no feasible complete assignment, `csp_planner` falls back to the greedy mapping for that event and logs a warning (ENG).

### 5.10 `erp/greedy.py` (baseline, OQ-8)

```python
def greedy_assignment(p: AllocationProblem) -> dict[str, str]
    """Incidents in order_key order; each takes the capable responder (free now or busy) with the
    earliest arrival given the responders' already-built queues (simulate_schedule); ties by
    natural responder id. Used as CSP incumbent."""
def greedy_planner(cfg: Config) -> Planner
    """Baseline for comparison: incidents in order_key order; each takes the capable responder
    that is free NOW with the earliest arrival; a responder takes at most one incident per event;
    no reservations of busy responders."""
```

### 5.11 `erp/simulate.py`

```python
@dataclass(frozen=True)
class SimulationResult:
    assignments: tuple[Assignment, ...]
    unhandled: Mapping[str, str]          # incident id -> reason ("no capable responder" | "unreachable")
    event_log: tuple[str, ...]
    planner_calls: int
    csp_nodes_expanded: int
    csp_all_optimal: bool

def simulate(s: Scenario, net: RoadNetwork, cfg: Config,
             planner: Planner, router: RouteCache) -> SimulationResult
```

Algorithm (rolling horizon [D 3]):

```
state[r] = ResponderState(r.id, r.start_location, free_at = r.time_until_available if Busy else 0)
assigned = {}; t = 0
loop:
    known   = [i for i in incidents if i.timestamp <= t]                 # exact, no EPS: never later ones [C]
    pending = [i for i in known if i.id not in assigned]
    free    = [r for r in state if state[r].free_at <= t + EPS]
    if pending and free:
        p = build_problem(t, pending, state, ...)                        # asserts timestamps <= t
        mapping = planner(p)
        for r in free (natural order):
            queue = [i for i in mapping if mapping[i] == r] sorted by order_key
            if queue:  commit head j:
                route = router.route(state[r].position, j.location)
                arrival = t + route.cost ; finish = arrival + j.time_required
                on-site: state[r] = (j.location, finish)
                return:  back = router.route(j.location, r.start_location)
                         state[r] = (r.start_location, finish + back.cost)   if back
                                    (j.location, finish) + warning           if not back (OQ-7)
                append Assignment(r, j, route.path, t); assigned[j] = r
        if a commit produced free_at <= t + EPS (zero-length job): repeat at the same t
           (bounded: each repetition commits ≥ 1 incident)
    next_t = min({i.timestamp > t} ∪ {state[r].free_at > t + EPS})      # timestamps exact, free_at with EPS
    if none: break
    t = next_t
unhandled = remaining pending (+ incidents never known — impossible, all timestamps are finite);
reason = "no capable responder" if no responder has the capability [T 1], else "unreachable" [T 2] (OQ-6)
```

Properties: a job in progress is never interrupted [T 9]; a responder is never dispatched before it is free [D 1]; the loop terminates because event times strictly increase and there are finitely many incidents and responders [T 2].

### 5.12 `erp/validate.py`

```python
def dijkstra_all(net: RoadNetwork, source: NodeId) -> dict[NodeId, float]   # independent of search.py
def reconstruct_timeline(s: Scenario, net: RoadNetwork, cfg: Config,
                         plan: Sequence[Assignment]) -> tuple[dict[str, list[TimelineEntry]], list[Issue]]
def validate_plan(s: Scenario, net: RoadNetwork, cfg: Config,
                  raw_plan: object) -> tuple[list[Assignment], dict[str, list[TimelineEntry]], list[Issue]]
def load_plan_json(path: Path) -> object
```
Checks and codes: §7. Exit status of `run.py` is 1 if any error-severity issue is found (ENG).

### 5.13 `erp/stats.py`

```python
@dataclass(frozen=True)
class Statistics:
    n_total: int; n_handled: int; n_unhandled: int; n_late: int
    responders_used: int
    avg_response_time: float | None          # s
    pct_deadlines_met: float | None          # %
    pct_critical_met: float | None           # %
    missed_by_class: tuple[int, int, int]    # Critical, High, Medium/Low
    per_incident: tuple[...]
def compute_statistics(s: Scenario, timeline: Mapping[str, list[TimelineEntry]],
                       unhandled: Mapping[str, str]) -> Statistics
```

### 5.14 `erp/output.py`

```python
def write_plan(path: Path, plan: Sequence[Assignment]) -> None
def format_statistics(st: Statistics, cfg: Config, net: RoadNetwork, issues: Sequence[Issue]) -> str
def write_statistics(path: Path, text: str) -> None
```

### 5.15 `run.py`

```
python run.py --scenario Scenarios/Scenario1 [--out DIR] [--planner csp|greedy]
              [--after-job on-site|return] [--tau 0.5]
              [--traffic-mult Low=1.0,Medium=1.2,High=1.5]
              [--unobserved-traffic initial|neutral|stationary]
              [--hmm-init pi_is_t1|pi_is_t0] [--csp-node-limit N] [--no-validate]
              [--no-bayes] [--no-hmm]
```
Exit codes: 0 = OK, 1 = plan has validation errors (files are still written), 2 = input error.

### 5.16 `experiments/sensitivity.py`

Baseline: tau = 0.5, after_job = on-site, unobserved_traffic = initial,
default traffic multipliers.
For every scenario and planner ∈ {csp, greedy}: run the baseline, then vary
one factor at a time, keeping the others at baseline:
  * tau ∈ {0.3, 0.7}                                  [D 5]
  * unobserved_traffic ∈ {neutral, stationary}        OQ-2
  * after_job = return                                [D 2]
  * use_bayes = False; use_hmm = False; both False      D06
Writes `outputs/sensitivity.md`: one row per run with columns
scenario, planner, varied factor, value, handled, avg response (s),
% met, % Critical met, removed roads, roads with observed traffic / usable
roads, CSP nodes, CSP optimal (yes/no).
These columns are "self-evaluated" (the plan judged on the network it was planned on); each row additionally has "baseline-evaluated" columns — error codes with counts, avg response, % met, % Critical met — from `validate_plan(scenario, baseline_network, Config(after_job = the run's after_job), plan)`, where `baseline_network` uses the default tau, multipliers, use_bayes and use_hmm.
A plan with any error-severity issue under the baseline model (§7.1, e.g. E304 a path uses a removed road, E404 a responder departs while still busy) is infeasible there: its error codes are listed with counts, and its baseline avg response, % met and % Critical met are shown as "n/a (infeasible)" (they would be computed from an impossible timeline).
Sanity expectation: in S1 every road has traffic observations, so the
unobserved_traffic variants must give results identical to the baseline.
---

## 6. Formulas

### 6.1 Road-status posterior (roads with reports) [F]

For directed road e with reports r_1..r_k (all with weather w, local to the road [S-README]):

```
P(S | w, r_1..r_k) = P(S | w) · Π_{j=1..k} P(r_j | S, source_j)  /  Z
Z = Σ_{S'} P(S' | w) · Π_j P(r_j | S', source_j)
```
S ∈ {Open, Congested, Blocked}; `P(r | S, src) = cpts.report[src][S][r]` (outer = true status). Dimensionless. Implies reports are conditionally independent given S and do not depend on w given S (naive-Bayes structure of the given CPTs).

### 6.2 Prior via P(W) (roads without reports) [D 6]

```
P(S) = Σ_{w ∈ {Clear,Rain,Storm}} P(w) · P(S | w)
```
All scenarios: Open = 0.5·0.95 + 0.3·0.60 + 0.2·0.15 = **0.685**; Congested = 0.5·0.04 + 0.3·0.30 + 0.2·0.35 = **0.18**; Blocked = 0.5·0.01 + 0.3·0.10 + 0.2·0.50 = **0.135**.

### 6.3 Blocked rule and status multiplier [D 5], [F]

```
removed(e)  ⇔  P(Blocked | evidence) ≥ τ          (τ = 0.5 default)
E[mult | not Blocked] = (P(Open)·1 + P(Congested)·m_C) / (P(Open) + P(Congested)),  m_C = 1.5 [A §3.3]
```
Dimensionless, in [1, 1.5]. For prior roads: 0.955 / 0.865 = **1.104046**. (If P(Open)+P(Congested) = 0 the road is removed for every τ ≤ 1, so the division never happens.)

### 6.4 HMM forward filtering [D 8]

States and observations L ∈ {Low, Medium, High}; π = `initial`, A[i][j] = `transition[i][j]` = P(X_t=j | X_{t-1}=i), B[i][o] = `emission[i][o]` = P(O_t=o | X_t=i). Observations o_1..o_T of one directed road (order = `observation_nr`).

Convention `pi_is_t1` (default, OQ-1):
```
α̃_1(j) = π(j) · B[j][o_1]
α̃_t(j) = B[j][o_t] · Σ_i α_{t-1}(i) · A[i][j]         t = 2..T
α_t(j) = α̃_t(j) / Σ_k α̃_t(k)                          (normalise every step)
```
Convention `pi_is_t0`: α_0 = π, then the recursion for t = 1..T.
Result: P(X_T | o_1..o_T) = α_T. Static use: this distribution is used for the whole simulation [D 8]. Dimensionless.

### 6.5 Traffic factor and edge weight [D 7], [F]

```
f_traffic(e) = Σ_L P(X_T = L | o_1..o_T) · mult(L)      mult = {Low 1.0, Medium 1.2, High 1.5}   (dimensionless, ≥ 1)
w(e) [s] = distance(e) [m] / speed(e) [m/s] · E[mult | not Blocked](e) · f_traffic(e)      if not removed(e)
w(e) = ∞                                                                                   if removed(e)
```
Roads without traffic observations: `f_traffic` by OQ-2 — `initial`: Σ_L π(L)·mult(L) (S1/S3 1.110, S2 1.145); `neutral`: 1.0; `stationary`: Σ_L π∞(L)·mult(L) (S1/S3 1.2071, S2 1.2288).

Route cost: `cost(path) = Σ_{consecutive (u,v)} w(u,v)` [s]; 0 for a single-node path.

### 6.6 A* heuristic [F], OQ-3

```
h(n) = ‖(x_n, y_n) − (x_goal, y_goal)‖₂ [m] / v_max [m/s]      → seconds
```
v_max = 30 m/s in ASSUMPTIONS.md; by OQ-3 default computed as max road speed of the loaded graph (= 30 in all scenarios).
Admissible and consistent because for every usable road (u,v): `euclid(u,v) ≤ distance(u,v)` (checked, I010), `speed ≤ v_max`, `E[mult] ≥ 1`, `f_traffic ≥ 1` ⇒ `w(u,v) ≥ euclid(u,v)/v_max`; with the triangle inequality `h(u) ≤ w(u,v) + h(v)` (consistency) and h(goal)=0, consistency ⇒ admissibility.
A*: `f(n) = g(n) + h(n)`, g in s.

### 6.7 Schedule and lexicographic cost [D 1], [D 2], [D 9], [D 11]

For responder r with snapshot `(position p_0, free_at F)` and assigned incidents sorted by `order_key`: j_1..j_m:
```
t_0 = max(now, F),  pos = p_0
for k = 1..m:
    dep_k  = max(t_{k-1}, j_k.timestamp)                      (= t_{k-1}: pending incidents are known)
    arr_k  = dep_k + travel(pos, j_k.location)                 s; ∞ ⇒ infeasible
    fin_k  = arr_k + j_k.time_required                         s
    on-site: t_k = fin_k, pos = j_k.location
    return : t_k = fin_k + travel(j_k.location, r.start_location), pos = r.start_location   (OQ-7 if ∞)
```
Missed: `missed(j) ⇔ arr(j) > j.deadline + EPS` [A §3.2: deadline = latest arrival].
Cost (compared lexicographically, smaller is better):
```
cost = ( #missed Critical,
         #missed High,
         #missed Medium + #missed Low,
         Σ_j (arr(j) − j.timestamp) [s] )
```

### 6.8 Statistics [A §5.2], [D 9], [D 10]

From the validator timeline (one entry per handled incident, arrival = `time + cost(path)` with §6.5 weights):

| Statistic | Formula | Unit |
|---|---|---|
| incidents handled H | number of incidents with an assignment in plan.json (late ones included [D 4]) | count |
| unhandled U | N − H, N = rows in incidents.csv | count |
| responders used | number of distinct `responder_id` in plan.json | count |
| response time of i | `arrival_i − timestamp_i` [D 9] | s |
| average response time | `Σ_{i handled} response_i / H`; "n/a" if H = 0 | s |
| deadline met for i | handled and `arrival_i ≤ deadline_i + EPS` | bool |
| % deadlines met | `100 · #met / N` (unhandled count as missed) [D 10] | % |
| % Critical met | `100 · #met Critical / #Critical`; "n/a" if no Critical | % |
| late | handled and not met | count |

---

## 7. Validator checks

The validator works on `raw_plan` (parsed JSON), the scenario, the network (same τ / multipliers / after-job mode as the run) and the config. It reconstructs each responder's timeline independently (§6.7 rules, with `dijkstra_all` for return trips). Entries of one responder are processed in order of `time` (ties: plan order).

Timeline reconstruction per responder r: `pos = start_location`, `free = time_until_available if Busy else 0` [D 2]. For each of its entries: departure = `time`, arrival = `time + net.path_cost(path)`, finish = arrival + time_required; on-site: `pos = incident.location, free = finish`; return: `pos = start_location, free = finish + dijkstra(incident.location → start_location)` (if unreachable: `pos = incident.location, free = finish`, OQ-7).

### 7.1 Errors (plan is invalid)

| Code | Check |
|---|---|
| E101 | plan.json is not valid JSON or its top level is not a list |
| E102 | an entry is not a JSON object |
| E103 | an entry lacks one of `responder_id`, `incident_id`, `path`, `time` |
| E104 | wrong type: ids not strings; `path` not a list of strings; `time` not a number (booleans rejected) |
| E105 | `time` is NaN, ±∞ or negative |
| E106 | `path` is empty |
| E201 | unknown `responder_id` |
| E202 | unknown `incident_id` |
| E203 | a path node is not in the graph |
| E204 | an incident appears in more than one entry (one responder per incident [D add.]) |
| E301 | `path[0]` ≠ responder position at departure (start_location for the first job; after that the previous incident location (on-site) or start_location (return)) [D 2], [T 4] |
| E302 | `path[-1]` ≠ incident location |
| E303 | consecutive path nodes (u, v) are not a road of the graph (direction matters) |
| E304 | consecutive path nodes (u, v) use a removed road (P(Blocked) ≥ τ) [D 5] |
| E401 | responder lacks the incident's required capability [A §3.1] |
| E402 | `time < incident.timestamp`, compared exactly (no EPS, §0) (dispatch before the incident is known) [A §3.2], [C] |
| E403 | `time < time_until_available − EPS` for a responder that is Busy at t = 0 (first job) [D 1], [T 4] |
| E404 | `time < free − EPS` where `free` is the end of the responder's previous job (+ return trip in return mode): overlapping jobs [D 1], [T 3], [T 9] |
| E501 | an incident is absent from the plan although some capable responder can reach its location from its final position (end of its timeline) — contradicts [D 4] (unhandled only if no capable responder can reach it) |

### 7.2 Warnings (plan is valid but noteworthy)

| Code | Check |
|---|---|
| W101 | an entry has extra keys |
| W301 | path visits a node twice (not simple) |
| W302 | path cost > Dijkstra optimum from `path[0]` to `path[-1]` + 1e-6 s (A* result not optimal — cross-check of the student kernel) |
| W401 | deadline missed: arrival > deadline + EPS (allowed by [D 4], counted in statistics) |
| W402 | `time > max(incident.timestamp, free)` + EPS: responder departs later than it could (not forbidden; flags idle waiting) |
| W501 | incident unhandled and no capable responder exists (informational, [T 1]) |
| W502 | incident unhandled, capable responders exist but none can reach it (informational, [T 2]) |

### 7.3 Validation limitations (to be stated in the report)

* L1: travel times are **expected** times from the belief model; the true road states are unknown, so "arrival" and "deadline met" are estimates, not ground truth.
* L2: the validator uses the same `roadnet` edge model (and therefore the same Bayes/HMM results) as the planner; an error in the posterior or the filter is not detected by the validator. Kernel correctness is covered by the numeric unit tests (§8), not by the validator.
* L3: removed roads are judged with the same τ as the run; a road with P(Blocked) just below τ is treated as passable.
* L4: E501 checks only reachability from final positions, not whether the planner could have served the incident earlier; optimality of allocation is not validated (W302 only checks route optimality).
* L5: the validator cannot detect use of future knowledge beyond E402 (a decision taken at time t that depends on an incident with timestamp > t but departs later is invisible in plan.json). This is enforced in the simulator by an assertion and tested (T-SIM-3).

---

## 8. Tests

Tolerances: probabilities `abs=1e-4` unless more digits are given (then `1e-6`); times `abs=1e-3` s. Tests of STUDENT functions are written by the agent and are expected to fail until the student implements them; they must not be weakened. Fixtures that need a small graph are built in `tests/fixtures.py` (ENG) from in-memory dicts written to `tmp_path`.

### 8.1 Bayesian inference (`tests/test_bayes.py`)

| Id | Input | Expected |
|---|---|---|
| T-B1 | prior, any scenario | Open 0.685, Congested 0.18, Blocked 0.135 (abs 1e-12) |
| T-B2 | **S1 N1→N2**, w = Rain, reports Citizen Blocked, Police Blocked, Sensor Congested | unnormalised: Open 0.60·0.10·0.02·0.10 = 0.00012; Congested 0.30·0.20·0.08·0.80 = 0.00384; Blocked 0.10·0.70·0.90·0.07 = 0.00441; Z = 0.00837; posterior **Open 0.014337, Congested 0.458781, Blocked 0.526882** ⇒ removed at τ = 0.3 and 0.5, kept at τ = 0.7 |
| T-B3 | S1 N2→N1, Rain, Citizen/Police/Sensor all Congested | unnormalised 0.00072 / 0.12096 / 0.000112, Z = 0.121792; posterior **Open 0.005912, Congested 0.993169, Blocked 0.000920**; kept; E[mult] = 1.497042 [T 6] |
| T-B4 | S1 H1→N3 (and N3→H1), Storm, three Blocked | unnormalised 0.000006 / 0.00056 / 0.2835, Z = 0.284066; Blocked = **0.998008**; removed for all τ |
| T-B5 | S2 N1→N2, Storm, Citizen Blocked, Police Blocked, Sensor Congested | Open 0.001130, Congested 0.168675, Blocked **0.830196**; removed for all τ ∈ {0.3,0.5,0.7} |
| T-B6 | S2 H2→N8, Rain, Citizen Congested, Sensor Congested, Police Open | Open 0.488755, Congested 0.510005, Blocked 0.001240 (near-tie Open/Congested); E[mult] = 1.2553 |
| T-B7 | S2 N7→H2, Rain, Citizen Open, Police Congested, Sensor Open | Open 0.814097, Congested 0.185022, Blocked 0.000881 |
| T-B8 | any report list and all its permutations | identical posterior (order invariance) |
| T-B9 | empty report list, w = Storm | equals P(S | Storm) = 0.15 / 0.35 / 0.50 |
| T-B10 | every posterior | non-negative, sums to 1 ± 1e-9 |
| T-B11 | S1 belief set at τ = 0.5 | removed roads exactly {N1→N2, N2→N4, H1→N3, N3→H1}; S2: {N1→N2, N2→N1}; S3: {N5→N16, N16→N5} |

### 8.2 HMM filtering (`tests/test_hmm.py`)

| Id | Input | Expected |
|---|---|---|
| T-H1 | **S2 H2→N8**, observations Low, Medium, High, Medium, High, S2 parameters, `pi_is_t1` | α_1 = (0.878156, 0.115258, 0.006586); α_2 = (0.376579, 0.596366, 0.027054); α_3 = (0.041359, 0.421349, 0.537292); α_4 = (0.049707, 0.739731, 0.210563); **α_5 = (0.010113, 0.282220, 0.707666)** (Low, Medium, High); f_traffic = **1.410277** |
| T-H1b | same, `pi_is_t0` | α_5 = (0.010050, 0.281349, 0.708602); f_traffic = 1.410571 |
| T-H2 | S1 N2→N1 (High, Low, Medium, High, High, Low, Medium, High, Low, Low) | α_10 = (0.9290, 0.0659, 0.0051); f_traffic = 1.0157 |
| T-H3 | S1 N4→H1 (… Medium, Medium, High) | α_10 = (0.0119, 0.3220, 0.6662); f_traffic = 1.3975 |
| T-H4 | S3 N16→N17 (S3 parameters = S1 parameters) | α_10 = (0.0019, 0.0748, 0.9233); f_traffic = 1.4766 |
| T-H5 | single observation `Low`, S1, `pi_is_t1` | (0.9410, 0.0554, 0.0037) |
| T-H6 | every α_t | sums to 1 ± 1e-9, length of output = T |
| T-H7 | empty sequence | `ValueError` |
| T-H8 | emission rows all uniform | α_T equals the prediction π·A^(T−1) (filter reduces to prediction) |
| T-H9 | `unobserved_traffic` | initial: S1 1.110, S2 1.145; neutral: 1.0; stationary: S1 1.2071 (π∞ = 0.3543/0.3858/0.2598), S2 1.2288 |

### 8.3 Edge weights (`tests/test_roadnet.py`)

| Id | Road (S1, τ = 0.5, default multipliers) | Expected |
|---|---|---|
| T-W1 | N2→N1 | 775/15 = 51.6667 s × 1.497042 × 1.0157 = **78.5625 s** |
| T-W2 | H1→N4 (prior road) | 340/30 = 11.3333 s × 1.104046 × 1.0088 = **12.6232 s** |
| T-W3 | N4→N2 | 41.0 × 1.497042 × 1.0267 = 63.0174 s |
| T-W4 | N3→N4 | 51.6 × 1.104046 × 1.2040 = 68.5916 s |
| T-W5 | N1→N2 | removed, weight ∞, absent from `neighbours("N1")` |
| T-W6 | every usable road of S1/S2/S3 | `w ≥ distance/speed` and `w ≥ euclid/v_max` |
| T-W7 | `traffic_multipliers` with a value < 1 | `ValueError` |
| T-W8 | --no-bayes / --no-hmm | all e_mult = 1 and no removed roads / all f_traffic = 1 |

### 8.4 A* (`tests/test_search.py`, S1, τ = 0.5, `on-site`)

| Id | Query | Expected path / cost |
|---|---|---|
| T-A1 | H1 → N2 | [H1, N2], 53.5061 s (H1→N4→N2 = 75.6406 s is worse) |
| T-A2 | N1 → N2 (direct road removed) | [N1, H1, N2], 87.4947 s |
| T-A3 | N3 → N1 (R4's start; N3→H1 removed) | [N3, N4, H1, N1], 120.7102 s |
| T-A4 | N2 → N3 | [N2, H1, N4, N3], 124.5807 s |
| T-A5 | X → X | ([X], 0.0) |
| T-A6 | target with no usable incoming road (fixture) | None, terminates |
| T-A7 | all ordered pairs in S1, S2, S3 | A* cost = Dijkstra cost (abs 1e-9) |
| T-A8 | all nodes, all goals | h(n) ≤ Dijkstra cost (admissible); for all usable (u,v): h(u) ≤ w(u,v) + h(v) (consistent) |
| T-A9 | S1 H1 → N2 | h(H1) = euclid((512,100),(683,686))/30 = 20.348 s |

### 8.5 CSP (`tests/test_csp.py`)

Fixtures use an `AllocationProblem` with an explicit travel matrix (no graph).

| Id | Setup | Expected |
|---|---|---|
| T-C1 lexicographic | now = 0; R1 at X, R2 at Y, both capable; I1 Critical at P, deadline 10, I2 High at Q, deadline 25, time_required 10 each; travel X→P 5, X→Q 1, Y→P 20, Y→Q 30, P→Q = Q→P = 50 | {I1: R1, I2: R2}, cost (0, 1, 0, 35.0). Alternatives: {I1:R2, I2:R1} = (1,0,0,21.0) must lose although its Σ is smaller; both on R1 = (0,1,0,70.0) |
| T-C2 optimality | 200 random instances, ≤ 6 incidents, ≤ 4 responders, seeded | `solve_allocation` cost == brute-force minimum over all assignments (`itertools.product`) |
| T-C3 MRV | domains sizes {I1:3, I2:1, I3:2} | first variable selected = I2; ties broken by order_key |
| T-C4 FC wipe-out | I2 reachable from R1's position but not from I1's location; I1's only value R1, I2's only value R1 | forward_check after I1=R1 returns None |
| T-C5 B&B pruning | instance of T-C2 size 6 | nodes_expanded with incumbent < nodes_expanded without; same cost |
| T-C6 empty domain | incident with no capable responder | omitted from assignment, no exception |
| T-C7 node limit | node_limit = 1 | returns a feasible assignment (incumbent), `optimal = False` |
| T-C8 monotone cost | random partial assignments | adding one variable never decreases `schedule_cost` lexicographically |
| T-C9 determinism | same problem twice | identical result |

### 8.6 Simulation and integration (`tests/test_simulate.py`, `tests/test_integration.py`)

| Id | Setup | Expected |
|---|---|---|
| T-SIM-1 | S1, S2, S3 × planner {csp, greedy} × after_job {on-site, return} × τ {0.3, 0.5, 0.7} | run completes; validator reports 0 errors; both output files exist and statistics.txt starts with `System statistics:` |
| T-SIM-2 | S1 | every incident is handled (all capabilities exist and are reachable at τ = 0.5); 7 entries; no incident handled twice |
| T-SIM-3 | spy planner on S3 | every `AllocationProblem.incidents[k].timestamp ≤ now` [C] |
| T-SIM-4 | S1 twice | byte-identical plan.json and statistics.txt |
| T-SIM-5 | return mode fixture: R at A, incident at B (travel 10, time_required 5), second incident at A known at t = 0 | second job departs at 10 + 5 + travel(B→A), path starts at A |
| T-SIM-6 | zero travel + zero time_required fixture | two incidents at the responder's node both handled at t = timestamp; loop terminates |
| T-SIM-7 | S1 × unobserved_traffic {initial, neutral, stationary} | byte-identical plan.json (all S1 roads observed); in S2 and S3 at least one RoadBelief.f_traffic differs between initial and neutral |

### 8.7 Trap cases from ASSUMPTIONS.md (`tests/test_traps.py`)

| Trap | Fixture | Expected behaviour |
|---|---|---|
| T1 | S1 with an extra incident requiring `Pumping operations` (no S1 responder has it) | incident unhandled, reason "no capable responder"; W501; other incidents unaffected; exit code 0 |
| T2 | fixture: incident at node Z whose every incoming road has reports Rain/Citizen Blocked/Police Blocked/Sensor Congested (P(B) = 0.527 ≥ τ) | unhandled, reason "unreachable"; W502; simulation terminates (no infinite loop); no E501 |
| T3 | fixture: one capable responder R at A; I1 and I2 Critical, same deadline, timestamp 0, at B and C | both handled by R; I1 at t = 0, I2 at t = finish of I1 (I1 first by natural id); no E404; I2 counted missed iff its arrival > deadline |
| T4 | S1 R4 (Busy 10 s at N3) | if R4 appears in the plan: `time ≥ 10` and `path[0] == "N3"`; mutation test: setting its time to 5 ⇒ E403 |
| T5 | fixture: incident whose deadline is below the all-Open shortest travel time from every capable responder (no scenario incident has this property — checked on S1-S3) | assigned anyway, counted handled and late; W401; included in average response time; counted missed in % met |
| T6 | S1 | N1→N2 P(Blocked) = 0.526882 → removed (no plan path contains N1→N2); N2→N1 P(Congested) = 0.993169 → kept, E[mult] = 1.497042 |
| T7 | S1/S2 files as given (contain blank lines) and a fixture with trailing blank lines and a whitespace-only line | parsed without error; row counts: S1 reports 18, S1 observations 140, S2 reports 42, S2 observations 15 |
| T8 | fixture: timestamp 12.5, deadline 70.25, time_required 7.75, Busy 3.5 | plan `time` is 12.5 (float, not 12); statistics use unrounded values; arrival compared to 70.25 |
| T9 | fixture: R1 dispatched at t = 0 to a far incident (busy until 100); I2 appears at t = 5. Variant a: R2 capable and free; variant b: no R2 | a: I2 assigned to R2 at t = 5. b: I2 assigned to R1 with `time ≥ 100`; R1 never has an entry with `time` in (0, 100) |
| T10 | fixture: responder R1 at node X, all outgoing roads of X removed by reports; incidents elsewhere; variant with R2 capable elsewhere and variant without | R1 never dispatched to another node; incidents go to R2 or become unhandled ("unreachable"); no crash (OQ-5 for an incident located at X itself) |

### 8.8 Validator (`tests/test_validate.py`)

One mutation test per code: start from the valid S1 plan (or a hand-written valid fixture plan), apply one mutation, assert that the code is reported (and no unrelated error codes):

E101 (write `{}`), E102 (entry `"x"`), E103 (drop `path`), E104 (`time: "0"`, `time: true`), E105 (`time: -1`, `NaN`), E106 (`path: []`), E201 (`R99`), E202 (`I99`), E203 (node `N99`), E204 (duplicate entry), E301 (path starts elsewhere), E302 (path ends elsewhere), E303 (skip a node), E304 (route over N1→N2), E401 (swap to a responder without capability), E402 (time before timestamp), E403 (R4 at time 5), E404 (second job of one responder starting before the first finishes), E501 (delete an entry of a reachable incident), W101, W301, W302 (replace a path by a longer valid one), W401, W402 (depart later than possible), W501, W502. Plus: the valid plan yields zero errors.

### 8.9 Statistics (`tests/test_stats.py`)

| Id | Setup | Expected |
|---|---|---|
| T-ST1 | hand timeline: N = 4; handled 3 with responses 10, 20, 30 s, one late; 1 unhandled | handled 3; avg 20.0 s; % met = 100·2/4 = 50.0 %; responders used = distinct ids |
| T-ST2 | no incident handled | avg "n/a"; % met 0.0 % |
| T-ST3 | no Critical incidents | Critical % "n/a" |
| T-ST4 | arrival exactly = deadline | met |
| T-ST5 | output text | first 6 lines match the regex of the assignment example format |

---

## 9. Traceability (ASSUMPTIONS.md → spec)

| Decision / trap | Where |
|---|---|
| D1 departure time | §2.1, §5.11, E402–E404 |
| D2 after-job modes | §5.1, §5.11, §6.7, §7 reconstruction, T-SIM-5 |
| D3 rolling horizon | §5.11 |
| D4 assign late / unhandled | §5.9 (soft deadlines), §5.11, E501, W401, T5 |
| D5 τ = 0.5, sensitivity | §6.3, §5.16, T-B2, T-B11 |
| D6 prior via P(W) | §6.2, T-B1 |
| D7 traffic multipliers | §5.1, §6.5 |
| D8 static filtering | §6.4, T-H1 |
| D9 response time | §6.8 |
| D10 % deadlines met | §6.8 |
| D11 lexicographic objective | §6.7, T-C1 |
| Additional (one responder per incident, static roads, local weather, directed reports, float seconds) | §0, E204, §6.1, T8 |
| Traps 1–10 | §8.7 |

---

## 10. Known limitations (input for the report)

* Expected-value edge weights ignore variance; a route with a small chance of a long delay is treated like a certain medium delay.
* Removing roads by a hard threshold discards the residual P(Blocked) < τ of kept roads (e.g. 0.49 is treated as passable with certainty).
* Possible double counting of congestion: road status Congested ×1.5 and traffic level High ×1.5 are multiplied [D 7].
* Static filtering: the filtered state after the last historic observation is used for the entire simulation [D 8]; no prediction forward in time.
* Rolling horizon is myopic: it does not anticipate future incidents [A §3.4].
* Fixed service order per responder inside the CSP (OQ-4) may miss better orders.
* Exponential CSP worst case; guarded by `csp_node_limit` (result flagged as not proven optimal).

---

## 11. Open questions

All questions resolved by the student on 2026-11-08; answers are binding for the implementation.

* **OQ-1 HMM first step.** ASSUMPTIONS.md gives no convention for whether `initial` is P(X_1) or P(X_0). Default `pi_is_t1` (α_1 = π·B(o_1)). S2 H2→N8 final state: t1-convention (0.010113, 0.282220, 0.707666) vs t0-convention (0.010050, 0.281349, 0.708602).
  - Accepted: default.
* **OQ-2 Traffic factor for roads without observations.** [D 8] only covers observed roads. S2 has observations on 3 of 28 usable roads, S3 on 10 of 58 — so this choice affects most edges. Options: `initial` (Σπ·mult; analogue of D6; default), `neutral` (1.0), `stationary` (π∞; ASSUMPTIONS D8 itself calls it "worse"). S1 is unaffected (all roads observed).
  - Accepted default `initial`. `neutral` and `stationary` are evaluated in the sensitivity analysis (§5.16, T-SIM-7).
* **OQ-3 v_max = 30 m/s hard-coded in [F] vs CLAUDE.md "no hard-coded scenario values".** Default: v_max = maximum road speed of the loaded graph (30 in every scenario, so all numbers are unchanged).
  - Accepted: default.
* **OQ-4 CSP formulation inside the rolling horizon.** ASSUMPTIONS.md fixes the objective and the techniques but not: (a) whether domains include busy responders (default: yes, departure at free_at, only free responders' first jobs are committed); (b) the service order of several incidents planned on one responder (default: fixed by order_key — this matches the tie-break of [T 3]; alternative: search over orders); (c) whether an incident may be deferred (no value / ⊥) — default: no; every incident with a non-empty domain gets a responder (with ⊥ and a "pessimistic" cost, an already-lost incident could be deferred forever = starvation); (d) consequence: hard constraints are mostly unary, so forward checking prunes only chained-reachability violations and values whose bound ≥ incumbent (cost-based FC). An alternative with an AllDifferent constraint (one new incident per responder per event) makes FC classical but requires (c) to be answered.
  - Accepted: (a) default; (b) default; (c) default. (d) cost-based forward checking as described; the AllDifferent alternative is not used.
* **OQ-5 Responder already at the incident location.** Occurs in data: S2 I3 at N2 and R10 (Security) starts at N2. Assignment's path example always has ≥ 2 nodes. Default: path `[N2]`, travel 0 s, accepted by the validator (E302/E301 hold trivially). Related: [T 10] says a responder on a node without usable outgoing roads "cannot be dispatched" — default interpretation: cannot be dispatched to another node, but may serve an incident at its own node.
  - Accepted: default.
* **OQ-6 When an incident is declared "unhandled".** [D 4] "no capable responder can reach it at all" — reachability depends on responder positions, which change over time (directed graph). Default: the incident stays pending, is re-checked at every event, and is declared unhandled at the end of the simulation; E501 checks against final positions.
  - Accepted: default.
* **OQ-7 Return mode without a route back.** [D 2] does not say what happens if no usable route from the incident location to `start_location` exists. Default: responder stays at the incident location and is free at finish; warning in the event log; validator mirrors the rule.
  - Accepted: default.
* **OQ-8 Greedy baseline.** Not defined in the sources. Default (§5.10): priority/deadline order, earliest-arrival free responder, no reservations. Used only for comparison and as CSP incumbent.
  - Accepted: default. Two functions as in §5.10: `greedy_planner` (free-now
    responders, no reservations) is the comparison baseline;
    `greedy_assignment` (includes busy responders and their queues) is the
    CSP incumbent only.
* **OQ-9 Deadline misses in the validator.** Default: warnings (W401), not errors, because [D 4] allows late assignment while [A §5.1] requires a "valid" plan — confirm that "valid" does not include "all deadlines met".
  - Accepted: default. Reason: some deadlines cannot be met by any responder
    even on all-Open roads (e.g. S2 I4: best arrival 34.3 s with no slack for
    any Congested road), so hard deadlines would make the plan invalid or force
    leaving incidents unserved. Validity = feasibility (capability, roads,
    timing, no overlaps); deadlines are part of the objective [D 11] and are
    reported in statistics.
