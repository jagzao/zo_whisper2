#!/usr/bin/env python3
"""
Bilingual Post-Processing for Transcriptions
Formats numbers, dates, acronyms, and text according to language conventions
"""

import re
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BilingualFormatter:
    """
    Post-process transcription text according to language-specific conventions

    Handles:
    - Number formatting (1,000.50 vs 1.000,50)
    - Date formatting (MM/DD/YYYY vs DD/MM/YYYY)
    - Currency symbols and placement
    - Acronym formatting (FBI vs F.B.I.)
    - Punctuation and capitalization rules
    """

    def __init__(self, language: str = "en"):
        """
        Initialize formatter

        Args:
            language: Language code ('en', 'es', etc.)
        """
        self.language = language
        self.rules = self._get_language_rules(language)
        logger.info(f"Bilingual Formatter initialized for language: {language}")

    def _get_language_rules(self, language: str) -> Dict:
        """Get formatting rules for a language"""
        rules = {
            "en": {
                "decimal_separator": ".",
                "thousands_separator": ",",
                "date_format": "MM/DD/YYYY",
                "currency_position": "before",  # $100
                "acronym_dots": False,  # FBI (not F.B.I.)
                "quotation_marks": '""',
                "sentence_spacing": 1,
            },
            "es": {
                "decimal_separator": ",",
                "thousands_separator": ".",
                "date_format": "DD/MM/YYYY",
                "currency_position": "after",  # 100€
                "acronym_dots": True,  # F.B.I.
                "quotation_marks": '«»',
                "sentence_spacing": 1,
            }
        }

        return rules.get(language, rules["en"])

    def format_numbers(self, text: str) -> str:
        """
        Format numbers according to language conventions

        English: 1,234.56
        Spanish: 1.234,56

        Args:
            text: Input text

        Returns:
            Text with formatted numbers
        """
        try:
            # Find all numbers with decimals
            number_pattern = r'\b(\d+)[,.](\d+)\b'

            def replace_number(match):
                integer_part = match.group(1)
                decimal_part = match.group(2)

                # Add thousands separators
                if len(integer_part) > 3:
                    # Split into groups of 3 from right
                    groups = []
                    for i in range(len(integer_part), 0, -3):
                        groups.insert(0, integer_part[max(0, i-3):i])

                    integer_formatted = self.rules["thousands_separator"].join(groups)
                else:
                    integer_formatted = integer_part

                # Combine with decimal part
                return f"{integer_formatted}{self.rules['decimal_separator']}{decimal_part}"

            formatted = re.sub(number_pattern, replace_number, text)
            return formatted

        except Exception as e:
            logger.warning(f"Number formatting failed: {e}")
            return text

    def format_dates(self, text: str) -> str:
        """
        Format dates according to language conventions

        Converts date references to appropriate format

        Args:
            text: Input text

        Returns:
            Text with formatted dates
        """
        try:
            if self.language == "es":
                # Convert month names to Spanish
                month_translations = {
                    "january": "enero",
                    "february": "febrero",
                    "march": "marzo",
                    "april": "abril",
                    "may": "mayo",
                    "june": "junio",
                    "july": "julio",
                    "august": "agosto",
                    "september": "septiembre",
                    "october": "octubre",
                    "november": "noviembre",
                    "december": "diciembre",
                }

                formatted = text
                for en_month, es_month in month_translations.items():
                    formatted = re.sub(
                        rf'\b{en_month}\b',
                        es_month,
                        formatted,
                        flags=re.IGNORECASE
                    )

                # Format "March 5" -> "5 de marzo"
                formatted = re.sub(
                    r'\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(\d{1,2})\b',
                    r'\2 de \1',
                    formatted,
                    flags=re.IGNORECASE
                )

                return formatted

            return text

        except Exception as e:
            logger.warning(f"Date formatting failed: {e}")
            return text

    def format_acronyms(self, text: str) -> str:
        """
        Format acronyms according to language conventions

        English: FBI, NASA, API
        Spanish: F.B.I., N.A.S.A., A.P.I.

        Args:
            text: Input text

        Returns:
            Text with formatted acronyms
        """
        try:
            if self.language == "es" and self.rules["acronym_dots"]:
                # Find all-caps sequences of 2+ letters
                acronym_pattern = r'\b([A-Z]{2,})\b'

                def add_dots(match):
                    acronym = match.group(1)
                    # Add dots between letters
                    return '.'.join(acronym) + '.'

                # Only apply to known acronyms (to avoid breaking words)
                known_acronyms = ['FBI', 'CIA', 'NASA', 'API', 'SQL', 'HTML', 'CSS', 'USA', 'UK', 'EU']

                formatted = text
                for acronym in known_acronyms:
                    if acronym in text:
                        dotted = '.'.join(acronym) + '.'
                        formatted = re.sub(rf'\b{acronym}\b', dotted, formatted)

                return formatted

            return text

        except Exception as e:
            logger.warning(f"Acronym formatting failed: {e}")
            return text

    def format_currency(self, text: str) -> str:
        """
        Format currency according to language conventions

        English: $100.50
        Spanish: 100,50€

        Args:
            text: Input text

        Returns:
            Text with formatted currency
        """
        try:
            # Currency symbols
            currency_symbols = {
                "$": "dollar",
                "€": "euro",
                "£": "pound",
                "¥": "yen"
            }

            if self.language == "es":
                # Move currency symbol to after number
                for symbol in currency_symbols.keys():
                    # Pattern: $100.50 -> 100,50€
                    pattern = rf'\{symbol}(\d+(?:[.,]\d+)?)'
                    replacement = r'\1' + symbol
                    text = re.sub(pattern, replacement, text)

            return text

        except Exception as e:
            logger.warning(f"Currency formatting failed: {e}")
            return text

    def format_time(self, text: str) -> str:
        """
        Format time references according to language conventions

        English: 3:30 PM
        Spanish: 15:30 or 3:30 p.m.

        Args:
            text: Input text

        Returns:
            Text with formatted time
        """
        try:
            if self.language == "es":
                # Convert AM/PM to lowercase with dots
                text = re.sub(r'\bAM\b', 'a.m.', text)
                text = re.sub(r'\bPM\b', 'p.m.', text)

            return text

        except Exception as e:
            logger.warning(f"Time formatting failed: {e}")
            return text

    def fix_capitalization(self, text: str) -> str:
        """
        Fix capitalization according to language rules

        Args:
            text: Input text

        Returns:
            Text with corrected capitalization
        """
        try:
            # Capitalize first letter
            if text:
                text = text[0].upper() + text[1:]

            # Capitalize after sentence endings
            text = re.sub(
                r'([.!?]\s+)([a-z])',
                lambda m: m.group(1) + m.group(2).upper(),
                text
            )

            # Language-specific capitalizations
            if self.language == "es":
                # Days and months are lowercase in Spanish
                days_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
                months_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                           "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

                for day in days_es:
                    text = re.sub(rf'\b{day.capitalize()}\b', day, text, flags=re.IGNORECASE)
                for month in months_es:
                    text = re.sub(rf'\b{month.capitalize()}\b', month, text, flags=re.IGNORECASE)

            return text

        except Exception as e:
            logger.warning(f"Capitalization fix failed: {e}")
            return text

    def format_punctuation(self, text: str) -> str:
        """
        Format punctuation according to language rules

        Args:
            text: Input text

        Returns:
            Text with formatted punctuation
        """
        try:
            # Remove extra spaces before punctuation
            text = re.sub(r'\s+([,.!?;:])', r'\1', text)

            # Add space after punctuation if missing
            text = re.sub(r'([,.!?;:])([^\s\d])', r'\1 \2', text)

            # Language-specific punctuation
            if self.language == "es":
                # Spanish uses inverted question/exclamation marks
                # This is hard to add automatically, but we can clean up spacing
                text = re.sub(r'¿\s+', '¿', text)
                text = re.sub(r'¡\s+', '¡', text)

            return text

        except Exception as e:
            logger.warning(f"Punctuation formatting failed: {e}")
            return text

    def format_text(self, text: str) -> str:
        """
        Apply all formatting rules to text

        Args:
            text: Input text

        Returns:
            Fully formatted text
        """
        try:
            logger.info(f"Applying bilingual formatting ({self.language})")

            formatted = text

            # Apply formatters in sequence (with exception protection)
            formatters = [
                ("numbers", self.format_numbers),
                ("dates", self.format_dates),
                ("currency", self.format_currency),
                ("time", self.format_time),
                ("acronyms", self.format_acronyms),
                ("punctuation", self.format_punctuation),
                ("capitalization", self.fix_capitalization),
            ]

            for name, formatter in formatters:
                try:
                    formatted = formatter(formatted)
                except Exception as e:
                    logger.warning(f"{name} formatter failed: {e}, skipping")
                    continue

            logger.info("Bilingual formatting completed successfully")
            return formatted

        except Exception as e:
            logger.error(f"Bilingual formatting failed completely: {e}, returning original text")
            return text


def detect_and_format(text: str, language: Optional[str] = None) -> str:
    """
    Convenience function to format text

    Args:
        text: Input text
        language: Language code (or None to auto-detect)

    Returns:
        Formatted text
    """
    if language is None:
        # Simple language detection based on common words
        spanish_words = ["el", "la", "los", "las", "de", "que", "en", "y", "a", "por", "para", "con"]
        english_words = ["the", "of", "and", "to", "a", "in", "that", "is", "was", "for"]

        text_lower = text.lower()
        spanish_count = sum(1 for word in spanish_words if f" {word} " in text_lower)
        english_count = sum(1 for word in english_words if f" {word} " in text_lower)

        language = "es" if spanish_count > english_count else "en"
        logger.info(f"Auto-detected language: {language}")

    formatter = BilingualFormatter(language)
    return formatter.format_text(text)


if __name__ == "__main__":
    # Test formatter
    print("=== ENGLISH FORMATTING ===")
    en_text = "On march 5 we spent $1500.50 for the FBI investigation. The meeting was at 3:30 PM."
    en_formatter = BilingualFormatter("en")
    print(f"Original: {en_text}")
    print(f"Formatted: {en_formatter.format_text(en_text)}")

    print("\n=== SPANISH FORMATTING ===")
    es_text = "El 5 de march gastamos $1500.50 para la investigación del FBI. La reunión fue a las 3:30 PM."
    es_formatter = BilingualFormatter("es")
    print(f"Original: {es_text}")
    print(f"Formatted: {es_formatter.format_text(es_text)}")
