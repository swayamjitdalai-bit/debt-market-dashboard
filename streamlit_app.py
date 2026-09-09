"""Streamlit Dashboard for Indian Debt & Money Market.

Reads from data/market.db and data/cbrics.csv.
Provides an interactive multi-tab web application compatible with Streamlit Community Cloud.
"""
import datetime as dt
import os
import sqlite3
import pandas as pd
import streamlit as st

from app import db, exports, derive
from app.config import BASE_DIR, DATA_DIR, DB_PATH
from app.sources import cbrics

st.set_page_config(
    page_title="Indian Debt & Money Market Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for polished financial styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .kpi-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-left: 4px solid #1D4ED8;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 12px;
    }
    .kpi-title { font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em; }
    .kpi-value { font-size: 22px; font-weight: 800; color: #0F172A; margin-top: 4px; }
    .deal-log-header {
        background-color: #00B050;
        color: #000000;
        font-size: 22px;
        font-weight: 900;
        text-align: center;
        padding: 10px;
        border-radius: 6px 6px 0 0;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0px;
    }
    .disclaimer-box {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-left: 3px solid #94A3B8;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 12px;
        color: #64748B;
        line-height: 1.5;
        margin-bottom: 18px;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_db_connection():
    if not os.path.exists(DB_PATH):
        return db.init()
    return db.connect()


def load_cbrics_data():
    cbrics_csv = os.path.join(DATA_DIR, "cbrics.csv")
    if not os.path.exists(cbrics_csv):
        return pd.DataFrame()
    try:
        with open(cbrics_csv, "rb") as fh:
            rows = cbrics.parse_current_csv(fh.read())
        df = pd.DataFrame(rows)
        return df
    except Exception:
        try:
            return pd.read_csv(cbrics_csv)
        except Exception:
            return pd.DataFrame()


conn = get_db_connection()

# Sidebar
st.sidebar.title("📈 Debt Market")
st.sidebar.markdown("**Automated Daily Analytics**")
st.sidebar.markdown("---")

nav = st.sidebar.radio(
    "Navigation",
    ["Closing Report", "CBRICS Bond Deals", "CD / CP Secondary", "Market Overview"],
    index=0
)

st.sidebar.markdown("---")
st.sidebar.caption("Data Sources: CCIL F-TRAC, CCIL Money Market, FBIL MIBOR-OIS, NSE CBRICS, Yahoo Finance / FRED.")
st.sidebar.caption("Made by **Finqrate** for **Swayamjit Dalai**.")

# ------------------------------------------------------------- 1. CLOSING REPORT
if nav == "Closing Report":
    st.title("Fixed Income Closing Report")
    st.markdown('<div class="disclaimer-box">Automated end-of-day summary of the Indian debt and money market. CCIL F-TRAC, benchmark G-Sec curve, T-Bills, SDLs, OIS curve, AAA/AA PSU bonds, and Brent crude are refreshed daily after 5:15 PM IST.</div>', unsafe_allow_html=True)

    trade_dates = db.trade_dates(conn)
    report_dates = db.report_dates(conn)
    all_dates = sorted(set(trade_dates) | set(report_dates), reverse=True)

    if not all_dates:
        st.warning("No market data stored yet. Run data ingestion to populate the database.")
    else:
        selected_date = st.selectbox("Select Report Date", all_dates, index=0)
        from app import report as report_mod
        rep = report_mod.full_report(conn, selected_date)

        # Top KPIs
        kpi_cols = st.columns(4)
        fx_val = rep.get("fx", {}).get("close")
        call_val = rep.get("call", {}).get("weighted_avg")
        trep_val = rep.get("trep", {}).get("weighted_avg")
        brent_val = rep.get("brent", {}).get("price_usd")

        with kpi_cols[0]:
            fx_display = f"{fx_val:.4f}" if fx_val else "–"
            st.markdown(f'<div class="kpi-card"><div class="kpi-title">USD / INR</div><div class="kpi-value">{fx_display}</div></div>', unsafe_allow_html=True)
        with kpi_cols[1]:
            call_display = f"{call_val:.4f}%" if call_val else "–"
            st.markdown(f'<div class="kpi-card"><div class="kpi-title">CALL Wtd Avg</div><div class="kpi-value">{call_display}</div></div>', unsafe_allow_html=True)
        with kpi_cols[2]:
            trep_display = f"{trep_val:.4f}%" if trep_val else "–"
            st.markdown(f'<div class="kpi-card"><div class="kpi-title">TREP Wtd Avg</div><div class="kpi-value">{trep_display}</div></div>', unsafe_allow_html=True)
        with kpi_cols[3]:
            brent_display = f"${brent_val:.2f}" if brent_val else "–"
            st.markdown(f'<div class="kpi-card"><div class="kpi-title">Brent Crude</div><div class="kpi-value">{brent_display}</div></div>', unsafe_allow_html=True)

        # Dynamic Sections (Omit any section that has no data)
        for heading, key, _kind, columns in exports.SECTIONS:
            rows = rep.get(key) or []
            if isinstance(rows, dict):
                rows = [rows]
            valid_rows = [r for r in rows if isinstance(r, dict) and any(r.get(f) is not None for _, f, _ in columns)]
            if not valid_rows:
                continue

            st.subheader(heading)
            table_data = []
            for r in valid_rows:
                row_dict = {}
                for col_name, field, spec in columns:
                    val = r.get(field)
                    if val is not None and isinstance(val, (int, float)) and spec:
                        try:
                            val = spec.format(val)
                        except Exception:
                            pass
                    row_dict[col_name] = val if val is not None else "–"
                table_data.append(row_dict)
            st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

        # Brent Oil Section
        if brent_val is not None:
            st.subheader("Brent Oil")
            b_src = rep.get("brent", {}).get("source") or "Automated"
            st.write(f"**Price:** ${brent_val:.2f} USD | **Source:** {b_src}")

        # AI / Desk Commentary
        comm = (rep.get("ai_commentary") or "").strip()
        if comm:
            st.subheader("Closing Commentary")
            st.info(comm)

        # Exports
        st.markdown("---")
        exp_col1, exp_col2, exp_col3 = st.columns(3)
        with exp_col1:
            xlsx_bytes, _, _ = exports.render(rep, "xlsx")
            st.download_button("📥 Export Excel (.xlsx)", xlsx_bytes, f"Closing_Report_{selected_date}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with exp_col2:
            docx_bytes, _, _ = exports.render(rep, "docx")
            st.download_button("📄 Export Word (.docx)", docx_bytes, f"Closing_Report_{selected_date}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        with exp_col3:
            csv_bytes, _, _ = exports.render(rep, "csv")
            st.download_button("📊 Export CSV (.csv)", csv_bytes, f"Closing_Report_{selected_date}.csv", "text/csv")

# ------------------------------------------------------------- 2. CBRICS BOND DEALS
elif nav == "CBRICS Bond Deals":
    st.title("NSE CBRICS Corporate Bond Market Watch")
    st.markdown('<div class="disclaimer-box">Corporate bond deals reported on NSE CBRICS. Shows institutional trades ≥ ₹25 Crore by default in the official Bond Deal Log format.</div>', unsafe_allow_html=True)

    df_bonds = load_cbrics_data()

    if df_bonds.empty:
        st.warning("No CBRICS bond deals data available.")
    else:
        # Controls
        col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
        with col_f1:
            search_query = st.text_input("🔍 Search ISIN or Issuer", "")
        with col_f2:
            min_trade_val = st.selectbox(
                "Minimum Trade Value",
                [25, 0, 50, 100],
                format_func=lambda x: f"Deals ≥ ₹{x} Cr (Default)" if x == 25 else (f"All Deals (≥ ₹{x} Cr)" if x == 0 else f"Deals ≥ ₹{x} Cr"),
                index=0
            )
        with col_f3:
            sec_type = st.selectbox("Security Status", ["All", "Listed", "Unlisted"], index=0)

        # Filtering
        filtered = df_bonds.copy()
        if "trade_value_cr" in filtered.columns:
            filtered = filtered[filtered["trade_value_cr"].fillna(0) >= min_trade_val]
        if sec_type != "All" and "security" in filtered.columns:
            filtered = filtered[filtered["security"].astype(str).str.lower() == sec_type.lower()]
        if search_query:
            q = search_query.lower()
            m_isin = filtered["isin"].astype(str).str.lower().str.contains(q, na=False) if "isin" in filtered.columns else False
            m_iss = filtered["issuer"].astype(str).str.lower().str.contains(q, na=False) if "issuer" in filtered.columns else False
            filtered = filtered[m_isin | m_iss]

        st.markdown(f"**Showing {len(filtered)} deals** (filtered from {len(df_bonds)} total)")

        # Render Table in the requested 7 columns
        cols_to_show = ["deal_date", "isin", "coupon", "issuer", "maturity_date", "yield", "trade_value_cr"]
        existing_cols = [c for c in cols_to_show if c in filtered.columns]
        display_df = filtered[existing_cols].copy()

        # Format columns
        rename_map = {
            "deal_date": "Deal Date",
            "isin": "ISIN",
            "coupon": "Coupon",
            "issuer": "Issuer Name",
            "maturity_date": "Maturity Date",
            "yield": "Yield",
            "trade_value_cr": "Trade Value (Cr.)"
        }
        display_df = display_df.rename(columns=rename_map)

        if "Coupon" in display_df.columns:
            display_df["Coupon"] = display_df["Coupon"].apply(lambda v: f"{float(v):.4f}" if pd.notnull(v) and v != "" else "–")
        if "Yield" in display_df.columns:
            display_df["Yield"] = display_df["Yield"].apply(lambda v: f"{float(v):.4f}" if pd.notnull(v) and v != "" else "–")
        if "Trade Value (Cr.)" in display_df.columns:
            display_df["Trade Value (Cr.)"] = display_df["Trade Value (Cr.)"].apply(lambda v: f"{float(v):.2f}".rstrip('0').rstrip('.') if pd.notnull(v) else "–")

        st.markdown('<div class="deal-log-header">BOND DEAL LOG</div>', unsafe_allow_html=True)
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Excel download
        csv_data = display_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Bond Deals CSV", csv_data, "BOND_DEAL_LOG.csv", "text/csv")

# ------------------------------------------------------------- 3. CD / CP SECONDARY
elif nav == "CD / CP Secondary":
    st.title("CD / CP Secondary Market Analytics")
    st.markdown('<div class="disclaimer-box">Secondary Certificate of Deposit (CD) and Commercial Paper (CP) transaction trends from CCIL F-TRAC.</div>', unsafe_allow_html=True)

    trade_dates = db.trade_dates(conn)
    if not trade_dates:
        st.warning("No trade dates in database.")
    else:
        sel_date = st.selectbox("Select Trading Date", trade_dates, index=0)
        cd_trades = db.trades(conn, sel_date, "CD", "SEC")
        cp_trades = db.trades(conn, sel_date, "CP", "SEC")

        tab_cd, tab_cp = st.tabs(["Certificate of Deposit (CD)", "Commercial Paper (CP)"])

        with tab_cd:
            st.subheader("CD Tenor Summary")
            cd_tenors = derive.tenor_summary(cd_trades)
            if cd_tenors:
                st.dataframe(pd.DataFrame(cd_tenors), use_container_width=True, hide_index=True)
            else:
                st.info("No CD trades reported for this date.")

            st.subheader("CD Most Active Issuers")
            cd_issuers = derive.issuer_summary(cd_trades)
            if cd_issuers:
                st.dataframe(pd.DataFrame(cd_issuers), use_container_width=True, hide_index=True)

        with tab_cp:
            st.subheader("CP Tenor Summary")
            cp_tenors = derive.tenor_summary(cp_trades)
            if cp_tenors:
                st.dataframe(pd.DataFrame(cp_tenors), use_container_width=True, hide_index=True)
            else:
                st.info("No CP trades reported for this date.")

            st.subheader("CP Most Active Issuers")
            cp_issuers = derive.issuer_summary(cp_trades)
            if cp_issuers:
                st.dataframe(pd.DataFrame(cp_issuers), use_container_width=True, hide_index=True)

# ------------------------------------------------------------- 4. MARKET OVERVIEW
else:
    st.title("Indian Debt & Money Market Overview")
    st.markdown('<div class="disclaimer-box">Comprehensive analytics covering secondary money market trades, sovereign curves, T-bills, SDLs, corporate bonds, and key benchmark spreads.</div>', unsafe_allow_html=True)

    dates = db.trade_dates(conn)
    total_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    total_issuers = conn.execute("SELECT COUNT(DISTINCT issuer) FROM trades").fetchone()[0]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="kpi-card"><div class="kpi-title">Trading Days Tracked</div><div class="kpi-value">{len(dates)}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="kpi-card"><div class="kpi-title">Total Trades Processed</div><div class="kpi-value">{total_trades:,}</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="kpi-card"><div class="kpi-title">Issuers Tracked</div><div class="kpi-value">{total_issuers}</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="kpi-card"><div class="kpi-title">Latest Deal Date</div><div class="kpi-value">{dates[0] if dates else "–"}</div></div>', unsafe_allow_html=True)

    st.markdown("### Quick Navigation")
    st.markdown("""
    - **[Vercel Public Web Dashboard](https://debt-market-dashboard-main.vercel.app)** — Fast client-side baked dashboards for desktop and mobile.
    - **[Fixed Income Closing Report](/?nav=Closing+Report)** — End-of-day desk note with Word/Excel export.
    - **[CBRICS Bond Deal Log](/?nav=CBRICS+Bond+Deals)** — Institutional bond deals ≥ ₹25 Cr.
    """)
