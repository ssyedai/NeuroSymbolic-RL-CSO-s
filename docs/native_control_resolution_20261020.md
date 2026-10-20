# Native-control convergence resolution

## Decision

The remaining hydraulic blocker is now causally attributed, but it is **not
cleared**. Training, reference rebuilding, hindsight search and rule
calibration remain blocked. The unchanged native refinement criterion fails,
and no numerical candidate is adopted.

The fixed TRAIN event `USC00200230_20100719__T10` shows a non-asymptotic
native switching response as the maximum routing step is refined. By contrast,
the same hydraulic implementation passes the unchanged 1%/1 m3 criterion when
the control state is frozen. This isolates the failure to the coupled native
switching semantics rather than to fixed-policy hydraulic refinement alone.

## Same-model literature and model identity

The systematic brief in `literature_brief_20261020.md` found five same-site
published outputs, all from the FIU León/Amini group. None reports a routing
step, rule step, continuity error or timestep-sensitivity study. Yin et al.
(2023) use an unspecified rule-based comparator; Yin et al. (2024) use GA plus
SWMM; Syed et al. (2025) use all-open gates/pumps-off as the baseline and state
a 15-minute interval only for external actuator schedules. Those choices do
not establish a timestep-converged native reference.

The public FIU file `7MPF_25yr_P1_FF.inp` was downloaded and compared directly
with `7MPF_CSO_08.inp`. The files are not byte-identical: their SHA-256 hashes
are respectively
`7a790689b1dbc8ea613f4456a3032c5b5cbe8aa635627ac1eda174a7937c74be`
and
`186a0cfc57e59d1b815b224a89ddb506a72a1dc608585845c49043c1dfc4f125`.
A section-aware, whitespace-normalised diff verifies identical `[TITLE]`,
`[CONTROLS]`, `[ORIFICES]`, `[PUMPS]` and `[OUTFALLS]` content. The substantive
differences are rainfall/time series, start date, report step and display
geometry. Thus the public model directly verifies the native rule lineage, but
does not supply missing PLC cadence, deadband or dwell specifications.

## Predicate-level localization

`research.prepare_predicate_trace` adds a read-only observer to a separate
diagnostic source. It records the existing pre-iteration state after control
evaluation and actuator movement; it calls no hydraulic function and changes
no state. Instrumented runs reproduce the established final totals exactly.

Both 0.5 and 0.25 s runs command 35281_B open at 80,562 s, when storage-node
35440 first exceeds 609.27 ft. At that instant conduit 35281_A flow is nearly
identical: 470.346 and 470.402 cfs. During the unchanged 18-minute orifice ramp,
the flow trajectories diverge and oscillate around the rule threshold:

- 0.25 s: 35281_A first falls below 231 cfs at 80,792.25 s; gate setting is
  0.212963 and the close command is issued.
- 0.5 s: the first close command is not issued until 80,838.5 s; gate setting
  is 0.255556.

The 46.25 s command difference is therefore caused by the conduit-flow
predicate, not the storage-head predicate. PUMP29 chatter begins around
209,400 s, after the critical CSO/gate period, so it explains the switch-count
divergence but not this CSO-volume residual.

## Third refinement

The bounded 200-trial candidate was run at a pre-declared third refinement on
the same physical-rain TRAIN event with native rules and all four CSO outfalls:

| Maximum routing step | CSO (m3) | Flood (m3) | Routing error |
|---:|---:|---:|---:|
| 0.5 s | 3,959.124314 | 0 | -0.673596% |
| 0.25 s | 4,016.242457 | 0 | -0.710190% |
| 0.125 s | 3,776.846484 | 0 | -0.491477% |

The 0.5→0.25 s change is 57.118144 m3, or 1.422181% of the fine result. The
0.25→0.125 s change is 239.395973 m3, or 6.338515% of the fine result, and
reverses direction. The successive differences have opposite signs, so there
is no real observed convergence order and a standard monotone GCI estimate is
not valid. Lower continuity error at 0.125 s does not imply output convergence.

## Frozen-control causal check

`research.frozen_control_probe` removes only the `[CONTROLS]` body from copies
of the already generated 0.5 and 0.25 s TRAIN inputs. Rainfall, geometry,
solver settings and accounting remain unchanged. Orifices retain their initial
open targets and pumps remain off. This is deliberately not a native reference.

Read-only transition logs contain one initialization record per regulator and
pump at each resolution and no subsequent transitions. Results are:

| Maximum routing step | CSO (m3) | Flood (m3) | Routing error | Runtime |
|---:|---:|---:|---:|---:|
| 0.5 s | 74,491.262560 | 0 | 0.560558% | 757.9 s |
| 0.25 s | 74,314.432019 | 0 | 0.714776% | 1,338.3 s |

The difference is 176.830541 m3, or 0.237949% of the fine result. It passes the
unchanged `max(1 m3, 1%)` output criterion, zero-flood requirement and 1%
continuity bound. The large CSO magnitude is irrelevant to control performance;
only same-policy refinement is interpreted.

## Root cause and scientific boundary

The evidence supports this causal chain:

1. The public and canonical models have the same zero-deadband, per-routing-step
   native rules.
2. The storage threshold is crossed at the same time at both refinements.
3. Hydraulic feedback during the ramp makes the 35281_A flow trajectory cross
   the exact 231 cfs threshold on different oscillatory branches.
4. The changed close time changes the subsequent CSO trajectory.
5. Removing switching restores fixed-policy refinement below 1%.
6. Further native refinement reverses direction and worsens the discrepancy.

This does not justify inserting an arbitrary deadband, dwell time, rule cadence
or replayed schedule. Hybrid-system literature establishes that these
regularisations can select different limiting trajectories. Same-site work
provides a 15-minute external-action precedent but no physical native-control
specification.

## Required resolution paths

Only two scientifically defensible paths remain:

1. Obtain the GLWA/EGLE operational plan or PLC/SCADA logic specifying rule
   cadence, gate deadbands/travel logic, pump minimum on/off times and initial
   states. Implement that authoritative controller, version it, and rerun the
   unchanged acceptance screen.
2. If those records cannot be obtained, pre-register a physically realisable
   controller and sensitivity envelope as an explicit protocol change before
   examining validation/test performance. The original INP-native result must
   remain reported as a timestep-sensitive comparator.

Selecting the authored 10 s INP routing step, copying the 15-minute optimized
action interval, loosening the 1% threshold, or choosing the favorable 0.125 s
result would not resolve the convergence problem and is prohibited.

## Evidence locations

- Public-model copy and structured-diff inputs: ignored `runs/` evidence.
- Predicate traces and exact reproductions:
  `runs/hydraulic_resolution_20261020/predicate05.csv`,
  `predicate025.csv`, and `predicate_comparison.json`.
- Third refinement: `runs/hydraulic_resolution_20261020/refine0125/`.
- Frozen-control check: `runs/hydraulic_resolution_20261020/frozen_controls/`.
- Reproducible source: `research.prepare_predicate_trace`,
  `research.frozen_control_probe`, and `research.network_dll_probe`.
