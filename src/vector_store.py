import os
import sqlite3
import chromadb
# Import types directly from the top-level chromadb module to avoid deprecated types namespaces
from chromadb import EmbeddingFunction, Documents, Embeddings
from google import genai

try:
    import streamlit as st
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
except ImportError:
    api_key = os.environ.get("GEMINI_API_KEY")

# Initialize the official modern Google GenAI Client with the verified key fallback
genai_client = genai.Client(api_key=api_key)


class GeminiEmbeddingFunction(EmbeddingFunction):
    """
    Custom ChromaDB Embedding Function utilizing the official
    google-genai SDK and stable gemini-embedding-001 model.
    """
    def __init__(self, model_name: str = "gemini-embedding-001"):
        self.model_name = model_name

    def __call__(self, input_texts: Documents) -> Embeddings:
        # Generate vectors using the active Google API endpoint
        response = genai_client.models.embed_content(
            model=self.model_name,
            contents=input_texts
        )
        return [embedding.values for embedding in response.embeddings]


class SchemaVectorStore:
    def __init__(self, db_path: str = "./chroma_db"):
        """Initializes ChromaDB client and registers the embedding function."""
        self.chroma_client = chromadb.PersistentClient(path=db_path)
        self.embedding_function = GeminiEmbeddingFunction()
        
        # Setup specific collections for structural schemas and golden examples
        self.schema_collection = self.chroma_client.get_or_create_collection(
            name="database_schemas",
            embedding_function=self.embedding_function
        )
        self.example_collection = self.chroma_client.get_or_create_collection(
            name="golden_queries",
            embedding_function=self.embedding_function
        )

    def extract_and_load_sqlite_schema(self, sqlite_db_path: str = "./data/ecommerce.db"):
        """
        Dynamically extracts table definitions (DDL) from your active e-commerce 
        database and loads them into the ChromaDB vector store.
        """
        if not os.path.exists(sqlite_db_path):
            print(f"⚠️ Target database not found at {sqlite_db_path}. Skipping dynamic schema extraction.")
            return

        conn = sqlite3.connect(sqlite_db_path)
        cursor = conn.cursor()
        
        # Query the catalog for user-defined e-commerce tables
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = cursor.fetchall()
        
        documents, metadatas, ids = [], [], []

        for table_name, ddl_script in tables:
            if ddl_script:
                documents.append(f"Table Name: {table_name}\nDDL Schema Definition:\n{ddl_script}")
                metadatas.append({"table_name": table_name, "type": "schema_ddl"})
                ids.append(f"schema_{table_name}")

        conn.close()

        if documents:
            self.schema_collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
            print(f"✅ Successfully vectorized and stored {len(documents)} table schemas from ecommerce.db.")

    def seed_golden_query_pairs(self):
        """Seeds textbook analytical examples to guide the generation engine loop."""
        examples = [
            {
                "question": "Show total revenue generated in the first quarter of 2026",
                "sql": "SELECT SUM(amount) FROM transactions WHERE transaction_date BETWEEN '2026-01-01' AND '2026-03-31';"
            },
            {
                "question": "Find the top 3 items with the highest sales volume",
                "sql": "SELECT product_name, COUNT(*) FROM order_items GROUP BY product_name ORDER BY COUNT(*) DESC LIMIT 3;"
            }
        ]

        documents = [ex["question"] for ex in examples]
        metadatas = [{"sql_query": ex["sql"]} for ex in examples]
        ids = [f"golden_ex_{i}" for i in range(len(examples))]

        self.example_collection.upsert(documents=documents, metadatas=metadatas, ids=ids)

    def retrieve_relevant_context(self, user_query: str, n_tables: int = 2, n_examples: int = 1) -> dict:
        """Queries the vector database to retrieve highly relevant schema contexts."""
        # Ensure database schemas are fully populated before running lookups
        self.extract_and_load_sqlite_schema()
        
        schema_results = self.schema_collection.query(query_texts=[user_query], n_results=n_tables)
        example_results = self.example_collection.query(query_texts=[user_query], n_results=n_examples)

        retrieved_context = {
            "matched_schemas": schema_results.get("documents", [[]])[0],
            "few_shot_examples": []
        }

        if example_results.get("documents") and example_results["documents"][0]:
            retrieved_context["few_shot_examples"].append({
                "question": example_results["documents"][0][0],
                "sql": example_results["metadatas"][0][0]["sql_query"]
            })

        return retrieved_context