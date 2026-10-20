from pathlib import Path

import pytest

from research.prepare_predicate_trace import patch_source


def _minimal_source() -> str:
    return """static TXnode* Xnode;                  // extended nodal information
void dynwave_init(void) {
    VariableStep = 0.0;
}
void dynwave_close(void) {
    FREE(Xnode);
}
int dynwave_execute(double tStep) {
    initRoutingStep();
    return 0;
}
"""


def test_patch_adds_read_only_predicate_trace_once():
    patched = patch_source(_minimal_source())
    assert patched.count("static FILE *PredicateFile") == 1
    assert 'project_findObject(NODE, "35440")' in patched
    assert 'project_findObject(LINK, "35281_A")' in patched
    assert 'project_findObject(LINK, "35281_B")' in patched
    assert "link_getInflow" not in patched
    assert "Node[PredicateNode].newDepth" in patched
    assert "Link[PredicateConduit].newFlow" in patched


def test_patch_rejects_reapplication():
    patched = patch_source(_minimal_source())
    with pytest.raises(ValueError, match="already present"):
        patch_source(patched)
