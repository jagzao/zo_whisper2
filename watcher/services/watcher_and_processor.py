# C:\Jagzao\whisper\watcher\services\watcher_and_processor.py
import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s | %(message)s")

# Usar transcriptor optimizado con todas las mejoras
try:
    from core.transcription.optimized_transcriber import enhanced_transcribe as safe_transcribe
    logging.info("✨ [TRANSCRIBER] Usando transcriptor optimizado (faster-whisper + large-v2)")
except ImportError as e:
    # Fallback al transcriptor anterior si el optimizado no está disponible
    from core.transcription.safe_transcriber import safe_transcribe
    logging.warning(f"⚠️  [TRANSCRIBER] Usando transcriptor legacy: {e}")

# Scheduler para horarios de procesamiento
try:
    from core.scheduler_config import schedule_manager, SchedulerConfig
    SCHEDULER_AVAILABLE = True
    logging.info("⏰ [SCHEDULER] Gestor de horarios cargado")
except ImportError as e:
    SCHEDULER_AVAILABLE = False
    logging.warning(f"⚠️  [SCHEDULER] No disponible: {e}")

import os
import time
import threading
from datetime import datetime
from typing import Dict, Optional, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
import shutil
import queue
from threading import Lock
import signal
import sys

from core.transcription.transcription_provider import transcribe
# Importación condicional de transcripción en tiempo real
try:
    from core.transcription.realtime_transcriber import (
        realtime_transcriber,
        start_video_realtime_transcription,
        start_call_realtime_transcription,
        stop_realtime_transcription,
        get_realtime_results,
        get_realtime_full_text
    )
    REALTIME_AVAILABLE = True
    logging.info("Módulo de transcripción en tiempo real cargado correctamente")
except ImportError as e:
    logging.warning(f"Transcripción en tiempo real no disponible: {e}")
    REALTIME_AVAILABLE = False
    
    # Funciones mock para cuando no esté disponible
    def start_video_realtime_transcription(*args, **kwargs):
        raise RuntimeError("Transcripción en tiempo real no disponible")
    
    def start_call_realtime_transcription(*args, **kwargs):
        raise RuntimeError("Transcripción en tiempo real no disponible")
    
    def stop_realtime_transcription(*args, **kwargs):
        return False
    
    def get_realtime_results(*args, **kwargs):
        return []
    
    def get_realtime_full_text(*args, **kwargs):
        return ""
from core.summary.summary_provider import generate_summary
from core.notifier.email_notifier import send_email
from core.utils import convert_video_to_wav, clean_transcription, extract_project_and_company, detect_language_from_filename
from core.analysis.content_analyzer import ContentAnalyzer
from core.integration.rag_integrator import RAGIntegrator

VIDEO_BASE = "/app/Videos"
AUDIO_BASE = "/app/audio"
OUTPUT_BASE = "/app/CarpetaTranscripciones"
LANGUAGE = "en"  # Default language (can be overridden by filename prefix es_ or en_)

# Configuración de tiempo real
ENABLE_REALTIME_VIDEO = os.getenv("ENABLE_REALTIME_VIDEO", "true").lower() == "true"
ENABLE_REALTIME_CALLS = os.getenv("ENABLE_REALTIME_CALLS", "true").lower() == "true"
REALTIME_CHUNK_SIZE = int(os.getenv("REALTIME_CHUNK_SIZE", "30"))
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "3"))

# Cola de procesamiento para evitar concurrencia
processing_queue = queue.Queue()
processing_lock = Lock()
is_processing = False

# Conjunto para rastrear archivos ya procesados
processed_files = set()

# Sesiones de tiempo real activas
active_realtime_sessions = {}
realtime_lock = Lock()

# Heartbeat para healthcheck
HEARTBEAT_FILE = "/tmp/watcher_alive"
last_activity_time = time.time()
activity_lock = Lock()

def update_heartbeat():
    """Actualizar el archivo de heartbeat para el healthcheck"""
    try:
        with open(HEARTBEAT_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception as e:
        logging.warning(f"Error actualizando heartbeat: {e}")

def update_activity():
    """Actualizar el tiempo de última actividad"""
    global last_activity_time
    with activity_lock:
        last_activity_time = time.time()
    update_heartbeat()

def start_watchdog_thread():
    """Iniciar thread de watchdog que vigila la actividad del watcher"""
    def watchdog_worker():
        while True:
            try:
                with activity_lock:
                    inactive_time = time.time() - last_activity_time
                
                # Si no hay actividad por más de 15 minutos, reiniciar
                if inactive_time > 900:  # 15 minutos
                    logging.error(f"🚨 WATCHDOG: Sin actividad por {inactive_time:.0f}s - Reiniciando proceso")
                    os.kill(os.getpid(), signal.SIGTERM)
                
                # Actualizar heartbeat cada minuto
                update_heartbeat()
                time.sleep(60)
                
            except Exception as e:
                logging.error(f"Error en watchdog: {e}")
                time.sleep(60)
    
    watchdog_thread = threading.Thread(target=watchdog_worker, daemon=True)
    watchdog_thread.start()
    logging.info("🐕 Watchdog interno iniciado - reinicio automático si sin actividad > 5min")

def file_already_transcribed(video_path):
    """Verifica si ya existe transcripción para este archivo"""
    try:
        video_path = Path(video_path)
        project_name, _ = extract_project_and_company(video_path)
        
        # Crear nombre con prefijo de fecha de hoy
        date_prefix = datetime.now().strftime("%y_%m_%d")
        base_name = video_path.stem
        prefixed_name = f"{date_prefix}_{base_name}"
        
        output_folder = Path(OUTPUT_BASE) / project_name
        txt_file = output_folder / f"{prefixed_name}.txt"
        
        return txt_file.exists()
    except Exception:
        return False

class VideoHandler(FileSystemEventHandler):
    def on_created(self, event):
        logging.info(f"📦 Archivo creado: {event.src_path}")
        if not event.is_directory and event.src_path.endswith(('.mp4', '.mkv', '.mov', '.avi', '.webm', '.mp3', '.wav', '.m4a')):
            
            # Verificar si debe usar transcripción en tiempo real
            if should_use_realtime_transcription(event.src_path):
                logging.info(f"🔴 TIEMPO REAL: {event.src_path}")
                handle_realtime_transcription(event.src_path)
            else:
                logging.info(f"🎯 Añadiendo a cola normal: {event.src_path}")
                processing_queue.put(event.src_path)

def process_existing_files(base_path):
    logging.info("🔍 Buscando archivos existentes...")
    for root, _, files in os.walk(base_path):
        for file in files:
            if file.endswith(('.mp4', '.mkv', '.mov', '.avi', '.webm', '.mp3', '.wav', '.m4a')):
                full_path = os.path.join(root, file)
                
                # Verificar si ya fue procesado
                if full_path in processed_files:
                    continue
                    
                # Verificar si ya existe transcripción
                if file_already_transcribed(full_path):
                    processed_files.add(full_path)
                    logging.info(f"⏭️ Archivo ya transcrito, saltando: {full_path}")
                    continue
                
                logging.info(f"📦 Añadiendo archivo existente a cola: {full_path}")
                processing_queue.put(full_path)

def process_queue_worker():
    """Procesa archivos uno a la vez desde la cola, respetando horarios"""
    global is_processing

    # Log configuración de horarios al inicio
    if SCHEDULER_AVAILABLE:
        SchedulerConfig.log_current_schedule()

    while True:
        try:
            # Obtener siguiente archivo de la cola (bloquea hasta que haya uno)
            video_path = processing_queue.get(timeout=1)

            # Verificar horario antes de procesar
            if SCHEDULER_AVAILABLE:
                config = schedule_manager.get_config()
                is_work_hours = config['period'] == 'work_hours'

                if is_work_hours:
                    logging.info(f"⏰ Horario laboral (7am-11pm): Procesando 1 archivo con prioridad baja")
                else:
                    logging.info(f"🌙 Horario nocturno (11pm-7am): Modo procesamiento intensivo")

            with processing_lock:
                is_processing = True

            logging.info(f"📤 Procesando desde cola: {video_path}")
            success = process_video(video_path)

            # Marcar archivo como procesado si fue exitoso
            if success:
                processed_files.add(video_path)

            # Marcar tarea como completada
            processing_queue.task_done()

            with processing_lock:
                is_processing = False

        except queue.Empty:
            # No hay archivos en cola, continuar esperando
            continue
        except Exception as e:
            logging.error(f"❌ Error en procesador de cola: {e}")
            with processing_lock:
                is_processing = False

def process_video(video_path):
    logging.info(f"🎬 Procesando: {video_path}")
    update_activity()  # Marcar actividad al iniciar procesamiento
    try:
        video_path = Path(video_path)
        project_name, company_name = extract_project_and_company(video_path)
        logging.info(f"📁 Proyecto: {project_name} | Compañía: {company_name}")

        audio_folder = Path(AUDIO_BASE) / project_name
        output_folder = Path(OUTPUT_BASE) / project_name
        audio_folder.mkdir(parents=True, exist_ok=True)
        output_folder.mkdir(parents=True, exist_ok=True)

        # Add date prefix to filename
        date_prefix = datetime.now().strftime("%y_%m_%d")
        base_name = video_path.stem
        prefixed_name = f"{date_prefix}_{base_name}"
        
        wav_file = audio_folder / f"{base_name}.wav"  # WAV keeps original name for processing
        txt_file = output_folder / f"{prefixed_name}.txt"  # Output files get date prefix

        # Check if it's an audio file or video file
        wav_needs_cleanup = False
        if video_path.suffix.lower() in ['.mp3', '.wav', '.m4a']:
            logging.info(f"🎵 Archivo de audio detectado: {video_path.name}")
            # If it's already a WAV file, use it directly
            if video_path.suffix.lower() == '.wav':
                wav_file = video_path
                wav_needs_cleanup = False  # Don't delete original WAV files
            else:
                # Convert audio to WAV
                logging.info(f"🎧 Convirtiendo audio a WAV: {video_path.name}")
                wav_needs_cleanup = True  # Mark for cleanup after transcription
                if not convert_video_to_wav(str(video_path), str(wav_file)):
                    logging.error("❌ Fallo en la conversión de audio a WAV.")
                    return
        else:
            logging.info(f"🎧 Convirtiendo video a WAV: {video_path.name}")
            wav_needs_cleanup = True  # Mark for cleanup after transcription
            if not convert_video_to_wav(str(video_path), str(wav_file)):
                logging.error("❌ Fallo en la conversión a WAV.")
                return

        # Detectar idioma desde el nombre del archivo original
        detected_language = detect_language_from_filename(video_path)
        logging.info(f"🌐 Idioma detectado: {detected_language.upper()} (desde nombre de archivo)")

        status = safe_transcribe(str(wav_file), str(txt_file), language=detected_language)
        if status == "failed":
            logging.warning(f"⚠️ Transcripción fallida: {base_name}")
            return
        

        with open(txt_file, encoding="utf-8") as f:
            raw_text = f.read()

        logging.info("🧹 Limpiando transcripción...")
        cleaned_text = clean_transcription(raw_text)

        from core.summary.summary_provider import generate_summary, render_summary_html
        from notion_summary_writer import send_summary_to_notion

        # Análisis inteligente por tipo de contenido
        analyzer = ContentAnalyzer()
        content_type = analyzer.detect_content_type(cleaned_text)
        
        logging.info(f"🎯 Tipo de contenido detectado: {content_type}")
        
        # Generar análisis específico según el tipo
        analysis_result = None
        if content_type == 'interview':
            analysis_result = analyzer.analyze_interview(cleaned_text, project_name)
            logging.info(f"📊 Análisis de entrevista - Score: {analysis_result.get('overall_score', 'N/A')}")
        elif content_type == 'tutorial':
            analysis_result = analyzer.analyze_tutorial(cleaned_text, project_name)
            logging.info(f"📖 Tutorial detectado - {analysis_result.get('total_steps', 0)} pasos identificados")
        elif content_type == 'meeting':
            analysis_result = analyzer.analyze_meeting(cleaned_text, project_name)
            logging.info(f"🤝 Reunión detectada - {len(analysis_result.get('action_items', []))} tareas identificadas")
        else:
            logging.info(f"📄 Contenido general detectado")

        # Generar resumen tradicional
        summary = generate_summary(cleaned_text, project_name, company_name, str(video_path))
        
        # Crear resumen enriquecido con análisis
        enriched_summary = create_enriched_summary(summary, analysis_result, content_type)
        
        html_summary = render_summary_html(enriched_summary, project_name, company_name, base_name)
        
        # Integración con RAG para reuniones de proyecto y carpetas especiales
        rag_integrator = RAGIntegrator()
        if rag_integrator.should_integrate_with_rag(content_type, project_name):
            logging.info("🔄 Integrando con sistema RAG...")
            rag_integrator.create_rag_structure_if_needed()
            rag_success = rag_integrator.integrate_meeting_transcription(
                cleaned_text, analysis_result, project_name, base_name
            )
            if rag_success:
                logging.info("✅ Transcripción integrada exitosamente en RAG")
            else:
                logging.warning("⚠️ Fallo en integración RAG")
        
        # Integración especial para Authorization y Pmx
        special_rag_success = handle_special_rag_integration(
            project_name, prefixed_name, cleaned_text, txt_file
        )
        if special_rag_success:
            logging.info(f"✅ Transcripción copiada a ubicación especial RAG para {project_name}")

        # Guardar resumen HTML localmente
        html_file_path = output_folder / f"{prefixed_name}.html"
        with open(html_file_path, "w", encoding="utf-8") as f:
            f.write(html_summary)
        logging.info(f"✅ Resumen HTML guardado localmente: {html_file_path}")
        
        # Handle special py_ folder logic
        handle_py_folder_special_save(project_name, prefixed_name, cleaned_text, html_summary)

        # Enviar email de forma no-bloqueante
        try:
            logging.info("📳 Enviando correo...")
            email_success = send_email(
                subject=f"Resumen generado: {base_name}",
                body=html_summary,
                html=True  # 👈 Importante para usar formato visual
            )
            if email_success:
                logging.info("✅ Email enviado correctamente")
            else:
                logging.warning("⚠️ Email no enviado - continuando procesamiento")
        except Exception as email_error:
            logging.error(f"❌ Error enviando email (no bloquea procesamiento): {email_error}")
            # No detener el procesamiento por errores de email

        try:
            logging.info("📝 Enviando a Notion...")
            send_summary_to_notion(
                notion_token=os.getenv("NOTION_API_KEY"),
                database_id=os.getenv("NOTION_DATABASE_ID"),
                project=project_name,
                file_name=base_name,
                summary=summary
            )
        except Exception as notion_e:
            logging.error(f"❌ Error al enviar a Notion: {notion_e}")

        # Cleanup WAV file if it was created for transcription
        if wav_needs_cleanup and wav_file.exists() and wav_file != video_path:
            try:
                wav_file.unlink()
                logging.info(f"🧹 Archivo WAV temporal eliminado: {wav_file.name}")
            except Exception as cleanup_e:
                logging.warning(f"⚠️ No se pudo eliminar WAV temporal: {cleanup_e}")

        logging.info(f"✅ Finalizado: {base_name}\n")
        update_activity()  # Marcar actividad al completar procesamiento
        return True

    except Exception as e:
        logging.error(f"❌ Error procesando {video_path}: {e}")
        return False

def create_enriched_summary(original_summary: str, analysis_result: dict, content_type: str) -> str:
    """Crea un resumen enriquecido basado en el análisis específico por tipo de contenido"""
    
    if not analysis_result:
        return original_summary
    
    enriched_parts = [f"📊 **ANÁLISIS {content_type.upper()}**\n"]
    
    if content_type == 'interview':
        success_prob = analysis_result.get('success_probability', {})
        enriched_parts.extend([
            f"📊 **RESUMEN**: {analysis_result.get('interview_summary', 'No disponible')}",
            "",
            f"🎯 **Score General**: {analysis_result.get('overall_score', 'N/A')}/10",
            f"🔥 **Nivel de Confianza**: {analysis_result.get('confidence_level', 'N/A')}",
            f"📊 **Probabilidad de Éxito**: {success_prob.get('percentage', 'N/A')}% ({success_prob.get('level', 'N/A')})",
            f"💭 **Predicción**: {success_prob.get('recommendation', 'No disponible')}",
            f"❓ **Preguntas Identificadas**: {analysis_result.get('questions_identified', 0)}",
            "",
            "✅ **FORTALEZAS:**"
        ])
        
        for strength in analysis_result.get('strengths', []):
            enriched_parts.append(f"• {strength}")
        
        enriched_parts.extend([
            "",
            "📈 **ÁREAS DE MEJORA:**"
        ])
        
        for weakness in analysis_result.get('areas_to_improve', []):
            enriched_parts.append(f"• {weakness}")
            
        enriched_parts.extend([
            "",
            "💡 **RECOMENDACIONES:**"
        ])
        
        for rec in analysis_result.get('recommendations', []):
            enriched_parts.append(f"• {rec}")
    
    elif content_type == 'tutorial':
        enriched_parts.extend([
            f"📚 **Pasos Totales**: {analysis_result.get('total_steps', 0)}",
            f"⏱️ **Tiempo Estimado**: {analysis_result.get('estimated_completion_time', 'N/A')}",
            f"🎯 **Dificultad**: {analysis_result.get('difficulty_level', 'N/A')}",
            "",
            "📋 **CHECKLIST DE APLICACIÓN:**"
        ])
        
        for item in analysis_result.get('application_checklist', [])[:10]:
            enriched_parts.append(f"{item}")
            
        enriched_parts.extend([
            "",
            "🔑 **CONCEPTOS CLAVE:**"
        ])
        
        for concept in analysis_result.get('key_concepts', []):
            enriched_parts.append(f"• {concept}")
    
    elif content_type == 'meeting':
        enriched_parts.extend([
            f"📊 **RESUMEN EJECUTIVO**: {analysis_result.get('meeting_summary', 'No disponible')}",
            "",
            f"✅ **Decisiones**: {len(analysis_result.get('decisions_made', []))}",
            f"📋 **Tareas**: {len(analysis_result.get('action_items', []))}",
            f"⏰ **Deadlines**: {len(analysis_result.get('deadlines', []))}",
            f"👥 **Participantes**: {len(analysis_result.get('participants_mentioned', []))}",
            "",
            "🎯 **TAREAS IDENTIFICADAS:**"
        ])
        
        for item in analysis_result.get('action_items', []):
            responsible = item.get('responsible', 'Sin asignar')
            task = item.get('task', '')
            priority = item.get('priority', 'Media')
            enriched_parts.append(f"• **{responsible}**: {task} (Prioridad: {priority})")
            
        enriched_parts.extend([
            "",
            "🔑 **DECISIONES CLAVE:**"
        ])
        
        for decision in analysis_result.get('decisions_made', [])[:5]:
            enriched_parts.append(f"• {decision}")
            
        enriched_parts.extend([
            "",
            "📅 **PRÓXIMA REUNIÓN:**",
            f"{analysis_result.get('next_meeting', 'No especificado')}"
        ])
    
    enriched_parts.extend([
        "",
        "=" * 50,
        "",
        "📝 **RESUMEN ORIGINAL:**",
        "",
        original_summary
    ])
    
    return "\n".join(enriched_parts)

def handle_py_folder_special_save(project_name: str, prefixed_name: str, cleaned_text: str, html_summary: str) -> bool:
    """Maneja el guardado especial para carpetas con prefijo py_"""
    try:
        if project_name.startswith("py_"):
            # Remove py_ prefix for folder name
            folder_name = project_name[3:]  # Remove "py_" prefix
            
            target_dir = Path(f"C:/Dev/Triger/SyncFileNotion/sync/{folder_name}/transcripcion")
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Save transcription
            txt_target = target_dir / f"{prefixed_name}.txt"
            with open(txt_target, "w", encoding="utf-8") as f:
                f.write(cleaned_text)
            
            # Save HTML
            html_target = target_dir / f"{prefixed_name}.html"
            with open(html_target, "w", encoding="utf-8") as f:
                f.write(html_summary)
            
            logging.info(f"📁 Carpeta py_ detectada: {project_name} → Guardado en {target_dir}")
            return True
            
        return False
        
    except Exception as e:
        logging.error(f"❌ Error en guardado especial py_: {e}")
        return False

def should_use_realtime_transcription(file_path: str) -> bool:
    """Determinar si un archivo debe usar transcripción en tiempo real"""
    try:
        # Si tiempo real no está disponible, siempre falso
        if not REALTIME_AVAILABLE or not ENABLE_REALTIME_VIDEO:
            return False
        
        file_path = Path(file_path)
        
        # Criterios para tiempo real:
        # 1. Archivos muy grandes (>100MB)
        # 2. Videos de más de 30 minutos estimados
        # 3. Archivos en carpetas específicas marcadas para tiempo real
        # 4. Archivos que están siendo grabados activamente
        
        # Verificar tamaño
        if file_path.exists():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            if size_mb > 100:
                logging.info(f"Archivo grande detectado ({size_mb:.1f}MB) - usando tiempo real")
                return True
        
        # Verificar carpetas especiales
        realtime_folders = ["llamadas", "meetings", "calls", "live", "streaming", "realtime"]
        for folder in realtime_folders:
            if folder.lower() in str(file_path).lower():
                logging.info(f"Carpeta tiempo real detectada: {folder}")
                return True
        
        # Verificar si el archivo está siendo escrito activamente
        if is_file_being_written(file_path):
            logging.info("Archivo siendo escrito activamente - usando tiempo real")
            return True
        
        return False
        
    except Exception as e:
        logging.error(f"Error determinando si usar tiempo real: {e}")
        return False


def is_file_being_written(file_path: Path) -> bool:
    """Verificar si un archivo está siendo escrito actualmente"""
    try:
        if not file_path.exists():
            return False
        
        # Intentar abrir en modo exclusivo
        try:
            with open(file_path, 'r+b'):
                pass
            return False  # Se pudo abrir, no está siendo escrito
        except (IOError, OSError):
            return True  # No se pudo abrir, probablemente siendo escrito
            
    except Exception:
        return False


def handle_realtime_transcription(file_path: str):
    """Manejar transcripción en tiempo real de un archivo"""
    try:
        file_path = Path(file_path)
        session_id = f"rt_{file_path.stem}_{int(time.time())}"
        
        with realtime_lock:
            if session_id in active_realtime_sessions:
                logging.warning(f"Sesión de tiempo real ya existe: {session_id}")
                return
            
            active_realtime_sessions[session_id] = {
                "file_path": str(file_path),
                "start_time": datetime.now(),
                "status": "starting"
            }
        
        # Callback para recibir transcripciones parciales
        def realtime_callback(session_id, result):
            try:
                chunk_num = result["chunk_number"]
                text = result["text"]
                
                if text.strip():
                    logging.info(f"⚡ RT[{session_id}] Chunk {chunk_num}: {text[:100]}...")
                    
                    # Guardar chunk parcial
                    save_realtime_chunk(session_id, result)
                    
                    # Verificar si hay suficiente contenido para procesar
                    check_realtime_processing(session_id)
                    
            except Exception as e:
                logging.error(f"Error en realtime callback: {e}")
        
        # Iniciar transcripción en tiempo real
        if file_path.suffix.lower() in ['.mp4', '.mkv', '.mov', '.avi', '.webm']:
            logging.info(f"🎬 Iniciando transcripción tiempo real VIDEO: {file_path.name}")
            rt_session_id = start_video_realtime_transcription(
                video_path=str(file_path),
                session_id=session_id,
                callback=realtime_callback
            )
        else:
            # Es un archivo de audio
            logging.info(f"🎵 Iniciando transcripción tiempo real AUDIO: {file_path.name}")
            # Para archivos de audio, usar la función de video también funciona
            rt_session_id = start_video_realtime_transcription(
                video_path=str(file_path),
                session_id=session_id,
                callback=realtime_callback
            )
        
        with realtime_lock:
            active_realtime_sessions[session_id]["status"] = "running"
            active_realtime_sessions[session_id]["realtime_session_id"] = rt_session_id
        
        logging.info(f"✅ Transcripción tiempo real iniciada: {session_id}")
        
    except Exception as e:
        logging.error(f"❌ Error iniciando transcripción tiempo real: {e}")
        # Fallback a procesamiento normal
        logging.info("🔄 Fallback a procesamiento normal")
        processing_queue.put(file_path)


def save_realtime_chunk(session_id: str, result: Dict):
    """Guardar chunk de transcripción en tiempo real"""
    try:
        session_info = active_realtime_sessions.get(session_id)
        if not session_info:
            return
        
        file_path = Path(session_info["file_path"])
        project_name, company_name = extract_project_and_company(file_path)
        
        # Crear carpeta de chunks temporales
        output_folder = Path(OUTPUT_BASE) / project_name / "realtime_chunks"
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Guardar chunk
        chunk_file = output_folder / f"{file_path.stem}_chunk_{result['chunk_number']}.txt"
        with open(chunk_file, "w", encoding="utf-8") as f:
            f.write(f"CHUNK {result['chunk_number']} - {result['timestamp']}\n")
            f.write(f"CONFIDENCE: {result.get('confidence', 'N/A')}\n")
            f.write(f"PROCESSING_TIME: {result.get('processing_time', 'N/A')}\n")
            f.write("-" * 50 + "\n")
            f.write(result["text"])
        
        logging.debug(f"💾 Chunk guardado: {chunk_file}")
        
    except Exception as e:
        logging.error(f"Error guardando chunk tiempo real: {e}")


def check_realtime_processing(session_id: str):
    """Verificar si hay suficiente contenido para generar resumen parcial"""
    try:
        results = get_realtime_results(session_id)
        
        # Cada 10 chunks, generar un resumen parcial
        if len(results) % 10 == 0 and len(results) > 0:
            logging.info(f"📊 Generando resumen parcial para {session_id} - {len(results)} chunks")
            generate_partial_summary(session_id)
            
    except Exception as e:
        logging.error(f"Error verificando procesamiento tiempo real: {e}")


def generate_partial_summary(session_id: str):
    """Generar resumen parcial de transcripción en tiempo real"""
    try:
        session_info = active_realtime_sessions.get(session_id)
        if not session_info:
            return
        
        # Obtener texto completo hasta ahora
        full_text = get_realtime_full_text(session_id)
        if len(full_text) < 500:  # Muy poco texto
            return
        
        file_path = Path(session_info["file_path"])
        project_name, company_name = extract_project_and_company(file_path)
        
        # Limpiar texto
        cleaned_text = clean_transcription(full_text)
        
        # Generar resumen parcial
        partial_summary = generate_summary(
            cleaned_text, 
            project_name, 
            company_name, 
            f"{file_path.name} (PARCIAL)"
        )
        
        # Guardar resumen parcial
        output_folder = Path(OUTPUT_BASE) / project_name
        output_folder.mkdir(parents=True, exist_ok=True)
        
        date_prefix = datetime.now().strftime("%y_%m_%d")
        partial_file = output_folder / f"{date_prefix}_{file_path.stem}_PARCIAL.txt"
        
        with open(partial_file, "w", encoding="utf-8") as f:
            f.write(f"RESUMEN PARCIAL - {datetime.now()}\n")
            f.write(f"CHUNKS PROCESADOS: {len(get_realtime_results(session_id))}\n")
            f.write("=" * 50 + "\n\n")
            f.write(partial_summary)
        
        logging.info(f"📄 Resumen parcial guardado: {partial_file}")
        
    except Exception as e:
        logging.error(f"Error generando resumen parcial: {e}")


def start_call_transcription_service():
    """Iniciar servicio de transcripción de llamadas en tiempo real"""
    if not ENABLE_REALTIME_CALLS:
        logging.info("Transcripción de llamadas en tiempo real deshabilitada")
        return
    
    if not REALTIME_AVAILABLE:
        logging.warning("Módulo de tiempo real no disponible - servicio de llamadas deshabilitado")
        return
    
    try:
        logging.info("Iniciando servicio de transcripción de llamadas...")
        
        def call_callback(session_id, result):
            try:
                text = result["text"]
                if text.strip():
                    logging.info(f"LLAMADA: {text[:100]}...")
                    
                    # Guardar transcripción de llamada
                    save_call_transcription(session_id, result)
                    
            except Exception as e:
                logging.error(f"Error en call callback: {e}")
        
        # Iniciar transcripción de llamada por defecto
        call_session_id = start_call_realtime_transcription(
            device_id=None,  # Usar dispositivo por defecto
            session_id="default_call",
            callback=call_callback
        )
        
        logging.info(f"Servicio de llamadas iniciado: {call_session_id}")
        
    except Exception as e:
        logging.error(f"Error iniciando servicio de llamadas: {e}")


def save_call_transcription(session_id: str, result: Dict):
    """Guardar transcripción de llamada"""
    try:
        # Crear carpeta para llamadas
        calls_folder = Path(OUTPUT_BASE) / "Llamadas"
        calls_folder.mkdir(parents=True, exist_ok=True)
        
        # Archivo por día
        today = datetime.now().strftime("%y_%m_%d")
        call_file = calls_folder / f"{today}_llamadas.txt"
        
        # Agregar chunk de llamada
        timestamp = datetime.now().strftime("%H:%M:%S")
        with open(call_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp}] CHUNK {result['chunk_number']}\n")
            f.write(result["text"])
            f.write("\n" + "-" * 30)
        
        logging.debug(f"📞 Llamada guardada en: {call_file}")
        
    except Exception as e:
        logging.error(f"Error guardando llamada: {e}")


def handle_special_rag_integration(project_name: str, prefixed_name: str, cleaned_text: str, txt_file: Path) -> bool:
    """Maneja la integración especial RAG para Authorization y Pmx"""
    try:
        if project_name == "Authorization":
            target_dir = Path("C:/Dev/Triger/Automation/Rag/_transcripciones/Hexaware/Authorization/appContext")
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / f"{prefixed_name}.txt"
            
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(cleaned_text)
            
            logging.info(f"📄 Transcripción Authorization copiada a: {target_file}")
            return True
            
        elif project_name == "Pmx":
            target_dir = Path("C:/Dev/Triger/Automation/Rag/_transcripciones/Pmx")
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / f"{prefixed_name}.txt"
            
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(cleaned_text)
            
            logging.info(f"📄 Transcripción Pmx copiada a: {target_file}")
            return True
            
        return False
        
    except Exception as e:
        logging.error(f"❌ Error en integración RAG especial para {project_name}: {e}")
        return False

def start_watcher():
    logging.info("🟢 Watcher corriendo...\n")
    update_activity()  # Actividad inicial
    
    # Información de configuración
    logging.info(f"⚙️ TIEMPO REAL VIDEO: {'✅' if ENABLE_REALTIME_VIDEO else '❌'}")
    logging.info(f"⚙️ TIEMPO REAL LLAMADAS: {'✅' if ENABLE_REALTIME_CALLS else '❌'}")
    logging.info(f"⚙️ CHUNK SIZE: {REALTIME_CHUNK_SIZE}s")
    logging.info(f"⚙️ MAX CONCURRENT: {MAX_CONCURRENT_JOBS}")
    
    # Debugging email environment variables
    logging.info(f"DEBUG: EMAIL_SENDER: {os.getenv('EMAIL_SENDER')}")
    logging.info(f"DEBUG: EMAIL_PASSWORD: {'*' * len(os.getenv('EMAIL_PASSWORD')) if os.getenv('EMAIL_PASSWORD') else 'None'}") # Mask password
    logging.info(f"DEBUG: EMAIL_RECEIVER: {os.getenv('EMAIL_RECEIVER')}")
    
    # Iniciar watchdog interno
    start_watchdog_thread()
    
    # Iniciar worker thread para procesar cola secuencialmente
    worker_thread = threading.Thread(target=process_queue_worker, daemon=True)
    worker_thread.start()
    logging.info("🔄 Worker de procesamiento secuencial iniciado")
    
    # Iniciar servicio de transcripción de llamadas si está habilitado
    if ENABLE_REALTIME_CALLS:
        call_service_thread = threading.Thread(target=start_call_transcription_service, daemon=True)
        call_service_thread.start()
        logging.info("📞 Servicio de llamadas en tiempo real iniciado")
    
    # Process existing files in both directories
    process_existing_files(VIDEO_BASE)
    process_existing_files(AUDIO_BASE)

    observer = Observer()
    # Monitor both Videos and audio directories
    observer.schedule(VideoHandler(), path=VIDEO_BASE, recursive=True)
    observer.schedule(VideoHandler(), path=AUDIO_BASE, recursive=True)
    observer.start()
    logging.info(f"👀 Observando carpetas: {VIDEO_BASE} y {AUDIO_BASE}")
    logging.info(f"🔴 Transcripción en tiempo real: {'ACTIVA' if ENABLE_REALTIME_VIDEO else 'INACTIVA'}")
    logging.info(f"📞 Transcripción de llamadas: {'ACTIVA' if ENABLE_REALTIME_CALLS else 'INACTIVA'}\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("🛑 Deteniendo watcher...")
        
        # Detener sesiones de tiempo real activas
        with realtime_lock:
            for session_id in list(active_realtime_sessions.keys()):
                try:
                    stop_realtime_transcription(session_id)
                    logging.info(f"🔴 Sesión tiempo real detenida: {session_id}")
                except Exception as e:
                    logging.error(f"Error deteniendo sesión {session_id}: {e}")
        
        observer.stop()
    observer.join()

logging.info("🧪 Estoy vivo")

if __name__ == "__main__":
    logging.info("🟢 Watcher iniciado desde main.")
    start_watcher()