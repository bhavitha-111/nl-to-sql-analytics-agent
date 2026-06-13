"""
Database utility layer for the NL-to-SQL Analytics Agent.

Handles SQLite connection management, automatic mock-data seeding,
schema introspection, and read-only query execution with security guardrails.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
from faker import Faker

# Destructive SQL keywords blocked before any query reaches the database.
_BLOCKED_KEYWORDS = frozenset(
    {"DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE"}
)

# Default location for the e-commerce SQLite database.
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ecommerce.db"


class DatabaseManager:
    """Manages SQLite connections, schema metadata, and safe read-only queries."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.db_path.exists():
            self._initialize_mock_database()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Return a new SQLite connection to the configured database."""
        return sqlite3.connect(self.db_path)

    # ------------------------------------------------------------------
    # Mock database seeding
    # ------------------------------------------------------------------

    def _initialize_mock_database(self) -> None:
        """
        Create and seed the e-commerce database with realistic mock records.

        Runs automatically when ecommerce.db is missing. Uses Faker to
        generate interconnected users, products, and orders.
        """
        fake = Faker()
        Faker.seed(42)

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                sign_up_date DATE NOT NULL
            );

            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                stock_count INTEGER NOT NULL
            );

            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                order_date DATE NOT NULL,
                quantity INTEGER NOT NULL,
                total_amount REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
            """
        )

        categories = [
            "Electronics",
            "Clothing",
            "Home & Garden",
            "Sports",
            "Books",
            "Beauty",
            "Toys",
            "Food & Beverage",
        ]

        # Seed users
        users = []
        for user_id in range(1, 51):
            sign_up = fake.date_between(start_date="-2y", end_date="today")
            users.append(
                (
                    user_id,
                    fake.name(),
                    fake.unique.email(),
                    sign_up.isoformat(),
                )
            )
        cursor.executemany(
            "INSERT INTO users (id, name, email, sign_up_date) VALUES (?, ?, ?, ?)",
            users,
        )

        # Seed products
        products = []
        for product_id in range(1, 31):
            category = fake.random_element(categories)
            price = round(fake.pyfloat(min_value=5.0, max_value=500.0), 2)
            stock = fake.random_int(min=0, max=500)
            products.append(
                (
                    product_id,
                    fake.catch_phrase(),
                    category,
                    price,
                    stock,
                )
            )
        cursor.executemany(
            "INSERT INTO products (id, product_name, category, price, stock_count) "
            "VALUES (?, ?, ?, ?, ?)",
            products,
        )

        # Seed orders with valid foreign keys and computed totals
        product_prices = {p[0]: p[3] for p in products}
        orders = []
        for order_id in range(1, 201):
            user_id = fake.random_int(min=1, max=50)
            product_id = fake.random_int(min=1, max=30)
            quantity = fake.random_int(min=1, max=5)
            unit_price = product_prices[product_id]
            total_amount = round(unit_price * quantity, 2)
            order_date = fake.date_between(start_date="-1y", end_date="today")
            orders.append(
                (
                    order_id,
                    user_id,
                    product_id,
                    order_date.isoformat(),
                    quantity,
                    total_amount,
                )
            )
        cursor.executemany(
            "INSERT INTO orders "
            "(id, user_id, product_id, order_date, quantity, total_amount) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            orders,
        )

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    def get_schema_info(self) -> str:
        """
        Fetch every table's name and column definitions via PRAGMA table_info.

        Returns clean text metadata suitable for LLM context injection.
        """
        conn = self._get_connection()
        try:
            tables_df = pd.read_sql_query(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name",
                conn,
            )

            lines: list[str] = []
            for table_name in tables_df["name"].tolist():
                pragma_df = pd.read_sql_query(
                    f"PRAGMA table_info({table_name})",
                    conn,
                )
                lines.append(f"TABLE: {table_name}")
                for _, row in pragma_df.iterrows():
                    col_type = row["type"] or "TEXT"
                    pk_flag = " PRIMARY KEY" if row["pk"] else ""
                    not_null = " NOT NULL" if row["notnull"] else ""
                    lines.append(
                        f"  - {row['name']} {col_type}{pk_flag}{not_null}"
                    )
                lines.append("")

            return "\n".join(lines).strip()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Security guardrail
    # ------------------------------------------------------------------

    @staticmethod
    def _contains_destructive_keywords(sql_query: str) -> Optional[str]:
        """
        Scan the query for blocked destructive SQL keywords.

        Returns a descriptive violation message if a keyword is found,
        otherwise None.
        """
        # Strip single-line and block comments before scanning.
        cleaned = re.sub(r"--.*?$", "", sql_query, flags=re.MULTILINE)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)

        for keyword in _BLOCKED_KEYWORDS:
            # Word-boundary match avoids false positives (e.g., "created_at").
            pattern = rf"\b{keyword}\b"
            if re.search(pattern, cleaned, re.IGNORECASE):
                return (
                    f"Security violation: query contains blocked keyword "
                    f"'{keyword}'. Only read-only SELECT queries are permitted."
                )
        return None

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def execute_query(self, sql_query: str) -> Tuple[Optional[pd.DataFrame], str]:
        """
        Execute a read-only SQL query and return results as a DataFrame.

        Returns:
            (DataFrame, message) on success — message is empty string.
            (None, error_message) on failure — security block or SQL error.
        """
        if not sql_query or not sql_query.strip():
            return None, "No SQL query provided."

        violation = self._contains_destructive_keywords(sql_query)
        if violation:
            return None, violation

        conn = self._get_connection()
        try:
            df = pd.read_sql_query(sql_query, conn)
            return df, ""
        except Exception as exc:
            # Surface SQLite operational errors to the agent for self-correction.
            return None, str(exc)
        finally:
            conn.close()
