"""
src/ingest.py - FIXED untuk multi-file PDF
Root cause: semua file digabung jadi 1 dokumen, metadata file hilang
Fix: setiap file tetap punya metadata file_name yang jelas di setiap node
"""

import os
import shutil
import gc
import time
from llama_index.core import Document, VectorStoreIndex, Settings
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.storage.storage_context import StorageContext
import chromadb

from app.core.config import (
    EMBEDDING_MODEL, CHUNK_SIZE, CHUNK_OVERLAP,
    PERSIST_DIR, TEMP_DIR, COLLECTION_NAME
)
from app.services.utils import clean_text


class PDFIngestor:
    def __init__(self, username: str = None):
        self.embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
        Settings.embed_model = self.embed_model

        self.parser = SimpleNodeParser.from_defaults(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )

        self._chroma_client = None
        self._chroma_collection = None
        self.username = username
        self.ocr_status = {}
        self.processed_files_cache = []

        self.upload_dir = "./uploads"
        os.makedirs(self.upload_dir, exist_ok=True)

    def _force_close_chroma(self):
        try:
            if self._chroma_client is not None:
                self._chroma_client = None
        except Exception:
            pass
        self._chroma_collection = None
        gc.collect()
        time.sleep(0.5)

    def _close_chroma(self):
        self._force_close_chroma()

    def _delete_storage_files(self):
        paths_to_delete = [PERSIST_DIR, "./chroma_db", "./storage"]
        for path in paths_to_delete:
            if not os.path.exists(path):
                continue
            for attempt in range(3):
                try:
                    shutil.rmtree(path)
                    break
                except PermissionError:
                    time.sleep(1)
                except Exception:
                    pass
        time.sleep(0.5)
        os.makedirs(PERSIST_DIR, exist_ok=True)

    def _get_fresh_client(self):
        self._delete_storage_files()
        self._chroma_client = chromadb.PersistentClient(path=PERSIST_DIR)
        return self._chroma_client

    def process_pdfs(self, uploaded_files, progress_callback=None) -> VectorStoreIndex:
        """
        🔥 FIXED: Setiap file diproses secara terpisah dan metadata file_name
        disimpan di SETIAP NODE, bukan cuma di dokumen parent.
        """
        self._force_close_chroma()
        self._delete_storage_files()

        os.makedirs(TEMP_DIR, exist_ok=True)
        os.makedirs(self.upload_dir, exist_ok=True)

        all_nodes = []
        total_files = len(uploaded_files)
        self.processed_files_cache = []

        for file_idx, uploaded_file in enumerate(uploaded_files):
            if progress_callback:
                progress_callback(file_idx, total_files, f"Memproses {uploaded_file.name}...")

            permanent_path = os.path.join(self.upload_dir, uploaded_file.name)
            temp_path = os.path.join(TEMP_DIR, uploaded_file.name)

            with open(permanent_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            try:
                from app.services.ocr_utils import extract_text_smart

                result = extract_text_smart(permanent_path)

                if result.get("error") or not result["text"].strip():
                    print(f"Skip {uploaded_file.name}: tidak ada teks")
                    continue

                self.ocr_status[uploaded_file.name] = {
                    "total_pages": result["total_pages"],
                    "pages_with_text": result["pages_with_text"],
                    "is_scanned": result["pages_with_text"] == 0
                }

                file_documents = []

                full_doc = Document(
                    text=clean_text(result["text"]),
                    metadata={
                        "file_name": uploaded_file.name,
                        "source": uploaded_file.name,
                        "total_pages": str(result["total_pages"]),
                        "page_label": "all",
                        "page": "all",
                        "file_index": str(file_idx),
                    }
                )
                file_documents.append(full_doc)

                for page_data in result["pages"]:
                    if not page_data["text"].strip():
                        continue
                    page_doc = Document(
                        text=clean_text(page_data["text"]),
                        metadata={
                            "file_name": uploaded_file.name,
                            "source": uploaded_file.name,
                            "page_label": str(page_data["page_num"]),
                            "page": str(page_data["page_num"]),
                            "total_pages": str(result["total_pages"]),
                            "file_index": str(file_idx),
                        }
                    )
                    file_documents.append(page_doc)

                file_nodes = self.parser.get_nodes_from_documents(file_documents)

                for node in file_nodes:
                    if "file_name" not in node.metadata or not node.metadata["file_name"]:
                        node.metadata["file_name"] = uploaded_file.name
                        node.metadata["source"] = uploaded_file.name

                all_nodes.extend(file_nodes)
                self.processed_files_cache.append(uploaded_file.name)

                print(f"✅ {uploaded_file.name}: {len(file_nodes)} nodes dibuat")

            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        if not all_nodes:
            raise ValueError("Tidak ada teks yang bisa diekstrak dari PDF yang diunggah.")

        files_in_nodes = set(n.metadata.get("file_name", "") for n in all_nodes)
        print(f"📊 Total nodes: {len(all_nodes)}")
        print(f"📁 File terwakili: {files_in_nodes}")

        chroma_client = self._get_fresh_client()
        chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
        self._chroma_collection = chroma_collection

        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        index = VectorStoreIndex(
            nodes=all_nodes,
            storage_context=storage_context,
            embed_model=self.embed_model,
            show_progress=True,
        )

        index.storage_context.persist(persist_dir=PERSIST_DIR)
        return index

    def process_pdfs_from_paths(self, file_paths: list) -> VectorStoreIndex:
        """
        Process PDFs from file paths (for FastAPI)
        """
        self._force_close_chroma()
        self._delete_storage_files()

        os.makedirs(TEMP_DIR, exist_ok=True)
        os.makedirs(self.upload_dir, exist_ok=True)

        all_nodes = []
        self.processed_files_cache = []

        for file_path in file_paths:
            original_name = os.path.basename(file_path)

            try:
                from app.services.ocr_utils import extract_text_smart

                result = extract_text_smart(file_path)

                if result.get("error") or not result["text"].strip():
                    print(f"Skip {original_name}: tidak ada teks")
                    continue

                self.ocr_status[original_name] = {
                    "total_pages": result["total_pages"],
                    "pages_with_text": result["pages_with_text"],
                    "is_scanned": result["pages_with_text"] == 0
                }

                file_documents = []

                full_doc = Document(
                    text=clean_text(result["text"]),
                    metadata={
                        "file_name": original_name,
                        "source": original_name,
                        "total_pages": str(result["total_pages"]),
                        "page_label": "all",
                        "page": "all",
                    }
                )
                file_documents.append(full_doc)

                for page_data in result["pages"]:
                    if not page_data["text"].strip():
                        continue
                    page_doc = Document(
                        text=clean_text(page_data["text"]),
                        metadata={
                            "file_name": original_name,
                            "source": original_name,
                            "page_label": str(page_data["page_num"]),
                            "page": str(page_data["page_num"]),
                            "total_pages": str(result["total_pages"]),
                        }
                    )
                    file_documents.append(page_doc)

                file_nodes = self.parser.get_nodes_from_documents(file_documents)

                for node in file_nodes:
                    if "file_name" not in node.metadata or not node.metadata["file_name"]:
                        node.metadata["file_name"] = original_name
                        node.metadata["source"] = original_name

                all_nodes.extend(file_nodes)
                self.processed_files_cache.append(original_name)
                print(f"✅ {original_name}: {len(file_nodes)} nodes created")

            except Exception as e:
                print(f"Error processing {original_name}: {e}")
                continue

        if not all_nodes:
            raise ValueError("No text could be extracted from uploaded PDFs")

        chroma_client = self._get_fresh_client()
        chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
        self._chroma_collection = chroma_collection

        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        index = VectorStoreIndex(
            nodes=all_nodes,
            storage_context=storage_context,
            embed_model=self.embed_model,
            show_progress=True,
        )

        index.storage_context.persist(persist_dir=PERSIST_DIR)
        return index

    def get_preview_for_file(self, filename: str, max_pages: int = 2, max_chars: int = 300) -> dict:
        upload_path = os.path.join(self.upload_dir, filename)
        temp_path = os.path.join(TEMP_DIR, filename)

        file_path = None
        if os.path.exists(upload_path):
            file_path = upload_path
        elif os.path.exists(temp_path):
            file_path = temp_path
        else:
            return {
                "success": False,
                "error": f"File {filename} tidak ditemukan.",
                "preview_pages": []
            }

        try:
            from app.services.pdf_preview import get_pdf_preview_text
            result = get_pdf_preview_text(file_path, max_pages=max_pages, max_chars=max_chars)
            result["filename"] = filename
            return result
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "preview_pages": [],
                "filename": filename
            }

    def load_index(self):
        try:
            if self._chroma_client is None:
                self._chroma_client = chromadb.PersistentClient(path=PERSIST_DIR)
            chroma_collection = self._chroma_client.get_collection(COLLECTION_NAME)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(
                vector_store=vector_store,
                persist_dir=PERSIST_DIR,
            )
            return VectorStoreIndex.from_vector_store(
                vector_store,
                embed_model=self.embed_model,
                storage_context=storage_context,
            )
        except Exception:
            return None

    def clear_index(self):
        self._force_close_chroma()
        self._delete_storage_files()
        if os.path.exists(self.upload_dir):
            try:
                shutil.rmtree(self.upload_dir)
            except:
                pass
        os.makedirs(self.upload_dir, exist_ok=True)

    def get_uploaded_files(self) -> list:
        """Get list of uploaded files"""
        return self.processed_files_cache

    def get_ocr_status(self):
        return self.ocr_status