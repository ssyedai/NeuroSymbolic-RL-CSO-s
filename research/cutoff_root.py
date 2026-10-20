"""Branch-existence certificate for the isolated constant-area storage step."""
import argparse
import hashlib
import json
from pathlib import Path
import math
import pandas as pd

AREA=24231.285
CUTOFF=.0001
COEFFICIENT=.4*7*14.14*math.sqrt(64.4)


def classify(b,alpha):
    if not math.isfinite(b) or not math.isfinite(alpha) or alpha<=0:
        raise ValueError("Finite target and positive step coefficient required")
    jump=alpha*COEFFICIENT*math.sqrt(CUTOFF)
    if abs(b)<=CUTOFF:
        return "zero_branch"
    if abs(b)>CUTOFF+jump:
        return "flowing_branch"
    return "no_exact_root"


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--attempts',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    data=pd.read_csv(args.attempts,float_precision='round_trip')
    old=data[data.accepted].iloc[-1]
    trial=data.iloc[-1]
    if trial.accepted or abs(old.seconds+trial['dt']-trial.seconds)>1e-7:
        raise ValueError("Expected rejected successor to last accepted state")
    alpha=trial['dt']/(2*AREA)
    b=old.head_s-trial.head_o-alpha*old.flow
    result=dict(classification=classify(b,alpha),area_ft2=AREA,cutoff_ft=CUTOFF,
        dt_s=trial['dt'],old_head_ft=old.head_s,new_tail_ft=trial.head_o,old_flow_cfs=old.flow,
        alpha=alpha,b_ft=b,reverse_branch_limit_ft=-CUTOFF-alpha*COEFFICIENT*math.sqrt(CUTOFF),
        zero_branch_limit_ft=-CUTOFF,
        zero_branch_nearest_balance_residual_ft3=AREA*(-CUTOFF-b),
        reverse_branch_limiting_balance_residual_ft3=AREA*(-CUTOFF-alpha*COEFFICIENT*math.sqrt(CUTOFF)-b),
        equation="g + dt/(2*A)*q(g) = H_old - H_tail_new - dt/(2*A)*q_old",
        assumptions="one constant-area storage, no lateral inflow/loss, fully submerged open orifice, trapezoidal continuity",
        input_sha256=hashlib.sha256(args.attempts.read_bytes()).hexdigest())
    args.out.mkdir(parents=True,exist_ok=False)
    (args.out/'certificate.json').write_text(json.dumps(result,indent=2))
    (args.out/'source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
