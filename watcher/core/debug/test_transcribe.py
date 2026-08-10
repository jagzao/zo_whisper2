from pathlib import Path
from core.transcription.transcription_provider import transcribe
from core.utils import convert_video_to_wav, clean_transcription

# Rutas locales
video_file = Path("C:/Jagzao/whisper/Videos/Apoc/validacionesFaltantesRoles.webm")
wav_file = Path("C:/Jagzao/whisper/audio/Apoc/validacionesFaltantesRoles.wav")

# Crear carpeta de salida
wav_file.parent.mkdir(parents=True, exist_ok=True)

# Convertir video a WAV
if convert_video_to_wav(str(video_file), str(wav_file)):
    print("🎧 Conversión exitosa.")
else:
    print("❌ Conversión fallida.")

# Transcribir
result = transcribe(str(wav_file), language="es")
text = result["text"]
cleaned = clean_transcription(text)

print("\n📝 Transcripción:")
print(cleaned)
