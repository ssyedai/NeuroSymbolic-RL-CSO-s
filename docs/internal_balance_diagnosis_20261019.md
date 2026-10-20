# Internal balance diagnosis — 19 October 2026

Hydraulic acceptance remains failed. This investigation adds read-only evidence and an explicitly separate iteration-budget sensitivity experiment; it does not adopt a production engine or authorize training.

## Overflow-window tracing

The logging DLL reproduces all 12 recorded final numeric metrics at 0.5 and 0.25 seconds exactly. It preserves the saved TRAIN inputs and 288 calls to `swmm_stride(900)`. In the windows 81,000–85,500 s and 112,500–116,100 s it records every routing-step exit, selected node heads/areas/volumes/continuity residuals, and selected link flows/settings/targets/final-flow residuals. These are final-iteration traces, not every intermediate iteration.

First positive weir 35444 flow in the first window occurs at 82,116.5 s for 0.5-second routing and 82,150.0 s for 0.25-second routing: a **33.5-second onset difference**. In the second window the corresponding times are 113,419.5 and 113,719.5 s: **300 seconds apart**. The traced gates and treatment pump have no actual-setting or target changes within either window.

At 0.5 seconds, 2,276/9,001 routing steps fail convergence in window 1 and 5,362/7,201 in window 2. At 0.25 seconds, the counts are 750/18,001 and 7,754/14,401. Inclusive boundaries explain the extra endpoint. These are global step failures, not failures attributable only to the displayed nodes.

The sums of storage 35440's absolute final continuity residual are only 0.019492 and 0.101907 ft³ in the two coarse windows, versus 0.025249 and 0.078327 ft³ in the fine windows. Thus these local residuals alone do not explain the final 127.499 m³ CSO difference. Residual sums describe discrete-equation error and must not be presented as physical water losses or usable storage. Gate 1360_B's maximum final-flow mismatch in these windows is below 0.000049 CFS. Other regulator checks can still fail, including W1 (up to 0.205655 CFS in the finer second window).

## Full-event localization

A second logging-only DLL aggregates signed, absolute and maximum ordinary-node continuity residuals over 900-second bins. Both replays reproduce all prior final metrics exactly. There are 288 bins per node at each resolution, the step counts cover the full event, and per-node failure counts exactly match the independent failure-count trace.

Large upstream residuals occur **before overflow**, especially during 78,300–80,100 s (21.75–22.25 h):

- Junction 3528: summed absolute pre-overflow residual 2714.983 ft³ at 0.5 s and 2872.614 ft³ at 0.25 s.
- Junction 3517: 2182.618 and 1965.521 ft³.
- Junction 3534: 1849.095 and 1819.031 ft³.
- Junction 3536: 2097.801 and 2113.153 ft³.

These are computational continuity residuals, not independent physical volume deficits. They can have either sign and cannot simply be added to or subtracted from reported CSO. The magnitude ranking differs from the ranking by failure count: frequent tiny residuals at storage 35440 previously obscured less frequent but much larger upstream errors. The findings justify examining the upstream conduit–junction update rather than repeatedly changing the outlet law.

Evidence: `runs/hydraulic_validation_20261019/window_trace/` and `balance_bins/`, with configurations, saved driver sources, exact-match checks, raw logs and summaries. The source forks and patches are stored in the corresponding `*_source/` directories. One simulation process is used at a time; the INP's internal thread setting is retained. The installed SWMM DLL and original INP are unchanged.

Software verification after the diagnostic additions: **90 tests passed**. This verifies software regressions, not hydraulic acceptance. The subsequent iteration-budget experiment and upstream trace must be assessed separately before any revised acceptance claim.
