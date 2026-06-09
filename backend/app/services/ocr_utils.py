# backend/app/services/ocr_utils.py
import os
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from typing import Tuple

# ==================================================
# KONFIGURASI TESSERACT
# ==================================================
# UNCOMMENT DAN SESUAIKAN DENGAN INSTALLASI TESSERACT LO
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def is_scanned_pdf(pdf_path: str, check_pages: int = 3) -> Tuple[bool, int]:
    """
    Cek apakah PDF itu hasil scan (gak punya teks readable)
    
    Returns:
        (is_scanned, total_text_pages)
        is_scanned: True = PDF gambar, False = PDF teks
        total_text_pages: jumlah halaman yang punya teks
    """
    try:
        text_pages = 0
        total_pages = 0
        
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            pages_to_check = min(check_pages, total_pages)
            
            for i in range(pages_to_check):
                page = pdf.pages[i]
                text = page.extract_text()
                if text and text.strip():
                    text_pages += 1
        
        is_scanned = text_pages < 1
        return is_scanned, text_pages
        
    except Exception as e:
        print(f"Error cek PDF: {e}")
        return True, 0


def extract_text_with_ocr(
    pdf_path: str, 
    dpi: int = 300,
    lang: str = 'ind+eng'
) -> dict:
    """
    Ekstrak teks dari PDF gambar pake OCR
    """
    try:
        images = convert_from_path(pdf_path, dpi=dpi)
        all_text = ""
        pages_data = []
        
        for i, image in enumerate(images):
            page_num = i + 1
            
            page_text = pytesseract.image_to_string(
                image, 
                lang=lang,
                config='--oem 3 --psm 6'
            )
            
            if page_text.strip():
                pages_data.append({
                    "page_num": page_num,
                    "text": page_text
                })
                all_text += f"\n--- Halaman {page_num} ---\n{page_text}\n"
        
        return {
            "text": all_text,
            "pages": pages_data,
            "total_pages": len(images),
            "pages_with_text": len(pages_data)
        }
        
    except Exception as e:
        print(f"Error OCR: {e}")
        return {
            "text": "",
            "pages": [],
            "total_pages": 0,
            "pages_with_text": 0,
            "error": str(e)
        }


def extract_text_smart(pdf_path: str) -> dict:
    """
    Ekstrak teks dari PDF dengan metode pintar:
    - Kalau PDF teks biasa, pake pdfplumber (cepat)
    - Kalau PDF scan/gambar, pake OCR (akurat)
    """
    is_scanned, text_pages = is_scanned_pdf(pdf_path)
    
    if not is_scanned:
        return extract_text_normal(pdf_path)
    else:
        return extract_text_with_ocr(pdf_path)


def extract_text_normal(pdf_path: str) -> dict:
    """Ekstrak teks dari PDF teks biasa pake pdfplumber"""
    try:
        all_text = ""
        pages_data = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_num = i + 1
                page_text = page.extract_text() or ""
                
                if page_text.strip():
                    pages_data.append({
                        "page_num": page_num,
                        "text": page_text
                    })
                    all_text += f"\n--- Halaman {page_num} ---\n{page_text}\n"
        
        return {
            "text": all_text,
            "pages": pages_data,
            "total_pages": len(pdf.pages),
            "pages_with_text": len(pages_data)
        }
        
    except Exception as e:
        return {
            "text": "",
            "pages": [],
            "total_pages": 0,
            "pages_with_text": 0,
            "error": str(e)
        }