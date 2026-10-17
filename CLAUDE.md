# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

O.R.I.O.N. is a localhost-only, voice-first AI assistant prototype built on hosted APIs only (no local inference): Groq Whisper (speech-to-text), Groq chat model (default `qwen/qwen3.8-27b`), and Gemini TTS. There is no login, so it must never be exposed publicly. Never commit `.env`, API keys, recordings, or `data/orion.sqlite3`.

## Commands

- Setup: `python -m venv .venv`, activate it, `python -m pip install -r requirements-dev.txt`, copy `.env.example` to `.env` and add `GROQ_API_KEY` / `GEMINI_API_KEY`.
- Run: `python run.py` serves http://127.0.0.1:8787 (port via `ORION_PORT`). `START_WINDOWS.bat` is an optional Windows launcher.
- Tests: `python -m pytest -q`; single test: `python -m pytest -q tests/test_orion.py::test_health_and_frontend`. CI (`.github/workflows/tests.yml`) runs the same on Python 3.12.
- No linter or build step is configured.

## Architecture

- `orion_app.py` is the whole backend (FastAPI). `run.py` just loads `.env` and starts uvicorn bound to 127.0.0.1.
- `static/index.html` is the single-file browser UI (mic recording, chat, agent picker); served at `/`.
- Request flow: browser records audio, `POST /api/transcribe` (Groq Whisper, 10 MB limit), `POST /api/chat` (Groq chat), `POST /api/tts` (Gemini), then plays the returned WAV. API keys stay server-side; `require_key` returns 503 if a key is missing or still a `replace_...` placeholder.
- All provider calls go through `upstream()`, which maps provider/network failures to HTTP 502 with sanitized messages.
- The 18 "agents" in the `AGENTS` dict are only system-prompt personas (name -> specialty); they have no tools or external actions. `/api/health` reports them and whether keys are configured.
- Persistence: SQLite `data/orion.sqlite3` (auto-created), table `messages(session, role, content, agent)`. `/api/chat` loads the last 16 messages of the session as context. Sessions are client-generated 32-char lowercase hex ids, validated by regex.
- Security: `TrustedHostMiddleware` only allows `127.0.0.1`, `localhost`, `testserver` (the last is needed by tests); docs/redoc are disabled.
- The Gemini TTS response parser accepts multiple response shapes (`audio` or `outputs[].content[].audio.data`) because the API schema varies by version; unrecognized shapes return a 502 rather than bad audio.
- Tests use `httpx.ASGITransport` against the app with dummy keys and never call real providers.
