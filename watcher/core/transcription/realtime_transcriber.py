"""
Transcripción en tiempo real para videos y videollamadas
Optimizado para bajo consumo de recursos y alta eficiencia
"""

import asyncio
import threading
import time
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
import json
import queue
import numpy as np

# Imports optimizados - con manejo de dependencias opcionales
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logging.warning("OpenCV no disponible - funciones de video limitadas")

try:
    import pyaudio
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    logging.warning("PyAudio no disponible - transcripción de audio directo deshabilitada")

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    logging.warning("SoundDevice no disponible - usando alternativas")

from .transcription_provider import transcribe
from ..utils import clean_transcription

class RealtimeTranscriber:
    """Transcriptor en tiempo real optimizado para recursos limitados"""
    
    def __init__(self, 
                 chunk_duration: int = 30,  # segundos por chunk
                 overlap_duration: int = 5,  # solapamiento para continuidad
                 max_concurrent_jobs: int = 3,  # máximo trabajos simultáneos
                 temp_cleanup_interval: int = 300,  # limpiar archivos temporales cada 5 min
                 audio_quality: str = "medium"):  # low, medium, high
        
        self.chunk_duration = chunk_duration
        self.overlap_duration = overlap_duration
        self.max_concurrent_jobs = max_concurrent_jobs
        self.temp_cleanup_interval = temp_cleanup_interval
        self.audio_quality = audio_quality
        
        # Estados de transcripción
        self.active_sessions: Dict[str, Dict] = {}
        self.transcription_queue = queue.Queue(maxsize=50)  # Limitar cola
        self.results_cache: Dict[str, List[Dict]] = {}
        
        # Control de recursos
        self.active_workers = 0
        self.worker_lock = threading.Lock()
        
        # Configuración de audio optimizada
        self.audio_config = self._get_optimized_audio_config()
        
        # Worker threads
        self._start_background_workers()
        
        logging.info(f"RealtimeTranscriber inicializado - chunks:{chunk_duration}s, overlap:{overlap_duration}s")
    
    def _get_optimized_audio_config(self) -> Dict[str, Any]:
        """Configuración de audio optimizada por calidad"""
        configs = {
            "low": {
                "sample_rate": 16000,
                "channels": 1,
                "bit_depth": 16,
                "format": "wav"
            },
            "medium": {
                "sample_rate": 22050,
                "channels": 1,
                "bit_depth": 16,
                "format": "wav"
            },
            "high": {
                "sample_rate": 44100,
                "channels": 2,
                "bit_depth": 24,
                "format": "wav"
            }
        }
        return configs.get(self.audio_quality, configs["medium"])
    
    def _start_background_workers(self):
        """Iniciar workers en background para procesamiento"""
        # Worker para procesar transcripciones
        self.transcription_worker = threading.Thread(
            target=self._transcription_worker, 
            daemon=True
        )
        self.transcription_worker.start()
        
        # Worker para limpieza de archivos temporales
        self.cleanup_worker = threading.Thread(
            target=self._cleanup_worker,
            daemon=True
        )
        self.cleanup_worker.start()
        
        logging.info("Workers de transcripción en tiempo real iniciados")
    
    def start_video_transcription(self, 
                                  video_source: str,
                                  session_id: str,
                                  callback: Optional[Callable] = None) -> bool:
        """
        Iniciar transcripción en tiempo real de video
        
        Args:
            video_source: Ruta al archivo de video o URL de stream
            session_id: ID único para la sesión
            callback: Función callback para recibir transcripciones parciales
        """
        try:
            if session_id in self.active_sessions:
                logging.warning(f"Sesión {session_id} ya está activa")
                return False
            
            # Verificar que el video existe o es accesible
            if not self._verify_video_source(video_source):
                logging.error(f"Video source no accesible: {video_source}")
                return False
            
            # Crear sesión
            session = {
                "source": video_source,
                "start_time": datetime.now(),
                "callback": callback,
                "status": "starting",
                "chunks_processed": 0,
                "temp_files": [],
                "type": "video"
            }
            
            self.active_sessions[session_id] = session
            self.results_cache[session_id] = []
            
            # Iniciar procesamiento en thread separado
            thread = threading.Thread(
                target=self._process_video_realtime,
                args=(session_id, video_source, callback),
                daemon=True
            )
            thread.start()
            
            logging.info(f"Transcripción de video iniciada - sesión: {session_id}")
            return True
            
        except Exception as e:
            logging.error(f"Error iniciando transcripción de video: {e}")
            return False
    
    def start_call_transcription(self,
                                audio_device_id: Optional[int] = None,
                                session_id: str = "default_call",
                                callback: Optional[Callable] = None) -> bool:
        """
        Iniciar transcripción en tiempo real de videollamada/llamada
        
        Args:
            audio_device_id: ID del dispositivo de audio (None = por defecto)
            session_id: ID único para la sesión
            callback: Función callback para recibir transcripciones
        """
        try:
            if not AUDIO_AVAILABLE and not SOUNDDEVICE_AVAILABLE:
                logging.error("No hay bibliotecas de audio disponibles")
                return False
            
            if session_id in self.active_sessions:
                logging.warning(f"Sesión de llamada {session_id} ya está activa")
                return False
            
            # Crear sesión de llamada
            session = {
                "device_id": audio_device_id,
                "start_time": datetime.now(),
                "callback": callback,
                "status": "starting",
                "chunks_processed": 0,
                "temp_files": [],
                "type": "call"
            }
            
            self.active_sessions[session_id] = session
            self.results_cache[session_id] = []
            
            # Iniciar captura de audio en thread separado
            thread = threading.Thread(
                target=self._process_call_realtime,
                args=(session_id, audio_device_id, callback),
                daemon=True
            )
            thread.start()
            
            logging.info(f"Transcripción de llamada iniciada - sesión: {session_id}")
            return True
            
        except Exception as e:
            logging.error(f"Error iniciando transcripción de llamada: {e}")
            return False
    
    def stop_transcription(self, session_id: str) -> bool:
        """Detener transcripción de una sesión"""
        try:
            if session_id not in self.active_sessions:
                logging.warning(f"Sesión {session_id} no encontrada")
                return False
            
            session = self.active_sessions[session_id]
            session["status"] = "stopping"
            
            # Limpiar archivos temporales de la sesión
            self._cleanup_session_files(session_id)
            
            # Remover sesión
            del self.active_sessions[session_id]
            
            logging.info(f"Sesión {session_id} detenida")
            return True
            
        except Exception as e:
            logging.error(f"Error deteniendo sesión {session_id}: {e}")
            return False
    
    def get_transcription_results(self, session_id: str) -> List[Dict]:
        """Obtener resultados de transcripción de una sesión"""
        return self.results_cache.get(session_id, [])
    
    def _verify_video_source(self, source: str) -> bool:
        """Verificar que el video source es válido"""
        try:
            if source.startswith(("http://", "https://", "rtmp://", "rtsp://")):
                # Es una URL, asumir válida (se verificará en el procesamiento)
                return True
            else:
                # Es un archivo local
                return Path(source).exists()
        except Exception:
            return False
    
    def _process_video_realtime(self, session_id: str, video_source: str, callback: Optional[Callable]):
        """Procesar video en tiempo real con chunks - version simplificada usando FFmpeg"""
        try:
            session = self.active_sessions[session_id]
            session["status"] = "running"
            
            # Usar FFmpeg directamente para procesar video
            chunk_number = 0
            
            while session["status"] == "running":
                # Extraer chunk de audio usando FFmpeg directamente
                temp_audio = self._extract_audio_chunk_ffmpeg(
                    video_source, chunk_number, self.chunk_duration, self.overlap_duration
                )
                
                if temp_audio is None:
                    break  # Fin del video o error
                
                # Agregar a la cola de transcripción
                task = {
                    "session_id": session_id,
                    "chunk_number": chunk_number,
                    "audio_file": temp_audio,
                    "timestamp": datetime.now()
                }
                
                try:
                    self.transcription_queue.put(task, timeout=1)
                    session["temp_files"].append(temp_audio)
                    chunk_number += 1
                    session["chunks_processed"] = chunk_number
                    
                except queue.Full:
                    logging.warning(f"Cola de transcripción llena - saltando chunk {chunk_number}")
                    if temp_audio and Path(temp_audio).exists():
                        Path(temp_audio).unlink()
                
                # Dormir brevemente para no saturar
                time.sleep(0.1)
            
            session["status"] = "completed"
            logging.info(f"Procesamiento de video completado - sesión: {session_id}")
            
        except Exception as e:
            logging.error(f"Error procesando video tiempo real: {e}")
            if session_id in self.active_sessions:
                self.active_sessions[session_id]["status"] = "error"
    
    def _process_call_realtime(self, session_id: str, device_id: Optional[int], callback: Optional[Callable]):
        """Procesar llamada en tiempo real"""
        try:
            session = self.active_sessions[session_id]
            session["status"] = "running"
            
            # Configuración de audio
            sample_rate = self.audio_config["sample_rate"]
            channels = self.audio_config["channels"]
            chunk_samples = int(sample_rate * self.chunk_duration)
            
            # Buffer para audio
            audio_buffer = []
            chunk_number = 0
            
            def audio_callback(indata, frames, time, status):
                nonlocal audio_buffer
                if status:
                    logging.warning(f"Audio callback status: {status}")
                audio_buffer.extend(indata.flatten())
            
            # Iniciar stream de audio
            if SOUNDDEVICE_AVAILABLE:
                stream = sd.InputStream(
                    device=device_id,
                    channels=channels,
                    samplerate=sample_rate,
                    callback=audio_callback,
                    dtype=np.float32
                )
                stream.start()
            elif AUDIO_AVAILABLE:
                # Implementación con PyAudio si es necesaria
                logging.warning("Usando PyAudio como fallback")
                return
            else:
                logging.error("No hay biblioteca de audio disponible")
                return
            
            try:
                while session["status"] == "running":
                    # Esperar a tener suficientes samples
                    if len(audio_buffer) >= chunk_samples:
                        # Extraer chunk
                        chunk_data = audio_buffer[:chunk_samples]
                        audio_buffer = audio_buffer[chunk_samples - int(sample_rate * self.overlap_duration):]
                        
                        # Guardar chunk temporal
                        temp_audio = self._save_audio_chunk(chunk_data, sample_rate, chunk_number)
                        
                        if temp_audio:
                            # Agregar a la cola de transcripción
                            task = {
                                "session_id": session_id,
                                "chunk_number": chunk_number,
                                "audio_file": temp_audio,
                                "timestamp": datetime.now()
                            }
                            
                            try:
                                self.transcription_queue.put(task, timeout=1)
                                session["temp_files"].append(temp_audio)
                                chunk_number += 1
                                session["chunks_processed"] = chunk_number
                                
                            except queue.Full:
                                logging.warning(f"Cola de transcripción llena - saltando chunk {chunk_number}")
                                if Path(temp_audio).exists():
                                    Path(temp_audio).unlink()
                    
                    # Dormir brevemente
                    time.sleep(0.1)
                    
            finally:
                stream.stop()
                stream.close()
            
            session["status"] = "completed"
            logging.info(f"Procesamiento de llamada completado - sesión: {session_id}")
            
        except Exception as e:
            logging.error(f"Error procesando llamada tiempo real: {e}")
            if session_id in self.active_sessions:
                self.active_sessions[session_id]["status"] = "error"
    
    def _extract_audio_chunk_ffmpeg(self, video_source: str, chunk_number: int, chunk_duration: int, overlap_duration: int) -> Optional[str]:
        """Extraer chunk de audio de video usando FFmpeg"""
        try:
            # Calcular posición en segundos
            start_second = max(0, chunk_number * chunk_duration - overlap_duration)
            
            # Crear archivo temporal
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                temp_path = tmp.name
            
            # Usar FFmpeg para extraer audio del chunk
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-ss", str(start_second),
                "-t", str(chunk_duration + overlap_duration),
                "-i", video_source,
                "-acodec", "pcm_s16le",
                "-ar", str(self.audio_config["sample_rate"]),
                "-ac", str(self.audio_config["channels"]),
                "-y", temp_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            
            if result.returncode == 0 and Path(temp_path).exists() and Path(temp_path).stat().st_size > 1000:
                return temp_path
            else:
                logging.warning(f"FFmpeg falló para chunk {chunk_number} o archivo muy pequeño")
                if Path(temp_path).exists():
                    Path(temp_path).unlink()
                return None
                
        except Exception as e:
            logging.error(f"Error extrayendo audio chunk: {e}")
            return None
    
    def _get_video_source_from_cap(self, cap) -> str:
        """Obtener source del video desde VideoCapture (hack temporal)"""
        # Esto es un workaround - normalmente necesitaríamos pasar el source original
        # Por ahora, asumir que es el último video procesado
        return getattr(cap, '_source', 'unknown')
    
    def _save_audio_chunk(self, audio_data: List[float], sample_rate: int, chunk_number: int) -> Optional[str]:
        """Guardar chunk de audio en archivo temporal"""
        try:
            import wave
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                temp_path = tmp.name
            
            # Convertir a numpy array y normalizar
            audio_array = np.array(audio_data, dtype=np.float32)
            
            # Convertir a 16-bit PCM
            audio_16bit = (audio_array * 32767).astype(np.int16)
            
            # Guardar como WAV
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(self.audio_config["channels"])
                wav_file.setsampwidth(2)  # 16-bit = 2 bytes
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_16bit.tobytes())
            
            return temp_path
            
        except Exception as e:
            logging.error(f"Error guardando audio chunk: {e}")
            return None
    
    def _transcription_worker(self):
        """Worker que procesa la cola de transcripciones"""
        while True:
            try:
                # Obtener tarea de la cola
                task = self.transcription_queue.get(timeout=1)
                
                # Controlar concurrencia
                with self.worker_lock:
                    if self.active_workers >= self.max_concurrent_jobs:
                        # Reencolar y esperar
                        self.transcription_queue.put(task)
                        time.sleep(0.1)
                        continue
                    self.active_workers += 1
                
                try:
                    # Procesar transcripción
                    self._process_transcription_task(task)
                finally:
                    with self.worker_lock:
                        self.active_workers -= 1
                
            except queue.Empty:
                time.sleep(0.1)
                continue
            except Exception as e:
                logging.error(f"Error en transcription worker: {e}")
                with self.worker_lock:
                    if self.active_workers > 0:
                        self.active_workers -= 1
    
    def _process_transcription_task(self, task: Dict):
        """Procesar una tarea de transcripción"""
        try:
            session_id = task["session_id"]
            chunk_number = task["chunk_number"]
            audio_file = task["audio_file"]
            timestamp = task["timestamp"]
            
            if session_id not in self.active_sessions:
                # Sesión cancelada, limpiar archivo
                if Path(audio_file).exists():
                    Path(audio_file).unlink()
                return
            
            session = self.active_sessions[session_id]
            callback = session.get("callback")
            
            # Transcribir
            start_time = time.time()
            result = transcribe(audio_file, language="es")
            transcription_time = time.time() - start_time
            
            # Limpiar texto
            text = result.get("text", "").strip()
            if text:
                cleaned_text = clean_transcription(text)
                
                # Crear resultado
                transcription_result = {
                    "chunk_number": chunk_number,
                    "text": cleaned_text,
                    "timestamp": timestamp,
                    "processing_time": transcription_time,
                    "confidence": result.get("confidence", 0.0)
                }
                
                # Guardar en caché
                if session_id not in self.results_cache:
                    self.results_cache[session_id] = []
                self.results_cache[session_id].append(transcription_result)
                
                # Llamar callback si existe
                if callback:
                    try:
                        callback(session_id, transcription_result)
                    except Exception as e:
                        logging.error(f"Error en callback: {e}")
                
                logging.info(f"Chunk {chunk_number} transcrito en {transcription_time:.2f}s - {len(cleaned_text)} chars")
            
            # Limpiar archivo temporal
            if Path(audio_file).exists():
                Path(audio_file).unlink()
            
        except Exception as e:
            logging.error(f"Error procesando tarea de transcripción: {e}")
            # Limpiar archivo en caso de error
            if "audio_file" in task and Path(task["audio_file"]).exists():
                Path(task["audio_file"]).unlink()
    
    def _cleanup_worker(self):
        """Worker para limpiar archivos temporales periódicamente"""
        while True:
            try:
                time.sleep(self.temp_cleanup_interval)
                
                # Limpiar archivos temporales antiguos
                current_time = datetime.now()
                for session_id, session in list(self.active_sessions.items()):
                    if session["status"] in ["completed", "error"]:
                        # Limpiar archivos de sesiones terminadas
                        self._cleanup_session_files(session_id)
                        
                        # Remover sesión si es muy antigua (1 hora)
                        if current_time - session["start_time"] > timedelta(hours=1):
                            if session_id in self.results_cache:
                                del self.results_cache[session_id]
                            if session_id in self.active_sessions:
                                del self.active_sessions[session_id]
                
                logging.debug("Limpieza de archivos temporales completada")
                
            except Exception as e:
                logging.error(f"Error en cleanup worker: {e}")
    
    def _cleanup_session_files(self, session_id: str):
        """Limpiar archivos temporales de una sesión"""
        try:
            if session_id in self.active_sessions:
                session = self.active_sessions[session_id]
                temp_files = session.get("temp_files", [])
                
                for temp_file in temp_files:
                    try:
                        if Path(temp_file).exists():
                            Path(temp_file).unlink()
                    except Exception as e:
                        logging.warning(f"No se pudo eliminar archivo temporal {temp_file}: {e}")
                
                session["temp_files"] = []
                
        except Exception as e:
            logging.error(f"Error limpiando archivos de sesión {session_id}: {e}")
    
    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """Obtener estado de una sesión"""
        if session_id not in self.active_sessions:
            return {"error": "Sesión no encontrada"}
        
        session = self.active_sessions[session_id]
        results = self.results_cache.get(session_id, [])
        
        return {
            "session_id": session_id,
            "status": session["status"],
            "type": session["type"],
            "start_time": session["start_time"],
            "chunks_processed": session["chunks_processed"],
            "chunks_transcribed": len(results),
            "total_text_length": sum(len(r["text"]) for r in results),
            "active_workers": self.active_workers
        }
    
    def get_full_transcription(self, session_id: str) -> str:
        """Obtener transcripción completa de una sesión"""
        results = self.results_cache.get(session_id, [])
        
        # Ordenar por chunk number y concatenar
        sorted_results = sorted(results, key=lambda x: x["chunk_number"])
        return " ".join(r["text"] for r in sorted_results if r["text"].strip())


# Instancia global optimizada
realtime_transcriber = RealtimeTranscriber(
    chunk_duration=int(os.getenv("REALTIME_CHUNK_SIZE", "30")),
    max_concurrent_jobs=int(os.getenv("MAX_CONCURRENT_JOBS", "3")),
    audio_quality="medium"  # Optimizado para balance recursos/calidad
)


def start_video_realtime_transcription(video_path: str, session_id: str = None, callback: Callable = None) -> str:
    """
    Iniciar transcripción en tiempo real de video
    
    Returns:
        session_id: ID de la sesión iniciada
    """
    if session_id is None:
        session_id = f"video_{int(time.time())}"
    
    success = realtime_transcriber.start_video_transcription(
        video_source=video_path,
        session_id=session_id,
        callback=callback
    )
    
    if success:
        return session_id
    else:
        raise RuntimeError(f"No se pudo iniciar transcripción de video: {video_path}")


def start_call_realtime_transcription(device_id: int = None, session_id: str = None, callback: Callable = None) -> str:
    """
    Iniciar transcripción en tiempo real de videollamada
    
    Returns:
        session_id: ID de la sesión iniciada
    """
    if session_id is None:
        session_id = f"call_{int(time.time())}"
    
    success = realtime_transcriber.start_call_transcription(
        audio_device_id=device_id,
        session_id=session_id,
        callback=callback
    )
    
    if success:
        return session_id
    else:
        raise RuntimeError("No se pudo iniciar transcripción de llamada")


def stop_realtime_transcription(session_id: str) -> bool:
    """Detener sesión de transcripción en tiempo real"""
    return realtime_transcriber.stop_transcription(session_id)


def get_realtime_results(session_id: str) -> List[Dict]:
    """Obtener resultados de transcripción en tiempo real"""
    return realtime_transcriber.get_transcription_results(session_id)


def get_realtime_full_text(session_id: str) -> str:
    """Obtener texto completo de transcripción en tiempo real"""
    return realtime_transcriber.get_full_transcription(session_id)