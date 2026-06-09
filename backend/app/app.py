import streamlit as st
import os
import shutil
import gc
import time
import json
import base64
from datetime import datetime
from collections import defaultdict
from llama_index.core import Settings
from llama_index.llms.groq import Groq
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from core.config import GROQ_API_KEY, TOP_K, MODEL_NAME, EMBEDDING_MODEL
from services.ingest import PDFIngestor
from api.routers.chat import RAGChatbot

# ============================================================
# 🔐 AUTHENTICATION CONFIG (HANYA 1 KALI)
# ============================================================
VALID_USERS = {
    "admin": "admin123",
    "user1": "imam123"
}

def require_auth():
    """Cek apakah user sudah login - tampilan keren di sidebar"""
    if "user" not in st.session_state:
        with st.sidebar:
            st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #534AB7 0%, #433A9E 100%);
                    padding: 20px;
                    border-radius: 12px;
                    text-align: center;
                    margin-bottom: 20px;
                ">
                    <div style="font-size: 40px; margin-bottom: 10px;">🔐</div>
                    <div style="color: white; font-weight: 600; margin-bottom: 5px;">Login Required</div>
                    <div style="color: rgba(255,255,255,0.7); font-size: 12px;">Silakan login untuk melanjutkan</div>
                </div>
            """, unsafe_allow_html=True)
            
            username = st.text_input("Username", placeholder="admin or user1", key="login_username")
            password = st.text_input("Password", type="password", placeholder="******", key="login_password")
            
            if st.button("🔓 Login", key="login_button", use_container_width=True):
                if username in VALID_USERS and VALID_USERS[username] == password:
                    st.session_state.user = username
                    st.session_state.query_count = 0
                    st.success(f"✅ Selamat datang, {username}!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Username atau password salah!")
            
            st.markdown("""
                <div style="margin-top: 16px; font-size: 11px; color: #8B85C7; text-align: center;">
                    📝 Akun demo:<br>
                    admin / admin123<br>
                    user1 / imam123
                </div>
            """, unsafe_allow_html=True)
        
        return False
    return True

def render_logout():
    """Tampilkan tombol logout di sidebar"""
    if st.sidebar.button("🚪 Logout", key="logout_btn", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ==================================================
# 📁 FUNGSI EXPORT CHAT
# ==================================================
def export_chat_to_file():
    """Export chat history ke file dan langsung download"""
    
    if not st.session_state.messages:
        st.warning("📭 Tidak ada percakapan untuk diexport")
        return False
    
    chat_text = f"""
{'='*60}
RAG CHATBOT EXPORT
{'='*60}
Tanggal Export: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
User: {st.session_state.user}
Total Pesan: {len(st.session_state.messages)}
{'='*60}

"""
    
    for i, msg in enumerate(st.session_state.messages, 1):
        role = "👤 USER" if msg["role"] == "user" else "🤖 ASSISTANT"
        chat_text += f"\n[{i}] {role}\n{'-'*40}\n"
        chat_text += f"{msg['content']}\n"
        
        if msg["role"] == "assistant" and msg.get("sources"):
            chat_text += f"\n📚 SUMBER DOKUMEN:\n"
            for j, src in enumerate(msg["sources"], 1):
                chat_text += f"  {j}. File: {src['source']} (Halaman {src['page']})\n"
                chat_text += f"     Preview: {src['content'][:150]}...\n"
        
        chat_text += "\n"
    
    chat_text += f"\n{'='*60}\nEND OF EXPORT\n{'='*60}"
    
    file_name = f"chat_export_{st.session_state.user}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    b64 = base64.b64encode(chat_text.encode()).decode()
    href = f'''
    <a href="data:text/plain;base64,{b64}" 
       download="{file_name}" 
       style="display: inline-block; padding: 0.5em 1em; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 5px;">
       📥 Klik untuk Download Chat ({file_name})
    </a>
    '''
    st.markdown(href, unsafe_allow_html=True)
    st.success(f"✅ Chat berhasil diexport! ({len(st.session_state.messages)} pesan)")
    return True

# ==================================================
# 🔧 KONFIGURASI RATE LIMITING
# ==================================================
class SimpleRateLimiter:
    def __init__(self, max_queries=30):
        self.max_queries = max_queries
        self.queries = defaultdict(list)
    
    def can_query(self, user):
        now = time.time()
        minute_ago = now - 60
        
        self.queries[user] = [t for t in self.queries[user] if t > minute_ago]
        
        if len(self.queries[user]) >= self.max_queries:
            wait_seconds = int(60 - (now - self.queries[user][0])) + 1
            return False, wait_seconds
        
        self.queries[user].append(now)
        return True, 0

rate_limiter = SimpleRateLimiter(max_queries=30)

# ==================================================
# 🔧 KONFIGURASI LOGGING
# ==================================================
def log_query(user, question, answer_length, latency, success=True):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "question": question[:200],
        "answer_length": answer_length,
        "latency_ms": round(latency, 2),
        "success": success
    }
    try:
        with open("query_log.json", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass

# ==================================================
# 🔧 KONFIGURASI GLOBAL LLAMAINDEX
# ==================================================
if not GROQ_API_KEY:
    st.error("❌ GROQ_API_KEY tidak ditemukan. Set di file .env atau environment variable.")
    st.stop()

Settings.llm = Groq(model=MODEL_NAME, api_key=GROQ_API_KEY)
Settings.embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)

# ==================================================
# 🖥️ INTERFACE STREAMLIT
# ==================================================
st.set_page_config(page_title="RAG Chatbot", page_icon="🦙", layout="wide")

# ==================================================
# 🔐 CEK AUTHENTICATION (PALING PERTAMA SETELAH PAGE CONFIG)
# ==================================================
if not require_auth():
    st.stop()

# ==================================================
# 📦 INISIALISASI SESSION STATE
# ==================================================
for key, default in [
    ("index", None),
    ("chatbot", None),
    ("messages", []),
    ("processed", False),
    ("processed_files", []),
    ("ingestor", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ==================================================
# 🖥️ HEADER (SETELAH AUTH)
# ==================================================
st.title("🦙 RAG Chatbot — LlamaIndex + Groq")
st.caption("Analisis PDF berbasis AI | Data selalu segar setiap sesi baru")

# ==================================================
# 📄 SIDEBAR — UPLOAD & PROSES PDF (DENGAN USER INFO & LOGOUT)
# ==================================================
with st.sidebar:
    # User info & logout (tampil setelah login)
    st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #534AB7 0%, #433A9E 100%);
            padding: 12px;
            border-radius: 10px;
            margin-bottom: 16px;
        ">
            <div style="display: flex; align-items: center; gap: 10px;">
                <div style="
                    width: 36px;
                    height: 36px;
                    background: rgba(255,255,255,0.2);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 18px;
                ">👤</div>
                <div>
                    <div style="color: white; font-weight: 500; font-size: 14px;">{st.session_state.user}</div>
                    <div style="color: rgba(255,255,255,0.7); font-size: 11px;">Active</div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # Tombol logout
    if st.button("🚪 Logout", key="logout_btn", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    
    st.divider()
    
    # Upload Section
    st.header("📄 Upload PDF")
    uploaded_files = st.file_uploader(
        "Pilih file PDF (bisa lebih dari satu)",
        type="pdf",
        accept_multiple_files=True,
        key="pdf_uploader"
    )

    if st.button("🚀 Proses PDF", type="primary", key="process_button"):
        if uploaded_files:
            with st.spinner("🔄 Membersihkan data lama & memproses PDF baru... (butuh 5-10 detik)"):
                try:
                    if st.session_state.ingestor is not None:
                        try:
                            st.session_state.ingestor._force_close_chroma()
                        except:
                            pass
                        st.session_state.ingestor = None
                    
                    gc.collect()
                    time.sleep(1)
                    
                    import subprocess
                    for path in ["./storage", "./chroma_db"]:
                        if os.path.exists(path):
                            try:
                                subprocess.run(f'rmdir /s /q "{path}"', shell=True, capture_output=True)
                            except:
                                try:
                                    shutil.rmtree(path, ignore_errors=True)
                                except:
                                    pass
                    
                    time.sleep(1)
                    
                    ingestor = PDFIngestor()
                    st.session_state.ingestor = ingestor
                    index = ingestor.process_pdfs(uploaded_files)

                    st.session_state.index = index
                    st.session_state.chatbot = RAGChatbot(index)
                    st.session_state.processed = True
                    st.session_state.messages = []
                    st.session_state.processed_files = [f.name for f in uploaded_files]

                    st.success(f"✅ {len(uploaded_files)} PDF berhasil diproses!")
                    st.info("💡 Data PDF lama telah dihapus otomatis.")

                except PermissionError as e:
                    st.error(f"❌ Gagal menghapus data lama: {e}")
                    st.info("💡 Coba tutup semua aplikasi, lalu restart Streamlit, baru upload ulang.")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
        else:
            st.warning("Upload file PDF-nya dulu.")

    # Tampilkan file yang aktif dengan PREVIEW
    if st.session_state.processed_files:
        st.divider()
        st.caption("📂 **PDF aktif saat ini:**")
        
        for fname in st.session_state.processed_files:
            with st.expander(f"📄 {fname[:40]}", expanded=False):
                try:
                    if st.session_state.ingestor:
                        preview = st.session_state.ingestor.get_preview_for_file(
                            fname, max_pages=1, max_chars=200
                        )
                        if preview.get("success") and preview["preview_pages"]:
                            page = preview["preview_pages"][0]
                            st.caption(f"📑 Total halaman: {preview['total_pages']}")
                            st.text(page["text"])
                        else:
                            st.caption("Preview tidak tersedia")
                    else:
                        st.caption("Preview tidak tersedia")
                except Exception:
                    st.caption("Preview tidak tersedia")
    
    # Reset buttons
    if st.button("🗑️ Reset Semua", type="secondary", key="reset_button"):
        if st.session_state.ingestor is not None:
            try:
                st.session_state.ingestor._close_chroma()
            except:
                pass
            st.session_state.ingestor = None
            gc.collect()

        for path in ["./chroma_db", "./storage", "./temp", "./uploads"]:
            if os.path.exists(path):
                try:
                    shutil.rmtree(path)
                except Exception:
                    pass

        st.session_state.index = None
        st.session_state.chatbot = None
        st.session_state.processed = False
        st.session_state.messages = []
        st.session_state.processed_files = []
        st.success("Semua data berhasil direset.")
        st.rerun()
    
    # OCR Status
    if st.session_state.get("ingestor") and st.session_state.ingestor:
        ocr_status = st.session_state.ingestor.get_ocr_status()
        if ocr_status:
            st.divider()
            st.caption("📸 **Status OCR:**")
            for fname, status in list(ocr_status.items())[:3]:
                if status.get("is_scanned"):
                    st.caption(f"• {fname[:25]}: 🔍 OCR")
                else:
                    st.caption(f"• {fname[:25]}: 📝 Teks")
    
    # Force Reset
    if st.button("🔧 Force Reset", type="secondary", key="force_reset"):
        with st.spinner("Membersihkan semua data dengan force..."):
            try:
                if st.session_state.ingestor is not None:
                    try:
                        st.session_state.ingestor._force_close_chroma()
                    except:
                        pass
                    st.session_state.ingestor = None
                
                gc.collect()
                time.sleep(1)
                
                import subprocess
                for path in ["./chroma_db", "./storage", "./temp", "./uploads"]:
                    if os.path.exists(path):
                        subprocess.run(f'rmdir /s /q "{path}"', shell=True, capture_output=True)
                
                st.session_state.index = None
                st.session_state.chatbot = None
                st.session_state.processed = False
                st.session_state.messages = []
                st.session_state.processed_files = []
                
                st.success("✅ Force reset berhasil! Silakan upload PDF lagi.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Force reset gagal: {e}")
    
    st.divider()
    st.info(
        f"🤖 Model: `{MODEL_NAME}`\n\n"
        f"🎯 Top-K: `{TOP_K}`\n\n"
        f"🧬 Embedding: `{EMBEDDING_MODEL}`"
    )

# ==================================================
# 💬 AREA CHAT
# ==================================================
if st.session_state.processed and st.session_state.chatbot:

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📖 Sumber Dokumen"):
                    for src in msg["sources"]:
                        st.caption(f"📄 **{src['source']}** — Halaman {src['page']}")
                        st.text(src["content"])

    if prompt := st.chat_input("Tanya sesuatu tentang isi PDF..."):
        allowed, wait_seconds = rate_limiter.can_query(st.session_state.user)
        if not allowed:
            st.error(f"⚠️ Limit 30 query/menit. Coba lagi dalam {wait_seconds} detik.")
            st.stop()
        
        start_time = time.time()
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Menganalisis dokumen..."):
                try:
                    response = st.session_state.chatbot.ask(prompt)
                    
                    latency = (time.time() - start_time) * 1000
                    
                    log_query(
                        user=st.session_state.user,
                        question=prompt,
                        answer_length=len(response["answer"]),
                        latency=latency,
                        success=True
                    )
                    
                    st.markdown(response["answer"])
                    
                    if response["sources"]:
                        with st.expander("📖 Sumber Jawaban"):
                            for src in response["sources"]:
                                st.caption(f"📄 **{src['source']}** — Halaman {src['page']}")
                                st.text(src["content"])
                    
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response["answer"],
                        "sources": response["sources"],
                    })
                    
                except Exception as e:
                    latency = (time.time() - start_time) * 1000
                    log_query(
                        user=st.session_state.user,
                        question=prompt,
                        answer_length=0,
                        latency=latency,
                        success=False
                    )
                    st.error(f"❌ Error: {str(e)}")

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🧹 Hapus Riwayat", key="clear_chat"):
            st.session_state.messages = []
            if st.session_state.chatbot:
                st.session_state.chatbot.clear_memory()
            st.success("✅ Riwayat chat berhasil dihapus!")
            time.sleep(0.5)
            st.rerun()
    
    with col2:
        if st.button("💾 Export Chat", key="export_chat"):
            export_chat_to_file()

else:
    st.info("👈 Upload dan proses PDF di sidebar kiri untuk mulai analisa.")

# ==================================================
# 📊 FOOTER
# ==================================================
st.divider()
st.caption("RAG System | LlamaIndex + Groq + ChromaDB | 🔐 Authentication Active | ⚡ Rate Limit 30/min")