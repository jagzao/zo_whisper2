#!/usr/bin/env python3
"""
Timestamp Formatter Module
Provides formatting utilities for transcription timestamps
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class TimestampFormatter:
    """Formateador de timestamps para transcripciones"""

    @staticmethod
    def format_simple(segments: List[Dict]) -> str:
        """
        Formato simple: [HH:MM:SS] Texto...
        
        Args:
            segments: Lista de segmentos con start, end, text
            
        Returns:
            Texto formateado con timestamps simples
        """
        lines = []
        for seg in segments:
            timestamp = TimestampFormatter._format_time(seg["start"])
            lines.append(f"[{timestamp}] {seg['text'].strip()}")
        return "\n".join(lines)

    @staticmethod
    def format_detailed(segments: List[Dict]) -> str:
        """
        Formato detallado: [HH:MM:SS -> HH:MM:SS] Texto...
        
        Args:
            segments: Lista de segmentos con start, end, text
            
        Returns:
            Texto formateado con timestamps detallados
        """
        lines = []
        for seg in segments:
            start_time = TimestampFormatter._format_time(seg["start"])
            end_time = TimestampFormatter._format_time(seg["end"])
            lines.append(f"[{start_time} -> {end_time}] {seg['text'].strip()}")
        return "\n".join(lines)

    @staticmethod
    def format_srt(segments: List[Dict]) -> str:
        """
        Formato SRT estándar para reproductores de video.
        
        Args:
            segments: Lista de segmentos con start, end, text
            
        Returns:
            Texto en formato SRT
        """
        lines = []
        for i, seg in enumerate(segments, 1):
            start_time = TimestampFormatter._format_srt_time(seg["start"])
            end_time = TimestampFormatter._format_srt_time(seg["end"])
            
            lines.append(str(i))
            lines.append(f"{start_time} --> {end_time}")
            lines.append(seg["text"].strip())
            lines.append("")  # Línea vacía entre segmentos
        
        return "\n".join(lines)

    @staticmethod
    def format_vtt(segments: List[Dict]) -> str:
        """
        Formato WebVTT para web.
        
        Args:
            segments: Lista de segmentos con start, end, text
            
        Returns:
            Texto en formato WebVTT
        """
        lines = ["WEBVTT", ""]
        
        for seg in segments:
            start_time = TimestampFormatter._format_vtt_time(seg["start"])
            end_time = TimestampFormatter._format_vtt_time(seg["end"])
            
            lines.append(f"{start_time} --> {end_time}")
            lines.append(seg["text"].strip())
            lines.append("")  # Línea vacía entre segmentos
        
        return "\n".join(lines)

    @staticmethod
    def format_with_confidence(segments: List[Dict]) -> str:
        """
        Formato con información de confianza: [HH:MM:SS] (confianza: 0.95) Texto...
        
        Args:
            segments: Lista de segmentos con start, end, text, confidence
            
        Returns:
            Texto formateado con timestamps y confianza
        """
        lines = []
        for seg in segments:
            timestamp = TimestampFormatter._format_time(seg["start"])
            confidence = seg.get("confidence", 0.0)
            lines.append(f"[{timestamp}] (confianza: {confidence:.2f}) {seg['text'].strip()}")
        return "\n".join(lines)

    @staticmethod
    def _format_time(seconds: float) -> str:
        """
        Formatea segundos a HH:MM:SS
        
        Args:
            seconds: Tiempo en segundos
            
        Returns:
            Tiempo formateado como HH:MM:SS
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """
        Formatea segundos a HH:MM:SS,mmm (formato SRT)
        
        Args:
            seconds: Tiempo en segundos
            
        Returns:
            Tiempo formateado como HH:MM:SS,mmm
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _format_vtt_time(seconds: float) -> str:
        """
        Formatea segundos a HH:MM:SS.mmm (formato WebVTT)
        
        Args:
            seconds: Tiempo en segundos
            
        Returns:
            Tiempo formateado como HH:MM:SS.mmm
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    @staticmethod
    def format_transcription(
        segments: List[Dict],
        format_type: str = "simple"
    ) -> str:
        """
        Formatea una transcripción según el tipo especificado.
        
        Args:
            segments: Lista de segmentos con start, end, text
            format_type: Tipo de formato ("simple", "detailed", "srt", "vtt", "confidence")
            
        Returns:
            Texto formateado según el tipo especificado
            
        Raises:
            ValueError: Si el formato no es válido
        """
        formatters = {
            "simple": TimestampFormatter.format_simple,
            "detailed": TimestampFormatter.format_detailed,
            "srt": TimestampFormatter.format_srt,
            "vtt": TimestampFormatter.format_vtt,
            "confidence": TimestampFormatter.format_with_confidence,
        }
        
        if format_type not in formatters:
            raise ValueError(
                f"Formato no válido: {format_type}. "
                f"Opciones disponibles: {', '.join(formatters.keys())}"
            )
        
        return formatters[format_type](segments)


if __name__ == "__main__":
    # Test the formatter
    test_segments = [
        {"start": 0.0, "end": 5.2, "text": "Hola, bienvenidos a este tutorial.", "confidence": 0.95},
        {"start": 5.5, "end": 10.8, "text": "Hoy vamos a aprender sobre Python.", "confidence": 0.92},
        {"start": 11.0, "end": 15.3, "text": "Empecemos con lo básico.", "confidence": 0.88},
    ]
    
    print("=== FORMATO SIMPLE ===")
    print(TimestampFormatter.format_simple(test_segments))
    print()
    
    print("=== FORMATO DETALLADO ===")
    print(TimestampFormatter.format_detailed(test_segments))
    print()
    
    print("=== FORMATO SRT ===")
    print(TimestampFormatter.format_srt(test_segments))
    print()
    
    print("=== FORMATO CON CONFIANZA ===")
    print(TimestampFormatter.format_with_confidence(test_segments))
