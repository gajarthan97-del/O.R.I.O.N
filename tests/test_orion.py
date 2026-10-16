import os
os.environ.setdefault("GROQ_API_KEY","test-key")
os.environ.setdefault("GEMINI_API_KEY","test-key")
import httpx
import pytest
from orion_app import app, AGENTS

@pytest.mark.asyncio
async def test_health_and_frontend():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as client:
        r=await client.get("/api/health")
        assert r.status_code==200
        assert len(r.json()["agents"])==18
        page=await client.get("/")
        assert page.status_code==200
        assert "O.R.I.O.N." in page.text

@pytest.mark.asyncio
async def test_invalid_agent_no_provider_request():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as client:
        r=await client.post("/api/chat",json={"session":"a"*32,"agent":"unknown","text":"hello"})
        assert r.status_code==422

@pytest.mark.asyncio
async def test_empty_audio_is_rejected():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as client:
        r=await client.post("/api/transcribe",files={"file":("empty.webm",b"","audio/webm")})
        assert r.status_code==422

@pytest.mark.asyncio
async def test_history_input_validation():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as client:
        r=await client.get("/api/history/not-a-session")
        assert r.status_code==422
