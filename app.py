"""
Leverage Return Calculator 槓桿回報計算器
Covered Call ETF leveraged DCA scenario analysis (based on 2802.HK analysis).

Math model (matches 2802.HK_scenario_analysis.md):
  - Monthly dividend rate  y = div_yield / 12          (simple monthly)
  - Monthly appreciation   g = (1 + appr)^(1/12) - 1   (geometric monthly)
  - Each month: contribution added first, then growth (annuity-due)
        base = P + installment
        div  = base * (1+g) * y      (distribution on post-appreciation value)
        DRP:  P' = base * (1+g) * (1+y)
        Cash: P' = base * (1+g);  dividends accumulate as cash
  - Loan is revolving, interest-only: interest = loan * rate / 12 per month.
    Interest affects cash flow only; it is NOT deducted from portfolio/ROI
    (per source analysis - see Table 3 note).
  - Own Capital = initial own capital + installment * months
  - Equity = Portfolio + Cash dividends - Loan
  - Profit = Equity - Own Capital ;  ROI = Profit / Own Capital
  - Ann ROI = (1 + ROI)^(12/months) - 1

Run:  streamlit run app.py   (or: python3 -m streamlit run app.py)
"""

import numpy as np
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------- core engine


def simulate(initial: float, loan: float, installment: float, months: int,
             div_yield: float, appr: float, loan_rate: float,
             reinvest: bool = True) -> pd.DataFrame:
    """Month-by-month simulation. Returns one row per month."""
    y = div_yield / 12.0
    g = (1.0 + appr) ** (1.0 / 12.0) - 1.0
    monthly_interest = loan * loan_rate / 12.0

    P = float(initial) + float(loan)   # loan proceeds are invested too
    cash = 0.0
    cum_div = 0.0
    rows = []
    for m in range(1, months + 1):
        base = P + installment
        div = base * (1.0 + g) * y   # distribution on post-appreciation value
        cum_div += div
        if reinvest:
            P = base * (1.0 + g) * (1.0 + y)
        else:
            P = base * (1.0 + g)
            cash += div
        own = initial + installment * m
        equity = P + cash - loan
        profit = equity - own
        roi = profit / own if own > 0 else 0.0
        rows.append({
            "month": m,
            "portfolio": P,
            "cash_div": cash,
            "div": div,
            "cum_div": cum_div,
            "interest": monthly_interest,
            "cum_interest": monthly_interest * m,
            "ltv": loan / P if P > 0 else 0.0,
            "own": own,
            "equity": equity,
            "profit": profit,
            "roi": roi,
            "ann_roi": (1.0 + roi) ** (12.0 / m) - 1.0 if own > 0 else 0.0,
        })
    return pd.DataFrame(rows)


def end_state(initial, loan, installment, months, div_yield, appr, loan_rate,
              reinvest=True) -> dict:
    df = simulate(initial, loan, installment, months, div_yield, appr,
                  loan_rate, reinvest)
    return df.iloc[-1].to_dict()


def ltv_milestone(df: pd.DataFrame, threshold: float):
    """First month where LTV <= threshold, else None."""
    hit = df[df["ltv"] <= threshold]
    return int(hit.iloc[0]["month"]) if not hit.empty else None


def loan_breakeven(initial, loan, installment, div_yield, appr, loan_rate,
                   reinvest=True, max_months=240):
    """First month where cumulative dividends >= loan principal + cum interest."""
    if loan <= 0:
        return None
    df = simulate(initial, loan, installment, max_months, div_yield, appr,
                  loan_rate, reinvest)
    hit = df[df["cum_div"] >= loan + df["cum_interest"]]
    return int(hit.iloc[0]["month"]) if not hit.empty else None


# ------------------------------------------------------------- formatting


def k(v):        return f"${v / 1000:,.0f}k"
def pct(v):      return f"{v * 100:.1f}%"
def hkd(v):      return f"${v:,.0f}"
def mo(v):       return f"M{v}" if v is not None else "N/A"


# ------------------------------------------------------------------ layout

st.set_page_config(page_title="Leverage Return Calculator",
                   page_icon="📈", layout="wide")

st.title("📈 Leverage Return Calculator 槓桿回報計算器")
st.caption("Covered Call ETF leveraged DCA scenario analysis "
           "槓桿月供情境分析 — based on 2802.HK scenario analysis (2026-07-17)")

# ---- live data fetch (Yahoo Finance via yfinance, no API key needed)

st.session_state.setdefault("price", 7.27)
st.session_state.setdefault("dist", 0.15)


def fetch_market_data():
    """Fetch last close + most recent dividend for the ticker."""
    ticker = st.session_state.get("asset", "2802.HK").strip()
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            raise ValueError(f"No price data for '{ticker}' "
                             f"(check ticker format, e.g. 2802.HK)")
        st.session_state.price = round(float(hist["Close"].iloc[-1]), 2)
        divs = t.dividends
        if len(divs):
            st.session_state.dist = round(float(divs.iloc[-1]), 3)
            div_date = divs.index[-1].strftime("%Y-%m-%d")
        else:
            div_date = None
        st.session_state.fetch_msg = ("ok", ticker, div_date)
    except Exception as ex:
        st.session_state.fetch_msg = ("err", str(ex), None)


# ---- sidebar inputs
with st.sidebar:
    st.header("⚙️ Parameters 參數")
    asset = st.text_input("Asset 資產 (Yahoo ticker)", value="2802.HK",
                          key="asset")
    st.button("📡 Fetch real data 抓取實時數據", on_click=fetch_market_data,
              width="stretch")
    if "fetch_msg" in st.session_state:
        status, info, div_date = st.session_state.fetch_msg
        if status == "ok":
            st.success(f"{info}: price ${st.session_state.price:.2f}"
                       + (f", last dividend ${st.session_state.dist:.3f} "
                          f"({div_date})" if div_date else ", no dividend "
                          "history found 找不到派息記錄"))
        else:
            st.error(f"Fetch failed 抓取失敗: {info}")
    price = st.number_input("Current price 現價 (HKD)", min_value=0.01,
                            step=0.01, format="%.2f", key="price")
    dist = st.number_input("Monthly distribution 每月派息 (HKD/unit)",
                           min_value=0.0, step=0.01, format="%.3f",
                           key="dist")
    implied = dist * 12 / price if price > 0 else 0.0
    st.caption(f"Implied yield 隱含年息率: **{implied * 100:.1f}%** p.a. "
               f"(= {dist:.2f} × 12 ÷ {price:.2f})")

    st.divider()
    initial = st.number_input("Initial own capital 初始自有資金 (HKD)",
                              min_value=0, value=200_000, step=10_000)
    loan = st.number_input("Loan amount 貸款金額 (HKD)",
                           min_value=0, value=200_000, step=10_000)
    installment = st.slider("Monthly installment 每月月供 (HKD)",
                            10_000, 100_000, 30_000, step=1_000)
    loan_rate = st.slider("Loan rate 貸款年利率 (% p.a.)",
                          0.0, 10.0, 5.0, step=0.25) / 100.0
    st.divider()
    yield_src = st.radio(
        "Dividend yield source 股息率來源",
        ["Manual slider 手動設定",
         "Implied 由現價/派息推算"],
        index=0,
        help="Manual: use the slider below (md baseline = 25%). "
             "Implied: yield = monthly distribution × 12 ÷ current price, "
             "recalculates when you change price or distribution.")
    if yield_src.startswith("Implied"):
        div_yield = implied
        st.caption(f"Using implied yield 使用隱含息率: "
                   f"**{implied * 100:.1f}%** p.a.")
    else:
        div_yield = st.slider("Dividend yield 股息率 (% p.a.)",
                              5.0, 30.0, 25.0, step=0.5) / 100.0
    appr = st.slider("Asset appreciation 資產升值 (% p.a.)",
                     -10.0, 10.0, 0.0, step=0.5) / 100.0
    months = st.slider("Time horizon 投資期 (months)", 6, 60, 36, step=1)
    treatment = st.radio("Dividend treatment 股息處理",
                         ["Reinvest (DRP) 再投資", "Cash 現金收取"], index=0)
    reinvest = treatment.startswith("Reinvest")

start_port = initial + loan
start_ltv = loan / start_port if start_port > 0 else 0.0

# structures: A pure DCA, B half size, C full size (as in source analysis)
structures = [
    (f"A) Pure DCA {hkd(installment)}/mo", 0, 0),
    (f"B) {k(initial / 2)} own + {k(loan / 2)} loan", initial / 2, loan / 2),
    (f"C) {k(initial)} own + {k(loan)} loan", initial, loan),
]

# main scenario (structure C, user inputs)
main = end_state(initial, loan, installment, months, div_yield, appr,
                 loan_rate, reinvest)
main_df = simulate(initial, loan, installment, months, div_yield, appr,
                   loan_rate, reinvest)

# ------------------------------------------------------- quick summary

st.subheader("⚡ Quick Summary 快速摘要")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("End Portfolio 期末組合", k(main["portfolio"] + main["cash_div"]))
c2.metric("Equity 淨值", k(main["equity"]))
c3.metric("ROI 總回報率", pct(main["roi"]))
c4.metric("Ann ROI 年化回報率", pct(main["ann_roi"]))
c5.metric("End LTV 期末槓桿比率", pct(main["ltv"]))
st.caption(f"{asset} · {months} months · dividend yield {pct(div_yield)} p.a. · "
           f"appreciation {pct(appr)} p.a. · loan rate {pct(loan_rate)} p.a. · "
           f"{'DRP 再投資' if reinvest else 'Cash 現金'} · "
           f"Own capital invested 累計自有資金 {k(main['own'])} · "
           f"Total interest 總利息 {k(main['cum_interest'])}")

# ------------------------------------------------- table 1: structure comparison

st.subheader("1️⃣ Structure Comparison 結構比較")
rows = []
for name, ini, ln in structures:
    e = end_state(ini, ln, installment, months, div_yield, appr, loan_rate,
                  reinvest)
    sp = ini + ln
    rows.append({
        "Structure 結構": name,
        "Initial": k(ini), "Loan": k(ln), "Start Port": k(sp),
        "Start LTV": pct(ln / sp) if sp > 0 else "0.0%",
        "End Port": k(e["portfolio"] + e["cash_div"]),
        "End LTV": pct(e["ltv"]),
        "Equity": k(e["equity"]), "Profit": k(e["profit"]),
        "ROI": pct(e["roi"]), "Ann ROI": pct(e["ann_roi"]),
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ------------------------------------------------- table 2: appreciation sens.

APPRS = [-0.10, -0.05, 0.0, 0.05, 0.10]

st.subheader("2️⃣ Appreciation Sensitivity 升值敏感度")
rows = []
for name, ini, ln in structures:
    for a in APPRS:
        e = end_state(ini, ln, installment, months, div_yield, a, loan_rate,
                      reinvest)
        rows.append({
            "Structure 結構": name, "Appr": f"{a * 100:+.0f}%",
            "End Port": k(e["portfolio"] + e["cash_div"]),
            "End LTV": pct(e["ltv"]), "Equity": k(e["equity"]),
            "Profit": k(e["profit"]), "ROI": pct(e["roi"]),
        })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ------------------------------------------------- table 3: loan rate sens.

st.subheader("3️⃣ Loan Rate Sensitivity 貸款利率敏感度")
rows = []
for r in [0.0, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10]:
    e = end_state(initial, loan, installment, months, div_yield, appr, r,
                  reinvest)
    rows.append({
        "Rate": f"{r * 100:.0f}%",
        "End Port": k(e["portfolio"] + e["cash_div"]),
        "Equity": k(e["equity"]), "Profit": k(e["profit"]),
        "ROI": pct(e["roi"]), "Total Int": k(e["cum_interest"]),
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption("Loan is interest-only and revolving — interest affects cash flow, "
           "not portfolio value (dividends reinvested). "
           "貸款為循環式只還息:利息只影響現金流,不影響組合價值。")

# ------------------------------------------------- table 4: dividend yield sens.

st.subheader("4️⃣ Dividend Yield Sensitivity 股息率敏感度")
rows = []
for dy in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
    e = end_state(initial, loan, installment, months, dy, appr, loan_rate,
                  reinvest)
    rows.append({
        "Div Yield": f"{dy * 100:.0f}%",
        "End Port": k(e["portfolio"] + e["cash_div"]),
        "End LTV": pct(e["ltv"]), "Equity": k(e["equity"]),
        "Profit": k(e["profit"]), "ROI": pct(e["roi"]),
        "Ann ROI": pct(e["ann_roi"]),
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ------------------------------------------------- table 5: time horizon

st.subheader("5️⃣ Time Horizon Projection 投資期預測")
horizons = sorted({6, 12, 18, 24, 30, 36, 48, 60, months})
rows = []
for h in horizons:
    e = end_state(initial, loan, installment, h, div_yield, appr, loan_rate,
                  reinvest)
    rows.append({
        "Horizon": f"{h}mo",
        "End Port": k(e["portfolio"] + e["cash_div"]),
        "End LTV": pct(e["ltv"]), "Equity": k(e["equity"]),
        "Own Capital": k(e["own"]), "Profit": k(e["profit"]),
        "ROI": pct(e["roi"]), "Ann ROI": pct(e["ann_roi"]),
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ------------------------------------------------- table 6: LTV milestones

st.subheader("6️⃣ LTV Milestone Timeline 槓桿比率里程碑")
rows = []
for name, ini, ln in structures:
    sp = ini + ln
    if ln <= 0:
        rows.append({"Structure 結構": name, "Start LTV": "0.0%",
                     "LTV≤30%": "N/A", "LTV≤20%": "N/A",
                     "LTV≤10%": "N/A", "LTV≤5%": "N/A", "End LTV": "0.0%"})
        continue
    df = simulate(ini, ln, installment, months, div_yield, appr, loan_rate,
                  reinvest)
    rows.append({
        "Structure 結構": name,
        "Start LTV": pct(ln / sp),
        "LTV≤30%": mo(ltv_milestone(df, 0.30)),
        "LTV≤20%": mo(ltv_milestone(df, 0.20)),
        "LTV≤10%": mo(ltv_milestone(df, 0.10)),
        "LTV≤5%": mo(ltv_milestone(df, 0.05)),
        "End LTV": pct(df.iloc[-1]["ltv"]),
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption("N/A = not reached within horizon 投資期內未達到")

# ------------------------------------------------- table 7: loan breakeven

st.subheader("7️⃣ Loan Breakeven Analysis 貸款回本分析")
st.caption("Months until cumulative dividends can repay full loan principal "
           "+ interest 累計股息足以償還全部貸款本金及利息所需月數")
rows = []
for name, ini, ln in structures[1:]:
    row = {"Structure 結構": name}
    for a in APPRS:
        row[f"{a * 100:+.0f}%"] = mo(loan_breakeven(
            ini, ln, installment, div_yield, a, loan_rate, reinvest))
    rows.append(row)
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ------------------------------------------------- table 8: monthly cash flow

st.subheader("8️⃣ Monthly Cash Flow Timeline 每月現金流")
st.caption(f"Out-of-pocket 每月自付 = {hkd(installment)} DCA installment "
           f"(buys more units 用於買入資產) + "
           f"{hkd(loan * loan_rate / 12)} loan interest 貸款利息. "
           "Net CF = dividend − installment − interest, a hypothetical view "
           "if dividends were taken as cash 假設股息以現金收取時的淨現金流.")
show_months = [m for m in range(1, 13) if m <= months] + \
              [m for m in range(18, months + 1, 6)]
show_months = sorted(set(show_months + [months]))
rows = []
for m in show_months:
    r = main_df.iloc[m - 1]
    cash_out = installment + r["interest"]
    rows.append({
        "Mo": m,
        "Portfolio": k(r["portfolio"] + r["cash_div"]),
        "LTV": pct(r["ltv"]),
        "Div/mo": f"${r['div'] / 1000:,.1f}k",
        "Interest": hkd(r["interest"]),
        "Out-of-Pocket 自付": f"-{hkd(cash_out)}",
        "Net CF (cash div)": f"{'+' if r['div'] - cash_out >= 0 else ''}"
                             f"{hkd(r['div'] - cash_out)}",
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
be = main_df[main_df["div"] >= installment + main_df["interest"]]
if not be.empty:
    st.caption(f"✅ Cash flow turns positive at ~Month "
               f"{int(be.iloc[0]['month'])} 現金流於約第 "
               f"{int(be.iloc[0]['month'])} 個月轉正(股息超過每月成本)")
else:
    st.caption("⚠️ Cash flow does not turn positive within horizon "
               "投資期內現金流未轉正")

# ------------------------------------------------- table 9: matrix heatmap

st.subheader("9️⃣ Appreciation × Dividend Yield Matrix 升值 × 股息率矩陣")
st.caption(f"Values = {months}-month ROI (%) — structure C, "
           f"loan rate {pct(loan_rate)}")
yields = [0.10, 0.15, 0.20, 0.25, 0.30]
matrix = pd.DataFrame(
    [[end_state(initial, loan, installment, months, dy, a, loan_rate,
                reinvest)["roi"] * 100 for a in APPRS] for dy in yields],
    index=[f"{dy * 100:.0f}%" for dy in yields],
    columns=[f"{a * 100:+.0f}%" for a in APPRS],
)
matrix.index.name = "Div \\ Appr"
st.dataframe(
    matrix.style.background_gradient(cmap="RdYlGn", axis=None)
          .format("{:.1f}%"),
    width="stretch",
)

# ------------------------------------------------- caveats

st.divider()
st.subheader("⚠️ Assumptions & Caveats 假設與注意事項")
st.markdown(f"""
- Forward yield {pct(div_yield)} based on ${dist:.2f}/unit vs ${price:.2f} —
  may vary monthly 遠期息率按每月派息推算,實際每月可能變動
- {asset} is a covered call ETF; high yield = option premium, not earnings
  growth 高息來自期權金,並非盈利增長
- Covered call ETFs sacrifice upside; NAV may erode in rising markets
  備兌認購 ETF 犧牲上升空間,升市中 NAV 可能受損
- Consider **-3% to -5% annual NAV erosion** as realistic base case
  建議以每年 -3% 至 -5% NAV 侵蝕作為現實基準情境
- Loan rate {pct(loan_rate)} assumed; actual margin 4–8% depending on broker
  實際孖展利率視乎券商約 4–8%
- No transaction costs, no taxes, no withholding assumed
  未計交易成本、稅項及預扣稅
- Monthly compounding throughout 全程按月複利
- Loan is revolving and interest-only; principal unchanged unless repaid with
  dividends 貸款為循環式只還息,本金不變(除非以股息償還)
- **This is not investment advice 本工具僅供情境模擬,不構成投資建議**
""")
