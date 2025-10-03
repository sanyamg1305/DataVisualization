import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="EXIM Trade Analysis Demo", layout="wide")

# ----------------------------
# Load & Clean Data
# ----------------------------
@st.cache_data
def load_data(path="EXIM_Trade_Analysis_Report_579700_042024114401 (1).xlsx", sheet_name="Trade analysis report"):
    # read excel (header at row index 2)
    df = pd.read_excel(path, sheet_name=sheet_name, header=2)

    # clean column names
    df.columns = [str(c).strip() for c in df.columns]

    # Ensure DATE parsed
    if "DATE" in df.columns:
        df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")

    # Clean QUANTITY
    if "QUANTITY" in df.columns:
        df["QUANTITY"] = pd.to_numeric(df["QUANTITY"], errors="coerce").fillna(0)

    # Clean VALUE(USD)
    if "VALUE(USD)" in df.columns:
        df["VALUE(USD)"] = (
            df["VALUE(USD)"].astype(str)
            .replace(r"[\$,]", "", regex=True)
            .str.strip()
        )
        df["VALUE(USD)"] = pd.to_numeric(df["VALUE(USD)"], errors="coerce").fillna(0.0)

    # Clean UNIT PRICE
    if "UNIT PRICE" in df.columns:
        df["UNIT PRICE"] = (
            df["UNIT PRICE"].astype(str)
            .replace(r"[\$,]", "", regex=True)
            .str.strip()
        )
        df["UNIT PRICE"] = pd.to_numeric(df["UNIT PRICE"], errors="coerce")

    # Compute ASP safely
    df["ASP_COMPUTED"] = df["UNIT PRICE"].copy() if "UNIT PRICE" in df.columns else np.nan
    mask_missing_asp = df["ASP_COMPUTED"].isna() & (df["QUANTITY"] > 0)
    df.loc[mask_missing_asp, "ASP_COMPUTED"] = (
        df.loc[mask_missing_asp, "VALUE(USD)"] / df.loc[mask_missing_asp, "QUANTITY"]
    )

    return df


df = load_data()

# ----------------------------
# Sidebar Filters
# ----------------------------
st.sidebar.header("Filters")

buyers = st.sidebar.multiselect("Select Buyers", sorted(df["BUYER"].dropna().unique()))
hs_codes = st.sidebar.multiselect("Select HS Codes", sorted(df["HS CODE"].dropna().unique()))
sellers = st.sidebar.multiselect("Select Sellers (Competitors)", sorted(df["SELLER"].dropna().unique()))
industries = st.sidebar.multiselect("Select Industry", sorted(df["INDUSTRY"].dropna().unique()))

date_min, date_max = pd.to_datetime(df["DATE"].min()), pd.to_datetime(df["DATE"].max())
date_range = st.sidebar.date_input("Date Range", [date_min, date_max])

apply_filters = st.sidebar.button("Apply Filters")

if apply_filters:
    mask = pd.Series(True, index=df.index)

    if buyers:
        mask &= df["BUYER"].isin(buyers)
    if hs_codes:
        mask &= df["HS CODE"].isin(hs_codes)
    if sellers:
        mask &= df["SELLER"].isin(sellers)
    if industries:
        mask &= df["INDUSTRY"].isin(industries)
    if date_range:
        mask &= (pd.to_datetime(df["DATE"]) >= pd.to_datetime(date_range[0])) & (
            pd.to_datetime(df["DATE"]) <= pd.to_datetime(date_range[1])
        )

    df_filtered = df[mask]
else:
    df_filtered = df.copy()

# ----------------------------
# 1. Buying - Customer wise / HS Code wise
# ----------------------------
st.header("1. Buying Summary (Customer / HS Code wise)")

group_choice = st.radio("Group by:", ["BUYER", "HS CODE"])
summary = df_filtered.groupby(group_choice).agg(
    Total_Qty=("QUANTITY", "sum"),
    Total_Value=("VALUE(USD)", "sum"),
    Avg_ASP=("ASP_COMPUTED", "mean")
).reset_index()

st.dataframe(summary)

# ----------------------------
# 2. Growth % (Qty/Value)
# ----------------------------
st.header("2. Growth % in terms of Quantity / Value")

col1, col2 = st.columns(2)
with col1:
    start_period = st.date_input("Start Period", date_min, key="start_period")
with col2:
    end_period = st.date_input("End Period", date_max, key="end_period")

df_start = df[(pd.to_datetime(df["DATE"]) <= pd.to_datetime(start_period))]
df_end = df[(pd.to_datetime(df["DATE"]) <= pd.to_datetime(end_period))]

qty_growth = (
    (df_end["QUANTITY"].sum() - df_start["QUANTITY"].sum())
    / df_start["QUANTITY"].sum() * 100
    if df_start["QUANTITY"].sum()
    else np.nan
)
val_growth = (
    (df_end["VALUE(USD)"].sum() - df_start["VALUE(USD)"].sum())
    / df_start["VALUE(USD)"].sum() * 100
    if df_start["VALUE(USD)"].sum()
    else np.nan
)

st.metric("Growth in Quantity (%)", f"{qty_growth:.2f}%" if pd.notna(qty_growth) else "N/A")
st.metric("Growth in Value (%)", f"{val_growth:.2f}%" if pd.notna(val_growth) else "N/A")

# ----------------------------
# 3. Average Selling Price
# ----------------------------
st.header("3. Average Selling Price (ASP)")

asp_group = st.selectbox("Group ASP by:", ["HS CODE", "BUYER", "SELLER", "INDUSTRY"])
asp_summary = (
    df_filtered.groupby(asp_group)["ASP_COMPUTED"]
    .mean()
    .reset_index()
    .sort_values("ASP_COMPUTED", ascending=False)
)
st.dataframe(asp_summary)

# ----------------------------
# 4. Target Customers (HS Code / ASP)
# ----------------------------
st.header("4. Target Customers")

if len(hs_codes) > 0:
    hs_choice = st.selectbox("Select HS Code", hs_codes)
else:
    hs_choice = st.selectbox("Select HS Code", sorted(df_filtered["HS CODE"].dropna().unique()))

asp_min = st.number_input("Min ASP", value=float(df_filtered["ASP_COMPUTED"].min() or 0))
asp_max = st.number_input("Max ASP", value=float(df_filtered["ASP_COMPUTED"].max() or 1000))

target_df = df_filtered[
    (df_filtered["HS CODE"] == hs_choice)
    & (df_filtered["ASP_COMPUTED"] >= asp_min)
    & (df_filtered["ASP_COMPUTED"] <= asp_max)
]
target_summary = target_df.groupby("BUYER").agg(
    Total_Qty=("QUANTITY", "sum"),
    Total_Value=("VALUE(USD)", "sum"),
    Avg_ASP=("ASP_COMPUTED", "mean")
).reset_index()
st.dataframe(target_summary)

# ----------------------------
# 5. Competitor Mapping
# ----------------------------
st.header("5. Competitor Mapping")

comp_summary = (
    df_filtered.groupby("SELLER")
    .agg(
        Total_Qty=("QUANTITY", "sum"),
        Total_Value=("VALUE(USD)", "sum"),
        Avg_ASP=("ASP_COMPUTED", "mean"),
    )
    .reset_index()
    .sort_values("Total_Value", ascending=False)
)

st.subheader("Top Competitors by Value")
st.dataframe(comp_summary.head(10))

pivot = pd.pivot_table(
    df_filtered,
    index="SELLER",
    columns="HS CODE",
    values="VALUE(USD)",
    aggfunc="sum",
    fill_value=0,
)
st.subheader("Seller vs HS Code Mapping")
st.dataframe(pivot)

# ----------------------------
# Download Option
# ----------------------------
st.download_button(
    "Download Filtered Data as CSV",
    df_filtered.to_csv(index=False).encode("utf-8"),
    "filtered_data.csv",
    "text/csv"
)

