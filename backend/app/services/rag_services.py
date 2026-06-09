# backend/app/services/rag_services.py

import os
import chromadb
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.llms.groq import Groq
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.storage.storage_context import StorageContext
from llama_index.core.prompts import PromptTemplate
from typing import Dict, Optional, List
from collections import defaultdict

from app.core.config import (
    GROQ_API_KEY, MODEL_NAME, EMBEDDING_MODEL, 
    TOP_K, PERSIST_DIR, COLLECTION_NAME
)
from app.services.utils import normalize_slang


# ==================================================
# GROUPED RETRIEVER (Bisa baca semua file)
# ==================================================
class GroupedRetriever:
    """Retriever yang ambil top chunk dari SETIAP file"""
    def __init__(self, index, similarity_top_k: int = 30, chunks_per_file: int = 3):
        self.index = index
        self.similarity_top_k = similarity_top_k
        self.chunks_per_file = chunks_per_file
    
    def retrieve(self, query: str):
        retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=self.similarity_top_k,
        )
        all_nodes = retriever.retrieve(query)
        
        # Group berdasarkan file
        grouped = defaultdict(list)
        for node in all_nodes:
            file_name = node.node.metadata.get("file_name", "unknown")
            grouped[file_name].append(node)
        
        # Ambil top chunk per file
        final_nodes = []
        for file_name, nodes in grouped.items():
            nodes.sort(key=lambda x: x.score, reverse=True)
            final_nodes.extend(nodes[:self.chunks_per_file])
        
        # Urutkan lagi berdasarkan score
        final_nodes.sort(key=lambda x: x.score, reverse=True)
        
        return final_nodes


# ==================================================
# RAG SERVICE
# ==================================================
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
        """Load index dari ChromaDB"""
        try:
            print(f"[RAG] Loading index for user {self.user_id} from {PERSIST_DIR}")
            
            # Cek apakah folder persist ada
            if not os.path.exists(PERSIST_DIR):
                print(f"[RAG] Persist dir {PERSIST_DIR} not found")
                return None
            
            # Coba connect ke ChromaDB
            chroma_client = chromadb.PersistentClient(path=PERSIST_DIR)
            
            # Cek apakah collection ada
            try:
                chroma_collection = chroma_client.get_collection(self.user_collection)
                print(f"[RAG] Collection {self.user_collection} found")
            except Exception as e:
                print(f"[RAG] Collection not found: {e}")
                return None
            
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            
            index = VectorStoreIndex.from_vector_store(
                vector_store,
                embed_model=self.embed_model,
                storage_context=storage_context
            )
            
            print(f"[RAG] Index loaded successfully for user {self.user_id}")
            return index
            
        except Exception as e:
            print(f"[RAG] Error loading index: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def has_documents(self) -> bool:
        """Cek apakah user punya dokumen"""
        if self.index is not None:
            return True
        
        # Coba load ulang
        self.index = self._load_index()
        return self.index is not None
    
    def ask(self, question: str) -> Dict:
        if not self.has_documents():
            return {
                "answer": "📭 Belum ada dokumen yang diupload. Silakan upload PDF terlebih dahulu.",
                "sources": []
            }
        
        normalized_question = normalize_slang(question)
        
        # PAKE GROUPED RETRIEVER (biar semua file kebaca)
        retriever = GroupedRetriever(
            index=self.index,
            similarity_top_k=30,
            chunks_per_file=3
        )
        
        qa_prompt = PromptTemplate(
            """\
Kamu adalah asisten AI analisis dokumen.
Jawab berdasarkan KONTEKS DOKUMEN di bawah.

KONTEKS:
{context_str}

PERTANYAAN: {query_str}

JAWABAN:"""
        )
        
        synthesizer = get_response_synthesizer(
            llm=self.llm,
            text_qa_template=qa_prompt,
            response_mode="compact",
        )
        
        # Buat query engine pake retriever
        nodes = retriever.retrieve(normalized_question)
        
        # Gabungkan context dari nodes
        context = "\n\n".join([n.node.text for n in nodes[:10]])
        
        # Panggil LLM langsung
        prompt = qa_prompt.format(context_str=context, query_str=normalized_question)
        response = self.llm.complete(prompt)
        
        # Extract sources
        sources = []
        seen = set()
        for node in nodes[:5]:
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
            "answer": response.text,
            "sources": sources
        }
    
    def ask_stream(self, question: str):
        """Streaming version"""
        if not self.has_documents():
            yield "📭 Belum ada dokumen yang diupload. Silakan upload PDF terlebih dahulu."
            return
        
        result = self.ask(question)
        answer = result["answer"]
        
        for word in answer.split():
            yield word + " "
    
    def get_documents_info(self) -> List[Dict]:
        """Get list of documents that have been processed"""
        if not self.has_documents():
            return []
        
        retriever = GroupedRetriever(index=self.index, similarity_top_k=100)
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