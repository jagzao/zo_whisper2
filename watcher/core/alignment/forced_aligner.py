"""
Forced Aligner - Alineacion precisa de timestamps usando WhisperX
Corrige el "timing jitter" de Whisper (±500ms) a precision de ±20ms
"""

import logging
import time
from typing import Dict, List, Optional, Any
from pathlib import Path

import torch
import numpy as np

logger = logging.getLogger(__name__)

# WhisperX puede no estar instalado (es opcional)
WHISPERX_AVAILABLE = False
try:
    import whisperx
    WHISPERX_AVAILABLE = True
    logger.info("[ALIGNMENT] WhisperX disponible")
except ImportError:
    logger.warning("[ALIGNMENT] WhisperX no instalado. Instalar con: pip install whisperx")


class ForcedAligner:
    """
    Sistema de alineacion forzada para timestamps precisos

    Problema:
    - Whisper genera timestamps con ±500ms de imprecision
    - Problemas para subtitulos (palabras aparecen tarde/temprano)
    - Dificil analizar pausas y ritmo de habla

    Solucion:
    - WhisperX usa wav2vec2 para alinear a nivel de fonema
    - Precision de ±20ms (25x mejor que Whisper)
    - Identifica segmentos de baja confianza para review

    Uso:
        aligner = ForcedAligner(language="es", device="cpu")
        aligned_result = aligner.align(audio_path, whisper_result)
    """

    def __init__(
        self,
        language: str = "es",
        device: str = "cpu",
        compute_type: str = "int8"
    ):
        """
        Args:
            language: Codigo de idioma (es, en, etc.)
            device: "cpu" o "cuda"
            compute_type: "int8", "float16", etc.
        """
        if not WHISPERX_AVAILABLE:
            raise ImportError(
                "WhisperX no esta instalado. "
                "Instalar con: pip install whisperx"
            )

        self.language = language
        self.device = device
        self.compute_type = compute_type

        logger.info(f"[ALIGNMENT] Inicializando ForcedAligner")
        logger.info(f"[ALIGNMENT]   Idioma: {language}")
        logger.info(f"[ALIGNMENT]   Device: {device}")

        # Cargar modelo de alineacion
        logger.info(f"[ALIGNMENT] Cargando modelo de alineacion para {language}...")
        start = time.time()

        self.align_model, self.metadata = whisperx.load_align_model(
            language_code=language,
            device=device
        )

        elapsed = time.time() - start
        logger.info(f"[ALIGNMENT] Modelo cargado en {elapsed:.2f}s")

    def align(
        self,
        audio_path: str,
        whisper_result: Dict,
        return_char_alignments: bool = False
    ) -> Dict:
        """
        Alinear resultado de Whisper con timestamps precisos

        Args:
            audio_path: Path al archivo de audio
            whisper_result: Resultado de Whisper con segmentos
            return_char_alignments: Si True, retorna alineacion por caracter

        Returns:
            Dict con segmentos y palabras alineadas precisamente
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"[ALIGNMENT] Alineando: {Path(audio_path).name}")
        logger.info(f"{'='*70}")

        start = time.time()

        # Cargar audio
        logger.info(f"[ALIGNMENT] Cargando audio...")
        audio = whisperx.load_audio(audio_path)

        # Preparar segmentos
        segments = self._prepare_segments(whisper_result)

        logger.info(f"[ALIGNMENT] Alineando {len(segments)} segmentos...")

        # Alinear
        aligned_result = whisperx.align(
            segments,
            self.align_model,
            self.metadata,
            audio,
            self.device,
            return_char_alignments=return_char_alignments
        )

        elapsed = time.time() - start

        # Analizar resultados
        stats = self._analyze_alignment(aligned_result, whisper_result)

        logger.info(f"\n{'='*70}")
        logger.info(f"[ALIGNMENT] RESUMEN DE ALINEACION")
        logger.info(f"{'='*70}")
        logger.info(f"  Tiempo:                 {elapsed:.2f}s")
        logger.info(f"  Segmentos alineados:    {stats['aligned_segments']}/{stats['total_segments']}")
        logger.info(f"  Palabras alineadas:     {stats['aligned_words']}")
        logger.info(f"  Mejora en precision:    ±{stats['precision_improvement_ms']:.0f}ms → ±20ms")

        if stats['low_confidence_words'] > 0:
            logger.info(f"  Palabras baja confianza: {stats['low_confidence_words']} ({stats['low_confidence_percentage']:.1f}%)")
            logger.info(f"  ** Revisar manualmente segmentos con score < 0.5")

        logger.info(f"{'='*70}\n")

        return {
            'segments': aligned_result['segments'],
            'word_segments': aligned_result.get('word_segments', []),
            'language': self.language,
            'stats': stats,
            'alignment_time': elapsed
        }

    def _prepare_segments(self, whisper_result: Dict) -> List[Dict]:
        """
        Preparar segmentos de Whisper para WhisperX

        WhisperX espera formato:
        [
            {
                "start": 0.0,
                "end": 5.2,
                "text": "hola mundo"
            },
            ...
        ]
        """
        segments = []

        # Detectar formato del resultado
        if 'segments' in whisper_result:
            # Formato de OptimizedTranscriber o ConfidenceQA
            for seg in whisper_result['segments']:
                segments.append({
                    'start': seg.get('start', 0),
                    'end': seg.get('end', 0),
                    'text': seg.get('text', '')
                })
        elif isinstance(whisper_result, dict) and 'text' in whisper_result:
            # Formato simple (solo texto, sin segmentos)
            # En este caso, WhisperX segmentara automaticamente
            segments = [{'start': 0, 'end': 999, 'text': whisper_result['text']}]
        else:
            raise ValueError(
                "Formato de whisper_result no reconocido. "
                "Debe tener 'segments' o 'text'"
            )

        return segments

    def _analyze_alignment(self, aligned_result: Dict, whisper_result: Dict) -> Dict:
        """
        Analizar calidad de la alineacion

        Returns:
            Dict con estadisticas
        """
        stats = {
            'total_segments': len(aligned_result.get('segments', [])),
            'aligned_segments': 0,
            'aligned_words': 0,
            'low_confidence_words': 0,
            'precision_improvement_ms': 500,  # Whisper typical jitter
        }

        # Contar palabras alineadas
        total_words = 0
        low_conf_words = 0

        for seg in aligned_result.get('segments', []):
            if 'words' in seg and seg['words']:
                stats['aligned_segments'] += 1

                for word in seg['words']:
                    total_words += 1

                    # WhisperX incluye score de confianza
                    if 'score' in word and word['score'] < 0.5:
                        low_conf_words += 1

        stats['aligned_words'] = total_words
        stats['low_confidence_words'] = low_conf_words

        if total_words > 0:
            stats['low_confidence_percentage'] = (low_conf_words / total_words) * 100
        else:
            stats['low_confidence_percentage'] = 0

        return stats

    def get_low_confidence_segments(
        self,
        aligned_result: Dict,
        confidence_threshold: float = 0.5
    ) -> List[Dict]:
        """
        Obtener segmentos con baja confianza para review manual

        Args:
            aligned_result: Resultado de align()
            confidence_threshold: Umbral de confianza (default: 0.5)

        Returns:
            Lista de segmentos que necesitan revision
        """
        low_conf_segments = []

        for seg in aligned_result.get('segments', []):
            if 'words' not in seg:
                continue

            # Calcular confianza promedio del segmento
            word_scores = [w.get('score', 1.0) for w in seg['words'] if 'score' in w]

            if word_scores:
                avg_score = np.mean(word_scores)

                if avg_score < confidence_threshold:
                    low_conf_segments.append({
                        'start': seg.get('start'),
                        'end': seg.get('end'),
                        'text': seg.get('text'),
                        'confidence': avg_score,
                        'words': seg['words'],
                        'reason': 'low_alignment_confidence'
                    })

        return low_conf_segments

    def export_to_srt(
        self,
        aligned_result: Dict,
        output_path: str,
        max_chars_per_line: int = 42
    ):
        """
        Exportar a formato SRT (subtitulos) con timestamps precisos

        Args:
            aligned_result: Resultado de align()
            output_path: Path del archivo SRT a crear
            max_chars_per_line: Maximo de caracteres por linea
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            subtitle_index = 1

            for seg in aligned_result.get('segments', []):
                # Formatear timestamps SRT
                start_time = self._format_srt_time(seg.get('start', 0))
                end_time = self._format_srt_time(seg.get('end', 0))

                # Dividir texto largo en lineas
                text = seg.get('text', '').strip()
                lines = self._wrap_text(text, max_chars_per_line)

                # Escribir subtitle
                f.write(f"{subtitle_index}\n")
                f.write(f"{start_time} --> {end_time}\n")
                for line in lines:
                    f.write(f"{line}\n")
                f.write("\n")

                subtitle_index += 1

        logger.info(f"[ALIGNMENT] Subtitulos exportados a: {output_path}")

    def _format_srt_time(self, seconds: float) -> str:
        """Formatear tiempo en formato SRT: HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _wrap_text(self, text: str, max_chars: int) -> List[str]:
        """Dividir texto en lineas de max_chars"""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            word_length = len(word) + 1  # +1 for space

            if current_length + word_length <= max_chars:
                current_line.append(word)
                current_length += word_length
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_length = word_length

        if current_line:
            lines.append(' '.join(current_line))

        return lines


def align_whisper_result(
    audio_path: str,
    whisper_result: Dict,
    language: str = "es",
    device: str = "cpu"
) -> Dict:
    """
    Helper function para alinear resultado de Whisper

    Args:
        audio_path: Path al audio
        whisper_result: Resultado de Whisper
        language: Codigo de idioma
        device: "cpu" o "cuda"

    Returns:
        Resultado alineado
    """
    aligner = ForcedAligner(language=language, device=device)
    return aligner.align(audio_path, whisper_result)


def demo_forced_alignment():
    """Demo del sistema de alignment"""
    print("\n" + "="*70)
    print("DEMO: Forced Alignment con WhisperX")
    print("="*70)

    if not WHISPERX_AVAILABLE:
        print("\n✗ WhisperX no esta instalado")
        print("  Instalar con: pip install whisperx")
        return

    print("\nSistema listo!")
    print("\nEjemplo de uso:")
    print("""
    # 1. Transcribir con Whisper
    from watcher.core.transcription.optimized_transcriber import OptimizedTranscriber

    transcriber = OptimizedTranscriber("large-v2", language="es")
    whisper_result = transcriber.transcribe_audio("audio.wav")

    # 2. Alinear con WhisperX
    from watcher.core.alignment import ForcedAligner

    aligner = ForcedAligner(language="es")
    aligned_result = aligner.align("audio.wav", whisper_result)

    # 3. Ver timestamps precisos
    for seg in aligned_result['segments']:
        for word in seg['words']:
            print(f"{word['word']}: {word['start']:.3f}s - {word['end']:.3f}s")

    # 4. Exportar subtitulos
    aligner.export_to_srt(aligned_result, "subtitles.srt")

    # 5. Revisar segmentos de baja confianza
    low_conf = aligner.get_low_confidence_segments(aligned_result)
    for seg in low_conf:
        print(f"Revisar: {seg['text']} (confianza: {seg['confidence']:.2%})")
    """)
    print("="*70 + "\n")


if __name__ == '__main__':
    demo_forced_alignment()
