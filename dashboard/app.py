"""Tenora FX Risk Dashboard - Streamlit entry point.

Milestone 1: a wiring check over the parquet store (pull status and latest rows).
Charts and risk metrics arrive in later milestones.
"""

import pandas as pd
import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tenora_fx import storage

st.set_page_config(page_title="Tenora FX Risk", layout="wide")
st.title("Tenora FX Risk Dashboard")

manifest = storage.read_manifest()
if manifest is None:
    st.warning("No data yet. Run `python -m tenora_fx.pipeline` first.")
    st.stop()

window = manifest["lookback"]
summary = manifest["summary"]
st.caption(
    f"Last pull {manifest['generated_at']} | window {window['start']} to {window['end']} | "
    f"{summary['ok']}/{summary['total']} series ok"
)

st.subheader("Pull status")
status = pd.DataFrame(manifest["results"])
st.dataframe(
    status[["group", "key", "source", "status", "rows", "first", "last", "error", "note"]],
    hide_index=True,
)

st.subheader("Latest FX closes")
closes = storage.load_fx_closes()
if closes.empty:
    st.info("No FX files on disk.")
else:
    st.dataframe(closes.tail(10).sort_index(ascending=False))

st.subheader("Latest rates (%)")
rates = storage.load_rates()
if rates.empty:
    st.info("No rate files on disk.")
else:
    st.dataframe(rates.ffill().tail(10).sort_index(ascending=False))
