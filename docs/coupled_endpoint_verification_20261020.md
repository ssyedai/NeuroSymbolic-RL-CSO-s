# Coupled endpoint and native-control verification

## Decision

The hydraulic gate remains failed. None of the candidates meets the unchanged
criterion `max(1 m3, 1% of the finer result)` for the 0.5-to-0.25-second native
TRAIN refinement. No candidate is adopted, no installed SWMM library is
replaced, and reference rebuilding, calibration and training remain blocked.

This investigation fixes the previously invalid control-change observer,
tests simultaneous endpoint corrections, and narrows the remaining cause. It
does not establish a controller-performance improvement.

## Repaired control observer

The earlier logger used a NaN sentinel under Release `/fp:fast` and emitted
only its header. `research.prepare_control_trace` now uses a finite `-1`
sentinel. Fresh 0.5- and 0.25-second replays exactly reproduce every saved
surface-candidate final metric.

The valid traces contain 600 target changes at 0.5 seconds and 914 at 0.25
seconds. Pump `PUMP29@35445-3565` changes target 279 versus 563 times; gate
`3530` changes 149 versus 177 times. Bypass gate `35281_B` closes at 80,841.5
seconds in the 0.5-second run and 80,797.0 seconds in the 0.25-second run, a
44.5-second difference comparable to the previously measured CSO-onset shift.
These are native-rule threshold transitions, not learned actions. The traces
show timestep-dependent switching but do not by themselves prove that control
chatter causes all remaining CSO sensitivity.

## Coupled regulator endpoint candidate

`research.prepare_coupled_endpoint` was first evaluated with a simultaneous
dense Newton block for ordinary nodes joined by weirs and orifices. It retains
the same discharge laws, geometry, controls, SLOT formulation, 0.0001-foot
head tolerance and iteration limits. The two signed endpoint derivatives are
included as off-diagonal Jacobian terms; branch-crossing or singular proposals
fall back to the established scalar update.

All six filling and six draining tabular-storage cases pass their existing
independent head, flow and zero-flood criteria. With 40 trials, the full-network
results are:

- 0.5 seconds: CSO 3999.429261 m3, flood 0, routing error -0.706642%, 8.18% nonconverging.
- 0.25 seconds: CSO 3926.373223 m3, flood 0, routing error -0.628072%, 6.26% nonconverging.
- Difference: 73.056037 m3 (1.860650% of the finer value), fail.

An undamped full Newton step improves isolated errors but worsens the network
comparison to 84.484382 m3 (2.182496%) and is rejected. A bounded 200-trial
combination reduces nonconverging steps to 2.03% and 1.66%, but still differs
by 57.118144 m3 (1.422181%); it is also rejected. This is evidence that the
iteration cap alone is not the remaining explanation.

## Rule-cadence isolation

The regulator block with 200 trials was also run with native rules evaluated
once per second at both routing resolutions. This is a changed timing
diagnostic and cannot silently replace true native control. It still fails:
3977.972240 versus 3917.430517 m3, a 60.541722 m3 (1.545453%) difference.
Therefore evaluation cadence alone is insufficient.

## All-link endpoint candidate

The final bounded candidate adds SWMM's already-computed conduit `dq/dh` to the
same endpoint block; it introduces no new constitutive law or fitted
coefficient. The isolated tabular cases remain 12/12 passing. The network
result worsens to 3998.498517 versus 3874.448611 m3, a 124.049906 m3
(3.201672%) difference, with 8.18% and 6.03% nonconverging steps. The candidate
is rejected. Extending the matrix without an independent transient-conduit
trajectory reference is not justified by these data.

## Preserved evidence and next boundary

Evidence is under `runs/hydraulic_fix_20261020`: finite-sentinel control
replays, generated sources and builds, isolated tabular results, and every
network result/summary. `research.network_dll_probe` now exposes a bounded
`--max-trials {40,100,200}` ablation; its default remains 40.

The remaining blocker is a coupled hybrid-system problem: unresolved hydraulic
iterations coexist with native zero-deadband threshold switching. Changing the
native rules, adding pump/gate hysteresis, replaying a frozen native schedule,
or redefining the rule clock would change the reference semantics and requires
an explicit protocol decision. It cannot be presented as a numerical fix.
Until then, AGENTS.md section 4.9 requires stopping rather than relaxing the
1% threshold or choosing a favorable candidate.

