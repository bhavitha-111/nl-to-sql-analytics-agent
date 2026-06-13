"""
NL-to-SQL Analytics Agent — Streamlit frontend.

Provides a wide-layout dashboard for natural language database queries
with transparent SQL display, tabular results, and auto-generated charts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Ensure the project root is on sys.path for `src` imports.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent import NLToSQLAgent
from src.database import DatabaseManager

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="NL-to-SQL Analytics Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Cached resources
# ---------------------------------------------------------------------------


@st.cache_resource
def get_database() -> DatabaseManager:
    """Initialize the database manager once per session (auto-seeds if needed)."""
    return DatabaseManager()


# ---------------------------------------------------------------------------
# Visualization helper
# ---------------------------------------------------------------------------


def _detect_chart_columns(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """
    Identify the best categorical (x) and numeric (y) columns for charting.

    Returns (x_col, y_col) or (None, None) if no suitable pairing exists.
    """
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(
        include=["object", "string", "category"]
    ).columns.tolist()

    if not numeric_cols or not categorical_cols:
        return None, None

    # Prefer the first categorical column with moderate cardinality.
    x_col = None
    for col in categorical_cols:
        unique_count = df[col].nunique()
        if 1 < unique_count <= 50:
            x_col = col
            break

    if x_col is None and categorical_cols:
        x_col = categorical_cols[0]

    # Pick the first numeric column that isn't likely an ID.
    y_col = None
    for col in numeric_cols:
        if not col.lower().endswith("id") and col.lower() != "id":
            y_col = col
            break

    if y_col is None:
        y_col = numeric_cols[0]

    return x_col, y_col


def render_auto_chart(df: pd.DataFrame) -> None:
    """
    Automatically render a Plotly Express chart when the data supports it.

    Requires at least one numeric and one categorical column.
    Chooses bar vs. line based on row count and column characteristics.
    """
    if df.empty:
        return

    x_col, y_col = _detect_chart_columns(df)
    if x_col is None or y_col is None:
        return

    st.subheader("Auto-Generated Visualization")

    try:
        # Use a line chart when the x-axis looks temporal or has many points.
        x_lower = x_col.lower()
        is_temporal_name = any(
            token in x_lower for token in ("date", "month", "year", "time", "day")
        )

        if is_temporal_name or df[x_col].nunique() > 15:
            fig = px.line(
                df,
                x=x_col,
                y=y_col,
                title=f"{y_col} by {x_col}",
                markers=True,
            )
        else:
            # Aggregate for cleaner bar charts when there are duplicate x values.
            chart_df = (
                df.groupby(x_col, as_index=False)[y_col]
                .sum()
                .sort_values(y_col, ascending=False)
            )
            fig = px.bar(
                chart_df,
                x=x_col,
                y=y_col,
                title=f"{y_col} by {x_col}",
                color=x_col,
            )

        fig.update_layout(
            xaxis_title=x_col,
            yaxis_title=y_col,
            showlegend=False,
            margin=dict(l=40, r=40, t=60, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

    except Exception:
        # Chart generation is best-effort; never crash the UI.
        st.info("A chart could not be generated for this result set.")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def render_sidebar() -> str | None:
    """Render the secure sidebar and return the API key (or None)."""
    st.sidebar.header("Configuration")
    api_key = st.sidebar.text_input(
        "Gemini API Key",
        type="password",
        placeholder="AQ.Ab8...",
        help="Your API key is used only in this session and never stored.",
    )

    st.sidebar.divider()
    st.sidebar.markdown(
        "**Database:** `ecommerce.db`  \n"
        "**Tables:** users, products, orders"
    )

    with st.sidebar.expander("Sample Questions"):
        st.markdown(
            "- What are the top 5 product categories by total revenue?\n"
            "- How many orders were placed each month?\n"
            "- Which users spent the most money?\n"
            "- What is the average order value by category?\n"
            "- List products with stock count below 50"
        )

    return api_key if api_key and api_key.strip() else None


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the Streamlit application."""
    st.title("NL-to-SQL Analytics Agent")
    st.markdown(
        "Ask questions about the e-commerce database in plain English. "
        "The agent translates your question to SQL, executes it safely, "
        "and presents results with optional auto-visualization."
    )

    api_key = render_sidebar()

    st.divider()

    question = st.text_area(
        "Your Question",
        placeholder="e.g., What are the top 5 product categories by total revenue?",
        height=100,
    )

    run_analysis = st.button("Run Analysis", type="primary", use_container_width=False)

    if not run_analysis:
        return

    # --- Input validation ---
    if not question or not question.strip():
        st.warning("Please enter a question before running the analysis.")
        return

    if not api_key:
        st.warning("Please enter your Gemini API key in the sidebar.")
        return

    # --- Execute agent pipeline ---
    with st.spinner("Generating and executing SQL..."):
        try:
            db = get_database()
            # Synchronized argument naming with backend constructor
            agent = NLToSQLAgent(db_manager=db, api_key=api_key)
            
            # Synchronized with unpacking tuple syntax from agent.run()
            sql_query, dataframe, error_message = agent.run(question.strip())
        except Exception as exc:
            st.error(f"An unexpected error occurred during execution: {exc}")
            return

    # --- Render results ---
    if error_message is None and dataframe is not None:
        st.success("Analysis completed successfully.")

        with st.expander("Generated SQL Query", expanded=False):
            st.code(sql_query, language="sql")

        st.subheader("Query Results")
        st.dataframe(dataframe, use_container_width=True, hide_index=True)

        render_auto_chart(dataframe)

    else:
        st.error(error_message or "The analysis could not be completed.")
        
        if sql_query:
            with st.expander("Last Attempted SQL Query", expanded=False):
                st.code(sql_query, language="sql")


if __name__ == "__main__":
    main()