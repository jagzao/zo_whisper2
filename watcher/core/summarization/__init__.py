"""
Summarization Module - Resumenes estructurados con metadata
Integra diarizacion, timestamps y deteccion de temas
"""

from .metadata_summarizer import MetadataAwareSummarizer, create_structured_summary

__all__ = ['MetadataAwareSummarizer', 'create_structured_summary']
