# C:\Jagzao\whisper\transcription_provider.py
import whisper
import os

USE_PROVIDER = os.getenv("TRANSCRIBE_PROVIDER", "whisper")  # "whisper", "faster", "api"

# WHISPER BASE / MEDIUM
def whisper_transcribe(file_path, language="en"):
    model_size = os.getenv("WHISPER_MODEL", "medium")  # "base", "medium", etc.
    model = whisper.load_model(model_size)
    return model.transcribe(file_path, language=language)

# FASTER WHISPER
def faster_transcribe(file_path, language="en"):
    from faster_whisper import WhisperModel
    model_size = os.getenv("WHISPER_MODEL", "medium")
    model = WhisperModel(model_size, compute_type="int8", device="cpu")
    segments, _ = model.transcribe(file_path, language=language)
    return {"text": " ".join([seg.text for seg in segments])}

# OPENAI WHISPER API
def api_transcribe(file_path, language="en"):
    import openai
    openai.api_key = os.getenv("OPENAI_API_KEY")
    with open(file_path, "rb") as f:
        transcript = openai.Audio.transcribe("whisper-1", f, language=language)
    return {"text": transcript["text"]}

# SELECCIÓN GENERAL
def transcribe(file_path, language="en"):
    if USE_PROVIDER == "whisper":
        return whisper_transcribe(file_path, language)
    elif USE_PROVIDER == "faster":
        return faster_transcribe(file_path, language)
    elif USE_PROVIDER == "api":
        return api_transcribe(file_path, language)
    else:
        raise ValueError(f"Proveedor inválido: {USE_PROVIDER}")
