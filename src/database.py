import sqlite3

import pandas as pd

import re

from typing import Dict, List, Tuple



class DatabaseManager:

    def __init__(self, db_path: str = "./data/ecommerce.db"):

        """

        Initializes the manager targeting your active e-commerce database

        from your existing project workspace.

        """

        self.db_path = db_path



    def check_query_safety(self, sql_query: str) -> dict:

        """

        Statically checks a query text string to spot dangerous or

        data-modifying execution paths before they run.

        """

        clean_query = sql_query.strip().upper()

       

        # Keywords that alter database schema or change existing table values

        destructive_keywords = ["DELETE", "DROP", "UPDATE", "ALTER", "INSERT", "REPLACE", "TRUNCATE"]

       

        # Detect word boundaries to ensure keywords aren't accidentally matched inside column names

        is_destructive = any(re.search(rf"\b{keyword}\b", clean_query) for keyword in destructive_keywords)

       

        return {

            "is_safe": not is_destructive,

            "detected_action": "READ" if not is_destructive else "MODIFY/DESTRUCTIVE"

        }



    def execute_read_query(self, sql_query: str) -> pd.DataFrame:

        """

        Executes safe analytical SELECT strings and transforms the database

        rows directly into an organized, scannable Pandas DataFrame matrix.

        """

        safety_status = self.check_query_safety(sql_query)

        if not safety_status["is_safe"]:

            raise PermissionError(

                f"Execution Blocked: Read-only mode active. "

                f"Detected action profile: {safety_status['detected_action']}"

            )



        # Connect directly to your e-commerce sqlite instance

        with sqlite3.connect(self.db_path) as conn:

            df = pd.read_sql_query(sql_query, conn)

            return df



    def execute_destructive_query(self, sql_query: str) -> int:

        """

        Executes modification scripts exclusively after an administrator

        manually triggers an override on the Streamlit screen layout.

        """

        with sqlite3.connect(self.db_path) as conn:

            cursor = conn.cursor()

            cursor.execute(sql_query)

            conn.commit()

            return cursor.rowcount  # Returns how many database rows were modified



    def get_existing_tables(self) -> List[str]:

        """

        Queries the SQLite master table to discover the real names of

        all user tables currently initialized in the database.

        """

        query = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"

        try:

            with sqlite3.connect(self.db_path) as conn:

                cursor = conn.cursor()

                cursor.execute(query)

                tables = [row[0] for row in cursor.fetchall()]

                return tables

        except sqlite3.Error as e:

            print(f"Error scanning database tables: {e}")

            return []



    def get_database_schema_prompt(self) -> str:

        """

        Dynamically extracts the DDL (Data Definition Language) schemas

        for all existing tables in the database.

        """

        tables = self.get_existing_tables()

        if not tables:

            return "No tables found in the database. Check if the database path is correct or database is initialized."



        schema_details = []

        with sqlite3.connect(self.db_path) as conn:

            cursor = conn.cursor()

            for table_name in tables:

                # Query the exact CREATE TABLE statement saved by SQLite

                cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}';")

                create_statement_row = cursor.fetchone()

               

                if create_statement_row and create_statement_row[0]:

                    schema_details.append(create_statement_row[0])

               

                # Sample 2 rows so the LLM understands actual data formats

                try:

                    df_sample = pd.read_sql_query(f"SELECT * FROM {table_name} LIMIT 2", conn)

                    if not df_sample.empty:

                        sample_str = f"/* Sample rows from table {table_name}:\n{df_sample.to_string(index=False)}\n*/"

                        schema_details.append(sample_str)

                except Exception:

                    pass # Silently skip samples if table is empty or error occurs

                   

        return "\n\n".join(schema_details)