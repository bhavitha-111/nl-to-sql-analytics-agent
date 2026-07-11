import streamlit as st
import pandas as pd
import os
import re
import sqlite3

# Import our cleanly exported modules from our src package configuration
from src.agent import AnalyticsAgent
from src.database import DatabaseManager

# Page configuration
st.set_page_config(
    page_title="E-Commerce AI Analytics Console",
    page_icon="🛒",
    layout="wide"
)

# Premium stylesheet injector with Dark Mode high-contrast metric fixes
st.markdown("""
<style>
    .reportview-container {
        background: #f8f9fa;
    }
    .stButton>button {
        background-color: #ff4b4b;
        color: white;
        border-radius: 6px;
        font-weight: bold;
        border: none;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        background-color: #ff3333;
        transform: translateY(-1px);
    }
    .sql-box {
        background-color: #f1f3f5;
        border-left: 4px solid #1c7ed6;
        padding: 15px;
        border-radius: 4px;
        font-family: 'Courier New', Courier, monospace;
    }
    /* Fixed premium slate container styling for high-contrast visibility */
    div[data-testid="metric-container"], .stMetric {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        padding: 15px !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2) !important;
    }
    div[data-testid="metric-container"] label, div[data-testid="metric-container"] [data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-weight: 600 !important;
        font-size: 14px !important;
    }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #f8fafc !important;
        font-weight: 700 !important;
        font-size: 24px !important;
    }
</style>
""", unsafe_allow_html=True)

# Auto-Seeding Database Utility for Cloud Deployments
def auto_seed_if_empty(db_path: str):
    """Checks if the database has tables, if not, seeds it automatically."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if we have active user tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = cursor.fetchall()
    
    if not tables:
        # Create Users Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            joined_date TEXT NOT NULL,
            country TEXT NOT NULL
        );
        """)

        # Create Products Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            stock_count INTEGER NOT NULL
        );
        """)

        # Create Orders Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_date TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        """)

        # Create Order Items Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
        """)

        # Insert Seed Users
        users_data = [
            ("Aarav Sharma", "aarav@email.com", "2024-01-15", "India"),
            ("Sarah Jenkins", "sarah.j@email.com", "2024-02-10", "United States"),
            ("Liam O'Connor", "liam@email.com", "2024-03-01", "Canada"),
            ("Emma Watson", "emma@email.com", "2024-03-22", "United Kingdom"),
            ("Max Schmidt", "max@email.com", "2024-04-05", "Germany")
        ]
        cursor.executemany("INSERT INTO users (name, email, joined_date, country) VALUES (?, ?, ?, ?);", users_data)

        # Insert Seed Products
        products_data = [
            ("Smart Wireless Headphones", "Electronics", 129.99, 45),
            ("Mechanical Keyboard", "Electronics", 89.99, 120),
            ("Ultra-wide Monitor", "Electronics", 349.99, 15),
            ("Premium Cotton Hoodie", "Clothing", 49.99, 200),
            ("Slim Fit Denim Jeans", "Clothing", 59.99, 85),
            ("Ergonomic Desk Chair", "Home & Kitchen", 189.99, 30),
            ("Smart Coffee Maker", "Home & Kitchen", 79.99, 8),
            ("Adjustable Dumbbell Set", "Fitness", 149.99, 12)
        ]
        cursor.executemany("INSERT INTO products (product_name, category, price, stock_count) VALUES (?, ?, ?, ?);", products_data)

        # Insert Seed Orders
        import random
        from datetime import datetime, timedelta
        base_date = datetime(2025, 1, 1)
        
        for order_id in range(1, 21):
            user_id = random.randint(1, 5)
            order_date = (base_date + timedelta(days=random.randint(0, 150))).strftime("%Y-%m-%d")
            status = random.choice(["Delivered", "Processing", "Shipped"])
            cursor.execute("INSERT INTO orders (user_id, order_date, status) VALUES (?, ?, ?);", (user_id, order_date, status))
            
            # Generate items
            num_items = random.randint(1, 3)
            selected_products = random.sample(range(1, 9), num_items)
            for prod_id in selected_products:
                cursor.execute("SELECT price FROM products WHERE product_id = ?;", (prod_id,))
                price = cursor.fetchone()[0]
                quantity = random.randint(1, 3)
                cursor.execute("INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?);", 
                               (order_id, prod_id, quantity, price))
        conn.commit()
    conn.close()

@st.cache_resource
def initialize_analytics_backend():
    db_path = "./data/ecommerce.db"
    os.makedirs("./data", exist_ok=True)
    
    # Securely auto-seed database if running on a fresh environment/cloud deployment
    auto_seed_if_empty(db_path)
    
    agent = AnalyticsAgent(db_history_path="./chroma_db", db_path=db_path)
    db_mgr = DatabaseManager(db_path=db_path)
    return agent, db_mgr

try:
    agent, db_mgr = initialize_analytics_backend()
except Exception as e:
    st.error(f"Backend Engine Bootstrap Error: {e}")
    st.stop()

def format_sql_vertical(sql: str) -> str:
    """Format and indent raw SQL strings vertically to ensure extreme legibility."""
    keywords = ["SELECT", "FROM", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "JOIN", 
                "ON", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "UNION", "AND", "OR"]
    
    sql_clean = " ".join(sql.split())
    formatted = sql_clean
    for kw in keywords:
        formatted = re.sub(rf'\b{kw}\b', f'\n{kw}', formatted, flags=re.IGNORECASE)
        
    for kw in keywords:
        formatted = re.sub(rf'\b{kw}\b', kw.upper(), formatted, flags=re.IGNORECASE)
        
    lines = [line.strip() for line in formatted.split('\n') if line.strip()]
    
    indented_lines = []
    for line in lines:
        upper_line = line.upper()
        if any(upper_line.startswith(k) for k in ["SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "LIMIT", "JOIN", "LEFT JOIN", "INNER JOIN"]):
            indented_lines.append(line)
        elif upper_line.startswith("ON") or upper_line.startswith("AND") or upper_line.startswith("OR"):
            indented_lines.append("    " + line)
        else:
            indented_lines.append("    " + line)
            
    return "\n".join(indented_lines)

def render_dynamic_visuals(df: pd.DataFrame, user_query: str):
    """Scan columns dynamically to auto-select and render relevant graphical charts."""
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    categorical_cols = df.select_dtypes(exclude=['number']).columns.tolist()
    
    if not numeric_cols:
        st.info("ℹamp; Results contain only text data. Visual charts require at least one numerical column.")
        return  
        
    st.write("### 📊 Interactive Visual Analytics")
    
    value_col = numeric_cols[0]
    for col in numeric_cols:
        if any(keyword in col.lower() for keyword in ['revenue', 'amount', 'total', 'count', 'sales', 'value', 'price']):
            value_col = col
            break
            
    if categorical_cols:
        label_col = categorical_cols[0]
        is_time_series = any(any(time_key in col.lower() for time_key in ['month', 'date', 'year', 'day', 'time', 'period']) for col in categorical_cols)
        
        for col in categorical_cols:
            if any(key in col.lower() for key in ['month', 'date', 'category', 'product', 'name', 'user']):
                label_col = col
                break
                
        cols = st.columns(min(len(df), 3))
        for idx, row in df.head(len(cols)).iterrows():
            with cols[idx]:
                try:
                    val = float(row[value_col])
                    metric_val = f"${val:,.2f}" if any(x in value_col.lower() for x in ['revenue', 'amount', 'price']) else f"{val:,.0f}"
                except ValueError:
                    metric_val = str(row[value_col])
                st.metric(label=str(row[label_col]), value=metric_val)
        
        st.markdown("<br>", unsafe_allow_html=True)

        if is_time_series:
            st.info(f"Showing chronological progression of `{value_col}` grouped by `{label_col}`")
            st.line_chart(df.set_index(label_col)[value_col], use_container_width=True)
        else:
            st.info(f"Distribution analysis of `{value_col}` ranked by `{label_col}`")
            st.bar_chart(df.set_index(label_col)[value_col], use_container_width=True)
    else:
        if len(numeric_cols) >= 2:
            st.line_chart(df.set_index(numeric_cols[0])[numeric_cols[1]], use_container_width=True)
        else:
            st.bar_chart(df[value_col], use_container_width=True)

if "requires_approval" not in st.session_state:
    st.session_state.requires_approval = False
if "pending_sql" not in st.session_state:
    st.session_state.pending_sql = ""
if "agent_reasoning" not in st.session_state:
    st.session_state.agent_reasoning = ""
if "input_query_value" not in st.session_state:
    st.session_state.input_query_value = ""

with st.sidebar:
    st.title("Configuration")
    
    api_key_display = st.secrets.get("GEMINI_API_KEY") or "Using default demo key"
    st.text_input(
        "Gemini API Key", 
        type="password", 
        value="•" * 20 if "AQ." in api_key_display else api_key_display, 
        disabled=True,
        help="Protected securely via workspace secrets."
    )
    
    st.markdown("---")
    st.markdown("### Database Environment")
    st.markdown("📁 **Database:** `ecommerce.db`")
    
    # Read active SQLite DB dynamically
    live_tables = db_mgr.get_existing_tables()
    tables_list_str = ", ".join([f"`{t}`" for t in live_tables]) if live_tables else "None detected"
    st.markdown(f"📋 **Detected Tables:** {tables_list_str}")
    
    st.markdown("---")
    st.markdown("### 💡 Sample Questions")
    samples = [
        "What are the top 5 product categories by total revenue?",
        "How many orders were placed each month?",
        "Which users spent the most money?",
        "What is the average order value by category?",
        "List products with stock count below 50"
    ]
    
    for q in samples:
        if st.button(q, key=f"btn_{q}", use_container_width=True):
            st.session_state.input_query_value = q
            st.rerun()

# --- MAIN DASHBOARD INTERFACE ---
st.title("NL-to-SQL Analytics Console")
st.markdown(
    "Ask questions about the e-commerce database in plain English. The agent translates your question to SQL, "
    "executes it safely, and presents results with beautiful vertical code layouts and auto-visualization."
)

st.divider()

user_query = st.text_area(
    "Your Question",
    value=st.session_state.input_query_value,
    placeholder="e.g., What are the top 5 product categories by total revenue?",
    height=100
)

if st.button("Run Analysis", type="primary"):
    if user_query:
        st.session_state.input_query_value = user_query
        
        with st.spinner("Analyzing schema vector maps & drafting execution syntax..."):
            try:
                # Ask agent for execution plan
                agent_response = agent.generate_query(user_query)
                st.session_state.agent_reasoning = agent_response.reasoning
                
                # Format raw SQL cleanly
                formatted_sql = format_sql_vertical(agent_response.sql_query)
                
                # Check DB read safety settings
                static_safety_audit = db_mgr.check_query_safety(formatted_sql)
                
                if agent_response.confidence_score.upper() == "LOW" or not static_safety_audit["is_safe"]:
                    st.session_state.requires_approval = True
                    st.session_state.pending_sql = formatted_sql
                else:
                    st.session_state.requires_approval = False
                    st.session_state.pending_sql = ""
                    
                    st.info(agent_response.reasoning)
                    
                    st.markdown("### 💻 Compiled SQL Syntax")
                    st.code(formatted_sql, language="sql")
                    
                    try:
                        results_df = db_mgr.execute_read_query(formatted_sql)
                        st.success("Analysis completed successfully.")
                        
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            st.write("### 📋 Execution Matrix Results")
                            if results_df.empty:
                                st.warning("Query produced empty rows.")
                            else:
                                st.dataframe(results_df, use_container_width=True)
                        with col2:
                            if not results_df.empty:
                                render_dynamic_visuals(results_df, user_query)
                    except Exception as db_err:
                        # Self-healing loop execution
                        st.warning(f"⚠️ Initial query run failed with error: {db_err}. Retrying with auto-corrective agent...")
                        
                        try:
                            corrected_response = agent.generate_query(user_query, error_info=str(db_err))
                            corrected_sql = format_sql_vertical(corrected_response.sql_query)
                            
                            st.markdown("### 🛠️ Self-Corrected SQL Syntax")
                            st.code(corrected_sql, language="sql")
                            
                            results_df = db_mgr.execute_read_query(corrected_sql)
                            st.success("Self-correction loop was successful! Retrieved data successfully.")
                            st.info(f"Correction Log: {corrected_response.reasoning}")
                            
                            col1, col2 = st.columns([1, 1])
                            with col1:
                                st.write("### 📋 Execution Matrix Results")
                                if results_df.empty:
                                    st.warning("Query produced empty rows.")
                                else:
                                    st.dataframe(results_df, use_container_width=True)
                            with col2:
                                if not results_df.empty:
                                    render_dynamic_visuals(results_df, user_query)
                        except Exception as correction_err:
                            st.error(f"Database Query Fault: {db_err}")
                            st.error(f"Correction Agent Attempt also failed: {correction_err}")
                            
            except Exception as agent_err:
                st.error(f"Evaluation loop failure: {agent_err}")
    else:
        st.warning("Please input a natural language request first.")

# --- HUMAN IN THE LOOP VERIFICATION OVERRIDES ---
if st.session_state.requires_approval:
    st.divider()
    st.warning("⚠️ **Human-in-the-Loop Safeguard Activated**")
    st.markdown("This statement contains administrative database mutation functions and requires review.")
    
    edited_sql = st.text_area(
        "Inspect and Edit Target SQL Statement:",
        value=st.session_state.pending_sql,
        height=180
    )
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Confirm Override Execution", use_container_width=True):
            try:
                safety_check = db_mgr.check_query_safety(edited_sql)
                if safety_check["is_safe"]:
                    res = db_mgr.execute_read_query(edited_sql)
                    st.success("Override completed successfully.")
                    st.dataframe(res, use_container_width=True)
                else:
                    impact = db_mgr.execute_destructive_query(edited_sql)
                    st.success(f"Mutation array applied! Impacted row index total: {impact}")
                
                st.session_state.requires_approval = False
            except Exception as ex:
                st.error(f"Execution failure on override: {ex}")
    with c2:
        if st.button("❌ Drop Statement", use_container_width=True):
            st.session_state.requires_approval = False
            st.info("Execution sequence dropped safely.")