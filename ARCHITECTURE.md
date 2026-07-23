# A Decentralized Edge-AI Network for Adaptive Traffic Signal Control

**System architecture / design document**

Every intersection sees its own traffic, decides its own timing, and tells its neighbors
what is heading their way. No video leaves the pole, no control center is required, and
every failure path ends at an ordinary traffic light.

| | |
|---|---|
| **Compute** | Raspberry Pi 5 + Hailo-8L NPU |
| **Sensing** | IMX708 camera, 1280×720 @ 30 fps |
| **Transport** | MQTT, ~100 bytes/sec/node |
| **Status** | Phase 1 built, unvalidated · Phases 2–3 designed |

---

## 1. The problem

Most traffic lights have no idea what traffic is doing.

The majority of signals run a **fixed-time plan** — a fixed cycle written by an engineer
from a survey, sometimes decades ago, and rarely revisited. The light holds green for an
empty road because it is 4:15 PM on a Tuesday and the plan says so.

Where signals do adapt, they usually sense traffic with **inductive loops**: wire coils cut
into the road surface. Loops work, but they are costly to install, require closing the road,
fail invisibly, and detect only presence directly above them — no direction, no queue
length, no distinction between a bicycle and a truck, and typically no pedestrians at all.

A camera and a neural accelerator on the pole see all of it, cost a fraction of trenching a
road, and can be repositioned with a screwdriver.

---

## 2. Prior art

This is a real field and we are not first. Stating the precedent up front positions the
design inside an established lineage rather than presenting it as a novel invention, and it
makes clear which of the two existing philosophies we are choosing.

| System | Approach | Limitation we address |
|---|---|---|
| **SCOOT / SCATS**<br>1980s, widely deployed | Centralized adaptive control fed by in-road inductive loops | Single control center, expensive sensing, costly to extend |
| **Surtrac**<br>Carnegie Mellon, Pittsburgh | Decentralized — each intersection schedules itself and passes intentions downstream | Reported ~25% lower travel time; still relies on conventional detection |

Our design sits in the **Surtrac lineage** — decentralized scheduling with downstream intent
sharing — but replaces buried loops with vision at the edge. That is the whole contribution,
and it is a narrow enough claim to defend.

---

## 3. Roadmap: three phases, each independently useful

The numbering is a genuine dependency order — each phase requires the one before it. It is
also deliberate de-risking: the project delivers something real even if it stops after
phase 1.

### Phase 1 — Sense `[BUILT · UNVALIDATED]`

A single node counts and tracks vehicles, cyclists and pedestrians; measures queue length,
arrival rate and speed. Output is data, not decisions.

All of it runs: detection and tracking on the hardware, with stable IDs, speed, direction
of travel and unique counts that do not double-count a briefly occluded object; lane zones
(4.3) assigning each vehicle to a movement by its ground-contact point; and per-lane queue
length, PCU-weighted clearance time, arrival rate and observed turning split (6.3).

Two honest qualifications. Distances and speeds are still in **pixels** — real units need
the homography in 4.3, and the "stopped" threshold that separates a queue from moving
traffic has to be retuned for every mounting until then. And none of it has been validated
against real traffic: the tests drive synthetic vehicles through synthetic lanes, which
proves the arithmetic, not the perception.

### Phase 2 — Coordinate `[DESIGNED]`

Nodes exchange compact state. Node A tells node B that a platoon of twelve vehicles arrives
in roughly forty seconds. Nothing is controlled yet.

### Phase 3 — Act `[DESIGNED]`

Nodes advise their signal controllers. Green time follows real demand, and coordinated nodes
open a green wave ahead of a detected platoon.

---

## 4. Architecture

### 4.1 Inside one intersection node

The critical property of this stack is where the boundary sits. Video enters at the top and
is discarded within milliseconds; what leaves the bottom is a *recommendation* that a much
simpler, verifiable component is free to reject.

```
        ┌──────────────────────────────────────────┐
        │  CAMERA                                  │
        │  IMX708 · 1280×720 · 30 fps              │
        └────────────────────┬─────────────────────┘
                             ↓
        ┌──────────────────────────────────────────┐
        │  NPU INFERENCE                           │
        │  Hailo-8L · YOLOv8                       │
        │  frames discarded in memory              │
        └────────────────────┬─────────────────────┘
                             ↓
        ┌──────────────────────────────────────────┐
        │  TRACKER                                 │
        │  unique IDs · direction · speed          │
        │  queue length                            │
        └────────────────────┬─────────────────────┘
                             ↓
        ┌──────────────────────────────────────────┐
        │  ADVISORY LAYER                          │
        │  proposes phase timings from             │
        │  local + neighbor state                  │
        └────────────────────┬─────────────────────┘
                             ↓
                    ( recommendation only )
                             ↓
        ╔══════════════════════════════════════════╗
        ║  SAFETY LAYER                            ║
        ║  conflict matrix · min green             ║
        ║  clearance · pedestrian guarantee        ║
        ║                                          ║
        ║  May veto. Never vetoed.                 ║
        ╚════════════════════╤═════════════════════╝
                             ↓
        ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
          SIGNAL HARDWARE
        │ independent failsafe → flashing amber   │
        └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```

### 4.2 The network

Coordination is peer-to-peer and fast; supervision is centralized and slow. Keeping the
supervisor out of the control path is what allows an intersection to keep working when the
wider network does not.

```
              ┌────────────────────────────────────┐
              │  REGIONAL SUPERVISOR               │
              │  policy · monitoring · anomalies   │
              │  minutes–hours                     │
              │  never in the control path         │
              └─────────────────┬──────────────────┘
                                ↓
                  health & policy, out of band
                                ↓
   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
   │  INT-03     │←────→│  INT-04     │←────→│  INT-05     │
   │  Elm & 4th  │ 100  │  Elm & 5th  │ 100  │  Elm & 6th  │
   │             │ B/s  │             │ B/s  │             │
   └─────────────┘      └─────────────┘      └─────────────┘
```

### 4.3 Cameras, approaches and lanes

**One camera per approach, not per lane.** A 1280×720 sensor resolves three or four lanes
without difficulty; splitting them is a matter of drawing zones on the image, done once at
installation. Four cameras cover a standard crossroads.

This is where the comparison with buried loops is most stark. Loops need **one sensor per
lane**, so a junction with three-lane approaches needs twelve of them, each cut into the
road. Adding a lane means digging up the street again. For us, re-striping the junction is
an edit to a config file.

```
   Approach: EASTBOUND — camera on the opposite mast arm, looking back

   ┌────────────┬────────────┬────────────┐
   │  LANE 1    │  LANE 2    │  LANE 3    │   zones drawn once,
   │  ← LEFT    │  ↑ THROUGH │  → RIGHT   │   tagged with the movement
   └────────────┴────────────┴────────────┘   the road markings permit
         ↓            ↓            ↓
     left demand   through      right demand
                    demand
```

The controller does not think in lanes, it thinks in **movements**. Zones are how pixels
become movement demand, and for a dedicated turn lane the mapping is exact — the paint
already told us what that queue wants to do.

Vehicles are assigned to a zone by their **ground-contact point** (bottom-centre of the
box), not the box centre, which floats around the windscreen and drifts across lane
boundaries when the approach is viewed at an angle.

**Shared lanes** (through *or* left) are the genuinely hard case, and we do not claim to
read intent. Three responses, in descending order of trust: the queue is the queue
regardless of intent, and blocks the same either way; the turning split can be *learned*
from what vehicles were observed to actually do, which yields a continuously self-updating
turning-movement count where the profession normally pays for a manual survey every few
years; and indicators can in principle be read, but not reliably enough to base a decision
on.

**Mounting.** 5–10 m, on the mast arm over the opposite approach, looking back at oncoming
traffic. Height is the single largest lever on both occlusion and lane separation — a
low camera lets one lorry erase six cars.

**Occlusion** is the real limit on measuring a queue by looking at it; beyond roughly
50–80 m a queue is a solid mass. The answer is to count the boundary rather than the
contents: virtual counting lines at the stop line and upstream turn queue length into
arithmetic — what went in, minus what came out — which works when the middle of the queue
is not visible at all.

**Calibration.** A one-time homography from four points of known spacing on the road
converts image coordinates into ground positions. Until that exists, speed is in pixels
per second, which means nothing outside one specific mounting: a pixel near the horizon is
worth ten metres and a pixel at the stop line ten centimetres.

**Node count.** The Pi 5 has two CSI ports, so one node drives two cameras; a four-approach
junction is two nodes. Inference does not need 30 fps — 10 fps is ample for traffic, which
leaves an accelerator with headroom to spare.

---

## 5. Protocol: what crosses the wire

Not video. Not images. Not even individual detections. Each node publishes a compact summary
of what it currently sees and what it expects to send downstream. This **thin waist** is the
single most consequential decision in the diagram — it is what lets the system scale to a
whole city on ordinary networking.

```
topic: traffic/int-04/state

{
  "node":    "INT-04",
  "t":       1753180800,          // NTP-synced epoch seconds
  "queue":   { "n": 7, "s": 3, "e": 12, "w": 0 },
  "rate":    { "n": 4.2, "s": 2.1, "e": 9.8, "w": 0.3 },
  "platoon": { "to": "INT-05", "count": 12, "eta_s": 41 },
  "health":  "ok"
}
```

Shown as JSON for readability. On the wire this is CBOR-encoded and signed — roughly **100
bytes per node per second**, or about 250 MB per node per month. A thousand intersections
generate less traffic than a single 1080p video stream.

### Why MQTT

Publish/subscribe means a node announces its state once and any interested neighbor receives
it, rather than every node polling every other node. It was designed for constrained devices
on unreliable links, it has a last-will message that fires automatically when a node drops
off, and its broker is a few megabytes of software.

HTTP polling would work but scales as O(n²). gRPC would be faster than we need and heavier
than we want.

---

## 6. The two tradeoffs that shaped everything else

### 6.1 Where does inference run?

**Rejected — stream video to the cloud.** Simplest to build and easiest to upgrade
centrally. But signal decisions need sub-second latency, uplink for a thousand cameras is
economically absurd, an outage stops the intersection working, and continuous footage of a
public street leaving the pole is a legal and social problem.

**Chosen — inference at the edge.** Four independent justifications, any one of which would
be sufficient:

- **Latency** — decisions in milliseconds, not round trips
- **Bandwidth** — 100 bytes, not 4 Mbps
- **Privacy** — footage never leaves the device
- **Resilience** — the intersection works when the network does not

This is the argument that justifies the NPU existing. Lead with it.

### 6.2 Who decides the timings?

| Option | Strength | Why rejected |
|---|---|---|
| Fully centralized | True global optimum across the network | Single point of failure; round-trip latency on every decision; optimization grows intractable with intersection count |
| Fully decentralized | Maximally resilient, scales indefinitely | Only ever reaches a local optimum; no mechanism to notice the network as a whole has settled into bad behavior |
| **Hierarchical** ✓ | Local optimization with global oversight | — |

**Chosen — hierarchical.** A *fast local loop* (sub-second, peer-to-peer, safety-critical)
plus a *slow regional supervisor* (minutes to hours) that tunes policy, watches health and
flags anomalies — but is never in the control path.

### 6.3 What counts as demand?

The obvious rule — give green to whoever has the most vehicles — is wrong, because ten
lorries and ten hatchbacks are not the same demand. The obvious correction, measuring the
queue in metres instead, is also wrong, and more subtly: a queue's length includes the gaps
drivers leave, and gaps are not demand. Worse, for *clearance* the vehicle count matters
more than the length, because each vehicle costs roughly the same time to react and cross
the stop line regardless of its size. Pure distance would make the lorry problem worse.

The currency is neither. Green time is measured in seconds, so demand should be too:

```
clearance_time  ≈  startup_lost_time  +  (total_PCU × saturation_headway)
                ≈  2 s                +  (total_PCU × 2 s)
```

Both constants come from established practice — a saturated lane discharges around 1800
vehicles per hour of green, one every two seconds, after roughly two seconds of start-up
lost time. **PCU** (Passenger Car Units) is the profession's existing answer to the lorry
problem: bicycle 0.2, motorcycle 0.4, car 1.0, bus or lorry 2.0. These map directly onto
the classes the detector already emits, and belong in per-site config — they vary by
country and geometry, and an engineer will want to overrule them.

Which leaves three metrics doing three different jobs:

| Metric | Question it answers | Role |
|---|---|---|
| Clearance time (seconds, PCU-weighted) | How much green does this queue need? | Sets green **duration** |
| Accumulated delay (vehicle-seconds) | Who has been waiting, and how long? | Decides **who** gets green |
| Queue length (metres) | Is this about to block the junction upstream? | **Hard override** |

**Accumulated delay is the one that should drive the decision.** It has a property no
count-based rule has: it grows on its own while an approach is ignored, so a minor road
with two vehicles waiting ninety seconds outranks a main road with ten that just arrived.
Starvation stops being a rule we have to write and becomes something the metric cannot
express — and it is also the quantity the demo in section 11 is judged on.

Queue length in metres stays out of the score entirely and acts as an interrupt. A queue
that reaches back into the upstream junction blocks traffic that cannot then clear even on
green, and the jam propagates backwards faster than any optimiser can recover from.

None of this is safety logic. It all sits in the advisory layer; `min_green` and
`max_green` are enforced *below* it, which is what stops any of this reasoning, however
well-founded, from producing an unsafe or starving signal.

One consequence worth stating: once demand is weighted, *what* is being weighted becomes a
policy choice. A bus is two cars of road space and forty people. Whether the network
optimises for vehicle throughput or person throughput — and whether buses or trams get
priority on a corridor — is a decision for a transport authority, which is why it belongs
in supervisor policy (6.2) and not inside a model.

---

## 7. Safety: the neural network is an optimizer, not an authority

> **This is the single most important constraint in this document.**
>
> A traffic signal is safety-critical. A fault that shows green in two conflicting
> directions kills people. Therefore **the vision system never drives the signal hardware
> directly.**
>
> It emits recommendations to a controller that enforces hard constraints in simple,
> auditable logic. If the model proposes something unsafe, it is rejected. If the model
> crashes, the controller runs a fixed-time plan. The intelligent component is allowed to be
> wrong; the safety component is not allowed to be complicated.

### What the safety layer enforces

- **Conflict matrix** — conflicting green combinations are structurally unrepresentable, not merely disallowed
- **Minimum green** — a phase cannot be cut short below the duration a driver needs to react and clear
- **Clearance intervals** — amber and all-red timing is fixed by road geometry and speed limit, never by the model
- **Pedestrian guarantee** — a crossing phase cannot be starved, no matter how much vehicle demand the optimizer sees
- **Maximum cycle length** — no approach can be held indefinitely, even if it is genuinely the efficient choice

Three of these five constraints exist specifically to **prevent the optimizer from getting
what it wants**. An efficiency-maximizing model will starve a low-volume pedestrian crossing,
because that genuinely is the throughput optimum. Encoding the constraint in a separate layer
is what stops a correct optimization from producing an unacceptable outcome.

---

## 8. Failure modes

Every failure path terminates at **behave like an ordinary traffic light**. A system whose
worst case is the status quo is a system that is straightforward to argue for deploying.

| Failure | Response | Degrades to |
|---|---|---|
| Camera fails or view obstructed | Node self-flags unhealthy via MQTT last-will; stops publishing state | Fixed-time |
| Network partition | Node continues standalone; loses coordination, keeps local adaptation | Local adaptive |
| Neighbor goes silent | State expires after timeout; predictions on stale data discarded | Local adaptive |
| Detector outputs implausible values | Sanity bounds reject the reading — no intersection sees 900 vehicles a minute | Fixed-time |
| Node compromised or spoofing | Signed messages; neighbors weight rather than trust; supervisor flags outliers | Fixed-time |
| Advisory software crashes | Safety layer runs independently and never depended on it | Fixed-time |
| Power loss | Signal hardware's own failsafe engages, entirely outside our system | Flashing amber |

### Clock synchronization

"A platoon arrives in forty seconds" is meaningless if two nodes disagree about what time it
is. NTP is the baseline; PTP if tighter bounds are needed. A node whose clock has drifted
beyond tolerance must declare itself unhealthy rather than publish confidently wrong
predictions — **a plausible lie is worse than a declared absence.**

---

## 9. Privacy: counts persist, footage does not exist

Frames enter the detector and are discarded in memory. No images are written to disk, no
license plates are read, no faces are matched, and there is no recording to subpoena, leak,
or repurpose.

This is an engineering constraint, not a policy promise. A device that *architecturally
cannot* produce footage is a fundamentally different object from one that is configured not
to — and it is the difference between a camera a community will accept on their street and
one they will campaign to remove.

---

## 10. Extensions the network enables

**Emergency vehicle preemption.** Detect an approaching ambulance visually and by siren, then
cascade green along its predicted route. Signal preemption exists today using radio
transponders fitted to each vehicle; a vision-based version requires no equipment in the
vehicle at all, so it works for any emergency service including out-of-area responders.

**Pedestrian-aware phasing.** Detect people actually waiting rather than relying on a button
press, and extend the crossing interval when someone is still moving through it slowly. A
deliberate counterweight to a system that would otherwise optimize purely for vehicle
throughput.

**Continuous validation.** Because every node already logs demand, the network measures its
own effect. Any change to policy is a before-and-after study with the baseline already
collected — which is rarely true of infrastructure decisions.

---

## 11. Demonstration: what is real and what is simulated

One physical node exists. Stating plainly which parts are hardware and which are software
stand-ins is not a weakness in the demo — it is what makes the rest of the claims believable.

```
                  ┌────────────────────────────┐
                  │  MQTT BROKER               │
                  │  real · Mosquitto on LAN   │
                  └─────────────┬──────────────┘
                                ↓
   ╔═════════════╗      ┌ ─ ─ ─ ─ ─ ─ ┐      ┌ ─ ─ ─ ─ ─ ─ ┐
   ║  INT-04     ║        INT-03               INT-05
   ║  Pi 5+Hailo ║←────→│ simulated   │←────→│ simulated   │
   ║  REAL       ║        synthetic            synthetic
   ╚═════════════╝      └ ─ ─ ─ ─ ─ ─ ┘      └ ─ ─ ─ ─ ─ ─ ┘

   ╔═══╗ physical hardware      ┌ ─ ┐ software node, real protocol
```

The protocol, the broker, the coordination logic and the control policy are all genuine.
Only the additional cameras are synthetic — the simulated nodes publish to the same broker in
the same format, and no component can tell the difference.

### The four things to show live

1. **Real detection** — the Hailo running against traffic footage on a monitor, with counts and queue lengths updating.
2. **Coordination** — a platoon detected at one node, the message crossing the broker, the downstream node holding its green.
3. **Failure** — pull the plug on a node mid-demo and watch the network degrade to fixed-time instead of collapsing. Everyone demonstrates the happy path; almost nobody demonstrates the failure.
4. **The number** — identical simulated demand run through fixed-time signals and through the adaptive policy, compared on mean vehicle wait.

For that last one, **SUMO** (Simulation of Urban MObility) is free, open source, the standard
research tool in this field, and drivable from Python via TraCI. A real detector feeding a
real traffic simulator is a substantially stronger claim than a number we chose ourselves.

### Measuring demand from real footage

The strongest available version of that number uses real traffic: run the detector over
video of an actual four-way junction and compare what a fixed timer did with what our
policy would have done.

There is a trap in the obvious framing, and it has to be avoided explicitly. **You cannot
replay a recording and claim what would have happened.** The vehicles in that footage were
responding to the signal that was actually running; change the timing and every vehicle
reaches the stop line at a different moment, so within seconds the recording no longer
describes a world the new controller is operating in.

Video can honestly supply *demand*, not outcomes. Which gives a four-step method:

1. **Measure arrivals** — run detection and tracking over the footage to record, per
   vehicle, when it arrived at the approach, its class, and which movement it took. Real,
   platooned, with the true heavy-vehicle mix, and it doubles as a turning-movement count.
2. **Read the real signal timing** off the same video. The lights are in frame, so the
   baseline is observed rather than invented.
3. **Validate against reality** — run the model on those arrivals under the *observed*
   timing and check the simulated queues match the queues visible in the footage. This is
   the step that matters: if the model reproduces the real junction on the real timing, its
   prediction for a different controller is credible.
4. **Only then swap the controller** and report the difference.

Which supports one defensible sentence, and not a stronger one:

> We measured real demand at this junction from video, built a model that reproduces its
> actual behaviour under its actual timing, and asked what that same demand would do under
> our policy.

`VideoPipeline` is step 1's foundation; steps 1 and 4 also need the lane zones and
homography from 4.3. If the resulting improvement is modest, that is still a result — a
validated method with a small number is worth more than a large number nobody can check.

---

## 12. What this design does not claim

- **It is not deployed.** No node is mounted on a public pole and none controls a live signal. This is an architecture and a bench demonstration.
- **Nothing here is safety-certified.** Real signal controllers are built to standards with formal verification and independent audit. Our safety layer is designed in that spirit; it has not been through that process.
- **Detection accuracy is untested at night and in weather.** Rain, glare, headlights and heavy occlusion all degrade vision models, and we have not quantified by how much.
- **The efficiency figure is simulated.** Any improvement we report comes from SUMO under demand patterns we chose, not from a street.
- **Adaptive signals do not fix congestion.** They allocate an existing constraint more fairly. Induced demand is real, and better signal timing is not a substitute for the choice of what to build a street for.
