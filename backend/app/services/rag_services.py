# backend/app/services/rag_service.py
import os
import chromadb
from typing import Dict, Optional, List  # ← TAMBAHKAN List di sini
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.llms.groq import Groq
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.storage.storage_context import StorageContext
from llama_index.core.prompts import PromptTemplate

from app.core.config import (
    GROQ_API_KEY, MODEL_NAME, EMBEDDING_MODEL, 
    TOP_K, PERSIST_DIR, COLLECTION_NAME
)
from app.services.utils import normalize_slang


class RAGService:
    def __init__(self, user_id: int, index: VectorStoreIndex = None):
        self.user_id = user_id
        self.user_collection = f"{COLLECTION_NAME}_user_{user_id}"
        
        self.embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
        Settings.embed_model = self.embed_model
        
        self.llm = Groq(
            model=MODEL_NAME,
            api_key=GROQ_API_KEY,
            temperature=0.1,
        )
        
        # PAKE INDEX YANG DIKASIH ATAU LOAD SENDIRI
        if index is not None:
            self.index = index
        else:
            self.index = self._load_index()
    
    def _load_index(self) -> Optional[VectorStoreIndex]:
        try:
            chroma_client = chromadb.PersistentClient(path=PERSIST_DIR)
            try:
                chroma_collection = chroma_client.get_collection(self.user_collection)
            except:
                return None
            
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            
            return VectorStoreIndex.from_vector_store(
                vector_store,
                embed_model=self.embed_model,
                storage_context=storage_context
            )
        except Exception as e:
            print(f"Error loading index: {e}")
            return None
    
    def has_documents(self) -> bool:
        return self.index is not None
    
    def ask(self, question: str) -> Dict:
        if not self.has_documents():
            return {
                "answer": "📭 Belum ada dokumen yang diupload. Silakan upload PDF terlebih dahulu.",
                "sources": []
            }
        
        normalized_question = normalize_slang(question)
        
        qa_prompt = PromptTemplate(
            """\
Kamu adalah asisten AI analisis dokumen.
Jawab berdasarkan KONTEKS DOKUMEN di bawah.

KONTEKS:
{context_str}

PERTANYAAN: {query_str}

JAWABAN:"""
        )
        
        retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=TOP_K,
        )
        
        synthesizer = get_response_synthesizer(
            llm=self.llm,
            text_qa_template=qa_prompt,
            response_mode="compact",
        )
        
        query_engine = RetrieverQueryEngine(
            retriever=retriever,
            response_synthesizer=synthesizer,
        )
        
        response = query_engine.query(normalized_question)
        
        sources = []
        seen = set()
        for node in response.source_nodes[:5]:
            file_name = node.node.metadata.get("file_name", "Unknown")
            page = node.node.metadata.get("page_label", "?")
            key = f"{file_name}_{page}"
            if key not in seen:
                seen.add(key)
                sources.append({
                    "source": file_name,
                    "page": page,
                    "content": node.node.text[:200] + "..."
                })
        
        return {
            "answer": str(response),
            "sources": sources
        }
    
    def ask_stream(self, question: str):
        """
        Streaming version of ask - yields token by token
        """
        if not self.has_documents():
            yield "📭 Belum ada dokumen yang diupload. Silakan upload PDF terlebih dahulu."
            return
        
        result = self.ask(question)
        answer = result["answer"]
        
        # Stream token by token
        for word in answer.split():
            yield word + " "
    
    def get_documents_info(self) -> List[Dict]:
        """Get list of documents that have been processed"""
        if not self.has_documents():
            return []
        
        # Try to get unique file names from index
        retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=100,
        )
        
        try:
            # Dummy query to get nodes
            nodes = retriever.retrieve(" ")
            files = {}
            
            for node in nodes:
                file_name = node.node.metadata.get("file_name", "Unknown")
                if file_name not in files:
                    files[file_name] = {
                        "name": file_name,
                        "pages": set()
                    }
                page = node.node.metadata.get("page_label", node.node.metadata.get("page"))
                if page:
                    files[file_name]["pages"].add(page)
            
            return [
                {
                    "name": f["name"],
                    "pages": len(f["pages"])
                }
                for f in files.values()
            ]
        except:
            return []