# src/chat.py - COMPLETE FIX
from llama_index.core import VectorStoreIndex
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import VectorIndexRetriever, BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.llms.groq import Groq
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.chat_engine import ContextChatEngine
from llama_index.core.prompts import PromptTemplate
from collections import defaultdict
from typing import List
import logging

from core.config import GROQ_API_KEY, TOP_K, MODEL_NAME
from services.utils import normalize_slang

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GroupedRetriever(BaseRetriever):
    """
    Retriever yang mengambil 3 chunk terbaik dari SETIAP file
    """
    def __init__(self, index: VectorStoreIndex, similarity_top_k: int = 30):
        self._index = index
        self._similarity_top_k = similarity_top_k
        super().__init__()
    
    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        # Ambil banyak chunk
        temp_retriever = VectorIndexRetriever(
            index=self._index,
            similarity_top_k=self._similarity_top_k,
        )
        all_nodes = temp_retriever._retrieve(query_bundle)
        
        logger.info(f"Total nodes retrieved: {len(all_nodes)}")
        
        # Group berdasarkan file
        grouped_by_file = defaultdict(list)
        for node in all_nodes:
            file_name = node.node.metadata.get("file_name", "unknown")
            grouped_by_file[file_name].append(node)
        
        logger.info(f"Files found: {list(grouped_by_file.keys())}")
        
        final_nodes = []
        CHUNKS_PER_FILE = 3  # Ambil 3 chunk terbaik dari setiap file
        
        for file_name, nodes in grouped_by_file.items():
            # Urutkan dalam file ini
            nodes.sort(key=lambda x: x.score, reverse=True)
            # Ambil top chunks
            top_chunks = nodes[:CHUNKS_PER_FILE]
            final_nodes.extend(top_chunks)
            logger.info(f"  {file_name}: {len(top_chunks)} chunks (total {len(nodes)} available)")
        
        # Urutkan final berdasarkan score
        final_nodes.sort(key=lambda x: x.score, reverse=True)
        
        logger.info(f"Final nodes: {len(final_nodes)} from {len(grouped_by_file)} files")
        
        return final_nodes


class RAGChatbot:
    def __init__(self, index: VectorStoreIndex, username: str = None):
        self.index = index
        self.username = username
        self.top_k = TOP_K
        
        self.llm = Groq(
            model=MODEL_NAME,
            api_key=GROQ_API_KEY,
            temperature=0.1,
        )
        
        # Retriever yang ambil banyak chunk dari setiap file
        self.retriever = GroupedRetriever(
            index=self.index,
            similarity_top_k=self.top_k * 4,  # Ambil banyak untuk grouping
        )
        
        # Prompt yang lebih baik
        self.qa_prompt = PromptTemplate(
            """\
Kamu adalah asisten AI analisis dokumen. Jawab berdasarkan KONTEKS yang diberikan.

KONTEKS DOKUMEN:
---------------------
{context_str}
---------------------

PERTANYAAN: {query_str}

INSTRUKSI:
1. Jawab HANYA dari konteks di atas
2. Jika konteks kosong atau tidak relevan, katakan "Informasi tidak ditemukan"
3. Jika pertanyaan tentang file tertentu, cari di konteks dengan nama file tersebut

JAWABAN:"""
        )
        
        self.synthesizer = get_response_synthesizer(
            llm=self.llm,
            text_qa_template=self.qa_prompt,
            response_mode="compact",
        )
        
        self.query_engine = RetrieverQueryEngine(
            retriever=self.retriever,
            response_synthesizer=self.synthesizer,
        )
        
        self.memory = ChatMemoryBuffer.from_defaults(token_limit=4000)
        
        system_prompt = """\
Kamu adalah asisten AI analisis dokumen. 
Kamu HANYA boleh menjawab berdasarkan dokumen PDF yang diunggah oleh user.
Jika informasi tidak ada di dokumen, katakan "Informasi tidak ditemukan dalam dokumen".
"""
        
        self.chat_engine = ContextChatEngine.from_defaults(
            retriever=self.retriever,
            llm=self.llm,
            memory=self.memory,
            system_prompt=system_prompt,
        )
    
    def ask(self, question: str) -> dict:
        normalized_question = normalize_slang(question)
        
        logger.info(f"Question: {normalized_question[:100]}")
        
        response = self.chat_engine.chat(normalized_question)
        answer = response.response
        
        source_nodes = getattr(response, "source_nodes", [])
        if not source_nodes:
            source_nodes = self.retriever.retrieve(normalized_question)
        
        unique_files = set()
        sources = []
        for item in source_nodes[:10]:
            node = item.node if hasattr(item, "node") else item
            file_name = node.metadata.get("file_name", "Unknown")
            unique_files.add(file_name)
            sources.append({
                "content": node.text[:300] + "...",
                "source": file_name,
                "page": node.metadata.get("page_label", node.metadata.get("page", "?")),
            })
        
        logger.info(f"Files used: {unique_files}")
        
        return {"answer": answer, "sources": sources}
    
    def clear_memory(self):
        self.chat_engine.reset()
        self.memory.reset()