"""ORION Voice: cross-platform localhost client for hosted Groq + Gemini APIs."""
import asyncio
import base64
import json
import re
import os
import sqlite3
import uuid
from pathlib import Path
import edge_tts
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
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

# One shared client keeps TLS connections to the providers warm (saves ~0.4s per call).
HTTP = httpx.AsyncClient(timeout=90)

async def upstream(method, url, **kwargs):
    try:
        result = await HTTP.request(method, url, **kwargs)
        result.raise_for_status()
        return result
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, detail=f"AI provider returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, detail="AI provider connection error") from exc

@app.get("/")
async def root():
    return FileResponse(BASE / "static" / "index.html")

@app.on_event("startup")
async def preload_local_models():
    """Load local speech models in the background so the first voice turn isn't a 30s+ wait."""
    if "local" not in (os.getenv("STT_PROVIDER","local"), os.getenv("TTS_PROVIDER","local")):
        return
    def warm():
        try:
            import local_ai
            local_ai.whisper_model()
            local_ai.synthesize("Ready.")
            local_ai.synthesize("தயார்.")
        except Exception:
            pass
    asyncio.get_running_loop().run_in_executor(None, warm)

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

def build_messages(turn):
    if turn.agent not in AGENTS:
        raise HTTPException(422,detail="Unknown agent")
    with sqlite3.connect(DB) as db:
        old = db.execute("SELECT role, content FROM messages WHERE session=? ORDER BY id DESC LIMIT 16",(turn.session,)).fetchall()
    prompt = ("You are ORION's "+turn.agent+" agent. Specialty: "+AGENTS[turn.agent]+
              ". Reply in the user's language, including Tamil or Tanglish. Be concise, accurate and conversational. "+
              "You have no connected tools and cannot take external actions.")
    return [{"role":"system","content":prompt}] + [
        {"role":role,"content":content} for role,content in reversed(old)
    ] + [{"role":"user","content":turn.text}]

def save_turn(turn, answer):
    with sqlite3.connect(DB) as db:
        db.executemany("INSERT INTO messages(session,role,content,agent) VALUES(?,?,?,?)",
           [(turn.session,"user",turn.text,turn.agent),(turn.session,"assistant",answer,turn.agent)])

@app.post("/api/chat/stream")
async def chat_stream(turn: Turn):
    """Server-sent events: each event is {"d": text_delta}; used for the live-call mode."""
    messages = build_messages(turn)
    key = require_key("GROQ_API_KEY")
    async def events():
        answer = ""
        try:
            if True:
                async with HTTP.stream("POST","https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization":"Bearer "+key},
                    json={"model":os.getenv("GROQ_MODEL","qwen/qwen3.8-27b"),"messages":messages,"temperature":0.5,"stream":True}) as r:
                    if r.status_code >= 400:
                        yield "data: "+json.dumps({"error":f"AI provider returned HTTP {r.status_code}"})+"\n\n"
                        return
                    async for line in r.aiter_lines():
                        if not line.startswith("data:") or line.strip() == "data: [DONE]":
                            continue
                        try:
                            delta = json.loads(line[5:])["choices"][0]["delta"].get("content") or ""
                        except (ValueError, KeyError, IndexError, TypeError):
                            continue
                        if delta:
                            answer += delta
                            yield "data: "+json.dumps({"d":delta})+"\n\n"
        except httpx.HTTPError:
            yield "data: "+json.dumps({"error":"AI provider connection error"})+"\n\n"
        finally:
            if answer:
                save_turn(turn, answer)
    return StreamingResponse(events(), media_type="text/event-stream")

@app.post("/api/chat")
async def chat(turn: Turn):
    messages = build_messages(turn)
    result = await upstream("POST","https://api.groq.com/openai/v1/chat/completions",
      headers={"Authorization":"Bearer "+require_key("GROQ_API_KEY")},
      json={"model":os.getenv("GROQ_MODEL","qwen/qwen3.8-27b"),"messages":messages,"temperature":0.5})
    try:
        answer = result.json()["choices"][0]["message"]["content"]
    except (KeyError,IndexError,TypeError,ValueError) as exc:
        raise HTTPException(502,detail="Unexpected Groq response") from exc
    save_turn(turn, answer)
    return {"answer":answer}

@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    audio = await file.read(10_000_001)
    if len(audio) > 10_000_000:
        raise HTTPException(413,detail="Audio too large; limit 10 MB")
    if not audio:
        raise HTTPException(422,detail="Empty recording")
    if os.getenv("STT_PROVIDER","local") == "local":
        try:
            import local_ai
            return {"text":await asyncio.to_thread(local_ai.transcribe, audio)}
        except Exception:
            if not os.getenv("GROQ_API_KEY"):
                raise HTTPException(502,detail="Local transcription failed")
    result = await upstream("POST","https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization":"Bearer "+require_key("GROQ_API_KEY")},
        data={"model":os.getenv("GROQ_WHISPER_MODEL","whisper-large-v3-turbo")},
        files={"file":(file.filename or "recording.webm",audio,file.content_type or "audio/webm")})
    return {"text":result.json().get("text","")}

async def edge_tts_audio(text):
    """Free Microsoft neural voices (no key, no daily quota); Tamil text gets a Tamil voice."""
    voice = (os.getenv("EDGE_VOICE_TA","ta-LK-SaranyaNeural") if re.search("[஀-௿]", text)
             else os.getenv("EDGE_VOICE","en-US-AriaNeural"))
    chunks = []
    async for part in edge_tts.Communicate(text[:3000], voice).stream():
        if part["type"] == "audio":
            chunks.append(part["data"])
    if not chunks:
        raise RuntimeError("no audio")
    return b"".join(chunks)

@app.post("/api/tts")
async def tts(turn: Turn):
    provider = os.getenv("TTS_PROVIDER","local")
    if provider == "local":
        try:
            import local_ai
            return Response(await asyncio.to_thread(local_ai.synthesize, turn.text[:3000]), media_type="audio/wav")
        except Exception:
            provider = "edge"
    if provider == "edge":
        try:
            return Response(await edge_tts_audio(turn.text), media_type="audio/mpeg")
        except Exception:
            if not os.getenv("GEMINI_API_KEY"):
                raise HTTPException(502, detail="Edge TTS unavailable")
    return await gemini_tts(turn)

async def gemini_tts(turn: Turn):
    # Gemini Interactions endpoint with generate_audio response.
    result = await upstream("POST","https://generativelanguage.googleapis.com/v1beta/interactions",
      headers={"x-goog-api-key":require_key("GEMINI_API_KEY"),"Content-Type":"application/json"},
      json={"model":os.getenv("GEMINI_TTS_MODEL","gemini-3.8-flash-lite-tts"),
            "input":turn.text[:3000],
            "response_modalities":["audio"],
            "generation_config":{"speech_config":[{"voice":os.getenv("GEMINI_VOICE","Kore")}]}})
    data=result.json()
    # Schemas differ by version; report unsupported shapes rather than returning invalid audio.
    audio = data.get("audio")
    for step in data.get("steps",[]):
        for block in step.get("content",[]):
            if isinstance(block,dict) and isinstance(block.get("data"),str):
                audio=block["data"]
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
