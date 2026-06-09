# pages/settings.py
import streamlit as st
from services.setting_manager import SettingsManager
import time
st.set_page_config(page_title="Settings", page_icon="⚙️")
st.title("⚙️ Pengaturan AI")

if "user" not in st.session_state:
    st.warning("Silakan login dulu")
    st.stop()

user = st.session_state.user
settings_mgr = SettingsManager(user)
current = settings_mgr.get_all()

st.caption(f"👤 User: **{user}**")
st.divider()

with st.form("ai_settings_form"):
    st.subheader("🎯 Parameter Retrieval")
    
    top_k = st.slider(
        "Jumlah chunk dokumen yang diambil (Top-K)",
        min_value=2,
        max_value=10,
        value=current["top_k"],
        help="Semakin besar, semakin akurat tapi lebih lambat"
    )
    
    st.subheader("🔥 Parameter LLM")
    
    temperature = st.slider(
        "Temperature (Kreativitas)",
        min_value=0.0,
        max_value=1.0,
        value=current["temperature"],
        step=0.05,
        help="0 = sangat patuh dokumen, 1 = lebih kreatif"
    )
    
    st.subheader("📝 Gaya Jawaban")
    
    response_style = st.selectbox(
        "Pilih gaya respons",
        options=["default", "concise", "detailed", "formal"],
        format_func=lambda x: {
            "default": "Default (standar)",
            "concise": "Ringkas (1-2 kalimat)",
            "detailed": "Detail (penjelasan lengkap)",
            "formal": "Formal (bahasa baku)"
        }[x],
        index=["default", "concise", "detailed", "formal"].index(current["response_style"])
    )
    
    st.subheader("🌐 Bahasa")
    
    response_language = st.selectbox(
        "Bahasa respons",
        options=["indonesia", "english", "mix"],
        format_func=lambda x: {
            "indonesia": "Bahasa Indonesia",
            "english": "English",
            "mix": "Mix (ikuti bahasa pertanyaan)"
        }[x],
        index=["indonesia", "english", "mix"].index(current["response_language"])
    )
    
    st.subheader("✂️ Chunking (Perlu Reprocess PDF)")
    
    col1, col2 = st.columns(2)
    with col1:
        chunk_size = st.number_input(
            "Chunk Size (karakter)",
            min_value=256,
            max_value=1024,
            value=current["chunk_size"],
            step=64,
            help="Ukuran potongan teks. Lebih besar = lebih konteks"
        )
    with col2:
        chunk_overlap = st.number_input(
            "Chunk Overlap (karakter)",
            min_value=20,
            max_value=200,
            value=current["chunk_overlap"],
            step=10,
            help="Overlap antar potongan"
        )
    
    st.warning("⚠️ Mengubah Chunk Size atau Overlap memerlukan **reprocess PDF** untuk berlaku.")
    
    submitted = st.form_submit_button("💾 Simpan Pengaturan", use_container_width=True)
    
    if submitted:
        settings_mgr.set("top_k", top_k)
        settings_mgr.set("temperature", temperature)
        settings_mgr.set("response_style", response_style)
        settings_mgr.set("response_language", response_language)
        settings_mgr.set("chunk_size", chunk_size)
        settings_mgr.set("chunk_overlap", chunk_overlap)
        
        st.success("✅ Pengaturan disimpan!")
        
        # Reload chatbot settings
        if st.session_state.chatbot:
            st.session_state.chatbot.reload_settings()
        
        time.sleep(1)
        st.rerun()

# Tampilkan settings yang aktif
st.divider()
st.subheader("📋 Pengaturan Aktif")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Top-K", current["top_k"])
    st.metric("Temperature", f"{current['temperature']}")
with col2:
    st.metric("Response Style", current["response_style"])
    st.metric("Language", current["response_language"])
with col3:
    st.metric("Chunk Size", current["chunk_size"])
    st.metric("Chunk Overlap", current["chunk_overlap"])