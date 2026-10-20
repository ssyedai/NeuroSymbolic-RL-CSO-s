from research.prepare_coupled_endpoint import patch_source


def test_coupled_endpoint_patch_keeps_laws_and_adds_off_diagonals():
    source = (
        "runs/hydraulic_validation_20261020/integral_storage_source/"
        "src/solver/dynwave.c"
    )
    before = open(source, encoding="utf-8").read()
    after = patch_source(before)
    assert "applyCoupledEndpointCorrection(dt);" in after
    assert "derivative1 = Link[j].dqdh;" in after
    assert "derivative2 = -Link[j].dqdh;" in after
    assert "CoupledMatrix[r1*count+r2] += alpha * derivative2;" in after
    assert "CoupledMatrix[r2*count+r1] -= alpha * derivative1;" in after
    assert "candidate = DepthBeforeSolve[i] + damping * CoupledRhs[r1];" in after
    assert "qNew = link_getInflow(i);" in after
    assert "MAX_TRIALS" not in after  # option name is not hard-coded by the patch
    assert before.count("link_getInflow(i)") == after.count("link_getInflow(i)")


def test_coupled_endpoint_patch_fails_on_wrong_lineage():
    try:
        patch_source("not dynwave")
    except ValueError:
        pass
    else:
        raise AssertionError("patch must reject an unexpected source lineage")
