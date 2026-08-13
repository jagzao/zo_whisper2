import os
import re
import subprocess
from pathlib import Path


def convert_video_to_wav(video_path: str, wav_path: str) -> str | None:
    """
    Convierte un video a audio WAV usando ffmpeg.
    """
    if os.path.exists(wav_path):
        print(f"🎧 Audio ya existe: {wav_path}")
        return wav_path

    command = [
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "44100", "-ac", "2", wav_path
    ]

    try:
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=600)
        return wav_path
    except subprocess.CalledProcessError as e:
        print(f"❌ Error en ffmpeg: {e.stderr}")
        return None
    except subprocess.TimeoutExpired:
        print("❌ ffmpeg timed out converting video to wav")
        return None

def clean_transcription(
    text: str,
    language: str | None = None,
    custom_fillers: list | None = None,
    corrections: dict | None = None,
) -> str:
    """
    Remove filler words calibrated from 206 real transcriptions (464k ES words, 20k EN words).
    Per-project custom_fillers and corrections are applied on top of the global rules.

    Top fillers found:
      ES: okay/ok (8.8/1k), pues (1.3/1k), bueno (1.1/1k), este (0.8/1k),
          o sea (0.7/1k), am (0.6/1k), entonces at sentence start, ajá, mm, ah
      EN: so at sentence start (14.6/1k), like as filler (5.4/1k), right alone (2.6/1k)

    Rules are conservative: only remove isolated/repeated fillers, not content words.
    """
    # Whisper output is a single inline string — patterns use lookbehinds, not ^ multiline.

    # --- 1. Collapse repetitions: "okay okay okay" → "okay" ----------------------
    for pat in [r"(okay)(\s+okay)+", r"(ok)(\s+ok)+", r"(so)(\s+so)+",
                r"(sí)(\s+sí)+", r"(ya)(\s+ya)+", r"(mm+)(\s+mm+)+"]:
        text = re.sub(pat, r"\1", text, flags=re.IGNORECASE)

    # --- 2. Remove filler micro-sentences: ". Mm. Next" → ". Next" ---------------
    # \b prevents matching inside words (e.g. "am" in "también")
    _sounds = r"\b(mm+|ah+(?!ora)|eh+|ajá|aja|um+|uh+|am)\b"
    text = re.sub(r"(?<=[.!?])\s+" + _sounds + r"\s*[.!?,]?\s+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^" + _sounds + r"\s*[.!?,]?\s+", "", text, flags=re.IGNORECASE)

    # --- 3. Remove standalone acknowledgments: ". Right. Next" → ". Next" --------
    _acks = r"\b(right|okay|ok|yeah|yep|claro|exacto|correcto)\b"
    text = re.sub(r"(?<=[.!?])\s+" + _acks + r"\s*[.!?,]\s+", " ", text, flags=re.IGNORECASE)

    # --- 4. Filler sounds mid-sentence: ", mm, " → " " / " ajá " → " " ----------
    text = re.sub(r",?\s*" + _sounds + r"\s*,?", " ", text, flags=re.IGNORECASE)

    # --- 5. ES sentence-start fillers (handles chains: "Este, bueno pues, X") ----
    _es_alts = r"pues\s+este|bueno\s+pues|o\s+sea\s+este|bueno|pues|entonces|o\s+sea|este|osea"
    # After sentence boundary — single pass covers most cases
    text = re.sub(r"(?<=[.!?])\s+(" + _es_alts + r")\s*[,\s]+", " ", text, flags=re.IGNORECASE)
    # At string start — loop to handle consecutive fillers: "Este, bueno pues, X" → "X"
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"^(?:" + _es_alts + r")\s*[,\s]+", "", text, flags=re.IGNORECASE)

    # --- 6. EN sentence-start "So" (14.6/1k) -------------------------------------
    text = re.sub(r"(?<=[.!?])\s+so\b[,\s]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^so\b[,\s]+", "", text, flags=re.IGNORECASE)

    # --- 7. ", like," mid-sentence -----------------------------------------------
    text = re.sub(r",\s*like\s*,", ",", text, flags=re.IGNORECASE)

    # --- 8. Project corrections: fix names/terms Whisper transcribed wrong -------
    # Applied before custom fillers so corrected words aren't then removed.
    # Example: "Baibav" → "Vaibhav", "Capegimi" → "Capgemini"
    if corrections:
        for wrong, right in corrections.items():
            text = re.sub(r"\b" + re.escape(wrong) + r"\b", right, text, flags=re.IGNORECASE)

    # --- 9. Project-specific custom fillers ---------------------------------------
    # Same conservative rules as global fillers: remove at sentence boundary or start.
    # Example custom_fillers: ["like", "right", "basically", "you know", "perfecto"]
    for filler in (custom_fillers or []):
        f = re.escape(filler.strip())
        # After sentence boundary: ". Right. Next" → ". Next"
        text = re.sub(r"(?<=[.!?])\s+\b" + f + r"\b\s*[.!?,]?\s+", " ", text, flags=re.IGNORECASE)
        # At string start: "Right, the problem..." → "The problem..."
        text = re.sub(r"^\b" + f + r"\b\s*[,\s]+", "", text, flags=re.IGNORECASE)
        # Mid-sentence isolated: ", right," → ","
        text = re.sub(r",\s*\b" + f + r"\b\s*,", ",", text, flags=re.IGNORECASE)

    # --- 10. Final cleanup -------------------------------------------------------
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"([.!?]\s+)([a-záéíóúñü])", lambda m: m.group(1) + m.group(2).upper(), text)
    if text:
        text = text[0].upper() + text[1:]

    return text.strip()

def extract_project_and_company(video_path: Path) -> tuple[str, str]:
    parts = video_path.parts
    project_name = parts[-2] if len(parts) >= 2 else "desconocido"
    company_name = parts[-3] if len(parts) >= 3 else "default"
    return project_name, company_name

def detect_language_from_filename(file_path: str | Path) -> str | None:
    """
    Detect language from filename prefix.

    Convention:
    - 'en_' prefix -> English
    - 'es_' prefix -> Spanish
    - No prefix -> English (default)

    Args:
        file_path: Path to the audio/video file

    Returns:
        str: Language code ('en' or 'es')

    Examples:
        >>> detect_language_from_filename("en_meeting_2024.mp4")
        'en'
        >>> detect_language_from_filename("es_entrevista.mp4")
        'es'
        >>> detect_language_from_filename("meeting_notes.mp4")
        'en'
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    filename = file_path.stem  # Get filename without extension

    if filename.startswith("en_"):
        return "en"
    elif filename.startswith("es_"):
        return "es"
    return None  # None → Whisper auto-detects


def is_tutorial_video(file_path: str | Path) -> bool:
    """
    Detecta si un video es un tutorial basado en el nombre del archivo.

    Busca la palabra "tutorial" en el nombre del archivo (case-insensitive).
    Esta función se usa para activar funcionalidades especiales como
    la extracción de frames clave y la inclusión de timestamps.

    Args:
        file_path: Ruta al archivo de video

    Returns:
        True si el nombre contiene 'tutorial' (case-insensitive)

    Examples:
        >>> is_tutorial_video("tutorial_python_basico.mp4")
        True
        >>> is_tutorial_video("JavaScript_Tutorial_2024.mp4")
        True
        >>> is_tutorial_video("meeting_notes.mp4")
        False
        >>> is_tutorial_video("TUTORIAL_JavaScript.mp4")
        True
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    filename = file_path.stem.lower()
    return "tutorial" in filename
