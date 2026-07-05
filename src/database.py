import sqlite3
import pandas as pd
import re

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