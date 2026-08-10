import os
import time
import whisper
import logging

# Configuración del logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")

def already_transcribed(output_txt_path):
    return os.path.exists(output_txt_path) and os.path.getsize(output_txt_path) > 100

def safe_load_model(model_name="base", max_retries=3, wait_sec=10):
    for attempt in range(max_retries):
        try:
            logging.info(f"🧠 Cargando modelo Whisper (intento {attempt + 1})...")
            return whisper.load_model(model_name)
        except Exception as e:
            logging.error(f"❌ Error al cargar modelo: {e}")
            time.sleep(wait_sec)
    raise RuntimeError("❌ No se pudo cargar Whisper.")

def safe_transcribe(audio_path, output_txt_path, model_name="base"):
    if already_transcribed(output_txt_path):
        logging.info(f"📄 Ya existe transcripción: {output_txt_path}")
        return "already_exists"

    try:
        model = safe_load_model(model_name)
        result = model.transcribe(audio_path)
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(result["text"])
        logging.info(f"✅ Transcripción exitosa: {output_txt_path}")
        return "success"
    except Exception as e:
        logging.error(f"❌ Error al transcribir {audio_path}: {e}")
        return "failed"
