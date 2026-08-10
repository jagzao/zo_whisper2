"""
Review Queue - Sistema de cola para revision manual de segmentos
Gestiona segmentos de baja confianza que necesitan revision humana
"""

import logging
import json
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class ReviewSegment:
    """Segmento que necesita revision manual"""
    id: str
    transcription_id: str
    audio_path: str
    start_time: float
    end_time: float
    text: str
    confidence: float
    flagged_reason: List[str]
    metadata: Dict
    created_at: str
    reviewed: bool = False
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    corrected_text: Optional[str] = None
    original_text: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class ReviewQueue:
    """
    Sistema de cola para gestion de revision manual

    Funcionalidad:
    - Agregar segmentos que necesitan revision
    - Obtener siguiente segmento para revisar
    - Marcar segmento como revisado
    - Estadisticas de revision
    - Persistencia en JSON
    """

    def __init__(self, queue_file: str = "./review_queue.json"):
        """
        Args:
            queue_file: Path al archivo JSON de persistencia
        """
        self.queue_file = queue_file
        self.queue: List[ReviewSegment] = []

        # Cargar cola existente
        self._load_queue()

        logger.info(f"[REVIEW] ReviewQueue inicializada")
        logger.info(f"[REVIEW]   Queue file: {queue_file}")
        logger.info(f"[REVIEW]   Pending reviews: {self.count_pending()}")

    def add_segment(
        self,
        transcription_id: str,
        audio_path: str,
        start_time: float,
        end_time: float,
        text: str,
        confidence: float,
        flagged_reason: List[str],
        metadata: Optional[Dict] = None
    ) -> ReviewSegment:
        """
        Agregar segmento a la cola de revision

        Args:
            transcription_id: ID de la transcripcion
            audio_path: Path al audio original
            start_time: Inicio del segmento (segundos)
            end_time: Fin del segmento (segundos)
            text: Texto transcrito
            confidence: Confianza del segmento (0-1)
            flagged_reason: Razones por las que fue marcado
            metadata: Metadata adicional

        Returns:
            ReviewSegment creado
        """
        # Generar ID unico
        segment_id = self._generate_segment_id(
            transcription_id,
            start_time,
            end_time
        )

        # Verificar si ya existe
        existing = self.get_segment_by_id(segment_id)
        if existing:
            logger.warning(f"[REVIEW] Segmento {segment_id} ya existe en cola")
            return existing

        # Crear segmento
        segment = ReviewSegment(
            id=segment_id,
            transcription_id=transcription_id,
            audio_path=audio_path,
            start_time=start_time,
            end_time=end_time,
            text=text,
            confidence=confidence,
            flagged_reason=flagged_reason,
            metadata=metadata or {},
            created_at=datetime.now().isoformat()
        )

        # Agregar a cola
        self.queue.append(segment)

        # Persistir
        self._save_queue()

        logger.info(f"[REVIEW] Segmento agregado a cola: {segment_id}")
        logger.info(f"[REVIEW]   Confianza: {confidence:.2%}")
        logger.info(f"[REVIEW]   Razones: {', '.join(flagged_reason)}")

        return segment

    def get_next_pending(self) -> Optional[ReviewSegment]:
        """
        Obtener siguiente segmento pendiente de revision

        Returns:
            ReviewSegment o None si no hay pendientes
        """
        for segment in self.queue:
            if not segment.reviewed:
                return segment

        return None

    def get_pending_segments(self, limit: int = 50) -> List[ReviewSegment]:
        """
        Obtener lista de segmentos pendientes

        Args:
            limit: Maximo numero de segmentos a retornar

        Returns:
            Lista de ReviewSegment pendientes
        """
        pending = [s for s in self.queue if not s.reviewed]

        # Ordenar por confianza (mas bajo primero)
        pending.sort(key=lambda s: s.confidence)

        return pending[:limit]

    def mark_as_reviewed(
        self,
        segment_id: str,
        corrected_text: str,
        reviewed_by: str
    ) -> bool:
        """
        Marcar segmento como revisado

        Args:
            segment_id: ID del segmento
            corrected_text: Texto corregido
            reviewed_by: Usuario que reviso

        Returns:
            True si se marco exitosamente
        """
        segment = self.get_segment_by_id(segment_id)

        if not segment:
            logger.error(f"[REVIEW] Segmento no encontrado: {segment_id}")
            return False

        if segment.reviewed:
            logger.warning(f"[REVIEW] Segmento ya fue revisado: {segment_id}")
            return False

        # Actualizar segmento
        segment.original_text = segment.text
        segment.text = corrected_text
        segment.corrected_text = corrected_text
        segment.reviewed = True
        segment.reviewed_by = reviewed_by
        segment.reviewed_at = datetime.now().isoformat()

        # Persistir
        self._save_queue()

        logger.info(f"[REVIEW] Segmento marcado como revisado: {segment_id}")
        logger.info(f"[REVIEW]   Original: {segment.original_text}")
        logger.info(f"[REVIEW]   Corregido: {corrected_text}")
        logger.info(f"[REVIEW]   Por: {reviewed_by}")

        return True

    def get_segment_by_id(self, segment_id: str) -> Optional[ReviewSegment]:
        """Obtener segmento por ID"""
        for segment in self.queue:
            if segment.id == segment_id:
                return segment
        return None

    def count_pending(self) -> int:
        """Contar segmentos pendientes"""
        return len([s for s in self.queue if not s.reviewed])

    def count_reviewed(self) -> int:
        """Contar segmentos revisados"""
        return len([s for s in self.queue if s.reviewed])

    def get_stats(self) -> Dict:
        """Obtener estadisticas de la cola"""
        total = len(self.queue)
        pending = self.count_pending()
        reviewed = self.count_reviewed()

        # Confianza promedio de pendientes
        pending_segments = [s for s in self.queue if not s.reviewed]
        avg_confidence = (
            sum(s.confidence for s in pending_segments) / len(pending_segments)
            if pending_segments else 0
        )

        # Razones mas comunes
        all_reasons = []
        for seg in pending_segments:
            all_reasons.extend(seg.flagged_reason)

        reason_counts = {}
        for reason in all_reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        return {
            'total_segments': total,
            'pending': pending,
            'reviewed': reviewed,
            'completion_percentage': (reviewed / total * 100) if total > 0 else 0,
            'avg_confidence_pending': avg_confidence,
            'most_common_reasons': sorted(
                reason_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }

    def clear_reviewed(self):
        """Eliminar segmentos ya revisados de la cola"""
        before = len(self.queue)
        self.queue = [s for s in self.queue if not s.reviewed]
        after = len(self.queue)

        removed = before - after

        self._save_queue()

        logger.info(f"[REVIEW] Limpieza: {removed} segmentos revisados eliminados")

        return removed

    def _generate_segment_id(
        self,
        transcription_id: str,
        start_time: float,
        end_time: float
    ) -> str:
        """Generar ID unico para segmento"""
        unique_str = f"{transcription_id}_{start_time}_{end_time}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:16]

    def _load_queue(self):
        """Cargar cola desde archivo JSON"""
        if not Path(self.queue_file).exists():
            logger.info(f"[REVIEW] Queue file no existe, creando nuevo")
            self.queue = []
            return

        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Reconstruir ReviewSegments
            self.queue = []
            for item in data:
                segment = ReviewSegment(**item)
                self.queue.append(segment)

            logger.info(f"[REVIEW] Cola cargada: {len(self.queue)} segmentos")

        except Exception as e:
            logger.error(f"[REVIEW] Error cargando cola: {e}")
            self.queue = []

    def _save_queue(self):
        """Guardar cola en archivo JSON"""
        try:
            data = [seg.to_dict() for seg in self.queue]

            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"[REVIEW] Cola guardada: {len(self.queue)} segmentos")

        except Exception as e:
            logger.error(f"[REVIEW] Error guardando cola: {e}")


def should_flag_for_review(
    segment: Dict,
    confidence_threshold: float = 0.65,
    check_language_switch: bool = True,
    check_overlap: bool = True
) -> Tuple[bool, List[str]]:
    """
    Determinar si un segmento debe ser marcado para revision

    Args:
        segment: Dict con info del segmento
        confidence_threshold: Umbral de confianza
        check_language_switch: Verificar cambio de idioma
        check_overlap: Verificar overlapping speech

    Returns:
        (should_flag, list_of_reasons)
    """
    reasons = []

    # 1. Baja confianza
    confidence = segment.get('confidence', 1.0)
    if confidence < confidence_threshold:
        reasons.append('low_confidence')

    # 2. No-speech probability alta
    no_speech_prob = segment.get('no_speech_prob', 0.0)
    if no_speech_prob > 0.5:
        reasons.append('high_no_speech_probability')

    # 3. Cambio de idioma
    if check_language_switch:
        language = segment.get('language', 'unknown')
        prev_language = segment.get('prev_language', language)
        if language != prev_language and prev_language != 'unknown':
            reasons.append('language_switch')

    # 4. Overlapping speech
    if check_overlap:
        if segment.get('has_overlap', False):
            reasons.append('overlapping_speech')

    # 5. Palabras desconocidas
    unknown_words = segment.get('unknown_words', [])
    if len(unknown_words) > 2:
        reasons.append(f'unknown_vocabulary_{len(unknown_words)}_words')

    # 6. Repeticiones sospechosas
    text = segment.get('text', '')
    if _detect_repetition(text):
        reasons.append('possible_hallucination')

    # 7. Segmento muy corto o muy largo
    duration = segment.get('end', 0) - segment.get('start', 0)
    if duration < 0.5:
        reasons.append('very_short_segment')
    elif duration > 30:
        reasons.append('very_long_segment')

    return len(reasons) > 0, reasons


def _detect_repetition(text: str, window: int = 5) -> bool:
    """Detectar repeticiones sospechosas (hallucination pattern)"""
    words = text.lower().split()

    if len(words) < window * 2:
        return False

    # Buscar secuencias repetidas
    for i in range(len(words) - window * 2 + 1):
        window_1 = ' '.join(words[i:i+window])
        window_2 = ' '.join(words[i+window:i+window*2])

        if window_1 == window_2:
            return True

    return False
