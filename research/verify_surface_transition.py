"""Query real compiled conduit geometry on both sides of each branch boundary."""
import ctypes as C
import hashlib
import json
from pathlib import Path


def main():
    base=Path('runs/hydraulic_validation_20261019')
    out=base/'surface_boundary_checks';out.mkdir(exist_ok=False)
    source=base/'network_balance_bypass/native_0.5.inp'
    cfg=json.loads((source.parent/'run_config.json').read_text())
    assert cfg['split']=='train'
    cfg.update(purpose='Compiled forward-conduit boundary continuity; initialization only, no hydraulic advance',
               expected_runs=2,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),engines={})
    data={}
    for variant in ('surface_original','surface_transition'):
        dll=base/(variant+'_build')/'src/solver/Release/swmm5.dll'
        cfg['engines'][variant]=hashlib.sha256(dll.read_bytes()).hexdigest()
        lib=C.CDLL(str(dll.resolve()))
        lib.swmm_open.argtypes=[C.c_char_p]*3;lib.swmm_start.argtypes=[C.c_int]
        lib.swmm_getIndex.argtypes=[C.c_int,C.c_char_p]
        lib.diag_surface.argtypes=[C.c_int,C.c_double,C.c_double,C.c_double,C.POINTER(C.c_double)]
        def call(fn,*args):
            if getattr(lib,fn)(*args)!=0:raise RuntimeError(fn)
        call('swmm_open',str(source.resolve()).encode(),str((out/(variant+'.rpt')).resolve()).encode(),str((out/(variant+'.out')).resolve()).encode())
        try:
            call('swmm_start',0)
            try:
                rows=[]
                for name,q,y1 in [('35171',80.064523,2.697257),('35271',237.277757,4.895478)]:
                    idx=lib.swmm_getIndex(3,name.encode());assert idx>=0
                    def query(qval,y2):
                        values=(C.c_double*7)();call('diag_surface',idx,qval,y1,y2,values)
                        return list(values)
                    initial=query(q,3);lo,hi=sorted(initial[:2]);assert hi-lo>1e-4
                    for boundary,centre in [('lower',lo),('upper',hi)]:
                        left=query(q,centre-1e-7);right=query(q,centre+1e-7)
                        rows.append(dict(link=name,boundary=boundary,lower_depth=lo,upper_depth=hi,
                            left=left,right=right,max_area_jump_ft2=max(abs(left[i]-right[i]) for i in (2,3))))
                    rows.append(dict(link=name,control=True,below=query(q,lo-.01),above=query(q,hi+.01),reverse=query(-q,(lo+hi)/2)))
                data[variant]=rows
            finally:call('swmm_end')
        finally:call('swmm_close')
    checks=[]
    for old,new in zip(data['surface_original'],data['surface_transition']):
        if new.get('control'):
            checks.append(all(old[k]==new[k] for k in ('below','above','reverse')))
        else:checks.append(new['max_area_jump_ft2']<.1 and old['max_area_jump_ft2']>1)
    result=dict(passed=all(checks),checks=checks,data=data,
        scope='Two actual incident conduits; forward branch boundary continuity and unchanged outside/reverse controls. Not full hydraulic validation.')
    (out/'run_config.json').write_text(json.dumps(cfg,indent=2))
    (out/'results.json').write_text(json.dumps(result,indent=2))
    (out/'runner_source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(result,indent=2))
    if not all(checks):raise RuntimeError('Surface transition verification failed')


if __name__=='__main__':main()
