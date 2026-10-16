"""ORION Voice: cross-platform localhost client for hosted Groq + Gemini APIs."""
import base64
import os
import sqlite3
import uuid
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
DB = BASE / "data" / "orion.sqlite3"
DB.parent.mkdir(exist_ok=True)
app = FastAPI(docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
with sqlite3.connect(DB) as db:
    db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, session TEXT, role TEXT, content TEXT, agent TEXT)")
AGENTS = {
"orion":"General personal assistant and coordinator",
"vega":"Software engineering and debugging",
"mira":"Research and teaching",
"aegis":"Security advice",
"radar":"Risk analysis",
"forge":"Infrastructure planning",
"bolt":"Automation planning",
"pulse":"Hardware advice",
"mnemo":"Conversation summaries",
"atlas":"Scheduling assistance",
"ledger":"Financial explanation",
"nexus":"API and MCP integration advice",
"iris":"Data interpretation",
"echo":"Communication writing",
"quartz":"Quality review",
"mercury":"Marketing and sales",
"care":"Customer support",
"spark":"Product ideation",
}
class Turn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    session: str = Field(pattern=r"^[a-f0-9]{32}$")
    agent: str = "orion"

def require_key(name):
    key = os.getenv(name, "")
    if not key or key.startswith("replace_"):
        raise HTTPException(503, detail=f"Configure {name} in .env")
    return key

async def upstream(method, url, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=90) as cli:
            result = await cli.request(method, url, **kwargs)
        result.raise_for_status()
        return result
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, detail=f"AI provider returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, detail="AI provider connection error") from exc

@app.get("/")
async def root():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/api/health")
def health():
    return {"status":"ok","mode":"hosted APIs only","agents":list(AGENTS),
            "groq_configured":bool(os.getenv("GROQ_API_KEY")),
            "gemini_configured":bool(os.getenv("GEMINI_API_KEY"))}

@app.get("/api/history/{session}")
def history(session: str):
    if len(session) != 32 or not all(c in "0123456789abcdef" for c in session):
        raise HTTPException(422, detail="Invalid session")
    with sqlite3.connect(DB) as db:
        rows = db.execute("SELECT role,content,agent FROM messages WHERE session=? ORDER BY id",(session,)).fetchall()
    return {"messages":[{"role":x[0],"content":x[1],"agent":x[2]} for x in rows]}

@app.post("/api/chat")
async def chat(turn: Turn):
    if turn.agent not in AGENTS:
        raise HTTPException(422,detail="Unknown agent")
    with sqlite3.connect(DB) as db:
        old = db.execute("SELECT role, content FROM messages WHERE session=? ORDER BY id DESC LIMIT 16",(turn.session,)).fetchall()
    prompt = ("You are ORION's "+turn.agent+" agent. Specialty: "+AGENTS[turn.agent]+
              ". Reply in the user's language, including Tamil or Tanglish. Be concise, accurate and conversational. "+
              "You have no connected tools and cannot take external actions.")
    messages = [{"role":"system","content":prompt}] + [
        {"role":role,"content":content} for role,content in reversed(old)
    ] + [{"role":"user","content":turn.text}]
    result = await upstream("POST","https://api.groq.com/openai/v1/chat/completions",
      headers={"Authorization":"Bearer "+require_key("GROQ_API_KEY")},
      json={"model":os.getenv("GROQ_MODEL","qwen/qwen3.8-27b"),"messages":messages,"temperature":0.5})
    try:
        answer = result.json()["choices"][0]["message"]["content"]
    except (KeyError,IndexError,TypeError,ValueError) as exc:
        raise HTTPException(502,detail="Unexpected Groq response") from exc
    with sqlite3.connect(DB) as db:
        db.executemany("INSERT INTO messages(session,role,content,agent) VALUES(?,?,?,?)",
           [(turn.session,"user",turn.text,turn.agent),(turn.session,"assistant",answer,turn.agent)])
    return {"answer":answer}

@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    audio = await file.read(10_000_001)
    if len(audio) > 10_000_000:
        raise HTTPException(413,detail="Audio too large; limit 10 MB")
    if not audio:
        raise HTTPException(422,detail="Empty recording")
    result = await upstream("POST","https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization":"Bearer "+require_key("GROQ_API_KEY")},
        data={"model":os.getenv("GROQ_WHISPER_MODEL","whisper-large-v3-turbo")},
        files={"file":(file.filename or "recording.webm",audio,file.content_type or "audio/webm")})
    return {"text":result.json().get("text","")}

@app.post("/api/tts")
async def tts(turn: Turn):
    # Gemini Interactions endpoint with generate_audio response.
    result = await upstream("POST","https://generativelanguage.googleapis.com/v1beta/interactions",
      headers={"x-goog-api-key":require_key("GEMINI_API_KEY"),"Content-Type":"application/json"},
      json={"model":os.getenv("GEMINI_TTS_MODEL","gemini-3.8-flash-lite-tts"),
            "input":turn.text[:3000],
            "generation_config":{"response_modalities":["AUDIO"],
             "speech_config":{"voice_config":{"prebuilt_voice_config":{"voice_name":os.getenv("GEMINI_VOICE","Kore")}}}}})
    data=result.json()
    # Schemas differ by version; report unsupported shapes rather than returning invalid audio.
    audio = data.get("audio")
    if not isinstance(audio,str):
        for item in data.get("outputs",[]):
            for block in item.get("content",[]):
                if isinstance(block,dict) and isinstance(block.get("audio"),dict):
                    audio=block["audio"].get("data")
    if not isinstance(audio,str):
        raise HTTPException(502,detail="TTS response format not recognized; verify current Gemini API schema")
    try:
        sound=base64.b64decode(audio)
    except ValueError as exc:
        raise HTTPException(502,detail="Invalid TTS audio") from exc
    return Response(sound,media_type="audio/wav")
