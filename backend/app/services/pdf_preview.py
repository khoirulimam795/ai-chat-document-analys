# backend/app/services/pdf_preview.py
import os
import pdfplumber
from typing import Dict, List, Optional

from app.core.config import settings


def get_pdf_preview(
    file_path: str, 
    max_pages: int = 2, 
    max_chars: int = 300
) -> Dict:
    """
    Extract preview text from PDF file
    
    Args:
        file_path: Path to PDF file
        max_pages: Number of pages to preview
        max_chars: Max characters per page
    
    Returns:
        {
            "success": bool,
            "total_pages": int,
            "preview_pages": [
                {"page_num": 1, "text": "..."},
                ...
            ],
            "error": str (if failed)
        }
    """
    try:
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": f"File not found: {file_path}",
                "total_pages": 0,
                "preview_pages": []
            }
        
        preview_pages = []
        total_pages = 0
        
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            
            for i in range(min(max_pages, total_pages)):
                page = pdf.pages[i]
                page_text = page.extract_text()
                
                if page_text and page_text.strip():
                    # Trim text
                    preview_text = page_text[:max_chars]
                    if len(page_text) > max_chars:
                        preview_text += "..."
                    
                    preview_pages.append({
                        "page_num": i + 1,
                        "text": preview_text
                    })
                else:
                    preview_pages.append({
                        "page_num": i + 1,
                        "text": "[Halaman ini tidak memiliki teks readable - mungkin PDF scan/gambar]"
                    })
        
        return {
            "success": True,
            "total_pages": total_pages,
            "preview_pages": preview_pages,
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total_pages": 0,
            "preview_pages": []
        }


def get_pdf_preview_by_user_file(
    user_id: int, 
    filename: str, 
    max_pages: int = 2,
    max_chars: int = 300
) -> Dict:
    """
    Get preview for a specific user's uploaded file
    """
    upload_dir = settings.UPLOAD_DIR
    
    # Search for file with user prefix
    for f in os.listdir(upload_dir):
        if f.startswith(f"{user_id}_") and filename in f:
            file_path = os.path.join(upload_dir, f)
            return get_pdf_preview(file_path, max_pages, max_chars)
    
    return {
        "success": False,
        "error": f"File {filename} not found for user {user_id}",
        "total_pages": 0,
        "preview_pages": []
    }


def get_all_user_files_preview(user_id: int) -> List[Dict]:
    """
    Get preview for all files uploaded by a user
    """
    upload_dir = settings.UPLOAD_DIR
    previews = []
    
    for f in os.listdir(upload_dir):
        if f.startswith(f"{user_id}_"):
            file_path = os.path.join(upload_dir, f)
            original_name = f.replace(f"{user_id}_", "")
            preview = get_pdf_preview(file_path, max_pages=1, max_chars=150)
            
            previews.append({
                "filename": original_name,
                "total_pages": preview["total_pages"],
                "preview": preview["preview_pages"][0]["text"] if preview["preview_pages"] else "",
                "success": preview["success"]
            })
    
    return previews