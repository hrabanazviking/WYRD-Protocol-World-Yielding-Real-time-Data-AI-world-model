# Mind Wiring — Time, Theory of Mind, Micro-Realities & MTOM

The WYRD world model now carries four wired-in cognitive dimensions. All four
are deterministic ECS components — no LLM involvement at the component level —
plus one opt-in tick system that weaves them together.

## The four modules

### 1. Time awareness — `ecs/components/temporal.py`

A world model without time is a photograph; with time it becomes a saga.

- `TemporalAnchorComponent` — validity windows (`valid_from` / `valid_until`)
  plus `observed_at` (when the world *learned* it, distinct from when it became
  true). Answers "what is true *now*" vs "what was true *then*".
- Tense is computed against world-now on the three threads of wyrd:
  **urðr** (become/past), **verðandi** (becoming/present), **skuld** (shall-be/future).
- `WorldClock` — deterministic world-time. Nothing inside the simulation reads
  wall-clock. `advance()` moves forward; rewinding raises (query anchors instead).

### 2. Theory of Mind — `ecs/components/theory_of_mind.py`

Ground truth is what the *world* knows. Theory of mind is what each *entity*
believes — including what it believes about what others believe.

- `BeliefComponent` — an entity's beliefs, each with `subject`, `claim`,
  `confidence` (0..1), and `source` (`observed` / `told` / `inferred` / `assumed`).
- `MindModelComponent` — A's model of other minds: believed beliefs, desires,
  intentions per known entity.
- `divergence()` — the false-belief task as data: compares A's model of B
  against B's actual beliefs and reports false beliefs, missing beliefs, and
  an agreement score. Divergence is not an error; it is the data that makes
  social reasoning, deception, and dramatic irony possible.

### 3. Micro-Realities — `ecs/components/micro_reality.py`

Wired from the [Micro-Reality protocol framework](https://github.com/hrabanazviking/Micro-Reality):
a self-chosen, self-sustained living myth per entity — the lens it inhabits.

- Data fields per the protocol: `physical_environment`, `daily_rituals`,
  `inner_narrative` (self-talk & metaphors), `ethics`, `myths_symbols`.
- `sovereign=True` by default — the Sacred Territory Principle: a micro-reality
  is never imposed, only inhabited. Systems read; they do not rewrite.
- `coexistence_with()` — peace through coexistence rather than consensus:
  reports shared symbols/rituals (resonance) and ethic tensions (witnessed,
  never resolved by force). Sovereign micro-realities can always coexist;
  the report says *how*, not *whether*.

### 4. Metaphysical Theory of Mind — `ecs/components/mtom.py`

The [Level 101 rule set](https://github.com/hrabanazviking/Metaphysical-Theory-of-Mind-for-AI)
as executable code:

1. **Default manifest** — every claim is `MANIFEST` (present physical here/now)
   unless explicitly invoked otherwise.
2. **Explicit invocation** — `PotentialSpace` opens only with a named invoker
   and reason. Metaphysical/future/creative content is valid *inside* its space.
3. **Zero-bleed firewall** — `assert_zero_bleed()` raises `ZeroBleedError` the
   moment a POTENTIAL-tagged claim is read as manifest ground truth. This is
   the structural fix for projecting explored possibilities onto present reality.
4. **Explicit subjectivity** — `explicit_subjectivity_check()` flags beliefs
   whose confidence exceeds their source's warrant
   (`observed` 1.0 / `told` 0.9 / `inferred` 0.7 / `assumed` 0.4).
   `assumed` can never pose as `observed`.
5. **Objective observation** — metaphysical claims are valid observations,
   tagged POTENTIAL with their space: respected, never dismissed, never
   silently promoted.

## The weaving system — `ecs/systems/mind.py`

`CognitionSystem` (opt-in via `WorldRunner`) per tick:

1. Advances the `WorldClock` by `delta_t`.
2. Reports temporal anchors that newly became *urðr* (nothing deleted — the
   past stays queryable).
3. Maintains the manifest/potential entity partition for oracle-facing code.
4. Flags speculation per Rule 4.

## Usage

```python
from wyrdforge.ecs.components.temporal import TemporalAnchorComponent, WorldClock
from wyrdforge.ecs.components.theory_of_mind import BeliefComponent, MindModelComponent
from wyrdforge.ecs.components.micro_reality import MicroRealityComponent
from wyrdforge.ecs.components.mtom import RealityStateComponent, assert_zero_bleed
from wyrdforge.ecs.systems.mind import CognitionSystem
from wyrdforge.ecs.system import WorldRunner
from wyrdforge.ecs.world import World

world = World("saga")
runner = WorldRunner(world)
runner.add_system(CognitionSystem())  # opt-in: time + mind weaving

e = world.create_entity(entity_id="unnr")
# ... attach components, tick, query divergence / coexistence / partitions
```

## Why these four together

- **Time** gives the *when* — every truth has its thread of wyrd.
- **Theory of mind** gives the *who-believes-what-about-whom* — minds differ
  from ground truth and from each other, honestly tracked.
- **Micro-reality** gives the *lens each mind inhabits* — sovereign, never imposed.
- **MTOM** gives the *firewall between manifest and potential* — so a mind's
  explorations can never corrupt the world's ground truth.

Together: a world model that knows what time it is, what its characters
believe (truly or falsely), the myth each one lives inside, and which
realities are real versus invoked.
