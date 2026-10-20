# Reference-controller choice: what the same-site (7MPF / PFSMC) literature supports

Prepared 2026-10-20, 18:57–19:40 Asia/Karachi (UTC+5). Reference numbers match `docs/literature_brief_20261020.md` §(f) and `docs/literature_references_20261020.json`.

**Read levels:**
- **FT** = full text read.
- **AB** = abstract only.
- **CODE** = file or source parsed.

**Same-site corpus.** This covers everything found on this model and catchment:
- Yin et al. 2022 [60] (AB);
- Yin et al. 2023 [61] (FT, NSF PAR);
- Yin et al. 2024 [58] (FT, NSF PAR);
- Syed et al. 2025 [62] (FT, NSF PAR);
- Syed et al. 2026 [63] (AB), plus its SSRN preprint [64] (metadata only) and Mendeley dataset [65] (description and file list);
- the GitHub repo and `7MPF_25yr_P1_FF.inp` [66] (CODE);
- GLWA/EGLE documents: [40] WWMP (FT), [45] NPDES MI0022802 (FT), [67] GLWA CEO report Apr 2019 (FT), [68] CSO Public Notification Plan 2018 (FT), [69] digital-twin abstract (AB).

Anything labelled **NOT same-site** is general literature.

## 1. Bottom line

- **No same-site paper documents a fully specified, step-verified native-rule reference.** No same-site source defines a routing-step-independent reference controller. None reports a routing step, a rule step, continuity error, or a step-convergence test. None reports a sensitivity study or envelope over controller settings. Yin et al. 2023 mention a rule-based baseline, but do not give enough information to establish that it was the unchanged INP control block.
- **Prior baselines were something else.** The comparators were:
  - an unspecified "rule-based passive control" [61, pp. 716–717];
  - a genetic algorithm (GA) coupled to SWMM [58, p. 11];
  - "Un_Optim", meaning pumps inactive and gates fully open [62, p. 731].

  None was checked for step independence. The project is therefore the first on this model to need one.
- **Public sources do not fix the control parameters.** No public GLWA/EGLE document gives cadence, deadband, dwell, gate travel, pump minimum on/off times, or fail-safe states for this facility. What they do establish:
  - Operating elevations for gates and level sensors must exist in the annual NPDES Operational Plan [45, Part I.A.15.d, pp. 37–38].
  - VR-17 (the Shiawassee gate) was upgraded in 2019 for remote control from the Systems Control Center during wet weather [67, PDF p. 15].
  - SCADA logs levels every 5 min [68, §IV], which is a logging interval, not a control spec.
- **The only physical-spec numbers available** are pump ratings and basin design data [40, p. 3-11], and the INP's pump curves are consistent with them. The INP's orifice open/close times and rule bands are authored model values of unknown provenance.
- **Recommendation:**
  - Request Option 1 documents now, but do not block on them.
  - Pre-register **Option 3**: an envelope built around an Option-2 nominal controller. Regularise only the zero-deadband native rules (PUMP29, the two flow-split rules, the two first-flush primaries). Bound the envelope with the INP's own authored band widths and ramp times and the 5-min SCADA logging interval. Fix every value before any CSO is computed.
  - Keep **Option 4** for pipeline dry-runs only.

## 2. Per-option same-site evidence

| Option | What same-site studies did or imply (citation, read level) | Same-site silence | Verdict for this project |
|---|---|---|---|
| **1. Authoritative GLWA/EGLE spec** | NPDES requires an annually revised (due April 1) Collection System & CSO Treatment Facilities Operational Plan, including "hydraulic operational elevations for … regulators, diversion devices, gates, level sensors" [45, pp. 37–38, FT]. ROP sets "critical hydraulic grade elevations" and an RTB dewatering protocol via a "Real Time Control Dashboard" [40, pp. 1-13–1-14, FT]. RTBs "shall be promptly dewatered … and maintained in readiness" [45, p. 18, FT]. VR-17 "controls the flow to the Seven Mile basin" and its actuators were being upgraded for remote control from the SCC in wet weather [67, PDF p. 15, FT]. The regional model has "detailed operating rules" [69, AB]. **No FIU paper cites a GLWA operating document as the source of the INP rules.** The INP title points to IWOP-model lineage: "Hubbell Southfield imported from IWOP Model" [66, CODE]. | Plan, PLC logic and SCADA cadence not public. Silent on deadbands, dwell, travel times, pump minimum on/off, fail-safe states. | Highest validity if obtained. Cannot be assumed; time-box it. |
| **2. Pre-registered regularised controller** | Not done on this model. Native rules in [66] already contain hysteresis for PUMP27 (13–19 ft), PUMP28 (4–12 ft) and gate 35263 (closes at 35391 head > 603.0 ft; reopens only below 597.6 ft). There is **no** band for PUMP29 (OFF < 3.5 ft, ON > 3.5 ft) or for the IF/ELSE rules `7M_Flow_split`, `PF_Flow_split`, `FIRSTFLUSH_7M_FF`, `FIRSTFLUSH_PF_FF` [66, CODE]. Syed et al. used a fixed 15-min interval for the **optimiser's** actions [62, p. 729, FT]. That is not a native-control cadence, and it is excluded by the project rules. | No same-site justification for any particular cadence, deadband or dwell value. | Defensible only as a declared protocol change. Any single value is a modeller choice. |
| **3. Envelope of configurations** | **No same-site precedent.** The only sensitivity-type analyses are a GA hyper-parameter convergence test on the optimiser [58, Fig. 10, p. 12, FT] and a 60-random-sequence surrogate check [62, p. 731, FT]. Neither varies the controller. *NOT same-site:* Kroll et al. 2018 [28] ran global sensitivity analysis over rule-based-control parameter ranges; Morris screening [56][57]. | Silent. | Most defensible way to handle the missing spec. Novel on this model, so it should be stated as such. |
| **4. Exploratory only** | In effect, all same-site studies are exploratory with respect to a native reference. None verified its baseline under time-step refinement [58][61][62]. | — | Use only for pipeline debugging; not citable as thesis results. |

**How native `[CONTROLS]` were handled in each study:**
- [61] Agent sets all seven orifices via PySWMM. The paper does not say whether the INP rules stayed active.
- [58] Gate time series drawn uniformly from 0 (closed) to 1 (open), "for each individual controlled orifice gate" [58, pp. 4–5]. Rule handling is not stated.
- [62] Random sequences over 10 actuators (7 orifices + 3 pumps), 0–1 in 0.05 steps [62, p. 729]. Rule handling is not stated.

**The GitHub repo [66]** contains only two INP files: this model and the Cincinnati "D-town" model. It has one commit (2023-08-08 01:42 Asia/Karachi), no scripts and no licence. **No code shows the control step or routing step actually used.**

The separately shared Syed Python text is not claimed to come from that public repository. It is audited in `docs/legacy_syed_code_audit_20261021.md`; its 15-minute control interval is useful as an experiment setting, but the shared script is not an executable or valid reference implementation as written.

## 3. Values available from same-site sources for Option 2/3

| Quantity | Value | Source | Physical spec or modelling/logging choice? |
|---|---|---|---|
| Seven Mile RTB | 2.2 MG; ≤ 656 cfs treatment; 1-yr/1-h design storm; 30 min detention; "no flow routed" in dry weather | [40, p. 3-11] | Physical design |
| Puritan-Fenkell RTB/PS | 2.8 MG; ≤ 845 cfs; 20 min detention; 2 × 1,100 gpm sanitary pumps; 3 × 4,500 gpm dewatering pumps | [40, p. 3-11] | Physical design |
| INP pump curves (Type 3, cfs vs ft) | P/F_dry: 4.9 at 20 ft, 4.24 at 27 ft. P/F_basin_dewatering: 20.06 at 15 ft, 14.26 at 25 ft. 7Mile_pumps: 13.36 at 17 ft, 8.92 at 25 ft | [66] | Modelling. **Inference (my arithmetic):** 4.9 cfs ≈ 2 × 1,100 gpm and 20.06 cfs ≈ 2 × 4,500 gpm, consistent with [40]. No Seven Mile pump rating was found. |
| Pump startup/shutoff depths in `[PUMPS]` | 0 / 0 (native hysteresis unused); initial status OFF | [66] | Modelling |
| Rule-based pump bands | PUMP27 OFF < 13 ft or JCT-2112 > 5 ft, ON > 19 ft. PUMP28 OFF < 4 ft (or JCT-2112 > 5 ft), ON > 12 ft. PUMP29 OFF < 3.5 ft or JCT-3090 > 3 ft, ON > 3.5 ft | [66] | Authored modelling values; provenance undocumented |
| Gate 35263 (Shiawassee) band | Close: 3530 setting = 0 or 35391 head > 603.0. Open: 0.25 if node 3527 head > 605, else 1.0, only when 35391 head < 597.6 (5.4 ft band) | [66] | Authored modelling values |
| Zero-deadband orifice thresholds | 35281_A flow > 231 cfs and 35440 head > 609.27. 35291_A > 321 cfs and 35390 head > 603.28. 35442 head > 605.0 (1360). 35391 head > 601.03 (3530). Secondary orifices 1360_B/3530_B key on primary "SETTING = 0.0" | [66] | Authored modelling values |
| Orifice open/close times | 0.117 h ≈ 7.0 min (1360, 1360_B, 3530, 3530_B); 0.07 h ≈ 4.2 min (35263); 0.3 h = 18 min (35281_B, 35291_B). Units are hours per [2, p. 236] | [66] | Modelling. **Plausible but unverified** proxy for gate travel; no GLWA source confirms it. |
| Orifice geometry | 1360/1360_B: rectangular closed 7 × 14.14 ft. 3530/3530_B: 7 × 17.28 ft. 35281_B/35291_B: 6 × 13 ft. 35263: circular 4.25 ft | [66] | Modelling (geometry, likely from as-builts; unverified) |
| Initial states | Pumps OFF [66]. Orifices start at setting 1.0, the SWMM default in `link.c` [4]. Storage InitDepth 0 [66]. FIU studies "assumed that initial conditions … were empty" [58, p. 5; 62, p. 729] | as cited | Modelling; fail-safe states not stated anywhere |
| SCADA level measurement | "every five minutes as part of the SCADA System" | [68, §IV] | Logging interval, not control cadence |
| SCADA data to the digital twin | 540 points at 5-min intervals, incl. "pump and gate operating records" | [69] (AB) | Logging/transfer interval |
| VR-17 operation | Remote control from SCC during wet weather (2019 upgrade) | [67, PDF p. 15] | Operational fact; no cadence or deadband given |
| Routing / rule step in public INP | ROUTING_STEP 10 s; RULE_STEP 0; VARIABLE_STEP 0.75; MINIMUM_STEP 0.5 s | [66] | Modelling choice; not evidence of convergence |
| RL depth safety margin | 2 ft below maximum allowable depth | [61, p. 716] | Modelling (reward design) |
| Optimiser action interval / resolution | 15 min; 0.05 | [62, p. 729] | Modelling. **Not usable** as a native cadence under the project rules |

## 4. What prior same-site work did that is on the user's "will not resolve" list (citable limitations)

1. **Single, unreported routing step; no convergence evidence.**
   - None of [58][60–63] reports the routing step. The only public value is the INP's authored `ROUTING_STEP 0:00:10` with `RULE_STEP 0` [66].
   - Results were "verified" only by re-running optimised schedules in SWMM at one step [58, p. 11; 62, p. 732].
   - Syed et al.'s "mass balance" is a storage-utilisation check, not SWMM's continuity error [62, p. 732].
2. **15-min external action interval.** Syed et al. 2025 applied controls "at each 15-minute time step" [62, p. 729]. That is the optimiser's cadence, decoupled from hydraulics. Copying it into native control is excluded here.
3. **Baselines that are not a step-verified native reference.**
   - "Rule-based passive control" is never specified [61].
   - GA + SWMM is used instead of rules [58].
   - Pumps off/gates open [62].
4. **No hysteresis or dwell design, and no switching analysis.** RL gate positions change "more rapidly" in high rainfall, with no smoothness term [61, pp. 716–717]. Whether the INP rules were overridden is never stated.
5. **No envelope or sensitivity over controller settings** (Section 2, Option 3).
6. **Not observed in the same-site work:** relaxing a convergence tolerance, cherry-picking a finer step, or adding hysteresis after seeing CSO results. There is no evidence either way, because no step study was done.
7. **Minor issues.**
   - [61, p. 713] names the Shiawassee orifice "O35262"; the INP names it 35263.
   - The INP references curve `7Mile_Pumps` but defines `7Mile_pumps`. This is harmless because SWMM ID matching is case-insensitive (`hash.c`, `samestr`/`UCHAR`) [4].

## 5. Recommendation and justification

**1. Option 1 now, time-boxed.**
- Request the current Part I.A.15.d Operational Plan and the ROP critical-HGL table [45][40].
- Request the VR-17 / Seven Mile / Puritan-Fenkell SCADA/PLC logic [67].
- Ask the FIU authors [61] three things: was the INP `[CONTROLS]` block active under PySWMM, what routing step and action interval did they use, and where did the rule thresholds come from?
- Whether the plan contains cadence or deadbands is unknown. It is documented only to contain *operational elevations* [45].

**2. Pre-register Option 3 now: an envelope with an Option-2 nominal member.** Rules for building it:
- *Scope.* Keep the INP's authored thresholds and its already-banded rules (PUMP27, PUMP28, 35263) unchanged. Regularise only the zero-deadband rules (PUMP29, the two flow-split rules, the two first-flush primaries), using native SWMM features: pump Startup/Shutoff, `TIMEOPEN`/`TIMECLOSED`, `RULE_STEP`.
- *Band widths.* Take the hysteresis-width range from the model's own authored bands (5.4–8 ft for depth/head, per [66]). Scale it to each controlled variable before any CSO is computed. This is a declared modelling choice.
- *Gate ramps.* Keep the INP orifice ramp times [66].
- *Cadence.* Bound the cadence/dwell axis by values chosen a priori. The 5-min SCADA logging interval [68][69] may serve as a declared upper reference, explicitly labelled a logging interval and not a PLC spec.
- *Convergence gate.* Every member must pass the unchanged ≤ max(1 m³, 1%) check at 0.5 vs 0.25 s. Fix the exclusion rule for failing members in advance, and report any exclusions.
- *Claim.* Claim improvement only if it holds across all retained members.

**3. If Option 1 delivers before the protocol freeze,** add the GLWA values as the nominal member, or replace the nominal. Declare this as a pre-registered contingency.

**4. Option 4** is for dry-running steps 1–9 only.

**Why this works:**
- Same-site sources cannot justify any single cadence, deadband or dwell value, so Option 2 alone would rest on an arbitrary point choice.
- The envelope turns that arbitrariness into a robustness claim. It also anchors its ranges in the only same-site numbers available: the INP's authored bands and ramps, and GLWA's SCADA interval.
- *NOT same-site support:* the hybrid-systems result that the choice of regulariser changes the limit trajectory [13] means the choice must be declared, not inferred. Kroll et al. [28] give general precedent for sensitivity analysis across rule-based-control parameter ranges.

## 6. References

Full entries, with verification notes, are in `literature_brief.md` §(f) and `references.json`.
- [2] SWMM 5.2 User's Manual (FT)
- [4] USEPA SWMM source: `controls.c`, `link.c`, `hash.c` (CODE)
- [13] Johansson et al. 1999 (FT)
- [28] Kroll et al. 2018 (FT)
- [40] GLWA Wastewater Master Plan 2020 (FT)
- [45] NPDES MI0022802, 2019 (FT)
- [56][57] Morris / Saltelli (MD)
- [58] Yin et al. 2024, *J. Hydrol.* 628:130515 (FT, PAR)
- [60] Yin et al. 2022, EWRI pp. 194–205 (AB)
- [61] Yin et al. 2023, EWRI pp. 711–722 (FT, PAR)
- [62] Syed et al. 2025, EWRI pp. 725–735 (FT, PAR)
- [63] Syed et al. 2026, EWRI pp. 548–559 (AB)
- [64] SSRN 10.2139/ssrn.5393892 (MD)
- [65] Mendeley Data 10.17632/4spjvszr6z.1 (dataset description)
- [66] github.com/ZedaYin/Predicting-and-Minimizing-Combined-Sewer-Overflows (CODE)
- [67] GLWA CEO Report, 24 Apr 2019 (FT)
- [68] GLWA CSO Public Notification Plan, 2 Aug 2018 (FT)
- [69] Eichenwald et al. 2021, WEF Collection Systems (AB)
