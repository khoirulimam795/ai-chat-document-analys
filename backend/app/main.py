# backend/app/main.py

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List
import asyncio
import json
import os
import shutil
from datetime import datetime

from app.services.ingest import PDFIngestor
from app.services.rag_services import RAGService
from app.utils.auth import verify_token, create_token, hash_password, verify_password
from app.utils.rate_limiter import rate_limiter
from app.models.user import UserDB

# 🔥 TAMBAHKAN INI - Security scheme untuk Swagger
security = HTTPBearer(auto_error=False)

app = FastAPI(
    title="DocuChat API", 
    version="1.0.0",
    # 🔥 TAMBAHKAN INI AGAR SWAGGER PUNYA AUTH BUTTON
    swagger_ui_parameters={
        "persistAuthorization": True,
    }
)

# 🔥 TAMBAHKAN INI - Daftarkan security scheme
app.swagger_ui_init_oauth = {
    "usePkceWithAuthorizationCodeGrant": True,
}

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache
user_indexes = {}
user_rag_services = {}

UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ==================================================
# AUTH ENDPOINTS
# ==================================================
@app.post("/api/login")
async def login(request: dict):
    username = request.get("username")
    password = request.get("password")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    
    user = UserDB.get_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user["id"], username)
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/register")
async def register(request: dict):
    username = request.get("username")
    password = request.get("password")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    
    if UserDB.exists(username):
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user = UserDB.create(username, hash_password(password))
    token = create_token(user["id"], username)
    return {"access_token": token, "token_type": "bearer"}


# ==================================================
# DOCUMENT ENDPOINTS
# ==================================================
@app.post("/api/upload")
async def upload_pdf(
    files: List[UploadFile] = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Upload and process PDF files"""
    
    # 🔥 CEK MANUAL JIKA TOKEN TIDAK ADA
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = credentials.credentials
    user_id = verify_token(token)
    
    print(f"\n[UPLOAD] User ID: {user_id}")
    print(f"[UPLOAD] Files: {[f.filename for f in files]}")
    
    allowed, wait = rate_limiter.can_request(user_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Wait {wait} seconds")
    
    saved_files = []
    for file in files:
        if not file.filename.endswith('.pdf'):
            continue
        
        safe_filename = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        saved_files.append({
            "original_name": file.filename,
            "saved_name": safe_filename,
            "path": file_path
        })
    
    if not saved_files:
        raise HTTPException(status_code=400, detail="No valid PDF files uploaded")
    
    try:
        ingestor = PDFIngestor(str(user_id))
        index = ingestor.process_pdfs_from_paths([f["path"] for f in saved_files])
        
        user_indexes[user_id] = index
        user_rag_services[user_id] = RAGService(user_id, index=index)
        
        for f in saved_files:
            UserDB.add_upload(user_id, f["original_name"])
        
        print(f"[UPLOAD] SUCCESS! Cache keys: {list(user_indexes.keys())}")
        
        return {
            "status": "success",
            "files": [f["original_name"] for f in saved_files],
            "message": f"{len(saved_files)} PDF(s) processed successfully"
        }
        
    except Exception as e:
        print(f"[UPLOAD] ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        for f in saved_files:
            if os.path.exists(f["path"]):
                os.remove(f["path"])
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents")
async def get_documents(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = verify_token(credentials.credentials)
    uploads = UserDB.get_uploads(user_id)
    
    documents = []
    for i, upload in enumerate(uploads):
        documents.append({
            "id": str(i + 1),
            "name": upload["filename"],
            "upload_date": upload["upload_date"],
            "pages": None
        })
    
    return {"documents": documents}


# ==================================================
# CHAT ENDPOINTS
# ==================================================
@app.post("/api/chat")
async def chat(
    request: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = verify_token(credentials.credentials)
    question = request.get("question", "")
    
    print(f"[CHAT] User ID: {user_id}, Cache keys: {list(user_indexes.keys())}")
    
    allowed, wait = rate_limiter.can_request(user_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Wait {wait} seconds")
    
    if user_id not in user_indexes:
        raise HTTPException(status_code=404, detail="No documents uploaded yet. Please upload PDF first.")
    
    if user_id not in user_rag_services:
        user_rag_services[user_id] = RAGService(user_id, index=user_indexes[user_id])
    
    async def generate_stream():
        rag = user_rag_services[user_id]
        result = rag.ask(question)
        answer = result["answer"]
        sources = result.get("sources", [])
        
        words = answer.split()
        for i, word in enumerate(words):
            token_data = {
                "token": word + (" " if i < len(words) - 1 else ""),
                "done": False
            }
            yield json.dumps(token_data) + "\n"
            await asyncio.sleep(0.03)
        
        final_data = {
            "done": True,
            "sources": sources
        }
        yield json.dumps(final_data) + "\n"
    
    return StreamingResponse(generate_stream(), media_type="application/x-ndjson")


# ==================================================
# HEALTH CHECK
# ==================================================
@app.get("/api/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)