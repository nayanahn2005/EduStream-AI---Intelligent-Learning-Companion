import io
import logging
import os
from fastapi import UploadFile, HTTPException

logger = logging.getLogger("edustream.file_handler")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

async def extract_text(file: UploadFile) -> str:
    """Extract text from uploaded PDF, DOCX, or TXT file."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
    
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum 10MB allowed.")

    text = ""
    try:
        if ext == ".pdf":
            import fitz # PyMuPDF
            doc = fitz.open(stream=content, filetype="pdf")
            for page in doc:
                text += page.get_text() + "\n"
            doc.close()
        elif ext == ".docx":
            import docx
            doc = docx.Document(io.BytesIO(content))
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif ext == ".txt":
            try:
                text = content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    text = content.decode('latin-1')
                except Exception:
                    text = content.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.exception("Error extracting text")
        raise HTTPException(status_code=500, detail=f"Error extracting text: {str(e)}")
        
    return text.strip()
