"""
Evaluation Module - Sistema de Benchmark WER/CER para Whisper
Permite medir objetivamente la calidad de transcripciones
"""

from .benchmark import TranscriptionBenchmark, BenchmarkResult
from .metrics import calculate_wer, calculate_cer, calculate_mer

__all__ = [
    'TranscriptionBenchmark',
    'BenchmarkResult',
    'calculate_wer',
    'calculate_cer',
    'calculate_mer',
]
