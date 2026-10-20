"""Minimal binding for isolated verification against a separately built DLL.

Signatures/enums/structure verified against OWA 27dc699 toolkit headers.
Never changes PySWMM's installed engine. One open simulation at a time.
"""
import ctypes as C
import time


class RoutingTotals(C.Structure):
    _fields_ = [(key, C.c_double) for key in (
        "dwInflow", "wwInflow", "gwInflow", "iiInflow", "exInflow", "flooding",
        "outflow", "evapLoss", "seepLoss", "reacted", "initStorage", "finalStorage", "pctError")]


def run_model(dll_path, path, started, extra_nodes=(), extra_links=()):
    lib = C.CDLL(str(dll_path.resolve()))
    signatures = {
        "swmm_open": [C.c_char_p]*3, "swmm_start": [C.c_int],
        "swmm_step": [C.POINTER(C.c_double)], "swmm_end": [],
        "swmm_report": [], "swmm_close": [], "swmm_getVersion": [],
        "swmm_getIndex": [C.c_int, C.c_char_p],
        "swmm_getNodeResult": [C.c_int, C.c_int, C.POINTER(C.c_double)],
        "swmm_getLinkResult": [C.c_int, C.c_int, C.POINTER(C.c_double)],
        "swmm_getSystemRoutingTotals": [C.POINTER(RoutingTotals)],
        "swmm_getMassBalErr": [C.POINTER(C.c_float)]*3,
    }
    for name, args in signatures.items():
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = args, C.c_int
    def call(name, *args):
        code = getattr(lib, name)(*args)
        if code:
            raise RuntimeError(f"{name} returned error {code}; inspect {path.with_suffix('.rpt')}")
    def result(name, index, field):
        value = C.c_double()
        call(name, index, field, C.byref(value))
        return value.value
    samples = []
    opened = started_engine = False
    try:
        # ASCII-safe workspace on the current host; reject rather than misencode.
        call("swmm_open", *(str(p.resolve()).encode("ascii") for p in
                            (path, path.with_suffix(".rpt"), path.with_suffix(".out"))))
        opened = True
        call("swmm_start", 1)
        started_engine = True
        s, o, w = (lib.swmm_getIndex(kind, name) for kind, name in ((2,b"S"),(2,b"O"),(3,b"W")))
        if min(s, o, w) < 0:
            raise ValueError("This runner supports the isolated S/O/W model only")
        extra_node_ids = [lib.swmm_getIndex(2, name.encode('ascii')) for name in extra_nodes]
        extra_link_ids = [lib.swmm_getIndex(3, name.encode('ascii')) for name in extra_links]
        if any(i < 0 for i in extra_node_ids + extra_link_ids):
            raise ValueError('Unknown extra diagnostic object')
        initial = result("swmm_getNodeResult", s, 3)
        elapsed = C.c_double()
        while True:
            call("swmm_step", C.byref(elapsed))
            if elapsed.value <= 0:
                break
            samples.append((elapsed.value*86400, result("swmm_getNodeResult", s, 6),
                            result("swmm_getNodeResult", o, 6), result("swmm_getLinkResult", w, 0),
                            result("swmm_getNodeResult", s, 3)) +
                           tuple(result('swmm_getNodeResult', i, 6) for i in extra_node_ids) +
                           tuple(result('swmm_getLinkResult', i, 0) for i in extra_link_ids))
            if time.monotonic()-started > 600:
                raise TimeoutError("Isolated verification budget exceeded")
        totals = RoutingTotals()
        call("swmm_getSystemRoutingTotals", C.byref(totals))
        final = dict(outflow_ft3=totals.outflow, inflow_ft3=totals.exInflow,
                     flooding_ft3=totals.flooding, initial_storage_ft3=initial,
                     final_storage_ft3=result("swmm_getNodeResult", s, 3))
        # Preserve full system accounting: node volume alone omits link storage.
        final.update({"system_"+key: getattr(totals, key) for key, _ in RoutingTotals._fields_})
        call("swmm_end")
        started_engine = False
        runoff, routing, quality = C.c_float(), C.c_float(), C.c_float()
        call("swmm_getMassBalErr", C.byref(runoff), C.byref(routing), C.byref(quality))
        final["routing_error_pct"] = routing.value
        call("swmm_report")
        return samples, final
    finally:
        try:
            if started_engine:
                call("swmm_end")
        finally:
            if opened:
                call("swmm_close")
