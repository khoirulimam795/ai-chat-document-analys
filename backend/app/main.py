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

# Security scheme untuk Swagger
security = HTTPBearer(auto_error=False)

app = FastAPI(
    title="DocuChat API", 
    version="1.0.0",
    swagger_ui_parameters={
        "persistAuthorization": True,
    }
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================================================
# USER SESSION MANAGER (Fix masalah PDF lama)
# ==================================================
class UserSessionManager:
    """Manager untuk nyimpen session user"""
    def __init__(self):
        self._indexes = {}
        self._services = {}
    
    def set_index(self, user_id: int, index):
        self._indexes[user_id] = index
    
    def get_index(self, user_id: int):
        return self._indexes.get(user_id)
    
    def set_service(self, user_id: int, service):
        self._services[user_id] = service
    
    def get_service(self, user_id: int):
        return self._services.get(user_id)
    
    def has_user(self, user_id: int):
        return user_id in self._indexes
    
    def get_all_user_ids(self):
        return list(self._indexes.keys())

user_manager = UserSessionManager()

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
        
        # Simpan ke session manager
        user_manager.set_index(user_id, index)
        user_manager.set_service(user_id, RAGService(user_id, index=index))
        
        for f in saved_files:
            UserDB.add_upload(user_id, f["original_name"])
        
        print(f"[UPLOAD] SUCCESS! User {user_id} now has {len(user_manager.get_all_user_ids())} active user(s)")
        
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
    
    print(f"[CHAT] User ID: {user_id}, Active users: {user_manager.get_all_user_ids()}")
    print(f"[CHAT] User has documents: {user_manager.has_user(user_id)}")
    
    allowed, wait = rate_limiter.can_request(user_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Wait {wait} seconds")
    
    # Cek apakah user punya dokumen
    if not user_manager.has_user(user_id):
        # Coba load dari disk
        print(f"[CHAT] User {user_id} not in cache, attempting to load from disk...")
        rag_service = RAGService(user_id)
        if rag_service.has_documents():
            user_manager.set_service(user_id, rag_service)
            # Index juga perlu di-set
            if hasattr(rag_service, 'index'):
                user_manager.set_index(user_id, rag_service.index)
            print(f"[CHAT] Successfully loaded user {user_id} from disk")
        else:
            raise HTTPException(status_code=404, detail="No documents uploaded yet. Please upload PDF first.")
    
    # Ambil atau buat service
    rag_service = user_manager.get_service(user_id)
    if rag_service is None:
        rag_service = RAGService(user_id, index=user_manager.get_index(user_id))
        user_manager.set_service(user_id, rag_service)
    
    async def generate_stream():
        result = rag_service.ask(question)
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