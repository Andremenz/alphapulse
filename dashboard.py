import streamlit as st
import pandas as pd
import sqlite3
import os
import plotly.express as px

st.set_page_config(page_title="AlphaPulse Command Center", layout="wide", page_icon="🚀")
st.title("🚀 AlphaPulse Analytics Dashboard")
st.caption("Real-time Shadow Ledger metrics | Read-only | Auto-refreshes every 60s")

DB_PATH = os.environ.get("DB_PATH", "data/alpha_pulse_ledger.db")

@st.cache_data(ttl=60)
def load_data():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        df = pd.read_sql_query("SELECT * FROM alpha_signals", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

df = load_data()

if df.empty:
    st.info("📊 No trade data yet. The bot is scanning for signals. Trades will appear here after execution.")
    st.stop()

# Data Processing
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['entry_price'] = pd.to_numeric(df.get('entry_price', 0), errors='coerce')
df['target_price'] = pd.to_numeric(df.get('target_price', 0), errors='coerce')

# Calculate PnL for closed trades
closed = df[df['status'] == 'CLOSED'].copy()
if not closed.empty:
    closed['current_price'] = pd.to_numeric(closed.get('current_price', 0), errors='coerce')
    closed['pnl_pct'] = ((closed['current_price'] - closed['entry_price']) / closed['entry_price']) * 100
else:
    closed = pd.DataFrame(columns=['pnl_pct'])

active = df[df['status'] == 'OPEN'].copy()

# Top Metrics
st.subheader("📈 Portfolio Overview")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Signals Logged", len(df))
c2.metric("Active Positions", len(active))
c3.metric("Closed Trades", len(closed))

if not closed.empty:
    wins = len(closed[closed['pnl_pct'] > 0])
    win_rate = (wins / len(closed)) * 100
    avg_pnl = closed['pnl_pct'].mean()
    c4.metric("Win Rate", f"{win_rate:.1f}%")
    st.metric("Avg Realized PnL", f"{avg_pnl:+.2f}%")
else:
    c4.metric("Win Rate", "N/A")
    st.metric("Avg Realized PnL", "N/A")

# Charts
st.subheader("🎯 AI Confidence vs Realized Returns")
if not closed.empty:
    fig = px.scatter(
        closed, x='ai_score', y='pnl_pct', 
        title="Does higher AI confidence correlate with higher returns?",
        labels={'ai_score': 'AI Confidence Score (0-100)', 'pnl_pct': 'Realized PnL (%)'},
        color='ai_score', color_continuous_scale='RdYlGn'
    )
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("📉 Closed trades will populate this chart after exits trigger.")

# Recent Trade Log
st.subheader("📜 Recent Trade Ledger")
display_cols = ['timestamp', 'space', 'ai_score', 'status', 'entry_price', 'target_price']
existing_cols = [c for c in display_cols if c in df.columns]
st.dataframe(
    df.sort_values('timestamp', ascending=False)[existing_cols].head(15),
    use_container_width=True,
    hide_index=True
)

st.caption("Powered by AlphaPulse Shadow Ledger | Data syncs from Railway mounted volume")
