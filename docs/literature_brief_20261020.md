# Literature brief: routing-step sensitivity of native SWMM controls and how to justify a reference controller

Prepared 2026-10-20 (Asia/Karachi, UTC+5) for the NS-SAFE-SAC / 7MPF_CSO_08 project.
Scope: the five research questions in the task, plus a dedicated same-study-area / same-model review (Section a2, added 2026-10-20 15:33–16:30 Asia/Karachi). Every citation [n] is in Section (f). Each entry says how it was verified and how much of it was actually read (full text, abstract only, or metadata only). Claims marked *(abstract)* or *(metadata)* rest only on that level of access. Some items are my own reasoning from the cited material rather than something a source states. Those are labelled **Inference**.

---

## (a) Bottom line

The literature and the SWMM engine both point the same way. A zero-deadband threshold rule that is evaluated at every routing step is a time-discretised switching (hybrid) system. Its switching instants are quantised to the routing step: rules are evaluated at the start of each step, and the resulting setting is held for that whole step [1][3][4]. The hybrid-systems literature shows two things about such systems. First, they can chatter, or become Zeno or sliding, as the step shrinks [11–15]. Second, how the chattering is regularised (a switching delay/dwell time versus a hysteresis band) can change the limiting trajectory itself, not just how fast the solution converges [13]. The observed 600 vs 914 switch counts, and the residual 1.42% CSO difference after the solver fixes, fit that picture. They are not, by themselves, evidence of a remaining solver bug.

No source I found shows a step-size-independence (grid-convergence) test of a native rule-based baseline in SWMM RTC/RL work. Benchmarks and RL studies do one of three things: control at every routing step (pystorms, Mullapudi et al.) [35][36]; impose a fixed controller interval decoupled from the hydraulic step (5 min in the SWMM Astlingen benchmark and its MPC; 15 min in Saliba et al.) [30][31]; or penalise "control roughness" [30][35]. Public GLWA/EGLE documents confirm that operating elevations for gates, regulators and level sensors exist, and that they are *required to be documented* in an annually revised NPDES Operational Plan [45]. No public source gives the PLC scan interval, deadband or dwell time for the Seven Mile/Shiawassee gate, Puritan-Fenkell, or the seven modelled orifices.

The defensible path is therefore:
1. Run cheap diagnostics that keep the semantics fixed (frozen-control hydraulics, a third refinement level, GCI-style reporting) [52–54].
2. Obtain the NPDES Operational Plan and SCADA/PLC documentation. This is already the pre-registered route.
3. Failing that, pre-register an explicit, physically motivated regularised reference controller and a sensitivity envelope as a declared protocol change, and do not tune it to the diagnostic storm.

All three keep the 1% threshold unchanged.

**Project follow-up (completed 2026-10-20).** The recommended diagnostics now
resolve the causal question. Native CSO is non-monotone across 0.5, 0.25 and
0.125 s (3,959.124, 4,016.242 and 3,776.846 m³), so a real observed order/GCI
cannot be computed. With the complete control block frozen, 0.5 versus 0.25 s
differs by only 0.238% and passes the unchanged criterion. Predicate tracing
shows that 35281_B opens at the same instant in both native runs, but closes
46.25 s apart when the oscillatory 35281_A flow crosses 231 cfs. These results
isolate native switching semantics as the blocker; they do not select a
regularisation. Full evidence is in `native_control_resolution_20261020.md`.

**Same-site evidence (new).** The systematic search identified five published outputs using this model, all from one FIU group (León/Amini): Yin et al. 2022, 2023 and 2024, and Syed et al. 2025 and 2026 [58][60–65]. This is a search result, not a proof that no unindexed or confidential work exists. None reports its routing step, a rule step, continuity errors, or any time-step or chatter analysis. Their baselines are an unspecified rule-based control [61], GA + SWMM [58], or an all-open/pumps-off scenario [62]. None is a step-converged native-rule reference. The one explicit cadence is a fixed 15-min actuator interval [62].

The group's public INP [66] uses the same seven orifice IDs and the same three pump IDs as this project. It runs `ROUTING_STEP` 10 s with `RULE_STEP` 0. Its native rules include a zero-width on/off threshold for PUMP29 (OFF below 3.5 ft, ON above 3.5 ft) and zero-deadband IF/ELSE rules on 35281_B, 35291_B, 1360 and 3530. They also include exact-equality `SETTING = 0.0` premises on ramped orifices. A local structured diff completed on 2026-10-20 confirms that the public and canonical files have identical `[CONTROLS]`, `[ORIFICES]`, `[PUMPS]` and `[OUTFALLS]` content after whitespace normalisation. **Inference:** these rules are therefore a concrete mechanism for the project's Δt-dependence. PUMP29 explains much of the switch-count divergence, but its switching occurs after the critical CSO period and does not explain the residual CSO-volume difference; the observed 35281_B transition shift remains the temporally relevant lead.

---

## (a2) Same study area and same physical model: how prior work handled this

**Scope and search.** "7MPF" very likely stands for Seven Mile / Puritan-Fenkell. **Inference:** the public model file of the FIU group is named `7MPF_25yr_P1_FF.inp` [66], and the group calls the system the "Puritan-Fenkell 7-mile facility" / "Puritan Fenkell/Seven-Mile Collection System (PFSMC)" [60][61, p. 713]. To find every study on this model or catchment I searched:
- OpenAlex author records for Z. Yin and Y. Saadati;
- OpenAlex `cites:` lists for Yin et al. 2022, 2023 and 2024, plus Semantic Scholar citations of Yin et al. 2024 (19 citing works);
- OpenAlex full-text search ("Puritan Fenkell", "Seven Mile basin", "Detroit combined sewer reinforcement learning", "Detroit combined sewer overflow SWMM", "Great Lakes Water Authority SWMM", "Shiawassee");
- NSF Public Access Repository (PAR) author and term searches;
- the León lab publication list;
- GitHub (user ZedaYin) and Mendeley Data;
- web searches for GLWA RTC/SWMM, Seven Mile and Shiawassee-gate material.

**Result.** The search identified studies using this model or catchment from one group only: FIU (A.S. León, Civil & Environmental Engineering, with M.H. Amini, Computing & Information Sciences). There are five outputs, plus a dataset and a public INP. None of the 19 works citing Yin et al. 2024 that were inspected is a same-site study apart from the group's own follow-ups. I found no thesis or dissertation in a public repository: Yin's PhD (FIU, Spring 2024) is confirmed on the lab page [73], but I did not locate the ETD itself. I found no arXiv preprint for any same-site paper.

### Same-model evidence: the public INP [66]

Yin et al. (2024) say they "uploaded both SWMM model files on GitHub" [58, p. 4]. The repository (created 2023-08-08 01:41 Asia/Karachi) contains `7MPF_25yr_P1_FF.inp`, which I downloaded and parsed.

**Its links match this project exactly.** The orifices are 35281_B, 1360, 1360_B, 35291_B, 3530, 3530_B and 35263 (commented ";Shiawasee Gates"). The pumps are `PUMP27@35395-3535`, `PUMP28@35390-3535` and `PUMP29@35445-3565`. The storage units are 35390/35391 (PF Basins 2/1) and 35440/35442 (7M Basins 2/1). The outfalls are 54, 54_B, 65, 65_B, JCT-2112 and JCT-3090.

**Its dates match the RL paper.** The simulation runs 06/01–06/05/2018, and its `[EVENTS]` block lists the ten calibration events from 9/22/2016 to 6/24/2017 that the RL paper describes [61, p. 715]. So this is very likely the model used in [61] and [58].

**Local model identity check (2026-10-20).** The downloaded public file is not byte-identical to `7MPF_CSO_08.inp`: SHA-256 is `7a790689b1dbc8ea613f4456a3032c5b5cbe8aa635627ac1eda174a7937c74be` versus `186a0cfc57e59d1b815b224a89ddb506a72a1dc608585845c49043c1dfc4f125`. A section-aware, whitespace-normalised diff found identical `[TITLE]`, `[CONTROLS]`, `[ORIFICES]`, `[PUMPS]` and `[OUTFALLS]` sections. The substantive differences are the rainfall input/time series, start date (06/01 versus 06/02), report step (1 versus 15 min), and map/polygon display data. The routing and native-control configuration relevant to this diagnosis is therefore verified as the same, while the storm forcing and reporting configuration are not.

**Lineage.** The `[TITLE]` reads: "DWF Flow Distribution / Updated hydraulic equivlencies / NAVD88 using Corpson / Hubbell Southfield imported from IWOP Model / Updated Model Delineation from: West-Side-Model-Delineation_07112017.shp". This points to an origin in GLWA/DWSD west-side IWOP modelling (cf. [40] on the IWOP and regional model). This is an inference from the file header only.

**OPTIONS (verbatim values).**

| Option | Value |
|---|---|
| `ROUTING_STEP` | 0:00:10 |
| `RULE_STEP` | 00:00:00 |
| `VARIABLE_STEP` | 0.75 |
| `MINIMUM_STEP` | 0.5 |
| `LENGTHENING_STEP` | 5 |
| `MAX_TRIALS` | 8 |
| `HEAD_TOLERANCE` | 0.005 |
| `SYS_FLOW_TOL` / `LAT_FLOW_TOL` | 5 |
| `INERTIAL_DAMPING` | PARTIAL |
| `NORMAL_FLOW_LIMITED` | BOTH |
| `REPORT_STEP` | 00:01:00 |
| `THREADS` | 6 |

So the public same-site model uses SWMM's default solver settings and per-routing-step rule evaluation.

**Native `[CONTROLS]` (paraphrased exactly; thresholds verbatim).**

*Orifice rules:*

| Rule | Logic | Native hysteresis? |
|---|---|---|
| `7M_Flow_split` | IF flow in conduit 35281_A > 231 AND node 35440 head > 609.27, THEN 35281_B = 1.0, ELSE 0.0 | None (IF/ELSE on a single threshold pair) |
| `PF_Flow_split` | Same pattern, on 35291_A > 321 and 35390 head > 603.28 | None |
| `FIRSTFLUSH_7M_FF` | 1360 = 0 if node 35442 head > 605.0, else 1 | None |
| `FIRSTFLUSH_PF_FF` | 3530 = 0 if node 35391 head > 601.03, else 1 | None |
| `FIRSTFLUSH_7M_FT`, `FIRSTFLUSH_PF_FT` | 1360_B / 3530_B open IF orifice 1360 / 3530 "SETTING = 0.0" | Condition is an exact equality on another orifice's setting |
| Shiawassee gate (35263) | Close if 3530 setting = 0.0 OR node 35391 head > 603.0. Open to 0.25 (if node 3527 head > 605) or to 1.0 (if < 605), only when node 35391 head < 597.6 | **Yes:** no rule acts between 597.6 and 603.0, so the gate holds its setting |

*Pump rules:*

| Pump | Logic | Native hysteresis? |
|---|---|---|
| PUMP27 | OFF if JCT-2112 depth > 5.0 or 35391 depth < 13.0; ON if 35391 depth > 19.0 | **Yes:** 13–19 ft band, via rules |
| PUMP28 | OFF below 4.0 ft (or JCT-2112 > 5.0); ON above 12.0 ft | **Yes:** 4–12 ft band |
| PUMP29 | OFF if JCT-3090 depth > 3 (PRIORITY 3); OFF if 35442 depth < 3.5; ON if 35442 depth > 3.5 (both PRIORITY 2) | **None:** the same 3.5 ft threshold for on and off |

*Native SWMM anti-chatter fields:*
- The `[PUMPS]` Startup/Shutoff depths are 0/0, so SWMM's native pump depth hysteresis [2, p. 235] is unused.
- Orifice close times (SWMM "Time to Open/Close", hours [2, p. 236]): 0.117 h (≈7.0 min) for 1360, 1360_B, 3530 and 3530_B; 0.07 h (≈4.2 min) for 35263; 0.3 h (18 min) for 35281_B and 35291_B.

**What the engine does with these rules (source read [4]).** In `controls.c`, numeric premises use exact comparisons (`case EQ: if (lhsValue == rhsValue)`). A `SETTING` premise reads the link's *current* setting, not its target. In `link.c`, an orifice with non-zero open/close time moves by Δt/orate per step and snaps to the target once `step + 0.001 >= |delta|`.

**Inference, linking these to this project's diagnostics:**
- `FIRSTFLUSH_*_FT` fires on the first routing step at which the ramped primary orifice reaches exactly 0.0. That instant is quantised to Δt, and it fires one evaluation after the primary's ramp completes.
- PUMP29 has a zero-width on/off threshold. This is the textbook relay that chatters as Δt shrinks [11][14], and it matches the PUMP29 target-change counts of 279 vs 563 in `coupled_endpoint_verification_20261020.md`. Instrumented runs localise that pump chatter to about 209,400 s, after the critical CSO/gate period, so it is evidence of hybrid sensitivity but not the cause of the residual CSO volume.
- 35281_B (`7M_Flow_split`) and 3530 (`FIRSTFLUSH_PF_FF`) are also zero-deadband IF/ELSE rules. The observed 35281_B close time shifts from 80,838.5 s at a 0.5 s maximum step to 80,792.25 s at 0.25 s, within the critical CSO period. Later 3530 chatter is not temporally aligned with that residual.

Together with the verified structured diff against `7MPF_CSO_08.inp`, this is strong evidence that native switching semantics contribute to the 1.42% residual. It does not yet prove exclusive causation; the frozen-control and third-refinement diagnostics remain necessary.

### Per-study summaries

**S1. Yin, Zahedi, León, Amini & Bian (2022), EWRI Congress, pp. 194–205 [60]** *(abstract only; ASCE paywall, no PAR copy found).*
- *Problem and method:* deep-learning time-series forecasting of CSO location and volume from rainfall, trained on SWMM output for several return periods and tested on a held-out one.
- *Model:* "The combined sewer system (CSS) of the Puritan-Fenkell 7-mi facility in Detroit, MI, is chosen as the prototype."
- *Result:* "accurately predict the location and time traces of sewer overflow volumes in a time frame of seconds."
- *Not available from the abstract:* routing step, controls, baseline, continuity or step sensitivity.

**S2. Yin, León, Sharifi & Amini (2023), EWRI Congress, pp. 711–722 [61]** *(full text: NSF PAR author manuscript).*
- *Model:* EPA SWMM "version 5.1"; 19 subcatchments, 37 junctions, 6 outfalls, 4 storage units, 38 conduits, 3 pumps, 7 orifices, 4 weirs (p. 713).
  - Controls are the "7 gated orifices (O35281B, O1360, O1360B)" for the upper half, "(O35291B, O3530, O3530B)" for the lower half, and "O35262", which links the two halves (p. 713). The INP names that orifice **35263**; 35262 is a conduit there, so "O35262" is probably a typo (inference).
  - Calibrated and validated on ten events, 9/22/2016–6/24/2017. Simulated 6/2/2018–6/5/2018 with hypothetical Detroit-IDF / NRCS MSE-3 design storms (p. 715).
- *Method:* PySWMM environment with deep RL. DDPG is the main algorithm; PPO, A2C and SAC are compared.
  - Reward per timestep: −w1·Σ(depth − (limit − 2 ft)) − w2·Σ(weir flow). The 2 ft margin is below the maximum allowable depth (p. 716).
  - CSOs are measured as flow over weirs 35391 and 35444.
- *Baseline:* "rule-based passive control" (pp. 716–717). The paper does not say whether this is the INP's `[CONTROLS]`. It also does not say whether those rules were removed or overridden while the agent acted.
- *Timing:* **not stated.** No routing step, control or action interval, or `RULE_STEP` is given.
- *Switching:* not addressed. The optimal gate positions show changes "in the entire period, and it changes more rapidly during the time periods with high rainfall intensity" (p. 717). There is no smoothness or dwell penalty in the reward (p. 716).
- *Convergence, continuity, step sensitivity:* not reported.
- *Results (p. 717):*
  - 10-yr storm: RL keeps CSOs at both weirs at zero, while rule-based control has CSOs at both.
  - Storms below the 15-yr return period: all CSOs eliminated without nodal flooding.
  - 20- and 25-yr storms: peak CSO rate "minimized by around a half", and total volume "nearly 1/10 of rule-based control results".
  - Algorithm ranking: DDPG > SAC > A2C > PPO (p. 720).

**S3. Yin, Saadati, León, Amini, Bian & Hu (2024), *J. Hydrol.* 628, 130515 [58]** *(full text: NSF PAR copy of the published article).*
- *Model:* "C-town" = PFSMC, with the same element counts as S2 (p. 4). A second system, "D-town" (MSD Greater Cincinnati), is also used. Both INPs are on GitHub [66] (p. 4).
- *Data generation:* PySWMM time-series orifice gate states drawn from "a uniform distribution, ranged from zero (fully closed) to 1 (fully open)" for "each individual controlled orifice gate" (pp. 4–5). Historical (20-year gauge record) and synthetic Detroit-IDF storms are used.
- *Method:* seven ML surrogates (XGBoost, MLP, GRU, LSTM, CNN, ResNet, Seq2Seq) predict event CSO volume at weirs W35391 and W35444 plus total flooding. Then "inversion of neural networks" back-propagates to the gate inputs. Objective weights are 10 for flooding and 1 per CSO location (p. 10).
- *Baseline:* GA + SWMM optimisation (p. 11), **not** the native rules. No rule-based baseline result is reported for C-town.
- *Timing:* **not stated** (no gate-update interval, routing step or rule step). The paper says only that the output sampling time is constant (p. 5).
- *Switching, continuity, step sensitivity:* not addressed. Verification consists of re-running the optimised gate series in SWMM (p. 11).
- *Results:*
  - C-town MAPE 1.77–3.64% across models (p. 13).
  - On the 7 Aug 2019 event, GA + SWMM and all inversion variants reach 0 m³ total CSO. GA took 12,628.61 s; inversion took 0.65–61.53 s (Table 4, p. 12).
  - D-town: GA reached 135,306 m³, inversion 131,226–140,520 m³; GA took up to 13.8 days (p. 12).

**S4. Syed, Saadati, Yin, Amini & León (2025), EWRI Congress, pp. 725–735 [62]** *(full text: NSF PAR).*
- *Model:* "the same study area previously examined by (Yin et al., 2023, 2024)", with the same element counts ("3 dewatering pumps") (p. 727).
- *Method:* bias-corrected, disaggregated 15-min NA-CORDEX projected rainfall (14 events). Random control sequences "applied at each 15-minute time step", with regulators "on a uniform scale from 0 to 1, with intervals of 0.05, for the 10 actuators (7 orifices and 3 pumps)", and 3,000 SWMM runs per event (p. 729). An MLP surrogate (NSE 0.948) is followed by neural inversion with Adam.
- *Baseline:* "Un_Optim": "pumping was inactive, all CSO gates remained fully open, and no diversion to treatment plant took place" (p. 731). This is **not** the native rules.
- *Timing:* a **fixed 15-min control interval**, decoupled from the routing step, which is not stated.
- *Switching or step sensitivity:* not addressed.
- *"Mass balance":* refers to a storage-utilisation check in SWMM (p. 732), not SWMM's continuity error.
- *Result:* total CSO fell 49.1%, from 188,206.9 to 95,787.77 m³. Peak storage utility rose from 39.8% to 94.5% (p. 732).

**S5. Syed, Saadati, Yin, Amini & León (2026), EWRI Congress, pp. 548–559 [63]** *(abstract only; PAR full text embargoed until 23 Apr 2027).* Also SSRN preprint [64] *(metadata only; download blocked)* and Mendeley dataset [65] *(description and file list read: three output CSVs, no INP)*.
- *Method:* continual learning (EWC, with replay buffer; the dataset also lists VCL/EVCL and Bayesian DNNs) for the surrogate, plus neural inversion. There is a baseline task and four climate-shift tasks.
- *Result:* EWC alone reached R² 0.90 on the new tasks, but the baseline task's R² fell from 0.96 to −28.81. With replay, the baseline R² was 0.93 and the RMSE of CSO volume fell from 4,422.0 to 216.7 m³.
- *Implementation:* the dataset's "Steps to reproduce" says it was built with "EPA SWMM and PySWMM" and validated by running optimised gate and pump actions "through the SWMM simulation".
- *Not stated:* timing and baseline-control details.

**Adjacent Detroit work (not this model):**
- Troutman et al. [38] and Ewing et al. [70] (Kerkez group, U. Michigan, with GLWA): a GDRSS subsection with in-system-storage control points. Its pilot features a 30 MG RTB [70, *(preview)*], not the 2.2/2.8 MG Seven Mile/Puritan-Fenkell RTBs [40]. Code controls every 10 s routing step [38].
- Eichenwald et al. [69] *(abstract)*: GLWA's regional SWMM model (≈4,400 subcatchments, 16,000 pipes, "detailed operating rules"), run daily as a digital twin. SCADA data, including "pump and gate operating records", arrive "at 5-minute intervals".
- CDM [71] *(abstract)*: continuous SWMM for citywide CSO notification.
- León, Yin & Sharifi [72] *(full text)*: the group's own finite-volume sewer solver, applied to "three sewer systems that closely resemble real-world conditions … intentionally modified for confidentiality". None is identifiable as PFSMC.

### Comparison table

| Study | Model/area match | Control representation | Time step / control interval | Step sensitivity or chatter | Baseline | Method | Result | Access |
|---|---|---|---|---|---|---|---|---|
| Yin+ 2022 [60] | PFSMC ("Puritan-Fenkell 7-mi facility") | Not stated in abstract | Not stated | Not stated | — | DL forecasting (several nets) | Fast, accurate CSO prediction (qualitative) | AB |
| Yin+ 2023 [61] | PFSMC, SWMM 5.1; same 7 orifices (one ID typo); same calibration events and dates as public INP [66] | RL sets all 7 orifice positions via PySWMM; native-rule handling not stated | **Not stated** (routing step, action interval, RULE_STEP) | Not addressed; gates move "more rapidly" in high rain | "Rule-based passive control" (unspecified; presumably INP rules) | DDPG (vs PPO, A2C, SAC) | 0 CSO up to <15-yr storms; 20/25-yr: peak ~½, volume ~1/10 of rule-based | FT (PAR) |
| Yin+ 2024 [58] | PFSMC = "C-town"; INP on GitHub [66] | Random 0–1 gate time series via PySWMM; inversion outputs gate series | **Not stated** | Not addressed | GA + SWMM (not native rules) | 7 ML surrogates + NN inversion | C-town MAPE 1.77–3.64%; 0 m³ CSO on 7 Aug 2019 for GA and inversion | FT (PAR) |
| Syed+ 2025 [62] | PFSMC, "same study area"; 7 orifices + 3 pumps | 10 actuators, 0–1 in 0.05 steps | **15-min control interval**; routing step not stated | Not addressed | "Un_Optim": pumps off, gates fully open | MLP surrogate + NN inversion, projected 15-min rain | CSO −49.1% (188,206.9 → 95,787.77 m³); storage 39.8% → 94.5% | FT (PAR) |
| Syed+ 2026 [63][64][65] | PFSMC (dataset text) | Gates and pumps via SWMM/PySWMM | Not stated in abstract | Not addressed | Baseline-task surrogate | EWC/replay continual learning + inversion | R² baseline 0.96 → −28.81 (EWC) → 0.93 (with replay) | AB / MD / dataset description |
| Public INP [66] | Same hydraulic/control core as this project (structured diff verified); rainfall/reporting differ | Native `[CONTROLS]`; PUMP29 and four orifice rules zero-deadband; PUMP27/28 and 35263 banded | ROUTING_STEP 10 s, VARIABLE_STEP 0.75, MIN 0.5 s, **RULE_STEP 0** | — | — | — | — | CODE |

### What this means for this project

- **No same-model study addressed step-size sensitivity, control-rule chattering, SWMM continuity error, or routing/rule-step choice.** None reports the routing step it used. The only explicit control cadence is Syed et al.'s fixed 15-min interval [62].
- **No same-model study compared against native rules evaluated at every routing step under a convergence test.** The comparators were:
  - an unspecified "rule-based passive control" [61];
  - GA + SWMM [58];
  - an all-open/pumps-off scenario [62].

  The project's ≤ max(1 m³, 1%) gate is therefore stricter than anything done on this model.
- **Mapping onto the ranked options in (d):**
  - The FIU practice of a fixed actuator interval (15 min [62]) is the same-site precedent for **option 4** (a pre-registered, decoupled control cadence). It is applied there to the optimiser, not to the native baseline. *Protocol change.*
  - Their verification by re-running optimised schedules in SWMM [58][62] is the same-site precedent for the *replayed-schedule* arm of **option 1**. *Numerical diagnostic; adopting the replayed schedule as the reference would be a protocol change.*
  - The public INP's own structure argues for **option 3/4** in a narrow, defensible form. Two of its controls already carry hysteresis (PUMP27/28, the 35263 gate). The zero-deadband rules (PUMP29, `*_Flow_split`, `FIRSTFLUSH_*`) are the candidates to regularise with native `Startup/Shutoff`, a TIMEOPEN/TIMECLOSED dwell, or a `RULE_STEP`. Their values must come from GLWA documents [45] or be fixed a priori. *Protocol change unless GLWA supplies them.*
  - Nothing in the same-site literature supports options 6 or 7 as a route to passing the gate.
- **Ask the FIU group directly (gap):**
  - Was the INP's `[CONTROLS]` block active during RL and inversion runs?
  - What routing step and action interval did they use?
  - Where did the rule thresholds come from (GLWA / DWSD model handover)?
  - Contacts: corresponding author Z. Yin (zyin005@fiu.edu, given in [61]); PI A.S. León. This is a contact suggestion only; I have not contacted anyone.

---

## (b) Findings by question

### Q1. Time-step and routing-step sensitivity of SWMM dynamic-wave routing with controls

**Solver structure.** SWMM 5 dynamic-wave routing solves the momentum and continuity equations by Picard (successive-approximation) iteration with a fixed relaxation factor θ = 0.5. It updates one conduit/node at a time rather than simultaneously. The defaults are a 0.005 ft head-convergence tolerance and 8 trials [1, pp. 46–47]. Because there is "no spatial coupling between elements as would occur in an unconditionally stable implicit solution scheme", the CFL condition "would still apply but perhaps not as strictly" [1, p. 58]. The manual suggests 10–30 s steps for typical 200–400 ft conduits [1, p. 59]. The project's coupled-Newton endpoint block is therefore a departure from SWMM's documented scheme. That is consistent with the project's own caution against presenting it as SWMM-equivalent.

**Pumps and orifices are special cases in the iteration.**
- Pumps: "No under-relaxation is applied to consecutive pump flows" within a step [1, p. 106]. For Type 3/4 curves, dQ/dH is the negative curve-segment slope; for other pump types it is zero [1, p. 106].
- Orifices: settings move toward a target ω* set "the last time that a control rule involving the orifice was activated". The move is instantaneous if the open/close time Δt_O = 0, and otherwise ramps at Δt/Δt_O per step (Eq. 6-4) [1, p. 108]. The setting is updated at the *start* of a time step, then held across that step's iterations [1, p. 113].

**Inference:** with Δt_O = 0 and zero-deadband rules, each switch is a step discontinuity in the regulator law that lands on a step boundary.

**Rule-evaluation timing, verified in documentation and source.**
- *Default behaviour.* The SWMM 5.2 User's Manual says the Control Rule Time Step "default is 0 which means that controls are evaluated at every routing time step" [2, p. 149]. The 5.2.0 update history says: "Users can now choose to set a periodic time step for control rule evaluation. If this step is 0 then rules are tested as before at every routing time step" [3].
- *When RULE_STEP was added.* The engine source dates `RULE_STEP` support to 5.1.013 (comment `//(5.1.013)` in `project.c` at tag v5.1.13) [4]. GUI and documentation support arrived with 5.2.
- *Order of operations in `routing.c` (current master)* [4]:
  1. `evaluateControlRules()` runs at the start of `routing_execute()`.
  2. It first applies the non-rule targets (pump startup/shutoff depths via `link_setTargetSetting`).
  3. It then calls `controls_evaluate()` if `RuleStep == 0` or the rule time has been reached.
  4. It applies any changed settings for the whole step.
- *Alignment of rule times.* When `RuleStep > 0`, the routing step is shortened so a step lands exactly on the next rule time [4].

**Inference:** with RULE_STEP = 0, the native controller is effectively a zero-order hold sampled at Δt. Halving Δt changes the controller's sampling rate as well as the hydraulic discretisation. The native "reference" is therefore not a fixed controller across the refinement study.

**Built-in anti-chatter mechanisms in the INP language** (all user-specified; none applied by default):
- Separate pump Startup/Shutoff depths. The shutoff depth must be lower than the startup depth, so this is a hysteresis band [2, p. 235; 4].
- Orifice "Time to Open/Close", an actuator ramp [2, p. 236; 1, p. 108].
- Rule conditions on `TIMEOPEN`/`TIMECLOSED`, the duration a link has been open or closed. These can encode minimum dwell times [2, p. 256].
- `PRIORITY` for conflict resolution [2, p. 254].
- RULE_STEP for cadence [2, p. 149; 3; 4].

**Diagnostics and accuracy guidance.**
- The manual flags system continuity errors above "5 to 10 percent" as possible instability, and says the Flow Instability Index does not measure magnitude [1, pp. 57–58]. The User's Manual uses "such as 10 percent" [2, p. 158], recommends ≤1 min reporting to see short instabilities, and recommends smaller or variable steps, ignoring inertial terms, or conduit lengthening [2, p. 159].
- These are far looser than, and different in kind from, the project's 1% CSO-volume refinement criterion. **Inference:** SWMM guidance provides no precedent for a 1% step-independence target on a controlled output, but nothing in it contradicts imposing one either.
- Pachaly et al. compared SWMM 5.1 alternatives (link-node vs artificial spatial discretisation; EXTRAN vs Preissmann slot) on the EPA QA cases. They report that results improve "with an adequate selection of temporal and spatial discretization" (assessed by continuity error and stability) [6, *(abstract)*]. The EPA QA report documents dynamic-wave verification against SWMM 4 [5, *(metadata/listing)*].

**Gap.** I found no peer-reviewed study that quantifies routing-step sensitivity of SWMM *control-rule* switching (rule chatter versus Δt) for orifices, weirs or pumps. Practitioner material exists but is not peer-reviewed and is not cited as evidence here.

### Q2. Hybrid/discontinuous-ODE numerics: chattering, Zeno/sliding behaviour, and remedies

- **Theory.**
  - Filippov's framework defines solutions for discontinuous right-hand sides, including sliding motion on a switching surface [11].
  - Utkin surveys variable-structure systems with sliding modes [12].
  - Goebel, Sanfelice and Teel give the modern hybrid-systems formalism [15].
  - Zhang et al. give conditions for Zeno executions. They note that "physical systems do not show Zeno behaviour" but "models of real systems may be Zeno due to modelling abstraction" [14, *(abstract)*].
- **Key result for this project.** Johansson, Egerstedt, Lygeros and Sastry regularise Zeno automata to extend executions past the Zeno time. They show that "different types of regularization may, however, lead to different extensions". Their worked example is a two-water-tank switching controller, where temporal regularisation (switching delay) and spatial regularisation (hysteresis) "suggest different extensions of the executions" [13, full text pp. 141, 145]. **Inference:** choosing a scan interval, dwell time or deadband is a modelling decision that can change the reference trajectory, not a numerical tolerance. This supports the project's position that such a choice is a protocol change unless it comes from documented physical specifications.
- **Remedies in the control literature.**
  - Hysteresis switching bounds the number of switches [17][18]. Hespanha and Morse show that "scale-independent hysteresis can produce switching that is slow-on-the-average" [17, *(abstract)*].
  - Average/minimum dwell time is the standard way to bound switching frequency [16][17].
- **Remedies in the numerical literature.**
  - Event (discontinuity) detection and location: find the crossing time and restart the integrator there, instead of stepping over the discontinuity [19][20][21].
  - Park and Barton's algorithm "guarantees the location of all state events in strict time order", even with multiple crossings per step [20, *(abstract)*].
  - Gear and Østerby treat stepping over discontinuities with controlled error [21, *(abstract)*].
  - Dieci and Lopez survey event-driven and Filippov/sliding treatments for ODEs with discontinuous right-hand sides [22, *(metadata)*].
  - Mosterman surveys hybrid-simulation phenomena (including chattering) and simulator support [23, *(metadata)*].
- **Inference for SWMM.** SWMM uses neither event location nor regularisation for rules. Switching is quantised to Δt (Q1). Event location would make switch *times* converge with Δt. But at a zero-deadband threshold where the flow field pushes the state back toward the threshold from both sides, the Δt→0 limit is a sliding or chattering regime. Switch counts would then grow without bound, as 279→563 pump switches suggests. Integrated volumes may converge more slowly or not at all. This is consistent with the project's finding that a fixed 1 s rule cadence still fails (1.545%). That test changed the sampling clock, but the zero-width threshold still interacts with unresolved iterations.

### Q3. RTC/CSO practice: cadence, deadbands, dwell, and how baselines are modelled in SWMM

**What benchmark and RL studies actually do** (from full text or code unless marked). Background: the Kerkez group's "smart stormwater" framing [37]; co-simulation interfaces PySWMM [9] and MatSWMM [10] are what make external, step-wise control of SWMM possible.
- **pystorms** [34][35, code]. `environment.step()` applies actions and then calls `swmm_step()` once. Control therefore happens at every SWMM routing step. The tutorial rule-based controller is a bare threshold (depth > 0.5 → setting 0.5, else 0) with no deadband. Scenario zeta's metric includes a penalty for "roughness of control". None of the code I read tests step-size independence.
- **Mullapudi et al. 2020** [36, full text]. Their co-simulation "halt[s] the hydraulic model at every time step". The RL agent produced "chattering" valve actions. The authors note "a real-world stormwater system could not be throttled in this fashion". No step-independence test.
- **Saliba et al. 2020** [31, full text]. Actions and measurements on "a 15-min basis". The baseline is a passive system (all valves 100% open). Orifice close time is 0.2 in the SWMM table. RL policies showed "rapid cycling of the orifices from 0–100%".
- **Sun et al. 2020 (Astlingen in SWMM)** [30, full text; GitHub INP]. MPC sampling time 5 min, with "roughness of control" weighted 0.01. The EFD rule baseline is written as SWMM `[CONTROLS]` with a 20% filling threshold. Sensor and control delays were "deliberately not considered". The published `Astlingen_SWMM.inp` (uploaded 2020-01-08) sets `ROUTING_STEP 0:00:30`, `RULE_STEP 00:05:00`, `VARIABLE_STEP 0.75`, `MINIMUM_STEP 0.5`. This is a direct precedent for decoupling native-rule cadence from the hydraulic step in a published SWMM RTC benchmark. The paper text does not discuss RULE_STEP. The original Astlingen benchmark is [29, *(abstract)*].
- **Troutman, Love and Kerkez 2020** [38, metadata; code]. Load-balancing control on "a simulated subsection of the Detroit combined sewer network" [39, dissertation abstract]. Their public code sets `routime_step = 10` s and computes an action at every `env.step`. Its control points include `ISD013_DOWN`, which matches the "Seven Mile Rd. (ISD013)" in-system storage device listed in the GLWA WWMP [40, p. 3-49]. **Inference:** this ties the Kerkez-group Detroit work to the same regional system, but it is not the 7MPF model. I could not verify the "15-minute control window" a search snippet attributed to this work, so that claim is dropped.
- **Kroll et al. 2018** [28, full text]. RBC designed for PLC implementation ("can be straight-forwardly programmed into simple PLC ... units"). They run Morris global sensitivity analysis on the control parameters. Parameter ranges (Table 3): FD_max 0.90–1.05 (default 1 or 0.95); time constant T 300 s (60–500 s). Existing gates "might not be configured to handle frequent control actions". This is methodological precedent for an a priori controller-parameter envelope.
- **Other studies, abstract-level only.** Bowes et al. compare RL with MPC and an RBC [32, *(abstract)*]. Tian et al. train RL via a Koopman emulator of a SWMM UDS [33, *(abstract)*]. Neither abstract reports a step-independence test of the baseline. I did not read full texts, so I cannot say whether their methods sections do.
- **Reviews and guidance**, cited for framing only (*abstract/metadata*): García et al. [24]; Lund et al. [25]; Schütze et al. 2004 [26]; Mollerup et al., who propose a "time-scale dependent framework" [27]; Vezzaro and Grum (DORA) [41]; van der Werf et al. [42]; Campisano et al. on sensors, actuators, controllers and telemetry [43]; Schütze et al. on the DWA-M180 guideline [44]; Colas et al. and Pleau et al. on Quebec global optimal RTC [46][47]. I did not extract any cadence, deadband or dwell numbers from these because I could not read their full text legally in this session.
- **Pump-cycling standard.** Ten States Standards §42.62 requires that "design fill time and minimum pump cycle time shall be considered in sizing the wet well". Fill time is "not to exceed 30 minutes" (unless the facility provides equalisation), and "the pump manufacturer's duty cycle recommendations shall be utilized in selecting the minimum cycle time" [48, p. 40-5]. **Inference:** real pumps have a manufacturer-defined minimum cycle time. A zero-dwell pump rule that switches 563 times in one event at 0.25 s is unlikely to represent physical operation. The standard does not give a number to use.

**What studies assume when PLC parameters are unknown.** Among the sources I read: either the controller runs at the simulator step (pystorms, Mullapudi, Troutman code), or a round fixed interval is chosen (5 min, 15 min) without justification from plant PLC data (Sun, Saliba). None reports a grid-independence test of the baseline. **Inference:** the project's pre-registered acceptance gate is stricter than any published precedent I found.

### Q4. Detroit/GLWA-specific public information

- **Seven Mile RTB** [40, p. 3-11]: 2.2 MG storage, treatment up to 656 cfs, designed for the 1-yr 1-h storm with 30 min detention. "During dry weather, there is no flow routed to the Seven Mile Road Basin. During wet weather, the control gate at Seven Mile and Shiawassee regulates the flow to the Seven Mile Basin."
- **Puritan-Fenkell RTB and pump station** [40, p. 3-11]: 2.8 MG storage; 845 cfs; 20 min detention; two 1,100 gpm sanitary pumps; three 4,500 gpm dewatering pumps. The Rouge district had seven double-leaf in-system storage slide gates completed in 1998, "most of these have since been removed" [40, p. 3-10].
- **Asset tables** [40, pp. 3-45, 3-49, 3-51]: "VR-17 (Shiawassee Gate) … Operational"; "Seven Mile Rd. (ISD013)"; "Puritan Outfall Gates"; outfalls 102/103 under permit MI0022802.
- **Operations framework** [40, pp. 1-13–1-14, 5-2]:
  - The Regional Operating Plan (ROP) extends GLWA's Interim Wet Weather Operating Plan (IWOP).
  - It establishes "critical hydraulic grade elevations".
  - It introduces a "Real Time Control Dashboard" and an RTB dewatering protocol.
  - It plans to use the regional SWMM model as a "digital twin" of the SCADA system.
  - Existing-condition model runs used "operating rules and condition in effect in 2018".
  - None of this gives scan intervals, deadbands or dwell times.
- **NPDES permit MI0022802** (EGLE, issued June 28, 2019) [45]:
  - It authorises discharges from the Puritan/Fenkell (102A/102) and Seven Mile (103A/103) RTBs "when the basins are full and wastewater flows exceed downstream interceptor capacity" (p. 16).
  - Part I.A.15.d requires an annually revised (due April 1) "Collection System and CSO Treatment Facilities Operational Plan". It must include "the hydraulic profile and hydraulic operational elevations for system pump stations, regulators, diversion devices, gates, level sensors, interceptors" for dry and wet weather (items 7 and 10; pp. 37–38).
  - **This is the most specific public pointer to where operating levels are documented.** The plan itself was not found publicly.
- **Other GLWA documents.**
  - The GLWA Aug 25, 2021 rain-events update [49] describes revised operating protocols for east-side facilities (Conner Creek launder/emergency gates, Fairview PS) and remote operation retrofits, not Rouge facilities.
  - Salim and McCord describe GLWA's SCADA-based Interceptor Hydraulic Viewer. It checks outfall activity "every time step (whether one minute, five minutes, or more)" [50]. This is a data or visualisation interval, **not** a PLC scan interval.
- **DWSD in-system storage and RTC history.** DWSD designed 13 inflatable-dam ISDs (54 MG) with control schemes developed using a transient analysis program [51][59, *(abstracts)*]. The Quebec "global optimal" RTC papers [46][47] are by BPR (Pleau, Colas et al.). I found **no** verifiable source that DWSD ran that global optimal RTC system, and a search synthesis said explicitly that the results did not show this. The claim is treated as unverified.
- **Same-model studies:** see Section (a2). Yin et al. 2024 [58] was read in full via its NSF PAR copy.
- **VR-17 operations history.** GLWA's April 2019 CEO report: "VR-17 controls the flow to the Seven Mile basin. The actuators on the gate are being upgraded to provide remote control functionality to Systems Control Center (SCC) during wet weather operations". It also lists "a Seven Mile and Puritan-Fenkell hydraulic study" as underway [67, PDF pp. 12, 15]. **Inference:** in practice the Shiawassee gate is operated through the control centre (possibly with operators in the loop), not necessarily by an autonomous PLC threshold rule. That makes the zero-deadband per-step rule in the model an idealisation.
- **SCADA cadence.** GLWA's 2018 CSO Public Notification Plan says treated-overflow facilities, including Seven Mile and Puritan-Fenkell, are monitored by SCADA. It says regulator "water levels are being measured continuously every five minutes as part of the SCADA System", and that the Puritan outfall has "dynamic control gates (weir equations)" [68, §IV]. The regional digital twin also ingests SCADA "pump and gate operating records" at 5-minute intervals [69]. These are measurement and logging intervals, not proven control scan rates.
- **GLWA CIP 2026–2030 Appendix D** [54b]: the Legistar URL resolves (HTTP 200) but I did not re-read it in this session.

### Q5. Methodological precedent for justifying a reference controller

- **Discretisation-error reporting.**
  - Roache's Grid Convergence Index gives uniform reporting of refinement studies from generalised Richardson extrapolation [52].
  - The ASME/JFE procedure by Celik et al. prescribes three-level refinement, observed order and GCI reporting [53].
  - Eça, Dowding and Roache explain that V&V 20-2009 treats validation as estimating model error, "not ... a pass/fail exercise" [54].
  - Oberkampf and Roy cover code and solution verification [55].
  - **Inference:** these methods assume the asymptotic range, which a zero-deadband switching system with non-converging switch counts may never reach. A third level (0.125 s) and the observed order are therefore diagnostic. Using an extrapolated value to *pass* the gate would be a protocol change.
- **Sensitivity and envelope reporting.** Pianosi et al. give a GSA workflow for environmental models [56]. Saltelli et al. is the standard primer [57]. Kroll et al. apply Morris screening to RTC parameters with a priori bounds [28].
- **Fixed control interval decoupled from the hydraulic step.** The Astlingen SWMM INP (RULE_STEP 5 min, routing 30 s) [30]; MPC at 5 min [30]; RL at 15 min [31]; PySWMM's `step_advance(seconds)`, which "does not change the routing step" [9, code].
- **Which choices change the reference.** By [13], choosing between dwell and hysteresis can change the limit trajectory. Any regularisation not taken from documented PLC logic is a modelling choice and must be declared. This matches the project's existing rule.

---

## (c) Parameter values stated in sources

Only values stated in the cited sources are listed. None is a GLWA/Detroit PLC value.

| Quantity | Value | Source | Context / caveat |
|---|---|---|---|
| Control-rule evaluation step (SWMM default) | 0 = every routing step | [2, p. 149]; [3]; [4] | Engine default; RULE_STEP added in engine 5.1.013, documented in 5.2 |
| Control-rule step in a published SWMM RTC benchmark | 5 min (`RULE_STEP 00:05:00`), routing 30 s with variable step 0.75, min 0.5 s | [30] GitHub INP | Astlingen SWMM model; not discussed in the paper text |
| MPC sampling interval | 5 min (horizon 100 min) | [30] | Astlingen; delays ignored |
| RL control interval | 15 min | [31] | Saliba et al., synthetic Norfolk-like network |
| RL control interval | every SWMM routing step | [36] | Mullapudi et al. |
| Benchmark controller interval | every SWMM routing step (`swmm_step()` per action) | [34][35] code | pystorms; tutorial RBC has zero deadband |
| Detroit-subsection control (code) | every step; routing step 10 s | [38] code | Troutman LBC repo; ISD013 control point |
| Orifice open/close time | 0.2 (SWMM field, hours by SWMM convention) | [31] Table 1 | Saliba et al. orifices R1–R3 |
| Pump hysteresis | Shutoff depth must be < Startup depth (user value) | [2, p. 235] | SWMM feature, no default number |
| SWMM head tolerance / max trials (defaults) | 0.005 ft / 8 | [1, p. 47]; [2, p. 151] | Project uses 0.0001 ft and 40–200 trials |
| SWMM minimum variable step (default) | 0.5 s | [2, p. 151] | |
| SWMM routing step guidance | 10–30 s for 200–400 ft conduits | [1, p. 59] | Uncontrolled stability guidance |
| Continuity-error flag | 5–10% [1]; "such as 10%" [2] | [1, pp. 57–58]; [2, p. 158] | Not a refinement criterion |
| RTC parameter ranges for GSA | FD_max 0.90–1.05; T 300 s (60–500 s); P gain 0.5–1.5 | [28] Table 3 | Flemish RBC, InfoWorks/SWMM |
| EFD threshold | 20% filling | [30] | Astlingen EFD rules |
| Wet-well fill time | ≤ 30 min (unless equalisation) | [48, §42.62] | Design standard; minimum pump cycle time is manufacturer-specified |
| GLWA SCADA viewer data interval | "one minute, five minutes, or more" | [50] | Visualisation/data interval, not PLC scan |
| Same-site public INP: routing / rule step | ROUTING_STEP 10 s; RULE_STEP 0; VARIABLE_STEP 0.75; MINIMUM_STEP 0.5 s; MAX_TRIALS 8; HEAD_TOLERANCE 0.005 | [66] CODE | `7MPF_25yr_P1_FF.inp`; same hydraulic/control core as `7MPF_CSO_08.inp`, verified by structured diff; rainfall/reporting differ |
| Same-site INP: PUMP29 on/off threshold | OFF < 3.5 ft, ON > 3.5 ft at node 35442 (zero band); OFF if JCT-3090 depth > 3 | [66] | Zero-deadband relay |
| Same-site INP: PUMP27 / PUMP28 bands | 13–19 ft / 4–12 ft at node 35391 (rule-based); [PUMPS] startup/shutoff 0/0 | [66] | Native depth hysteresis unused |
| Same-site INP: Shiawassee gate 35263 | Close if 35391 head > 603.0 (or 3530 closed); open (0.25 or 1.0) only if head < 597.6 | [66] | 5.4 ft band, implicit hysteresis |
| Same-site INP: flow-split / first-flush thresholds | 35281_A flow > 231 & 35440 head > 609.27; 35291_A flow > 321 & 35390 head > 603.28; 35442 head > 605.0; 35391 head > 601.03 | [66] | IF/ELSE, zero deadband |
| Same-site INP: orifice open/close times | 0.117 h (1360, 1360_B, 3530, 3530_B); 0.07 h (35263); 0.3 h (35281_B, 35291_B) | [66]; units per [2, p. 236] | |
| Same-site optimiser control interval | 15 min; actions 0–1 in 0.05 steps, 10 actuators | [62, p. 729] | Syed et al. 2025 |
| Same-site RL reward safety margin | 2 ft below maximum allowable nodal depth | [61, p. 716] | Yin et al. 2023 |
| GLWA SCADA regulator level logging | every 5 min | [68]; [69] | Measurement interval, not control scan |
| Seven Mile RTB | 2.2 MG; 656 cfs; 30 min detention | [40, p. 3-11] | Design data, not control parameters |
| Puritan-Fenkell | 2.8 MG; 845 cfs; 2×1,100 gpm sanitary; 3×4,500 gpm dewatering | [40, p. 3-11] | Design data |

No source I could access states a deadband or minimum dwell time in seconds or metres for any real CSO gate or pump.

---

## (d) Defensible options, ranked (none relaxes the 1% threshold)

1. **Frozen-control hydraulic refinement (diagnostic; numerical, no semantic change).** Run 0.5 vs 0.25 s with all regulators held at fixed settings, or replaying one fixed schedule identically in both runs, on the TRAIN storm.
   - If this passes ≤1%, the residual is attributable to switching (Q2, [13][14]), not the hydraulic solver.
   - If it fails, the solver is still implicated [1, pp. 57–59][6].
   - Cheap, and it directly tests the "does not by themselves prove" caveat in the verification report.
   - *Tag: numerical diagnostic.* Adopting a replayed schedule as the reference would be a *protocol change*.
   - *Executed:* the all-open/pumps-off frozen state passes at 0.238% with zero flood and continuity below 1% at both steps. It took about 35 minutes total, so it was not cheap for this operating state. It isolates switching but is not adopted as a comparator.
2. **Third refinement level plus observed-order/GCI reporting (diagnostic; numerical).** Add 0.125 s (and 1.0 s) and report the observed order of CSO volume and switch counts per [52][53]. Non-convergent switch counts would document a non-asymptotic hybrid regime (Q2).
   - *Tag: numerical diagnostic.* Passing the gate on an extrapolated value would be a *protocol change*.
   - *Executed:* the 0.125 s native result is 3,776.846 m³ versus 4,016.242 m³ at 0.25 s. The 6.339% change reverses direction, so the standard real-order/GCI calculation is invalid and the native response is non-asymptotic over these refinements.
3. **Obtain the authoritative control specification (pre-registered path).** Request the NPDES Part I.A.15.d Operational Plan ("hydraulic operational elevations for … regulators, diversion devices, gates, level sensors") [45], plus SCADA/PLC logic for VR-17 (Shiawassee gate), the Seven Mile and Puritan-Fenkell RTBs and the dewatering pumps [40]. Implement it via RULE_STEP, TIMEOPEN/TIMECLOSED dwell, startup/shutoff hysteresis and orifice open/close time, all native SWMM syntax [2][4]. Re-run the unchanged gate.
   - *Tag: protocol-sanctioned reference change.* It is already pre-registered in `control_spec_data_request.md`, so it is not a new deviation.
4. **Pre-registered physically realisable reference controller (if documents are unavailable).** Freeze a priori, *before* looking at diagnostic-storm results:
   - a rule cadence (e.g., 5 min per the Astlingen SWMM precedent [30], or a sub-minute value justified as a PLC scan);
   - a hysteresis band;
   - a minimum dwell justified from Ten States/manufacturer duty-cycle logic [48].

   Report the original zero-deadband native rules as a flagged sensitivity. Justification: [13] (the regularisation must be chosen), [16][17][18] (hysteresis/dwell are the standard remedies), [9][30][31] (decoupled control intervals are standard practice).
   - *Tag: protocol change.* It must be declared, versioned and not tuned.
5. **Reference envelope.** Evaluate the agent against a pre-declared family of regularised native controllers (cadence × deadband × dwell grid, or Morris design [28][56][57]). Claim improvement only if it holds across the whole envelope.
   - *Tag: protocol change* to the comparator definition. It is more conservative than option 4.
6. **Event-located rule evaluation (engine change).** Locate threshold crossings inside a step and split the step [19][20][21].
   - *Tag: numerical fix* only if the reference is defined as the continuous-time controller. Relative to SWMM's documented semantics (evaluation at routing-step boundaries [2][4]) it is a *protocol change*.
   - Expected to converge switch *times*, but it may expose sliding/Zeno chattering at zero-deadband thresholds [11][14]. High implementation risk.
7. **More solver work only** (tolerances, trials, Jacobian extensions). The project's evidence suggests this is exhausted, and the hybrid-systems literature gives no reason to expect convergence while the switching semantics depend on Δt. *Tag: numerical fix; low expected yield.*

---

## (e) Gaps: what remains undisclosed and who could supply it

**Not disclosed in any public source found:**
- PLC/RTU scan interval and rule-evaluation cadence for VR-17 (Seven Mile/Shiawassee gate), the Seven Mile RTB, the Puritan-Fenkell RTB/PS, and the seven modelled orifices (35281_B, 1360, 1360_B, 35291_B, 3530, 3530_B, 35263).
- Open/close thresholds, deadbands and hysteresis bands.
- Pump minimum on/off times and starts per hour. Ten States defers to manufacturer duty cycles [48].
- Gate travel speed and command delay.
- Fail-safe and initial states.
- Whether the 7MPF model's `[CONTROLS]` came from as-built logic or modeller assumptions.
- The mapping from SWMM link IDs to GLWA asset IDs (VR-17, ISD013, etc.).
- Same-site studies [58][60–63] do not state their routing step, action interval, or whether the INP's `[CONTROLS]` stayed active under external control. The provenance of the public INP's rule thresholds is undocumented [66].

**Document types to request:**
- The annual *Collection System and CSO Treatment Facilities Operational Plan* (NPDES MI0022802 Part I.A.15.d, submitted to EGLE each April 1) [45].
- The *WRRF Wet Weather Operational Plan* (Part I.A.11) [45].
- The *Regional Operating Plan* and IWOP [40].
- SCADA functional design specifications.
- RTB O&M manuals and commissioning reports (both RTBs completed 1999 [40]).
- PLC program exports.
- The calibration and operating-rule documentation for the Regional Wastewater Collection System Model ("operating rules … in effect in 2018") [40, p. 5-2].

**Who could supply it:**
- GLWA wastewater/CSO-facility operations and the SCADA/systems-control group.
- GLWA's permit-compliance staff (the Operational Plan is a permit deliverable).
- Michigan EGLE (copy of the approved Operational Plan, via public-records request).
- The consultants or authors of the regional SWMM model and the 7MPF INP.
- The FIU group (Z. Yin, corresponding author of [61]; A.S. León; M.H. Amini; Z. Syed): they hold the PFSMC SWMM model lineage and can say which controls, routing step and action interval they used, and where the INP came from.
- The Kerkez group, University of Michigan: they used a Detroit subsection model with ISD control points [38][39], though they are unlikely to hold PLC parameters.

**Literature gaps:**
- No peer-reviewed SWMM-specific study of control-rule chatter versus routing step was found.
- Review full texts (Schütze 2004, Lund 2018, Campisano 2013, Mollerup 2017, Colas 2004) were not legally accessible here (publisher bot-blocking). They may contain typical PLC cadence values that I could not verify.
- A GLWA 2026 draft permit public-notice document surfaced in search; I did not read it.
- Same-site full texts not accessible: Yin et al. 2022 [60] (ASCE, no PAR copy) and Syed et al. 2026 [63] (PAR embargo to 23 Apr 2027). The SSRN preprint [64] download was blocked. Yin's dissertation was not located in a public repository.

---

## (f) References

Access codes: **FT** = full text read in this session (open/legal); **AB** = abstract only; **MD** = bibliographic metadata only; **CODE** = public source code read.

1. Rossman, L.A. (2017). *Storm Water Management Model Reference Manual Volume II – Hydraulics*. EPA/600/R-17/111. https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P100S9AS.TXT (mirror read: https://downloads.tuflow.com/SWMM/SWMM5_Reference_Manual_Volume2_Hydaulics_P100S9AS.pdf). Open. *Verified:* FT, pages located via pdftotext.
2. Rossman, L.A., & Simon, M.A. (2022). *Storm Water Management Model User's Manual Version 5.2*. EPA/600/R-22/030. https://www.epa.gov/system/files/documents/2022-04/swmm-users-manual-version-5.2.pdf (read via https://cfpub.epa.gov/si/si_public_file_download.cfm?Lab=CESER&p_download_id=544334). Open. *Verified:* FT.
3. US EPA (2022). *SWMM 5.2 Update History* (5.2.0 updates and bug fixes, item 11). https://cfpub.epa.gov/si/si_public_file_download.cfm?Lab=CESER&p_download_id=544332. Open. *Verified:* FT.
4. US EPA. *Stormwater-Management-Model source code* (`src/solver/routing.c`, `project.c`, `link.c`, `controls.c`; tags v5.1.13, v5.2.0, master). https://github.com/USEPA/Stormwater-Management-Model. Open. *Verified:* CODE.
5. Rossman, L.A. (2006). *Storm Water Management Model Quality Assurance Report: Dynamic Wave Flow Routing*. EPA/600/R-06/097. https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10089TF.TXT. Open. *Verified:* MD (NEPIS listing via search).
6. Pachaly, R.L., Vasconcelos, J.G., Allasia, D.G., Tassi, R., & Bocchi, J.P.P. (2020). Comparing SWMM 5.1 calculation alternatives to represent unsteady stormwater sewer flows. *J. Hydraulic Engineering* 146(7), 04020046. https://doi.org/10.1061/(ASCE)HY.1943-7900.0001762. Closed. *Verified:* Crossref + AB (OpenAlex).
9. McDonnell, B.E., Ratliff, K., Tryby, M.E., Wu, J.J.X., & Mullapudi, A. (2020). PySWMM: The Python Interface to Stormwater Management Model (SWMM). *JOSS* 5(52), 2292. https://doi.org/10.21105/joss.02292; `step_advance` in https://github.com/pyswmm/pyswmm. Open. *Verified:* Crossref + FT (PDF) + CODE.
10. Riaño-Briceño, G., Barreiro-Gomez, J., Ramirez-Jaime, A., Quijano, N., & Ocampo-Martinez, C. (2016). MatSWMM – An open-source toolbox for designing real-time control of urban drainage systems. *Environ. Model. Softw.* 83, 143–154. https://doi.org/10.1016/j.envsoft.2016.05.009. Green OA. *Verified:* Crossref/MD.
11. Filippov, A.F. (1988). *Differential Equations with Discontinuous Righthand Sides*. Kluwer (Mathematics and Its Applications). https://doi.org/10.1007/978-94-015-7793-9. Closed. *Verified:* Crossref/MD.
12. Utkin, V. (1977). Variable structure systems with sliding modes. *IEEE Trans. Automatic Control* 22(2), 212–222. https://doi.org/10.1109/TAC.1977.1101446. Closed. *Verified:* Crossref + AB.
13. Johansson, K.H., Egerstedt, M., Lygeros, J., & Sastry, S. (1999). On the regularization of Zeno hybrid automata. *Systems & Control Letters* 38(3), 141–150. https://doi.org/10.1016/S0167-6911(99)00059-6 (author copy: https://kth.diva-portal.org/smash/get/diva2:495789/FULLTEXT01). Open (repository). *Verified:* Crossref + FT.
14. Zhang, J., Johansson, K.H., Lygeros, J., & Sastry, S. (2001). Zeno hybrid systems. *Int. J. Robust Nonlinear Control* 11(5), 435–451. https://doi.org/10.1002/rnc.592. Green OA. *Verified:* Crossref + AB.
15. Goebel, R., Sanfelice, R.G., & Teel, A.R. (2009). Hybrid dynamical systems. *IEEE Control Systems Magazine* 29(2), 28–93. https://doi.org/10.1109/MCS.2008.931718. Closed. *Verified:* Crossref/MD.
16. Liberzon, D. (2003). *Switching in Systems and Control*. Birkhäuser. https://doi.org/10.1007/978-1-4612-0017-8. Closed. *Verified:* Crossref/MD.
17. Hespanha, J.P., & Morse, A.S. (1999). Stability of switched systems with average dwell-time. *Proc. 38th IEEE CDC*, 3, 2655–2660. https://doi.org/10.1109/CDC.1999.831330. Closed. *Verified:* Crossref + AB.
18. Hespanha, J.P., Liberzon, D., & Morse, A.S. (2003). Hysteresis-based switching algorithms for supervisory control of uncertain systems. *Automatica* 39(2), 263–272. https://doi.org/10.1016/S0005-1098(02)00241-8. Green OA. *Verified:* Crossref/MD.
19. Shampine, L.F., & Thompson, S. (2000). Event location for ordinary differential equations. *Computers & Mathematics with Applications* 39(5–6), 43–54. https://doi.org/10.1016/S0898-1221(00)00045-6. Bronze OA. *Verified:* Crossref/MD.
20. Park, T., & Barton, P.I. (1996). State event location in differential-algebraic models. *ACM TOMACS* 6(2), 137–165. https://doi.org/10.1145/232807.232809. *Verified:* Crossref + AB.
21. Gear, C.W., & Østerby, O. (1984). Solving ordinary differential equations with discontinuities. *ACM TOMS* 10(1), 23–44. https://doi.org/10.1145/356068.356071. *Verified:* Crossref + AB.
22. Dieci, L., & Lopez, L. (2012). A survey of numerical methods for IVPs of ODEs with discontinuous right-hand side. *J. Comput. Appl. Math.* 236(16), 3967–3991. https://doi.org/10.1016/j.cam.2012.02.011. Bronze OA. *Verified:* Crossref/MD.
23. Mosterman, P.J. (1999). An overview of hybrid simulation phenomena and their support by simulation packages. In *Hybrid Systems: Computation and Control*, LNCS 1569, 165–177. https://doi.org/10.1007/3-540-48983-5_17. Closed. *Verified:* Crossref/MD.
24. García, L., Barreiro-Gomez, J., Escobar, E., Téllez, D., Quijano, N., & Ocampo-Martinez, C. (2015). Modeling and real-time control of urban drainage systems: A review. *Adv. Water Resour.* 85, 120–132. https://doi.org/10.1016/j.advwatres.2015.08.007. Green OA. *Verified:* Crossref/MD.
25. Lund, N.S.V., Falk, A.K.V., Borup, M., Madsen, H., & Mikkelsen, P.S. (2018). Model predictive control of urban drainage systems: A review and perspective towards smart real-time water management. *Crit. Rev. Environ. Sci. Technol.* 48(3), 279–339. https://doi.org/10.1080/10643389.2018.1455484. Bronze OA (download blocked here). *Verified:* Crossref/MD.
26. Schütze, M., Campisano, A., Colas, H., Schilling, W., & Vanrolleghem, P.A. (2004). Real time control of urban wastewater systems—where do we stand today? *J. Hydrol.* 299(3–4), 335–348. https://doi.org/10.1016/j.jhydrol.2004.08.010. Closed. *Verified:* Crossref/MD.
27. Mollerup, A.L., Mikkelsen, P.S., Thornberg, D., & Sin, G. (2017; online 2016). Controlling sewer systems – a critical review based on systems in three EU cities. *Urban Water J.* 14(4), 435–442. https://doi.org/10.1080/1573062X.2016.1148183. Closed. *Verified:* Crossref + AB.
28. Kroll, S., Weemaes, M., Van Impe, J., & Willems, P. (2018). A methodology for the design of RTC strategies for combined sewer networks. *Water* 10(11), 1675. https://doi.org/10.3390/w10111675. Gold OA. *Verified:* Crossref + FT.
29. Schütze, M., Lange, M., Pabst, M., & Haas, U. (2018). Astlingen – a benchmark for real time control (RTC). *Water Sci. Technol.* 2017(2), 552–560. https://doi.org/10.2166/wst.2018.172. Closed. *Verified:* Crossref + AB.
30. Sun, C., Lorenz Svensen, J., Borup, M., Puig, V., Cembrano, G., & Vezzaro, L. (2020). An MPC-enabled SWMM implementation of the Astlingen RTC benchmarking network. *Water* 12(4), 1034. https://doi.org/10.3390/w12041034; model: https://github.com/open-toolbox/SWMM-Astlingen (`Astlingen_SWMM.inp`, `EFD_Control.txt`). Gold OA. *Verified:* Crossref + FT + CODE/INP (commit history checked: uploaded 2020-01-08).
31. Saliba, S.M., Bowes, B.D., Adams, S., Beling, P.A., & Goodall, J.L. (2020). Deep reinforcement learning with uncertain data for real-time stormwater system control and flood mitigation. *Water* 12(11), 3222. https://doi.org/10.3390/w12113222. Gold OA. *Verified:* Crossref + FT.
32. Bowes, B.D., Tavakoli, A., Wang, C., Heydarian, A., Behl, M., Beling, P.A., & Goodall, J.L. (2021; online 2020). Flood mitigation in coastal urban catchments using real-time stormwater infrastructure control and reinforcement learning. *J. Hydroinformatics* 23(3), 529–547. https://doi.org/10.2166/hydro.2020.080. Hybrid OA (download blocked here). *Verified:* Crossref + AB.
33. Tian, W., Liao, Z., Zhang, Z., Wu, H., & Xin, K. (2022). Flooding and overflow mitigation using deep reinforcement learning based on Koopman operator of urban drainage systems. *Water Resour. Res.* 58(7), e2021WR030939. https://doi.org/10.1029/2021WR030939. Hybrid OA (download blocked here). *Verified:* Crossref + AB.
34. Rimer, S.P., Mullapudi, A., Troutman, S.C., Ewing, G., Bowes, B.D., Akin, A.A., Sadler, J., Kertesz, R., et al. (2023). pystorms: A simulation sandbox for the development and evaluation of stormwater control algorithms. *Environ. Model. Softw.* 162, 105635. https://doi.org/10.1016/j.envsoft.2023.105635. Bronze. *Verified:* Crossref/MD.
35. kLabUM. *pystorms* source code (`environment.py`, `scenarios/zeta.py`, `tutorials/rule_based_controller.py`). https://github.com/kLabUM/pystorms. Open. *Verified:* CODE.
36. Mullapudi, A., Lewis, M.J., Gruden, C.L., & Kerkez, B. (2020). Deep reinforcement learning for the real time control of stormwater systems. *Adv. Water Resour.* 140, 103600. https://doi.org/10.1016/j.advwatres.2020.103600 (author copy: https://randomstorms.net/data/papers/rl.pdf). *Verified:* Crossref + FT (author-hosted copy).
37. Kerkez, B., Gruden, C., Lewis, M., Montestruque, L., Quigley, M., Wong, B., Bedig, A., Kertesz, R., et al. (2016). Smarter stormwater systems. *Environ. Sci. Technol.* 50(14), 7267–7273. https://doi.org/10.1021/acs.est.5b05870. Bronze. *Verified:* Crossref/MD (background only).
38. Troutman, S.C., Love, N.G., & Kerkez, B. (2020). Balancing water quality and flows in combined sewer systems using real-time control. *Environ. Sci.: Water Res. Technol.* 6(5), 1357–1369. https://doi.org/10.1039/C9EW00882A; code: https://github.com/stroutm/LBCsewer. Closed (paper); open (code). *Verified:* Crossref + CODE.
39. Troutman, S.C. (2020). *Coupled, Data-Driven, and Real-Time Modeling and Control of Sewer Systems and Water Resource Recovery Facilities*. PhD dissertation, University of Michigan. https://hdl.handle.net/2027.42/163069. Open (PDF behind bot check). *Verified:* AB (repository page).
40. Great Lakes Water Authority (2020). *Wastewater Master Plan* (Final, June 2020). https://www.glwater.org/wp-content/uploads/2020/12/Full_WWMP_Report_Final_June-2020.pdf. Open. *Verified:* FT (pp. 1-13–1-14, 3-10–3-11, 3-45, 3-49, 3-51, 5-2).
41. Vezzaro, L., & Grum, M. (2014). A generalised Dynamic Overflow Risk Assessment (DORA) for Real Time Control of urban drainage systems. *J. Hydrol.* 515, 292–303. https://doi.org/10.1016/j.jhydrol.2014.05.019. Closed. *Verified:* Crossref/MD.
42. van der Werf, J.A., Kapelan, Z., & Langeveld, J. (2022). Towards the long term implementation of real time control of combined sewer systems: a review of performance and influencing factors. *Water Sci. Technol.* 85(4), 1295–1320. https://doi.org/10.2166/wst.2022.038. Diamond OA (download blocked here). *Verified:* Crossref/MD.
43. Campisano, A., Cabot Ple, J., Muschalla, D., Pleau, M., & Vanrolleghem, P.A. (2013). Potential and limitations of modern equipment for real time control of urban wastewater systems. *Urban Water J.* 10(5), 300–311. https://doi.org/10.1080/1573062X.2013.763996. Closed. *Verified:* Crossref + AB.
44. Schütze, M., Erbe, V., Haas, U., Scheer, M., & Weyand, M. (2008). Sewer system real-time control supported by the M180 guideline document. *Urban Water J.* 5(1), 69–78. https://doi.org/10.1080/15730620701754376. Closed. *Verified:* Crossref + AB.
45. Michigan Department of Environment, Great Lakes, and Energy (2019). *NPDES Permit No. MI0022802, Great Lakes Water Authority WRRF* (issued June 28, 2019). https://www.glwater.org/wp-content/uploads/2024/04/2019-NPDES-Permit-FINAL_GLWA-WRRF.pdf. Open. *Verified:* FT (p. 16; Part I.A.15.d, pp. 37–38).
46. Colas, H., Pleau, M., Lamarre, J., Pelletier, G., & Lavallée, P. (2004). Practical perspective on real-time control. *Water Qual. Res. J. Canada* 39(4), 466–478. https://doi.org/10.2166/wqrj.2004.058. Bronze OA (download blocked here). *Verified:* Crossref + AB.
47. Pleau, M., Colas, H., Lavallée, P., Pelletier, G., & Bonin, R. (2005). Global optimal real-time control of the Quebec urban drainage system. *Environ. Model. Softw.* 20(4), 401–413. https://doi.org/10.1016/j.envsoft.2004.02.009. Closed. *Verified:* Crossref/MD.
48. Great Lakes–Upper Mississippi River Board (2014). *Recommended Standards for Wastewater Facilities* ("Ten States Standards"), 2014 ed., §42.62 Wet well size. https://dam.assets.ohio.gov/image/upload/epa.ohio.gov/Portals/35/pti/10wastewaterstandards-2014.pdf. Open. *Verified:* FT (p. 40-5).
49. Great Lakes Water Authority (2021). *June & July Rain Events Update, as of August 25, 2021*. https://www.glwater.org/wp-content/uploads/2021/08/Rain-Events-Update-August-25-FINAL-210825.pdf. Open. *Verified:* FT.
50. Salim, I., & McCord, D. (2025). Harnessing data for smarter wastewater management: GLWA's Interceptor Hydraulic Viewer. *Clear Waters* (trade magazine; hosted by Wade Trim). https://www.wadetrim.com/wp-content/uploads/smart-ww-mgmt-clear-waters-25.pdf. Open. *Verified:* FT. Not peer reviewed; the year is inferred from the file name.
51. Ridgway, K.E., & Rabbaig, M.M. (2002). Development of inflatable dam design parameters and control schemes using the Transient Analysis Program. *Proc. WEF (WEFTEC)* 2002(9), 198–214. https://doi.org/10.2175/193864702784162552. Closed. *Verified:* Crossref + AB (search snippet).
52. Roache, P.J. (1994). Perspective: A method for uniform reporting of grid refinement studies. *J. Fluids Eng.* 116(3), 405–413. https://doi.org/10.1115/1.2910291. Closed. *Verified:* Crossref + AB.
53. Celik, I.B., Ghia, U., Roache, P.J., Freitas, C.J., Coleman, H., & Raad, P.E. (2008). Procedure for estimation and reporting of uncertainty due to discretization in CFD applications. *J. Fluids Eng.* 130(7), 078001. https://doi.org/10.1115/1.2960953. Bronze. *Verified:* Crossref (title, journal, article number). Crossref has no author field; author list from the publisher record as commonly cited (not independently re-checked here).
54. Eça, L., Dowding, K., & Roache, P.J. (2022). On the interpretation and scope of the V&V 20 Standard for verification and validation in computational fluid dynamics and heat transfer. *J. Verif. Valid. Uncert. Quant.* https://doi.org/10.1115/1.4053854. Closed. *Verified:* Crossref + AB.
54b. Great Lakes Water Authority. *Capital Improvement Plan FY2026–2030, Appendix D* (Legistar). https://glwater.legistar.com/View.ashx?GUID=0362A618-FDDD-4C47-AE08-5965014AF38A&ID=13768089&M=F. *Verified:* URL resolves (HTTP 200); content not re-read this session.
55. Oberkampf, W.L., & Roy, C.J. (2010). *Verification and Validation in Scientific Computing*. Cambridge University Press. https://doi.org/10.1017/CBO9780511760396. Closed. *Verified:* Crossref/MD.
56. Pianosi, F., Beven, K., Freer, J., Hall, J.W., Rougier, J., Stephenson, D.B., & Wagener, T. (2016). Sensitivity analysis of environmental models: A systematic review with practical workflow. *Environ. Model. Softw.* 79, 214–232. https://doi.org/10.1016/j.envsoft.2016.02.008. Hybrid OA. *Verified:* Crossref/MD.
57. Saltelli, A., Ratto, M., Andres, T., Campolongo, F., Cariboni, J., Gatelli, D., Saisana, M., & Tarantola, S. (2008; Crossref issued 2007). *Global Sensitivity Analysis: The Primer*. Wiley. https://doi.org/10.1002/9780470725184. Closed. *Verified:* Crossref/MD.
58. Yin, Z., Saadati, Y., Leon, A.S., Hadi Amini, M., Bian, L., & Hu, B. (2024). Forecasting and optimization for minimizing combined sewer overflows using machine learning frameworks and its inversion techniques. *J. Hydrol.* 628, 130515. https://doi.org/10.1016/j.jhydrol.2023.130515; NSF PAR copy: https://par.nsf.gov/servlets/purl/10523713. Bronze/open (PAR). *Verified:* Crossref + OpenAlex + FT (PAR copy of published article; pp. 4–5, 10–13).
59. Ridgway, K.E., & Rabbaig, M.M. (2006). Use of in-line inflatable dams for CSO control. *Proc. WEF (WEFTEC)* 2006(6), 5578–5590. https://doi.org/10.2175/193864706783775504. Closed. *Verified:* Crossref + AB.
60. Yin, Z., Zahedi, L., Leon, A.S., Amini, M.H., & Bian, L. (2022). A machine learning framework for overflow prediction in combined sewer systems. In *World Environmental and Water Resources Congress 2022*, pp. 194–205. ASCE. https://doi.org/10.1061/9780784484258.019. Closed. *Verified:* Crossref + OpenAlex + AB (also FIU Discovery record).
61. Yin, Z., Leon, A.S., Sharifi, A., & Amini, M.H. (2023). Optimal control of combined sewer systems to minimize sewer overflows by using reinforcement learning. In *World Environmental and Water Resources Congress 2023*, pp. 711–722. ASCE. https://doi.org/10.1061/9780784484852.067; NSF PAR: https://par.nsf.gov/servlets/purl/10459969. Open (PAR). *Verified:* Crossref + FT (PAR; pp. 713, 715–717, 720).
62. Syed, Z., Saadati, Y., Yin, Z., Hadi Amini, M., & Leon, A.S. (2025). Optimal control of combined sewer overflow (CSO) using gradient-based neural network inversion with projected precipitation inputs. In *World Environmental and Water Resources Congress 2025*, pp. 725–735. ASCE. https://doi.org/10.1061/9780784486184.068; NSF PAR: https://par.nsf.gov/servlets/purl/10615945. Open (PAR). *Verified:* Crossref + FT (PAR; pp. 727, 729, 731–732).
63. Syed, Z., Saadati, Y., Yin, Z., Hadi Amini, M., & Leon, A.S. (2026). Continual learning with elastic weight consolidation for robust combined sewer overflow optimization via neural inversion. In *World Environmental and Water Resources Congress 2026*, pp. 548–559. ASCE. https://doi.org/10.1061/9780784486931.045. Closed (PAR full text embargoed until 23 Apr 2027). *Verified:* Crossref + OpenAlex + AB.
64. Syed, Z., Saadati, Y., Yin, Z., Amini, M.H., & Leon, A.S. (2025). Continual learning with elastic weight consolidation (EWC) for robust combined sewer overflow prediction and optimization via neural inversion. *SSRN preprint*. https://doi.org/10.2139/ssrn.5393892. OA per OpenAlex, but download was bot-blocked here. *Verified:* Crossref/MD.
65. Syed, Z. (2026). *Integrated Continual Learning Frameworks for Real-Time Combined Sewer Overflow Control Prediction and Optimization via Neural Inversion* (Version 1) [Dataset]. Mendeley Data. https://doi.org/10.17632/4spjvszr6z.1. Open. *Verified:* OpenAlex + dataset landing page and public file list (description, "Steps to reproduce", three output CSVs; no INP).
66. Yin, Z. (2023). *Predicting-and-Minimizing-Combined-Sewer-Overflows* (GitHub repository; files `7MPF_25yr_P1_FF.inp`, `MU_Exist2020Q4_TY_2020Q4.inp`). https://github.com/ZedaYin/Predicting-and-Minimizing-Combined-Sewer-Overflows. Open. *Verified:* CODE (repository cited in [58, p. 4]; GitHub API metadata; INP downloaded and parsed: [TITLE], [OPTIONS], [ORIFICES], [PUMPS], [STORAGE], [CONTROLS], [EVENTS]).
67. Great Lakes Water Authority (2019). *CEO Report, April 24, 2019, and General Counsel Report*. https://www.glwater.org/wp-content/uploads/2019/04/CEO-Report-April-24-2019-and-General-Counsel-Report.pdf. Open. *Verified:* FT (PDF pp. 12, 15). Board report, not peer reviewed.
68. Great Lakes Water Authority (2018). *Combined Sewer Overflow (CSO) Public Notification Plan* (final, 8/2/2018). https://www.glwater.org/wp-content/uploads/2020/04/Final_CSO-Notification-Plan-8.2.2018.pdf. Open. *Verified:* FT (§IV–V, outfall tables).
69. Eichenwald, Z., McGrath, G., Burchi, J., Thomas, B., Saparia, B., & Gee, S. (2021). Real-time assessment of the GLWA's Regional Operating Plan using digital twin technology. *Proceedings of the Water Environment Federation*, Collection Systems 2021 (virtual, March 23–25, 2021). https://www.accesswater.org/publications/proceedings/-10044440/real-time-assessment-of-the-glwa-s-regional-operating-plan-using-digital-twin-technology. Closed. *Verified:* publisher landing page + AB (extended abstract). No DOI found via Crossref.
70. Ewing, G., Mullapudi, A., Troutman, S.C., Kerkez, B., Barrott, W., & Nastally, C. (2019). Open-Storm Detroit Dynamics. *WE&T* 31(7), 28–35. https://www.accesswater.org/publications/-325073/open-storm-detroit-dynamics. Closed. *Verified:* publisher landing page + section previews only. Trade magazine.
71. Brink, P., Santini, A.D., Ibrahim, A., & TenBroek, M.J. (Camp Dresser & McKee) (2001). Development and use of continuous SWMM for CSO notification for the City of Detroit. *Journal of Water Management Modeling*. https://doi.org/10.14796/jwmm.r207-20. Open (CHI). *Verified:* Crossref + OpenAlex + AB.
72. León, A.S., Yin, Z., & Sharifi, A. (2024). A finite volume model for maintaining stationarity and reducing spurious oscillations in simulations of sewer system filling and emptying. *J. Hydraul. Res.* 62(3), 267–282. https://doi.org/10.1080/00221686.2024.2341880; NSF PAR: https://par.nsf.gov/servlets/purl/10523709. Open (PAR). *Verified:* Crossref + FT (PAR; checked for Detroit/PFSMC: not identifiable).
73. León Research Group, FIU. *People: Zeda Yin* and *Our Publications* (web pages). https://web.eng.fiu.edu/arleon/People_Zeda.html; https://web.eng.fiu.edu/arleon/Publications.html. Open. *Verified:* pages opened (PhD Spring 2024; conference page ranges).

**Counts:** 72 reference entries (including public codebases/model files and URL-only items). Every entry was checked against Crossref/OpenAlex/DataCite (the 53 with DOIs) or by opening the official URL. Access levels: 24 full text or code read, 22 abstract only, 26 metadata or URL only. Same-site (PFSMC/7MPF) items: [58], [60]–[66]. Numbers 7–8 are unassigned; numbering matches `references.json`.
