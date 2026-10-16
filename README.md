# O.R.I.O.N. — Personal Voice AI

A Windows-ready, voice-first AI assistant prototype using **hosted APIs only**.

**Services:** Groq Whisper Large V3 Turbo (speech-to-text), Groq Qwen3.8-27B (chat), Google Gemini Flash-Lite TTS (speech).

**Features:** Tamil/English/Tanglish voice input, local browser UI, 18 role-based agent prompts, conversation history saved to SQLite, backend-only API keys, and basic error handling.

**Security:** This is a localhost-only prototype without login. **Never expose it publicly** or commit a real `.env`, API key, audio recording, or chat database.

## Windows setup

1. Install Python 3.11+.
2. Clone this repository.
3. Copy `.env.example` to `.env` and add your own Groq and Gemini API keys.
4. Run `START_WINDOWS.bat`.
5. Visit http://127.0.0.1:8787, enable microphone access, and test a conversation.

You can also run `python -m pip install -r requirements-dev.txt` followed by `python -m pytest -q`.

**Known limitation:** These 18 agents are configurable prompts, not connected autonomous tools. Live API calls require working provider keys and quota. The project intentionally uses cloud speech and reasoning services rather than local AI inference.

Owner: **gajarthan97-del**. This GitHub repository is currently public.
