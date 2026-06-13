import re
from google import genai
from src.database import DatabaseManager

class NLToSQLAgent:
    def __init__(self, db_manager: DatabaseManager, api_key: str):
        """Initializes the agent with the database and the Google GenAI Client."""
        self.db = db_manager
        # Initialize the canonical Google GenAI client
        self.client = genai.Client(api_key=api_key)

    def generate_sql(self, user_question: str, schema: str, past_error: str = None) -> str:
        """Prompts Gemini to generate a valid SQLite query based on schema context."""
        error_context = ""
        if past_error:
            error_context = f"\nCRITICAL: Your previous SQL query failed with this SQLite error: {past_error}. Please correct the syntax and logic errors."

        prompt = f"""
        You are an expert Data Engineer specializing in SQLite optimization.
        Given the database schema details below, generate a functional SQL query to fulfill the user's request.
        
        Database Schema:
        {schema}
        
        User Request: "{user_question}"
        {error_context}
        
        Formatting & Constraints:
        1. Output ONLY the raw executable SQL query string.
        2. Do not include markdown wraps (like ```sql) or trailing punctuation.
        3. Ensure all columns referenced exist explicitly in the provided schema.
        """
        
        # Using Gemini 2.5 Flash for rapid and accurate code inference
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()

    def run(self, user_question: str, max_retries: int = 3):
        """Runs the self-correction agent execution loop."""
        schema = self.db.get_schema_info()
        past_error = None
        
        for attempt in range(max_retries):
            try:
                # 1. Ask the model for SQL
                sql_query = self.generate_sql(user_question, schema, past_error)
                
                # Regex fallback clean up if the LLM ignores instructions and outputs Markdown blocks
                if "```" in sql_query:
                    sql_query = re.sub(r"```(sql)?", "", sql_query).strip()
                
                # 2. Test execute the query against the database manager
                df, error = self.db.execute_query(sql_query)
                
                if error:
                    # Capture syntax error string and retry the loop
                    past_error = error
                else:
                    # Success: Return the query and result package to the dashboard
                    return sql_query, df, None
                    
            except Exception as e:
                past_error = str(e)
                
        return None, None, f"Unable to generate a valid SQL query after {max_retries} attempts. Last error: {past_error}"