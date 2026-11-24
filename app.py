import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import BytesIO

# =========================================================
# PAGE CONFIG + PROFESSIONAL WHITE THEME
# =========================================================
st.set_page_config(
    page_title="Universal Data Analytics Dashboard",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
<style>
.stApp { background: #FFFFFF; color: #1F2937; }
[data-testid="stSidebar"] { background: #F1F5F9; }
h1, h2, h3 { color: #1E40AF !important; }
[data-testid="stMetric"] {
    background: #F1F5F9; padding: 16px;
    border-radius: 12px; border: 1px solid #DCE3ED;
}
[data-testid="stMetricValue"] { color: #047857; }
.stButton > button, .stDownloadButton > button {
    background: #2563EB; color: white; border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

st.title("📊 Universal Data Analytics Dashboard")
st.caption("Upload almost any CSV or Excel dataset • Automatic data cleaning • Interactive dashboard • Insights")

# =========================================================
# HELPERS
# =========================================================
def load_data(file):
    name = file.name.lower()
    if name.endswith(".csv"):
        try:
            return pd.read_csv(file)
        except UnicodeDecodeError:
            file.seek(0)
            return pd.read_csv(file, encoding="latin-1")
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file)
    raise ValueError("Please upload a CSV or Excel file.")

def make_unique_columns(columns):
    result, seen = [], {}
    for i, col in enumerate(columns):
        name = str(col).strip() or f"Column_{i+1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        result.append(name)
    return result

def is_probable_id(series, column_name):
    name = column_name.lower()
    id_words = [" id", "_id", "code", "zip", "postal", "phone", "account"]
    if any(word in name for word in id_words) or name.endswith("id"):
        return True
    return False

def detect_date_columns(frame):
    found = []
    for col in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[col]):
            found.append(col)
            continue
        if any(word in str(col).lower() for word in ["date", "time", "timestamp", "created", "updated"]):
            parsed = pd.to_datetime(frame[col], errors="coerce")
            if parsed.notna().mean() >= 0.5:
                frame[col] = parsed
                found.append(col)
    return found

def safe_numeric_columns(frame):
    return [
        c for c in frame.select_dtypes(include=np.number).columns
        if not is_probable_id(frame[c], str(c)) and frame[c].nunique(dropna=True) > 1
    ]

def fmt_number(value):
    if pd.isna(value):
        return "N/A"
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value/1_000_000:,.2f}M"
    if abs(value) >= 1_000:
        return f"{value:,.2f}"
    return f"{value:,.2f}"

# =========================================================
# SIDEBAR: UPLOAD + OPTIONS
# =========================================================
st.sidebar.title("⚙️ Dashboard Controls")
uploaded_file = st.sidebar.file_uploader(
    "Upload any dataset",
    type=["csv", "xlsx", "xls"],
    help="CSV and Excel files are supported."
)

if uploaded_file is None:
    st.info("👈 Upload a CSV or Excel file to automatically build your dashboard.")
    st.markdown("""
    ### What this dashboard generates automatically
    - Dataset overview and data-quality report
    - KPI cards for rows, columns, missing values and unique values
    - Interactive filters for categorical columns
    - Numeric summaries, distributions and correlations
    - Category-wise comparisons and date-wise trends
    - Automatically generated observations and downloadable reports
    """)
    st.stop()

try:
    raw_df = load_data(uploaded_file)
except Exception as exc:
    st.error(f"Could not read this file: {exc}")
    st.stop()

if raw_df.empty:
    st.error("The uploaded dataset has no rows.")
    st.stop()

raw_df.columns = make_unique_columns(raw_df.columns)
original_rows, original_cols = raw_df.shape
original_missing = int(raw_df.isna().sum().sum())
original_duplicates = int(raw_df.duplicated().sum())

# =========================================================
# DATA CLEANING
# =========================================================
df = raw_df.copy()
df = df.drop_duplicates().copy()

# Convert numeric-looking text columns, but avoid converting date-like columns.
for col in df.select_dtypes(include=["object"]).columns:
    if any(word in col.lower() for word in ["date", "time", "timestamp"]):
        continue
    converted = pd.to_numeric(
        df[col].astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False).str.replace("₹", "", regex=False),
        errors="coerce"
    )
    non_empty = df[col].notna().sum()
    if non_empty and converted.notna().sum() / non_empty >= 0.85:
        df[col] = converted

date_cols = detect_date_columns(df)

numeric_cols_all = df.select_dtypes(include=np.number).columns.tolist()
categorical_cols_all = [
    c for c in df.columns
    if c not in numeric_cols_all and c not in date_cols
]
# Keep missing values visible in the quality report; fill only the analysis copy.
analysis_df = df.copy()
for col in numeric_cols_all:
    if analysis_df[col].isna().any():
        median = analysis_df[col].median()
        analysis_df[col] = analysis_df[col].fillna(0 if pd.isna(median) else median)
for col in categorical_cols_all:
    analysis_df[col] = analysis_df[col].fillna("Unknown")

numeric_cols = safe_numeric_columns(analysis_df)
categorical_cols = [
    c for c in categorical_cols_all
    if analysis_df[c].nunique(dropna=True) > 1 and analysis_df[c].nunique(dropna=True) <= 100
]

# =========================================================
# FILTERS
# =========================================================
st.sidebar.divider()
st.sidebar.subheader("🎛️ Filters")
filtered = analysis_df.copy()

filter_candidates = [
    c for c in categorical_cols
    if 1 < filtered[c].nunique(dropna=True) <= 50
][:8]

for col in filter_candidates:
    options = sorted(filtered[col].astype(str).unique().tolist())
    chosen = st.sidebar.multiselect(
        f"{col}", options, default=options, key=f"filter_{col}"
    )
    filtered = filtered[filtered[col].astype(str).isin(chosen)]

if filtered.empty:
    st.warning("No rows match the selected filters. Please change the filters.")
    st.stop()

# =========================================================
# OVERVIEW / KPI DASHBOARD
# =========================================================
st.header("📌 Dashboard Overview")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Records", f"{len(filtered):,}", delta=f"{len(filtered)-len(df):,} after filters")
k2.metric("Total Columns", f"{len(filtered.columns):,}")
k3.metric("Missing Values (source)", f"{int(df.isna().sum().sum()):,}")
k4.metric("Duplicate Rows Removed", f"{original_duplicates:,}")

# Select a meaningful numeric metric for KPI and analysis.
default_metric = numeric_cols[0] if numeric_cols else None
metric_col = st.selectbox(
    "Choose a numeric metric for detailed analysis",
    options=numeric_cols,
    index=0 if numeric_cols else None,
    disabled=not bool(numeric_cols),
    help="For example: Sales, Revenue, Profit, Quantity, Salary or Score."
) if numeric_cols else None

if metric_col:
    a, b, c, d = st.columns(4)
    a.metric(f"Total {metric_col}", fmt_number(filtered[metric_col].sum()))
    b.metric(f"Average {metric_col}", fmt_number(filtered[metric_col].mean()))
    c.metric(f"Highest {metric_col}", fmt_number(filtered[metric_col].max()))
    d.metric(f"Lowest {metric_col}", fmt_number(filtered[metric_col].min()))

# =========================================================
# DATA PREVIEW + QUALITY
# =========================================================
st.divider()
st.header("🧹 Data Quality & Dataset Preview")
q1, q2, q3, q4 = st.columns(4)
q1.metric("Original Rows", f"{original_rows:,}")
q2.metric("Rows After Duplicate Removal", f"{len(df):,}")
q3.metric("Missing Cells", f"{original_missing:,}")
q4.metric("Numeric Columns", f"{len(numeric_cols_all):,}")

with st.expander("View cleaned dataset", expanded=True):
    st.dataframe(filtered, use_container_width=True, height=320)

quality = pd.DataFrame({
    "Column": df.columns.astype(str),
    "Data Type": df.dtypes.astype(str).values,
    "Missing Values": df.isna().sum().values,
    "Missing %": (df.isna().mean().values * 100).round(2),
    "Unique Values": df.nunique(dropna=True).values
})
with st.expander("Detailed column quality report"):
    st.dataframe(quality, use_container_width=True)

# =========================================================
# AUTOMATIC NUMERIC ANALYSIS
# =========================================================
st.divider()
st.header("📈 Numerical Analysis")
if numeric_cols:
    chosen_numeric = st.multiselect(
        "Select numeric columns to analyze",
        numeric_cols,
        default=numeric_cols[:min(4, len(numeric_cols))]
    )
    if chosen_numeric:
        st.subheader("Statistical Summary")
        st.dataframe(
            filtered[chosen_numeric].describe().T.round(2),
            use_container_width=True
        )

        selected_distribution = st.selectbox(
            "Choose a column for distribution chart", chosen_numeric
        )
        fig = px.histogram(
            filtered, x=selected_distribution, nbins=30,
            title=f"Distribution of {selected_distribution}",
            marginal="box", template="plotly_white"
        )
        st.plotly_chart(fig, use_container_width=True)

        if len(chosen_numeric) >= 2:
            corr = filtered[chosen_numeric].corr(numeric_only=True)
            fig = px.imshow(
                corr, text_auto=".2f", aspect="auto",
                title="Correlation Heatmap", color_continuous_scale="RdBu_r",
                template="plotly_white", zmin=-1, zmax=1
            )
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No suitable numeric columns were detected. Categorical analysis is still available.")

# =========================================================
# CATEGORICAL ANALYSIS
# =========================================================
st.divider()
st.header("🏷️ Category Analysis")
if categorical_cols:
    cat_col = st.selectbox("Choose a category column", categorical_cols)
    top_n = st.slider("Number of categories to display", 5, 30, 10)
    cat_counts = (
        filtered[cat_col].astype(str).value_counts().head(top_n)
        .rename_axis(cat_col).reset_index(name="Records")
    )
    left, right = st.columns(2)
    with left:
        fig = px.bar(
            cat_counts, x=cat_col, y="Records", color="Records",
            title=f"Top {top_n} values in {cat_col}", template="plotly_white"
        )
        st.plotly_chart(fig, use_container_width=True)
    with right:
        fig = px.pie(
            cat_counts, names=cat_col, values="Records",
            title=f"Share by {cat_col} (top values)", template="plotly_white"
        )
        st.plotly_chart(fig, use_container_width=True)

    if metric_col:
        grouped = (
            filtered.groupby(cat_col, dropna=False)[metric_col]
            .agg(["sum", "mean", "count"]).reset_index()
            .sort_values("sum", ascending=False).head(top_n)
        )
        st.subheader(f"{metric_col} by {cat_col}")
        st.dataframe(grouped.round(2), use_container_width=True)
        fig = px.bar(
            grouped, x=cat_col, y="sum", color="sum",
            title=f"Total {metric_col} by {cat_col}",
            labels={"sum": f"Total {metric_col}"}, template="plotly_white"
        )
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No suitable categorical columns were detected.")

# =========================================================
# DATE / TIME TREND ANALYSIS
# =========================================================
st.divider()
st.header("🗓️ Date & Time Trend Analysis")
if date_cols:
    date_col = st.selectbox("Choose a date column", date_cols)
    trend_metric = metric_col
    trend_df = filtered.copy()
    trend_df[date_col] = pd.to_datetime(trend_df[date_col], errors="coerce")
    trend_df = trend_df.dropna(subset=[date_col])
    if not trend_df.empty:
        trend_df["Month"] = trend_df[date_col].dt.to_period("M").astype(str)
        if trend_metric:
            trend = trend_df.groupby("Month")[trend_metric].sum().reset_index()
            fig = px.line(
                trend, x="Month", y=trend_metric, markers=True,
                title=f"Monthly {trend_metric} Trend", template="plotly_white"
            )
        else:
            trend = trend_df.groupby("Month").size().reset_index(name="Records")
            fig = px.line(
                trend, x="Month", y="Records", markers=True,
                title="Monthly Record Count", template="plotly_white"
            )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No valid date values are available after filtering.")
else:
    st.info("No date column was detected. Add a date/time column to enable trend analysis.")

# =========================================================
# AUTOMATIC BUSINESS / DATA INSIGHTS
# =========================================================
st.divider()
st.header("💡 Automatic Data Insights")
insights = [
    f"The dataset contains {len(filtered):,} records and {len(filtered.columns):,} columns after applying filters.",
    f"{original_duplicates:,} duplicate rows were identified in the uploaded data.",
    f"The original dataset has {original_missing:,} missing cells."
]
if metric_col:
    insights.append(
        f"For {metric_col}, the average is {fmt_number(filtered[metric_col].mean())}, "
        f"the minimum is {fmt_number(filtered[metric_col].min())}, "
        f"and the maximum is {fmt_number(filtered[metric_col].max())}."
    )
if categorical_cols:
    insight_cat = categorical_cols[0]
    top_value = filtered[insight_cat].astype(str).value_counts()
    if not top_value.empty:
        share = top_value.iloc[0] / len(filtered) * 100
        insights.append(
            f"The most common {insight_cat} is '{top_value.index[0]}' "
            f"with {top_value.iloc[0]:,} records ({share:.1f}% of filtered data)."
        )
if date_cols:
    date_values = pd.to_datetime(filtered[date_cols[0]], errors="coerce").dropna()
    if not date_values.empty:
        insights.append(
            f"The {date_cols[0]} range runs from {date_values.min().date()} "
            f"to {date_values.max().date()}."
        )
for item in insights:
    st.markdown(f"- {item}")

# =========================================================
# DOWNLOADS
# =========================================================
st.divider()
st.header("📥 Download Reports")
csv_bytes = filtered.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "⬇️ Download cleaned / filtered CSV",
    data=csv_bytes,
    file_name="cleaned_filtered_data.csv",
    mime="text/csv"
)

excel_buffer = BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    filtered.to_excel(writer, index=False, sheet_name="Cleaned Data")
    quality.to_excel(writer, index=False, sheet_name="Data Quality")
    if numeric_cols:
        filtered[numeric_cols].describe().T.to_excel(writer, sheet_name="Numeric Summary")
    pd.DataFrame({"Insights": insights}).to_excel(writer, index=False, sheet_name="Insights")

st.download_button(
    "⬇️ Download complete Excel analysis report",
    data=excel_buffer.getvalue(),
    file_name="universal_data_analysis_report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.divider()
st.caption("Universal Data Analytics Dashboard | Python • Pandas • Plotly • Streamlit")
st.caption("Note: Automatic insights are descriptive. They do not establish causation or guarantee business outcomes.")
