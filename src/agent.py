import json

import os

from pydantic import BaseModel, Field

from google import genai

from google.genai import types

from src.vector_store import SchemaVectorStore



# Get absolute path for local import safety

try:

    import streamlit as st

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

except ImportError:

    api_key = os.environ.get("GEMINI_API_KEY")



# Initialize GenAI Client

genai_client = genai.Client(api_key=api_key)



class SQLAgentResponse(BaseModel):

    """

    Enforces a strict, type-safe output matrix from Gemini,

    completely removing markdown code blocks or stray chat formatting.

    """

    reasoning: str = Field(description="Step-by-step logic detailing table choices, constraint mappings, or correction reasoning if correcting a previous error.")

    sql_query: str = Field(description="The clean, directly executable SQL query string.")

    confidence_score: str = Field(description="Must evaluate to 'HIGH' for safe SELECT strings, or 'LOW' for DML mutations like UPDATE/DELETE.")





class AnalyticsAgent:

    def __init__(self, db_history_path: str = "./chroma_db", db_path: str = "./data/ecommerce.db"):

        """Connects your core generation brain to the Schema RAG vector indexer and live DB."""

        self.vector_store = SchemaVectorStore(db_path=db_history_path)

        self.model_name = "gemini-2.5-flash"  # Highly responsive analytical model

       

        # Connect directly to DatabaseManager for live schema checks

        from src.database import DatabaseManager

        self.db_mgr = DatabaseManager(db_path=db_path)



    def build_system_instruction(self, schemas: list, examples: list, error_info: str = None) -> str:

        """Assembles operational instructions dynamically embedding your live database structures."""

        schema_context = "\n\n".join(schemas) if schemas else "No structural schemas found."

       

        example_context = ""

        for i, ex in enumerate(examples):

            example_context += f"\nExample {i+1}:\nUser Query: {ex['question']}\nTarget SQL: {ex['sql']}\n"

       

        instruction = f"""

You are an Elite Text-to-SQL Analytics backend engine. Your task is to generate highly accurate SQL statements based on a user's natural language request, the live verified table structures, and baseline historical examples.



[LIVE REAL-TIME DATABASE SCHEMAS (GUARANTEED CORRECT AND ACTIVE)]

{schema_context}



[HISTORICAL FEW-SHOT EXAMPLES]

{example_context}

"""



        if error_info:

            instruction += f"""

[CRITICAL: SELF-HEALING INSTRUCTION]

Your previous SQL attempt failed with this exact database runtime error:

👉 "{error_info}"



Analyze the live schemas carefully. Ensure all tables, column names, join clauses, and logic expressions are corrected to resolve this execution fault. Explain your fix in the reasoning field.

"""



        instruction += """

[CRITICAL DIRECTIVES]

1. Respond strictly matching the structural layout required by the schema. Do not output conversational introductory filler.

2. Do not wrap the code inside markdown fences (like ```sql).

3. If the user prompt asks to alter data (DELETE, UPDATE, INSERT, DROP), force the confidence_score field to output 'LOW' to trigger human review filters.

4. IMPORTANT: Always format the generated SQL query vertically with clear line breaks and indentation. Capitalize all standard SQL keywords (SELECT, FROM, JOIN, ON, WHERE, GROUP BY, ORDER BY, LIMIT, SUM, COUNT, AVG) to ensure maximum readability. Place each column, table join, and condition statement on its own vertical line, indented by 4 spaces.

"""

        return instruction



    def generate_query(self, user_prompt: str, error_info: str = None) -> SQLAgentResponse:

        """

        Coordinates the Schema RAG execution loop:

        1. Calls DatabaseManager to fetch the true live schema.

        2. Calls ChromaDB safely to fetch matching example contexts.

        3. Compiles system instruction (including self-healing logs if active).

        4. Returns a validated, correct Pydantic object.

        """

        few_shot_examples = []

        try:

            # Safely query 1 table and 1 example to satisfy chromaDB limits

            context = self.vector_store.retrieve_relevant_context(user_prompt, n_tables=1, n_examples=1)

            few_shot_examples = context.get("few_shot_examples", [])

        except Exception:

            few_shot_examples = []

       

        # Grab the exact real-time schemas living in SQLite

        live_schema = self.db_mgr.get_database_schema_prompt()

       

        # Assemble structured system prompts

        system_instruction = self.build_system_instruction(

            schemas=[live_schema],

            examples=few_shot_examples,

            error_info=error_info

        )

       

        # Run content generation with strict JSON schema format

        response = genai_client.models.generate_content(

            model=self.model_name,

            contents=user_prompt,

            config=types.GenerateContentConfig(

                system_instruction=system_instruction,

                temperature=0.1,  # Highly deterministic

                response_mime_type="application/json",

                response_schema=SQLAgentResponse,

            ),

        )

       

        return response.parsed