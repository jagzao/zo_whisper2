#!/usr/bin/env python3
"""
Script para procesar manualmente una carpeta específica
Uso: python3 manual_process_folder.py <nombre_carpeta>
"""

import sys
import logging
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s'
)

# Importar funciones del watcher
sys.path.insert(0, '/app')
from services.watcher_and_processor import process_video

def process_folder(folder_name):
    """Procesar todos los archivos de una carpeta específica"""

    logging.info(f"📂 Procesando carpeta: {folder_name}")

    # Buscar en audio/
    audio_folder = Path(f'/app/audio/{folder_name}')
    video_folder = Path(f'/app/Videos/{folder_name}')

    audio_files = []

    # Recolectar archivos de audio
    if audio_folder.exists():
        audio_files.extend(audio_folder.glob('*.mp3'))
        audio_files.extend(audio_folder.glob('*.wav'))
        audio_files.extend(audio_folder.glob('*.m4a'))
        audio_files.extend(audio_folder.glob('*.flac'))
        logging.info(f"📦 Encontrados {len(audio_files)} archivos en audio/{folder_name}")
    else:
        logging.warning(f"⚠️  Carpeta no existe: audio/{folder_name}")

    # Recolectar archivos de video
    if video_folder.exists():
        video_files = []
        video_files.extend(video_folder.glob('*.mp4'))
        video_files.extend(video_folder.glob('*.mkv'))
        video_files.extend(video_folder.glob('*.mov'))
        video_files.extend(video_folder.glob('*.avi'))
        video_files.extend(video_folder.glob('*.webm'))
        audio_files.extend(video_files)
        logging.info(f"📦 Encontrados {len(video_files)} archivos en Videos/{folder_name}")
    else:
        logging.warning(f"⚠️  Carpeta no existe: Videos/{folder_name}")

    if not audio_files:
        logging.error(f"❌ No se encontraron archivos en {folder_name}")
        return False

    logging.info(f"🎯 Total de archivos a procesar: {len(audio_files)}")
    logging.info("=" * 50)

    # Procesar cada archivo
    success_count = 0
    error_count = 0

    for idx, audio_file in enumerate(audio_files, 1):
        try:
            logging.info(f"\n[{idx}/{len(audio_files)}] 🎬 Procesando: {audio_file.name}")
            result = process_video(str(audio_file))

            if result:
                success_count += 1
                logging.info(f"✅ Completado: {audio_file.name}")
            else:
                error_count += 1
                logging.warning(f"⚠️  Fallo al procesar: {audio_file.name}")

        except Exception as e:
            error_count += 1
            logging.error(f"❌ Error procesando {audio_file.name}: {e}")

    # Resumen final
    logging.info("\n" + "=" * 50)
    logging.info("📊 RESUMEN DE PROCESAMIENTO")
    logging.info("=" * 50)
    logging.info(f"✅ Exitosos: {success_count}")
    logging.info(f"❌ Errores: {error_count}")
    logging.info(f"📁 Total: {len(audio_files)}")
    logging.info("=" * 50)

    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Error: Falta el nombre de la carpeta")
        print("Uso: python3 manual_process_folder.py <nombre_carpeta>")
        sys.exit(1)

    folder_name = sys.argv[1]

    try:
        success = process_folder(folder_name)
        sys.exit(0 if success else 1)
    except Exception as e:
        logging.error(f"❌ Error fatal: {e}")
        sys.exit(1)
