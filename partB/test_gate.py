import pytest
from partB.eta_mlflow import decide
PROD=dict(mae=10,mae_rush=10,mae_rain=10,p95_ms=2)
@pytest.mark.parametrize('change,expected',[(dict(),True),(dict(mae=9.7),True),(dict(mae=9.70001),False),(dict(mae=9.69999),True),(dict(p95_ms=10),True),(dict(p95_ms=10.0001),False),(dict(mae_rush=10.5),True),(dict(mae_rush=10.5001),False),(dict(mae_rain=10.5),True),(dict(mae_rain=10.5001),False)])
def test_decisions(change,expected):
    cand=dict(mae=9,mae_rush=9,mae_rain=9,p95_ms=1); cand.update(change)
    assert decide(PROD,cand)['promote'] is expected
