.PHONY: data audit unit-audit train-smoke train-x2 test report preflight train-v8-pilot eval-v8-test

data:
	PYTHONPATH=. .venv/bin/python -m research.acquire_ncei --config configs/data.json
	PYTHONPATH=. .venv/bin/python -m research.build_real_storms --config configs/data.json \
	  --out-dir data/useful/rain_real

unit-audit:
	PYTHONPATH=. .venv/bin/python -m research.unit_audit

audit:
	PYTHONPATH=. .venv/bin/python -m multistorm.audit \
	  --rain-dir data/useful/rain_real_stormy_x2 \
	  --split-manifest data/useful/splits/splits_stormy_x2.json

train-smoke:
	PYTHONPATH=. .venv/bin/python -m multistorm.train_multi \
	  --rain-dir data/unused/rain_real_smoke \
	  --split-manifest data/unused/splits/splits_smoke.json \
	  --real-only --episodes 4 --warmup-steps 300 --eval-every 2 --run-name real_smoke

# Active labelled ×2 stress-test (not primary "100% real" claim)
train-x2:
	PYTHONPATH=. .venv/bin/python -m multistorm.train_multi \
	  --rain-dir data/useful/rain_real_stormy_x2 \
	  --split-manifest data/useful/splits/splits_stormy_x2.json \
	  --physical-rain --scaling none --seed 0 --run-name m0_x2_s0

test:
	PYTHONPATH=. .venv/bin/python -m pytest tests/ -q

report:
	PYTHONPATH=. .venv/bin/python -m multistorm.report --run runs/m0_x2_s0

# --- NS-SAFE-SAC v8 ---
diag:
	PYTHONPATH=. .venv/bin/python -m research.diag_semantics | tee runs/diag_report.txt

topology:
	PYTHONPATH=. .venv/bin/python -m research.topology | tee runs/topology_report.txt

onset:
	PYTHONPATH=. .venv/bin/python -m research.onset_parallel \
	  --rain-dir data/useful/rain_real_full \
	  --events data/useful/rain_real_full/events.csv \
	  --min-year 2010 --workers 4 --out runs/onset_table.csv

scenarios:
	PYTHONPATH=. .venv/bin/python -m research.build_scaled_storms \
	  --rain-dir data/useful/rain_real_full \
	  --events data/useful/rain_real_full/events.csv \
	  --onset runs/onset_table.csv --atlas configs/atlas14_detroit_city_ams_mm.csv \
	  --out data/useful/rain_scenarios \
	  --val-years 2021,2022 --test-years 2023,2024,2025,2026 \
	  --min-year 2010 \
	  --ladder-train 5,10,25,50,100 --ladder-test 200,500,1000 \
	  --mults 1,1.5,2,3 --flat-factors 2

train-v8-smoke:
	PYTHONPATH=. .venv/bin/python -m multistorm.train_multi \
	  --rain-dir data/useful/rain_scenarios \
	  --split-manifest data/useful/rain_scenarios/splits.json \
	  --variant v8 --diet D2_ladder100 --physical-rain --real-only \
	  --episodes 20 --warmup-steps 500 --eval-every 10 --updates-per-step 1.0 \
	  --seed 0 --run-name v8_smoke_s0

preflight:
	PYTHONPATH=. .venv/bin/python -c "from research.readiness import assert_hydraulic_training_ready; assert_hydraulic_training_ready(); print('hydraulic gate: PASS')"

train-v8-pilot: preflight
	PYTHONPATH=. .venv/bin/python -m multistorm.train_multi \
	  --rain-dir data/useful/rain_scenarios \
	  --split-manifest data/useful/rain_scenarios/splits.json \
	  --variant v8 --diet D2_ladder100 --physical-rain --real-only \
	  --theta-path runs/theta.json --episodes 300 --warmup-steps 2000 \
	  --eval-every 25 --updates-per-step 0.25 --seed 0 --run-name v8_pilot_s0

eval-v8-test:
	PYTHONPATH=. .venv/bin/python -m multistorm.evaluate_checkpoint \
	  --run runs/v8_pilot_s0 --splits test --protocol-tag protocol-v1 --repeat-check
