import json
import os
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from src.vector_store import SchemaVectorStore

# --- WIN/POWERSHELL SECRET FALLBACK OVERRIDE ---
try:
    import streamlit as st
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
except ImportError:
    api_key = os.environ.get("GEMINI_API_KEY")

# Initialize the official modern Google GenAI Client with the verified key fallback
genai_client = genai.Client(api_key=api_key)

class SQLAgentResponse(BaseModel):
    """
    Enforces a strict, type-safe output matrix from Gemini, 
    completely removing markdown code blocks or stray chat formatting.
    """
    reasoning: str = Field(description="Step-by-step logic detailing table choices and constraint mappings.")
    sql_query: str = Field(description="The clean, directly executable SQL query string.")
    confidence_score: str = Field(description="Must evaluate to 'HIGH' for safe SELECT strings, or 'LOW' for DML mutations like UPDATE/DELETE.")


class AnalyticsAgent:
    def __init__(self, db_history_path: str = "./chroma_db"):
        """Connects your core generation brain to the Schema RAG vector indexer."""
        self.vector_store = SchemaVectorStore(db_path=db_history_path)
        self.model_name = "gemini-2.5-flash"  # Highly responsive analytical model

    def build_system_instruction(self, schemas: list, examples: list) -> str:
        """Assembles operational instructions dynamically embedding your vector contexts."""
        schema_context = "\n\n".join(schemas) if schemas else "No structural schemas found."
        
        example_context = ""
        for i, ex in enumerate(examples):
            example_context += f"\nExample {i+1}:\nUser Query: {ex['question']}\nTarget SQL: {ex['sql']}\n"
        
        instruction = f"""
You are an Elite Text-to-SQL Analytics backend engine. Your task is to generate highly accurate SQL statements based on a user's natural language request, the injected table structures, and baseline historical examples.

[DYNAMIC INJECTED E-COMMERCE DATABASE STRUCTURAL SCHEMAS]
{schema_context}

[HISTORICAL FEW-SHOT EXAMPLES]
{example_context}

[CRITICAL DIRECTIVES]
1. Respond strictly matching the structural layout required by the schema. Do not output conversational introductory filler.
2. Do not wrap the code inside markdown fences (like ```sql).
3. If the user prompt asks to alter data (DELETE, UPDATE, INSERT, DROP), force the confidence_score field to output 'LOW' to trigger human review filters.
4. IMPORTANT: Always format the generated SQL query vertically with clear line breaks and indentation. Capitalize all standard SQL keywords (SELECT, FROM, JOIN, ON, WHERE, GROUP BY, ORDER BY, LIMIT, SUM, COUNT, AVG) to ensure maximum readability. Place each column, table join, and condition statement on its own vertical line, indented by 4 spaces.
"""
        return instruction

    def generate_query(self, user_prompt: str) -> SQLAgentResponse:
        """
        Coordinates the Schema RAG execution loop:
        1. Calls ChromaDB to fetch matching tables & examples.
        2. Compiles a custom, isolated system instruction.
        3. Returns a validated Pydantic object.
        """
        # Step 1: Search the vector store for matching components
        context = self.vector_store.retrieve_relevant_context(user_prompt, n_tables=2, n_examples=1)
        
        # Step 2: Assemble the structured system prompt
        system_instruction = self.build_system_instruction(
            schemas=context["matched_schemas"],
            examples=context["few_shot_examples"]
        )
        
        # Step 3: Run structured execution via the Google GenAI library
        response = genai_client.models.generate_content(
            model=self.model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,  # Forces highly deterministic, code-stable generation
                response_mime_type="application/json",
                response_schema=SQLAgentResponse,
            ),
        )
        
        # Automatically unpacks into the Pydantic type layout
        return response.parsed