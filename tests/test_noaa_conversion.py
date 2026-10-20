from pathlib import Path
import pytest
from research.verify_noaa_table import parse_response


def test_official_axes_and_confidence_bounds():
    root=Path('runs/noaa_verification_20261017')
    if not root.exists(): pytest.skip('Saved official evidence not bundled')
    text=(root/'official_response.txt').read_text()
    html=(root/'official_page.html').read_text()
    js=(root/'code_gen_16.js').read_text()
    _,duration,years,data=parse_response(text,html,js)
    assert duration[7]==360 and years[-1]==1000
    assert data['quantiles'][7,-1]==151
    assert data['lower'][7,-1]==103 and data['upper'][7,-1]==200
    with pytest.raises(ValueError):parse_response(text.replace("unit = 'metric'","unit = 'english'"),html,js)
    with pytest.raises(ValueError):parse_response(text,html.replace('id="7-0"','id="8-0"'),js)
