"""
Alignment Module - Forced Alignment para timestamps precisos
Usa WhisperX con wav2vec2 para alinear palabras a frames exactos
"""

from .forced_aligner import ForcedAligner, align_whisper_result

__all__ = ['ForcedAligner', 'align_whisper_result']
