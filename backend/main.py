"""
EduStream AI — FastAPI Streaming Backend (Groq Edition)
========================================================
Production-grade async streaming endpoint using Groq API (OpenAI-compatible)
with Server-Sent Events (SSE) for real-time token delivery.

Security: API key is loaded exclusively from server-side environment variables.
No client-side key exposure is permitted.
"""

import os
import json
import logging
from typing import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from collections import defaultdict
import time

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("edustream")

# ---------------------------------------------------------------------------
# API Key Pool (Groq) — Supports multiple keys for rate limit rotation
# ---------------------------------------------------------------------------
# Set GROQ_API_KEYS as comma-separated keys, e.g.:
#   GROQ_API_KEYS=gsk_key1,gsk_key2,gsk_key3,gsk_key4
# Falls back to single GROQ_API_KEY if GROQ_API_KEYS is not set.

def _load_api_keys() -> list[str]:
    """Load API keys from environment. Supports multiple comma-separated keys."""
    multi = os.getenv("GROQ_API_KEYS", "")
    if multi.strip():
        keys = [k.strip() for k in multi.split(",") if k.strip()]
        if keys:
            return keys
    single = os.getenv("GROQ_API_KEY", "")
    if single.strip():
        return [single.strip()]
    return []


class GroqKeyPool:
    """Round-robin API key pool with automatic failover on rate limits."""

    def __init__(self, keys: list[str]):
        self.keys = keys
        self.clients: list[AsyncOpenAI] = []
        for key in keys:
            self.clients.append(
                AsyncOpenAI(
                    api_key=key,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=60.0,
                )
            )
        self._current_index = 0
        self._exhausted: set[int] = set()  # Indices of rate-limited keys
        self._exhausted_until: dict[int, float] = {}  # Reset timestamps

    @property
    def count(self) -> int:
        return len(self.keys)

    @property
    def available(self) -> bool:
        return len(self.keys) > 0

    def _refresh_exhausted(self):
        """Re-enable keys whose cooldown has expired."""
        now = time.time()
        expired = [i for i, t in self._exhausted_until.items() if now >= t]
        for i in expired:
            self._exhausted.discard(i)
            del self._exhausted_until[i]
            logger.info("API key #%d cooldown expired, re-enabled", i + 1)

    def get_client(self) -> tuple[AsyncOpenAI, int] | None:
        """Get the next available client. Returns (client, index) or None."""
        self._refresh_exhausted()
        if not self.clients:
            return None

        # Try all keys starting from current index
        for _ in range(len(self.clients)):
            idx = self._current_index % len(self.clients)
            self._current_index = (self._current_index + 1) % len(self.clients)
            if idx not in self._exhausted:
                return self.clients[idx], idx

        return None  # All keys exhausted

    def mark_exhausted(self, index: int, retry_after: float = 60.0):
        """Mark a key as rate-limited with a cooldown period."""
        self._exhausted.add(index)
        self._exhausted_until[index] = time.time() + retry_after
        remaining = len(self.clients) - len(self._exhausted)
        logger.warning(
            "API key #%d rate-limited (cooldown %.0fs). %d/%d keys available.",
            index + 1, retry_after, remaining, len(self.clients),
        )


API_KEYS = _load_api_keys()
key_pool = GroqKeyPool(API_KEYS)

if not API_KEYS:
    logger.critical(
        "No Groq API keys found. "
        "Set GROQ_API_KEYS (comma-separated) or GROQ_API_KEY in environment."
    )
else:
    logger.info("Loaded %d Groq API key(s) into rotation pool.", len(API_KEYS))

# ---------------------------------------------------------------------------
# CORS Origins — loaded from environment for production lockdown
# ---------------------------------------------------------------------------
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
if _raw_origins.strip() == "*":
    CORS_ORIGINS: list[str] = ["*"]
else:
    CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
logger.info("CORS allowed origins: %s", CORS_ORIGINS)

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="EduStream AI",
    version="2.0.0",
    description="AI-powered educational content streaming API (Groq)",
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 10  # requests per minute

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path == "/api/stream":
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        # Remove entries older than 60 seconds
        rate_limit_store[client_ip] = [t for t in rate_limit_store[client_ip] if now - t < 60]
        if len(rate_limit_store[client_ip]) >= RATE_LIMIT:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Maximum 10 requests per minute."})
        rate_limit_store[client_ip].append(now)
    return await call_next(request)

# ---------------------------------------------------------------------------
# CORS — origins controlled by ALLOWED_ORIGINS env var (default: "*")
# In production, set ALLOWED_ORIGINS=https://your-app.ap-south-1.awsapprunner.com
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request Schema
# ---------------------------------------------------------------------------
SUPPORTED_LANGUAGES = {"english", "kannada", "hindi"}
SUPPORTED_MODES = {"notes", "quiz", "simplify", "flashcard"}


class StreamRequest(BaseModel):
    """Structured JSON body for the /api/stream endpoint."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=500_000,
        description="The academic content to process.",
    )
    target_language: str = Field(
        default="english",
        description="Output language: english, kannada, or hindi.",
    )
    mode: str = Field(
        ...,
        description="Processing mode: notes, quiz, simplify, or flashcard.",
    )
    question_count: int = Field(
        default=5,
        ge=3,
        le=15,
        description="Number of quiz questions (quiz mode only)."
    )


# ---------------------------------------------------------------------------
# System Prompt Builders
# ---------------------------------------------------------------------------


def _build_system_prompt(mode: str, target_language: str, question_count: int = 5) -> str:
    """Return a detailed system prompt based on the selected mode."""

    language_instruction = (
        f"\n\nIMPORTANT: You MUST write your ENTIRE response in {target_language.capitalize()}. "
        f"Every heading, bullet point, question, option, and explanation must be in {target_language.capitalize()}. "
        f"Do not use any other language."
    )

    prompts = {
        "notes": (
            "You are an elite academic revision assistant. Your task is to extract "
            "immaculate, clean, and well-structured academic revision notes from the "
            "provided material.\n\n"
            "FORMAT REQUIREMENTS:\n"
            "- Use clear Markdown headers (##, ###) to organize topics and subtopics.\n"
            "- Use concise bulleted highlights (- ) for key points under each header.\n"
            "- Bold (**keyword**) critical terms and definitions.\n"
            "- Maintain a logical flow from broad concepts to specific details.\n"
            "- Include any important formulas, dates, or figures mentioned.\n"
            "- End with a brief 'Key Takeaways' section summarizing the 3-5 most "
            "important points."
            + language_instruction
        ),
        "quiz": (
            f"You are a world-class educational assessment designer. Your task is to "
            f"generate exactly {question_count} comprehensive multiple-choice questions based on the "
            f"provided material.\n\n"
            "CRITICAL FORMAT REQUIREMENTS:\n"
            "- You MUST return ONLY a valid JSON array. No markdown, no explanation, no extra text.\n"
            "- Each element in the array must be an object with exactly these keys:\n"
            '  - "question": a string containing the question text\n'
            '  - "options": an array of exactly 4 strings (the choices)\n'
            '  - "answer": a string that EXACTLY matches one of the 4 options\n'
            f"- Vary difficulty across the {question_count} questions: some easy, some medium, some challenging.\n"
            "- Questions should test comprehension and application, not just recall.\n\n"
            "EXAMPLE OUTPUT FORMAT:\n"
            '[{"question":"What is...?","options":["A","B","C","D"],"answer":"B"}]\n\n'
            "Return ONLY the JSON array. No other text before or after it."
            + language_instruction
        ),
        "flashcard": (
            "You are an expert educator. Your task is to generate 8-12 flashcards "
            "based on the provided material.\n\n"
            "CRITICAL FORMAT REQUIREMENTS:\n"
            "- You MUST return ONLY a valid JSON array. No markdown, no explanation, no extra text.\n"
            "- Each element in the array must be an object with exactly these keys:\n"
            '  - "front": a string containing the question or concept\n'
            '  - "back": a string containing the answer or explanation\n'
            "EXAMPLE OUTPUT FORMAT:\n"
            '[{"front":"What is...?","back":"It is..."}]\n\n'
            "Return ONLY the JSON array. No other text before or after it."
            + language_instruction
        ),
        "simplify": (
            "You are a world-class educational guide and master communicator. Your task "
            "is to explain difficult academic material in the simplest, most intuitive "
            "way possible.\n\n"
            "FORMAT REQUIREMENTS:\n"
            "- Start with a one-sentence 'Big Idea' summary.\n"
            "- Use vivid, relatable real-world analogies to explain each concept.\n"
            "- Break complex ideas into small, digestible pieces.\n"
            "- Use conversational, encouraging language suitable for a beginner.\n"
            "- Include 'Think of it like...' analogies wherever possible.\n"
            "- End with a 'Quick Recap' that ties everything together."
            + language_instruction
        ),
    }

    return prompts[mode]


# ---------------------------------------------------------------------------
# Content Truncation for Groq Rate Limits
# ---------------------------------------------------------------------------
# Groq free tier: 12K TPM for llama-3.3-70b (highest available).
# Rough estimate: 1 token ≈ 4 chars.
# Budget: 12K total - ~500 system prompt - ~2K max_tokens - ~1K buffer = ~8.5K input
# Safe limit: 20K chars (~5K tokens) leaves generous headroom.
# Groq model catalog changes frequently. Check available models at:
# https://api.groq.com/openai/v1/models
MODEL = "qwen/qwen3.8-27b"
CHAR_LIMIT = 20_000


def _truncate_content(content: str, char_limit: int) -> tuple[str, bool]:
    """Truncate content at a paragraph boundary if it exceeds char_limit.
    Returns (truncated_content, was_truncated)."""
    if len(content) <= char_limit:
        return content, False

    # Try to cut at a paragraph break (double newline)
    truncated = content[:char_limit]
    last_para = truncated.rfind("\n\n")
    if last_para > char_limit * 0.6:
        truncated = truncated[:last_para]
    else:
        # Fall back to sentence break
        last_sentence = max(truncated.rfind(". "), truncated.rfind(".\n"))
        if last_sentence > char_limit * 0.6:
            truncated = truncated[:last_sentence + 1]

    return truncated.strip(), True


# ---------------------------------------------------------------------------
# SSE Streaming Generator (Groq — OpenAI-compatible)
# ---------------------------------------------------------------------------


async def _stream_response(
    content: str, mode: str, target_language: str, question_count: int = 5
) -> AsyncGenerator[str, None]:
    """
    Async generator that streams Groq chat completion tokens as
    Server-Sent Events in the format:  data: {"text": "..."}\n\n
    Automatically rotates API keys on rate limit errors.
    """

    if not key_pool.available:
        error_payload = json.dumps(
            {"error": "Server configuration error: No Groq API keys configured."}
        )
        yield f"data: {error_payload}\n\n"
        return

    system_prompt = _build_system_prompt(mode, target_language, question_count)

    # Truncate content if it exceeds safe limits
    original_len = len(content)
    content, was_truncated = _truncate_content(content, CHAR_LIMIT)

    if was_truncated:
        truncated_len = len(content)
        notice = (
            f"> **Note:** Your document ({original_len:,} chars) was automatically "
            f"trimmed to {truncated_len:,} chars to fit processing limits. "
            f"The AI will work with the first portion of your content.\n\n"
        )
        logger.info(
            "Content truncated from %d to %d chars",
            original_len, truncated_len,
        )
        if mode in ("notes", "simplify"):
            notice_payload = json.dumps({"text": notice})
            yield f"data: {notice_payload}\n\n"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]

    # Try each available key until one works
    last_error = None
    attempts = 0
    max_attempts = key_pool.count

    while attempts < max_attempts:
        result = key_pool.get_client()
        if result is None:
            break  # All keys exhausted

        client, key_index = result
        attempts += 1

        try:
            logger.info("Attempting with API key #%d", key_index + 1)
            stream = await client.chat.completions.create(
                model=MODEL,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=1536,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    token_payload = json.dumps({"text": delta.content})
                    yield f"data: {token_payload}\n\n"

            done_payload = json.dumps({"done": True})
            yield f"data: {done_payload}\n\n"
            return  # Success — exit

        except Exception as exc:
            exc_str = str(exc)
            is_rate_limit = (
                "rate_limit" in exc_str.lower()
                or "429" in exc_str
                or "413" in exc_str
                or "too large" in exc_str.lower()
            )

            if is_rate_limit:
                # Parse retry-after if available, default 60s
                retry_after = 60.0
                if "try again in" in exc_str.lower():
                    import re
                    match = re.search(r"try again in (\d+)m", exc_str)
                    if match:
                        retry_after = float(match.group(1)) * 60
                key_pool.mark_exhausted(key_index, retry_after)
                last_error = exc
                logger.warning(
                    "Key #%d rate-limited, trying next key... (%d/%d attempted)",
                    key_index + 1, attempts, max_attempts,
                )
                continue  # Try next key
            else:
                # Non-rate-limit error — don't retry
                logger.exception("Groq streaming error (key #%d)", key_index + 1)
                error_payload = json.dumps({"error": exc_str})
                yield f"data: {error_payload}\n\n"
                return

    # All keys exhausted
    friendly_msg = (
        "All API keys have reached their rate limits. "
        "Please wait a few minutes and try again. "
        "Groq free tier allows ~100K tokens/day per key."
    )
    logger.error("All %d API keys exhausted. Last error: %s", key_pool.count, last_error)
    error_payload = json.dumps({"error": friendly_msg})
    yield f"data: {error_payload}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root_redirect():
    """Redirect root URL to the frontend app."""
    return RedirectResponse(url="/app", status_code=301)


@app.get("/api/health")
async def health_check():
    """Health-check / status endpoint."""
    return {
        "service": "EduStream AI",
        "status": "operational",
        "version": "2.0.0",
        "engine": "Groq (Qwen 3.8 27B)",
        "api_keys": f"{key_pool.count} key(s) loaded" if key_pool.available else "missing",
    }


@app.get("/api/capabilities")
async def get_capabilities():
    return {
        "modes": sorted(SUPPORTED_MODES),
        "languages": sorted(SUPPORTED_LANGUAGES),
        "max_content_length": 500000,
        "model": "qwen/qwen3.8-27b",
        "version": "2.0.0"
    }


from backend.file_handler import extract_text

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    text = await extract_text(file)
    return {"text": text, "filename": file.filename, "characters": len(text)}


@app.post("/api/stream")
async def stream_endpoint(payload: StreamRequest):
    """Stream AI-generated educational content as Server-Sent Events."""

    if payload.mode not in SUPPORTED_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid mode '{payload.mode}'. Supported: {', '.join(SUPPORTED_MODES)}",
        )

    lang = payload.target_language.lower().strip()
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid language '{payload.target_language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}",
        )

    if not key_pool.available:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: No Groq API keys configured.",
        )

    logger.info(
        "Stream request — mode=%s, language=%s, content_length=%d",
        payload.mode,
        lang,
        len(payload.content),
    )

    return StreamingResponse(
        _stream_response(payload.content, payload.mode, lang, payload.question_count),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Frontend Serving
# ---------------------------------------------------------------------------


@app.get("/app")
async def serve_frontend():
    """Serve the single-page frontend application."""
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found.")
    return FileResponse(str(index_path), media_type="text/html")
