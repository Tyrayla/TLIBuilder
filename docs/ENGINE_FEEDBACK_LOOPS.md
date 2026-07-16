# Feedback loops in the engine: damping & quantization

*A standalone explainer. Read on its own — no code needed. It answers: why does the
"use last pass's value, blend it halfway, round it to a grid" trick give the **correct**
answer while also **guaranteeing the loop stops**?*

---

## 1. The problem: some stats depend on themselves

Most stats are one-directional: gear gives you `+X% increased damage`, we add it up, done.

But a few mechanics are **circular** — a stat depends on an output that depends on that same stat. Two live examples:

- **Tide (Tide of the Styx):** more Attack Speed → you attack more often → you consume more Life per second →
  "Life consumed recently" goes up → which *grants more Attack Speed*. Round and round.
- **Flash Flood kismet (the new one):** `+8% Attack & Cast Speed for every Spell Burst triggered recently` →
  more attack/cast speed → you charge and fire Spell Bursts faster → more "bursts recently" → *more Attack & Cast Speed*.

There is no formula you can write once and evaluate top-to-bottom, because to compute the input you already need the
output. This is a classic **fixed-point problem**: we're looking for the value `x` that is *self-consistent* — the value
which, when you feed it through the whole calculation `f`, produces itself:

```
find x such that   x = f(x)
```

That self-consistent `x` is the honest answer. It's the number the game actually settles at during sustained play: the
attack speed that produces exactly the burst rate that grants exactly that attack speed. Nothing is "assumed"; it's the
steady state where every mutual constraint holds at once.

---

## 2. How we find it: iterate until it stops moving

The whole engine compute is already a loop that runs the calculation over and over ([`compute.py`](../backend/engine/compute.py),
`for iteration in range(_MAX_ITERS)`). Each pass rebuilds everything from the current guess, then checks: *did anything
change since last pass?* If not, we've found the self-consistent point and stop.

Naively, the loop is just:

```
x = 0                     # first guess
repeat:
    x_new = f(x)          # run the whole calc using the current guess
    if x_new == x: stop   # nothing changed → self-consistent → done
    x = x_new
```

This works great for most things. For **feedback** stats it has two failure modes, and each has a fix.

---

## 3. Failure mode A: it oscillates or overshoots  →  fix: **damping**

### What goes wrong

Feedback can have "gain": a small change in `x` causes a *bigger* change in `f(x)`. When you feed the output straight
back in, you can overshoot the target and bounce around it — or, if the gain is above 1, spiral outward and never
settle.

Toy example (gain = 2, true answer is 100):

```
x = 0  → f = 90
x = 90 → f = 120     (overshot)
x = 120 → f = 84     (overshot the other way)
x = 84 → f = 126 ...  bouncing, never lands
```

### The fix: don't take the full step — take a *partial* step

Instead of replacing `x` with `f(x)`, we **blend**: move only halfway from where we are toward what the calc suggests.

```
x_new = 0.5 · f(x)  +  0.5 · x          # α = 0.5  (the "0.5·current + 0.5·prev" you saw)
```

This is called **under-relaxation** (or damping). Re-running the toy example:

```
x = 0   → f = 90   → x_new = 0.5·90  + 0.5·0   = 45
x = 45  → f = 105  → x_new = 0.5·105 + 0.5·45  = 75
x = 75  → f = 97.5 → x_new = 0.5·97.5+ 0.5·75  = 86.25
x = 86  → ...      → ... 93 ... 96.5 ... 98.3 ... → 100
```

It walks **into** the answer instead of leaping past it. Halving the step halves the effective gain, which turns a
bouncing loop into a calm, monotone approach.

### The part that worries people: *doesn't damping change the answer?*

**No — and this is the key insight.** Damping changes the *path*, never the *destination*.

Look at what the blend does once you're already sitting on the true answer `x*` (the point where `x* = f(x*)`):

```
x_new = 0.5 · f(x*) + 0.5 · x*
      = 0.5 · x*    + 0.5 · x*     ← because f(x*) = x* by definition
      = x*
```

The damped update leaves the true fixed point **exactly** where it was. So the damped loop and the undamped loop have
the *same* solution; damping only affects how you get there, not where you end up.

> **Analogy.** You're rolling a ball to the bottom of a bowl. Taking smaller, gentler nudges (damping) doesn't move the
> bottom of the bowl — it just stops you from rolling up the far side and oscillating. The resting point is identical;
> you just reach it smoothly.

So damping costs you **nothing in accuracy**. It only costs a few extra passes (you approach in steps instead of one
leap), which is why we cap iterations and why fast convergence matters.

**How the code carries "last pass's value":** the blended number is stored in a `_prev_*` variable that survives across
loop iterations (e.g. Tide's `_prev_consumed_recently_life` at [`compute.py:592`](../backend/engine/compute.py#L592)).
Each pass reads the prior blended value, injects the feedback from it, then updates the blend with this pass's fresh
number. Reading *last* pass's value (not the same-pass value) is what breaks the circular dependency into a sequence of
ordinary, one-directional calculations.

---

## 4. Failure mode B: the loop can't tell it's done  →  fix: **quantization**

### What goes wrong

The loop stops when "nothing changed" — checked as **exact equality** of a snapshot of the state. That works for
booleans and whole numbers. It fails for **continuous decimals** produced by feedback + damping, because:

- damping approaches the answer *asymptotically* — 99.1, 99.55, 99.775, 99.887 … it gets ever-closer but the digits keep
  wiggling in the far decimals essentially forever;
- floating-point math has tiny rounding noise anyway.

So two consecutive passes are `99.8874213` then `99.8874219` — "practically" converged, but **not exactly equal**, so
the loop never sees a match and runs all the way to the iteration cap. Slow, and it *looks* like it failed to converge
even though it effectively did.

### The fix: round the value that drives the stop-check onto a grid

Before the fed-back value goes into the snapshot the loop compares, we **round it to a grid** — e.g. nearest 0.5, or
nearest whole number. Tide rounds "Life consumed recently" to 0.5 steps ([`compute.py:587`](../backend/engine/compute.py#L587)).

Now once the true value is inside one grid cell and stable, the *rounded* value is byte-for-byte identical every pass:

```
raw:      99.79  99.84  99.877  99.899        (never equal)
rounded:  100    100    100     100           (equal → loop cleanly stops)
```

The wiggle in the far decimals no longer matters; the snapshot lands on the same grid point and the loop declares
convergence.

### Doesn't rounding hurt accuracy?

Negligibly, by construction:

- The grid is chosen **finer than anything that can observe it** — finer than any threshold gate ("more than N Life
  consumed"), finer than what we display. Rounding to 0.5 when the nearest meaningful threshold is 100s introduces error
  far below the noise floor.
- For **discrete mechanics it's not even an approximation** — the real quantity is genuinely a whole number. Flash
  Flood's bonus is `+8% per Spell Burst recently`; the number of bursts in the last 4 seconds is an **integer**. There's
  no "3.7 bursts." Storing the integer stack count *is* the exact value, and integers compare exactly, so convergence is
  automatic with zero rounding loss.
- Only the **stop-check snapshot** needs to be quantized. If we want, the actual injected feedback can still use the
  full-precision damped number; the grid is purely a "have we settled?" detector.

---

## 5. Worked example: the Flash Flood kismet, start to finish

Mechanic: `Halves Spell Burst Upper Limit; +8% additional Attack & Cast Speed for every Spell Burst triggered recently
(last 4 s), up to 40%.` "Recently" = a 4-second window (engine convention), so
`bursts recently = burst_rate × 4`, and `stacks = min(floor(bursts_recently), 5)` (5 stacks × 8% = the 40% cap).

Suppose that without the buff you trigger ~1.0 bursts/sec, and each stack of AS/CS nudges the rate up a bit.

```
Pass 1: _prev_burst_rate = 0            → stacks = 0        → +0% AS/CS
        compute this pass's rate = 1.00 → blend: _prev = 0.5·1.00 + 0.5·0    = 0.50
Pass 2: _prev_burst_rate = 0.50         → floor(0.50·4)=2   → +16% AS/CS
        faster now, rate = 1.20         → blend: _prev = 0.5·1.20 + 0.5·0.50 = 0.85
Pass 3: _prev_burst_rate = 0.85         → floor(0.85·4)=3   → +24% AS/CS
        rate = 1.25                     → blend: _prev = 0.5·1.25 + 0.5·0.85 = 1.05
Pass 4: _prev_burst_rate = 1.05         → floor(1.05·4)=4   → +32% AS/CS
        rate = 1.27                     → blend: _prev = 1.16
Pass 5: stacks = floor(1.16·4)=4        → +32% AS/CS  (same as pass 4)
        rate settles ~1.27              → blend ≈ 1.21 ... stacks still 4
→ the integer stack count stops changing at 4 → snapshot identical → loop stops.
```

Two things did the work:

1. **Damping** (`_prev = 0.5·new + 0.5·old`) kept the rate from leaping — important because AS/CS pushing the burst
   rate across a whole-tick breakpoint could otherwise *gain then lose* a stack every pass (a 2-cycle: +32% → rate
   crosses a tick → +40% → too fast, drops back → +32% → …). Half-steps settle the rate *between* the two states
   instead of flip-flopping.
2. **Quantization** is free here: `stacks` is already an integer. We store that integer in the state snapshot, so the
   loop converges the instant the stack count stabilizes — no decimal wiggle to chase.

> **Subtle but important:** the AS/CS bonus itself lives on the per-pass `source` object, which is rebuilt from scratch
> every pass — it is *not* part of the snapshot the loop compares. If we only injected the bonus and stored nothing in
> the snapshot, the loop could declare "converged" (because the *conditions* it does compare stopped moving) while the
> AS/CS feedback was still climbing. That's why we deliberately write the integer `stacks` **into the condition state**:
> it makes the feedback visible to the stop-check, so the loop genuinely waits for it to settle. Injecting the number is
> not enough; it has to participate in the convergence test.

---

## 6. The rules of thumb

When you add a stat that feeds back on itself:

1. **Break the cycle in time.** Read *last* pass's value (a `_prev_*` variable), inject from it, then update it. Never
   read a same-pass value that your injection is currently changing.
2. **Damp if there's any gain or breakpoint risk.** `_prev = α·new + (1-α)·old`, α = 0.5 is the house default. It
   cannot move the answer (Section 3) — it only buys convergence. Lower α = safer but slower.
3. **Put the fed-back quantity into the convergence snapshot, quantized.** Round continuous values onto a grid finer
   than any gate/display; for discrete mechanics store the honest integer. This is both what lets the loop *stop* and
   what makes it stop *at the right place*.
4. **Cap iterations** as a backstop (`_MAX_ITERS`) and log if it's ever hit — that means something isn't contracting
   and needs a smaller α or a second look.

Accuracy and termination are not in tension here: the fixed point is fixed regardless of how gently you approach it
(damping) or how you *detect* that you've arrived (quantization). Both techniques touch only the journey, never the
destination.

---

## 7. Where to look in code

- Tide feedback (the reference implementation): injection at
  [`compute.py:453`](../backend/engine/compute.py#L453); quantization of the snapshot value at
  [`compute.py:587`](../backend/engine/compute.py#L587); the damped carry at
  [`compute.py:592`](../backend/engine/compute.py#L592).
- The fixed-point loop itself: [`compute.py`](../backend/engine/compute.py) `for iteration in range(_MAX_ITERS)` — each
  pass rebuilds `source` via `aggregate(...)` (so per-pass source values reset; only `condition_state` carries the
  converging state that the snapshot compares).
- Flash Flood (this pattern's newest user) lands in the Spell Burst loose-ends work — see the approved plan.
