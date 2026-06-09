import os
from dotenv import load_dotenv

load_dotenv()

# Groq API
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = "llama-3.3-70b-versatile"

# Embedding model
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

# Vector store
PERSIST_DIR = "./storage/chroma_db"
COLLECTION_NAME = "pdf_collection"

# Chunking
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

# Retrieval
TOP_K = 20

# Paths
TEMP_DIR = "./temp"
UPLOAD_DIR = "./uploads"  # ← TAMBAHKAN INI
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)