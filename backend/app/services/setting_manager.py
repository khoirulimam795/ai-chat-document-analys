# src/settings_manager.py
import json
import os

SETTINGS_FILE = "user_settings.json"

class SettingsManager:
    """Manage user settings for RAG backend"""
    
    DEFAULT_SETTINGS = {
        "temperature": 0.1,      # 0.0 - 1.0
        "top_k": 4,              # 2 - 10
        "response_style": "default",  # default, concise, detailed, formal
        "chunk_size": 512,       # 256 - 1024
        "chunk_overlap": 50,     # 20 - 200
        "response_language": "indonesia",  # indonesia, english, mix
    }
    
    # Prompt templates untuk setiap response style
    PROMPT_TEMPLATES = {
        "default": """\
Kamu adalah asisten AI yang HANYA boleh menjawab berdasarkan KONTEKS DOKUMEN.

KONTEKS:
{context_str}

PERTANYAAN: {query_str}

JAWAB berdasarkan konteks di atas. Jika tidak ada, bilang tidak tahu.
""",
        
        "concise": """\
JAWAB DENGAN SINGKAT (maks 2 kalimat) berdasarkan KONTEKS ini:

KONTEKS:
{context_str}

PERTANYAAN: {query_str}

JAWABAN SINGKAT:""",
        
        "detailed": """\
JAWAB DENGAN LENGKAP DAN DETAIL berdasarkan KONTEKS:

KONTEKS:
{context_str}

PERTANYAAN: {query_str}

JAWABAN LENGKAP:""",
        
        "formal": """\
Anda adalah asisten analisis dokumen profesional. 
Jawab dengan bahasa Indonesia yang baku dan formal berdasarkan KONTEKS berikut:

KONTEKS:
{context_str}

PERTANYAAN: {query_str}

JAWABAN (FORMAL):"""
    }
    
    def __init__(self, username: str):
        self.username = username
        self.settings = self._load_settings()
    
    def _load_settings(self) -> dict:
        """Load settings dari file"""
        try:
            with open(SETTINGS_FILE, 'r') as f:
                all_settings = json.load(f)
                user_settings = all_settings.get(self.username, {})
                # Merge dengan default settings
                return {**self.DEFAULT_SETTINGS, **user_settings}
        except (FileNotFoundError, json.JSONDecodeError):
            return self.DEFAULT_SETTINGS.copy()
    
    def _save_settings(self):
        """Save settings ke file"""
        try:
            with open(SETTINGS_FILE, 'r') as f:
                all_settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            all_settings = {}
        
        all_settings[self.username] = self.settings
        
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(all_settings, f, indent=2)
    
    def get(self, key: str):
        """Get setting value"""
        return self.settings.get(key, self.DEFAULT_SETTINGS.get(key))
    
    def set(self, key: str, value):
        """Set setting value"""
        if key in self.DEFAULT_SETTINGS:
            self.settings[key] = value
            self._save_settings()
            return True
        return False
    
    def get_prompt_template(self) -> str:
        """Get prompt template berdasarkan response_style"""
        style = self.get("response_style")
        return self.PROMPT_TEMPLATES.get(style, self.PROMPT_TEMPLATES["default"])
    
    def get_chunk_config(self) -> dict:
        """Get chunking configuration"""
        return {
            "chunk_size": self.get("chunk_size"),
            "chunk_overlap": self.get("chunk_overlap")
        }
    
    def get_llm_config(self) -> dict:
        """Get LLM configuration"""
        return {
            "temperature": self.get("temperature"),
            "top_k": self.get("top_k")
        }
    
    def get_all(self) -> dict:
        """Get all settings"""
        return self.settings.copy()