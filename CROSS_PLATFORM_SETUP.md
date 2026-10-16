# O.R.I.O.N. — Personal Voice AI

Cross-platform browser-based voice assistant using **hosted APIs only**. Runs on **Windows, macOS and Linux**, with Python 3.11+ and an Internet connection; **no Ollama or local GPU inference**.

- Speech recognition: Groq `whisper-large-v3-turbo`
- Reasoning: Groq `qwen/qwen3.8-27b`
- Voice output: Google Gemini `gemini-3.8-flash-lite-tts`
- Browser microphone, Tamil/English/Tanglish prompts, agent selection and SQLite chat history

## Run on any OS

1. Install Python 3.11+ and Git.
2. `git clone https://github.com/gajarthan97-del/O.R.I.O.N.git`
3. `cd O.R.I.O.N`
4. Create a virtual environment: `python -m venv .venv` (or `python3 -m venv .venv`).
5. Activate:
   - **Windows PowerShell:** `.venv\\Scripts\\Activate.ps1`
   - **Windows CMD:** `.venv\\Scripts\\activate.bat`
   - **macOS / Linux:** `source .venv/bin/activate`
6. `python -m pip install -r requirements.txt`
7. Copy `.env.example` to `.env`, insert your Groq and Gemini keys. Never commit `.env`.
8. `python run.py` (or `python3 run.py`) and visit **http://127.0.0.1:8787**.
9. Allow microphone access, click Record, Stop, and speak.

## Security and limitations

**Localhost prototype, not a public multiuser deployment.** No user authentication or login; never expose port 8787 publicly. Chat is stored in `data/orion.sqlite3`; API requests go to cloud providers. Uploaded audio is transmitted to Groq; response text to Gemini. Keys stay server-side. Free API quotas and live provider model schemas can change, especially Gemini TTS: validate using real keys.

18 named agents are role prompts, not autonomous tools or MCP connections. Their instructions do not grant access to your computer or accounts.

The optional `START_WINDOWS.bat` is only a convenience; the Python startup process works on all three OS platforms.
