"""Engine verification against the original 2802.HK scenario analysis tables.

The engine lives at the top of app.py (kept single-file by design); we exec
the section above the Streamlit layout to get the pure functions.
Run: python3 -m pytest tests/ -v
"""

from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app.py"
_src = APP.read_text().split(
    "# ------------------------------------------------------------------ layout")[0]
ns: dict = {}
exec(_src, ns)
simulate = ns["simulate"]
end_state = ns["end_state"]
ltv_milestone = ns["ltv_milestone"]
loan_breakeven = ns["loan_breakeven"]

K = 1000
BASE = dict(installment=30 * K, div_yield=0.25, appr=0.0, loan_rate=0.05)


def C(months=36, **over):
    p = {**BASE, "initial": 200 * K, "loan": 200 * K, "months": months, **over}
    return end_state(**p)


# ---- Table 1: structure comparison (0% appr, 36mo)

@pytest.mark.parametrize("ini,loan,port,roi,ann", [
    (0, 0, 1618, 49.8, 14.4),
    (100 * K, 100 * K, 2038, 64.3, 18.0),
    (200 * K, 200 * K, 2458, 76.4, 20.8),
])
def test_table1(ini, loan, port, roi, ann):
    e = end_state(ini, loan, 30 * K, 36, 0.25, 0.0, 0.05)
    assert e["portfolio"] / K == pytest.approx(port, abs=0.6)
    assert e["roi"] * 100 == pytest.approx(roi, abs=0.1)
    assert e["ann_roi"] * 100 == pytest.approx(ann, abs=0.1)


# ---- Table 2: appreciation sensitivity (structure C)

@pytest.mark.parametrize("appr,port,roi", [
    (-0.10, 1967, 38.1), (-0.05, 2203, 56.5), (0.0, 2458, 76.4),
    (0.05, 2734, 98.0), (0.10, 3032, 121.3),
])
def test_table2(appr, port, roi):
    e = C(appr=appr)
    assert e["portfolio"] / K == pytest.approx(port, abs=0.6)
    assert e["roi"] * 100 == pytest.approx(roi, abs=0.1)


# ---- Table 3: loan rate does not change ROI (interest-only, reported separately)

@pytest.mark.parametrize("rate,tot_int", [(0.0, 0), (0.05, 30), (0.10, 60)])
def test_table3(rate, tot_int):
    e = C(loan_rate=rate)
    assert e["roi"] * 100 == pytest.approx(76.4, abs=0.1)
    assert e["cum_interest"] / K == pytest.approx(tot_int, abs=0.1)


# ---- Table 4: dividend yield sensitivity

@pytest.mark.parametrize("dy,port,roi,ann", [
    (0.05, 1632, 11.9, 3.8), (0.10, 1803, 25.2, 7.8), (0.15, 1996, 40.3, 12.0),
    (0.20, 2213, 57.3, 16.3), (0.25, 2458, 76.4, 20.8), (0.30, 2735, 98.0, 25.6),
])
def test_table4(dy, port, roi, ann):
    e = C(div_yield=dy)
    assert e["portfolio"] / K == pytest.approx(port, abs=0.6)
    assert e["roi"] * 100 == pytest.approx(roi, abs=0.1)
    assert e["ann_roi"] * 100 == pytest.approx(ann, abs=0.1)


# ---- Table 5: time horizon

@pytest.mark.parametrize("mo,port,eq,prof,roi,ann", [
    (6, 646, 446, 66, 17.4, 37.9), (12, 925, 725, 165, 29.5, 29.5),
    (18, 1240, 1040, 300, 40.6, 25.5), (24, 1597, 1397, 477, 51.9, 23.2),
    (30, 2001, 1801, 701, 63.8, 21.8), (36, 2458, 2258, 978, 76.4, 20.8),
    (48, 3561, 3361, 1721, 105.0, 19.7), (60, 4974, 4774, 2774, 138.7, 19.0),
])
def test_table5(mo, port, eq, prof, roi, ann):
    e = C(months=mo)
    assert e["portfolio"] / K == pytest.approx(port, abs=0.6)
    assert e["equity"] / K == pytest.approx(eq, abs=0.6)
    assert e["profit"] / K == pytest.approx(prof, abs=0.6)
    assert e["roi"] * 100 == pytest.approx(roi, abs=0.1)
    assert e["ann_roi"] * 100 == pytest.approx(ann, abs=0.1)


# ---- Table 6: LTV milestones

@pytest.mark.parametrize("size,th,month", [
    (100, 0.30, 4), (100, 0.20, 9), (100, 0.10, 19), (100, 0.05, 36),
    (200, 0.30, 7), (200, 0.20, 14), (200, 0.10, 30),
])
def test_table6(size, th, month):
    df = simulate(size * K, size * K, 30 * K, 36, 0.25, 0.0, 0.05)
    assert ltv_milestone(df, th) == month


def test_table6_c_5pct_not_reached():
    df = simulate(200 * K, 200 * K, 30 * K, 36, 0.25, 0.0, 0.05)
    assert ltv_milestone(df, 0.05) is None


# ---- Table 7: loan breakeven
# Note: source md shows M12 for B @ -10%, but that is inconsistent with its own
# definition (cum dividends at M12 fall short of principal + interest); the
# strict definition yields M13. All other cells match the source.

@pytest.mark.parametrize("size,appr,month", [
    (100, -0.10, 13), (100, -0.05, 12), (100, 0.0, 12), (100, 0.05, 12),
    (100, 0.10, 12),
    (200, -0.10, 15), (200, -0.05, 15), (200, 0.0, 15), (200, 0.05, 14),
    (200, 0.10, 14),
])
def test_table7(size, appr, month):
    assert loan_breakeven(size * K, size * K, 30 * K, 0.25, appr, 0.05) == month


# ---- Table 8: monthly cash flow spot checks

def test_table8():
    df = simulate(200 * K, 200 * K, 30 * K, 36, 0.25, 0.0, 0.05)
    r1, r24, r36 = df.iloc[0], df.iloc[23], df.iloc[35]
    assert r1["portfolio"] / K == pytest.approx(439, abs=0.6)
    assert r1["div"] == pytest.approx(8958, abs=5)
    assert r1["div"] - 30_000 - r1["interest"] == pytest.approx(-21_875, abs=5)
    assert r24["div"] - 30_000 - r24["interest"] == pytest.approx(1_765, abs=5)
    assert r36["div"] - 30_000 - r36["interest"] == pytest.approx(19_338, abs=5)


# ---- Table 9: matrix corners

@pytest.mark.parametrize("dy,appr,roi", [
    (0.10, -0.10, -1.3), (0.10, 0.10, 56.0),
    (0.30, -0.10, 54.6), (0.30, 0.10, 148.9), (0.25, 0.0, 76.4),
])
def test_table9(dy, appr, roi):
    e = C(div_yield=dy, appr=appr)
    assert e["roi"] * 100 == pytest.approx(roi, abs=0.1)


# ---- cash (non-DRP) mode invariants

def test_cash_mode():
    e = end_state(200 * K, 200 * K, 30 * K, 36, 0.25, 0.0, 0.05,
                  reinvest=False)
    # no reinvestment, 0% appr: portfolio = contributions + initial only
    assert e["portfolio"] == pytest.approx(400 * K + 36 * 30 * K, rel=1e-9)
    # equity includes accumulated cash dividends
    assert e["cash_div"] > 0
    assert e["equity"] == pytest.approx(
        e["portfolio"] + e["cash_div"] - 200 * K, rel=1e-9)
