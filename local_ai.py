"""Optional fully-local speech: faster-whisper (STT), Kokoro (English TTS), MMS (Tamil TTS).

Everything is imported and loaded lazily so the app still starts when these extras are not installed.
"""
import io
import os
import re
import threading
import urllib.request
import wave
from pathlib import Path

MODELS = Path(__file__).resolve().parent / "models"
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
TAMIL = re.compile("[஀-௿]")
_lock = threading.Lock()
_whisper = _kokoro = _mms = None


def _add_cuda_dlls():
    """pip-installed CUDA libraries (nvidia-cublas/cudnn) live in site-packages/nvidia/*/bin on Windows."""
    try:
        import nvidia
    except ImportError:
        return
    for base in nvidia.__path__:
        for sub in Path(base).glob("*/bin"):
            os.add_dll_directory(str(sub))
            os.environ["PATH"] = str(sub) + os.pathsep + os.environ["PATH"]


def whisper_model():
    global _whisper
    with _lock:
        if _whisper is None:
            _add_cuda_dlls()
            from faster_whisper import WhisperModel
            name = os.getenv("LOCAL_WHISPER_MODEL", "large-v3-turbo")
            try:
                _whisper = WhisperModel(name, device="cuda", compute_type="float16")
            except Exception:
                _whisper = WhisperModel(name, device="cpu", compute_type="int8")
        return _whisper


def transcribe(audio: bytes) -> str:
    model = whisper_model()
    segments, _ = model.transcribe(io.BytesIO(audio), vad_filter=True, beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()


def _wav(samples, rate) -> bytes:
    import numpy as np
    pcm = (np.clip(np.asarray(samples, dtype="float32").squeeze(), -1, 1) * 32767).astype("int16")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return out.getvalue()


def _fetch(name: str) -> Path:
    MODELS.mkdir(exist_ok=True)
    path = MODELS / name
    if not path.exists():
        tmp = path.with_suffix(path.suffix + ".part")
        urllib.request.urlretrieve(KOKORO_URL + name, tmp)
        tmp.replace(path)
    return path


def _english(text: str) -> bytes:
    global _kokoro
    with _lock:
        if _kokoro is None:
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(str(_fetch("kokoro-v1.0.onnx")), str(_fetch("voices-v1.0.bin")))
        engine = _kokoro
    samples, rate = engine.create(text, voice=os.getenv("LOCAL_VOICE", "af_heart"), speed=1.0, lang="en-us")
    return _wav(samples, rate)


def _tamil(text: str) -> bytes:
    global _mms
    with _lock:
        if _mms is None:
            import torch
            from transformers import AutoTokenizer, VitsModel
            repo = "facebook/mms-tts-tam"
            _mms = (AutoTokenizer.from_pretrained(repo), VitsModel.from_pretrained(repo).eval(), torch)
        tok, model, torch = _mms
    with torch.no_grad():
        wave_out = model(**tok(text, return_tensors="pt")).waveform[0].numpy()
    return _wav(wave_out, model.config.sampling_rate)


def synthesize(text: str) -> bytes:
    """Tamil script goes to MMS, everything else to Kokoro. Returns WAV bytes."""
    return _tamil(text) if TAMIL.search(text) else _english(text)
