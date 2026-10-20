# Authoritative control-specification request

## Purpose

Official NS-SAFE-SAC experiments are blocked because the native SWMM control
trajectory is routing-step sensitive. On the fixed TRAIN diagnostic, the best
0.5-to-0.25-second comparison differs by 1.422%, above the unchanged 1%
acceptance limit, while native targets change 600 versus 914 times. The model's
zero-deadband threshold rules therefore cannot be treated as a
resolution-independent physical reference without additional evidence.

This request is for existing operational documentation. It is not a request to
tune parameters against the diagnostic storm.

## Facilities and controls in scope

- Seven Mile CSO Retention Treatment Basin and the Seven Mile/Shiawassee gate.
- Puritan-Fenkell CSO Retention Treatment Basin and pumping station.
- The seven controllable gates represented by model orifices `35281_B`, `1360`,
  `1360_B`, `35291_B`, `3530`, `3530_B`, and `35263`.
- Dewatering/sanitary pumps corresponding to the native model controls.

## Required fields

For each gate, pump, and relevant level/flow signal, please provide:

1. PLC/controller scan interval and wet-weather rule-evaluation cadence.
2. Sensor sampling interval, filtering/averaging, engineering units, and
   comparison precision.
3. Open/close thresholds, hysteresis or deadband, and rule priority/conflict
   resolution.
4. Minimum on/off or open/closed dwell time and any anti-chatter timer.
5. Command delay, actuator travel/ramp rate, and whether intermediate settings
   are allowed.
6. Initial, dry-weather, communication-loss, and power-loss states.
7. Manual/remote override behavior and whether SCADA commands latch.
8. Effective dates, controller/software revision, and any commissioning changes
   since the hydraulic model was produced.

## Acceptable evidence

- PLC function-block/ladder export or logic narrative.
- Approved O&M standard operating procedure.
- SCADA functional-design or control-description document.
- Commissioning report or as-built controls specification.
- Written confirmation from the facility/control engineer responsible for the
  operating logic.

If the material cannot be published, it can remain local. Record its SHA-256,
document identifier, revision, effective date, and the extracted control fields
in the experiment configuration without committing the source document.

## Response template

```text
Source document / revision:
Effective date:
Responsible organization or engineer:

Controller scan interval:
Rule evaluation cadence:

Asset ID:
Signal sampling/filtering:
Threshold(s):
Hysteresis/deadband:
Minimum dwell time:
Command delay/travel rate:
Initial/fail-safe state:
Priority/override behavior:
Notes:
```

## Acceptance use

The supplied specification will be implemented as a separately versioned native
controller, not silently substituted into the canonical INP. The fixed TRAIN
refinement study must then pass the original 1% CSO-volume criterion, preserve
zero flooding, and meet the existing continuity criteria before references,
scenario screening, rule calibration, or RL training resumes. A failing result
will be reported rather than fitted away.

Public background sources confirm the facility ownership and wet-weather role
but do not provide the fields above:

- GLWA Wastewater Master Plan (2020):
  https://www.glwater.org/wp-content/uploads/2020/12/Full_WWMP_Report_Final_June-2020.pdf
- GLWA Capital Improvement Plan 2026–2030, Appendix D:
  https://glwater.legistar.com/View.ashx?GUID=0362A618-FDDD-4C47-AE08-5965014AF38A&ID=13768089&M=F
- Yin et al., *Journal of Hydrology* 628 (2024), 130515:
  https://doi.org/10.1016/j.jhydrol.2023.130515
