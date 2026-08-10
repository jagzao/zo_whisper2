#!/usr/bin/env python3
"""
Custom Glossary Manager for Transcription
Handles project-specific terminology, names, and technical jargon
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class GlossaryManager:
    """
    Manages custom vocabularies for improved transcription accuracy

    Handles:
    - Technical terms (UPSI, EBITDA, XR Technologies)
    - Proper names (Vikas, Nuresh, Hexaware)
    - Company-specific jargon
    - Acronyms and abbreviations
    """

    def __init__(self, glossary_file: Optional[str] = None):
        """
        Initialize glossary manager

        Args:
            glossary_file: Path to JSON file with glossaries
        """
        self.glossary_file = glossary_file or str(Path(__file__).parent / "glossaries.json")
        self.glossaries = self._load_glossaries()

        # Default global glossary (always applied)
        self.global_glossary = self._get_global_glossary()

        logger.info(f"Glossary Manager initialized with {len(self.glossaries)} project glossaries")

    def _load_glossaries(self) -> Dict[str, Dict[str, str]]:
        """Load glossaries from JSON file"""
        try:
            glossary_path = Path(self.glossary_file)
            if glossary_path.exists():
                with open(glossary_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"Glossary file not found: {self.glossary_file}, using defaults")
                return {}
        except Exception as e:
            logger.error(f"Failed to load glossaries: {e}")
            return {}

    def _get_global_glossary(self) -> Dict[str, str]:
        """
        Global glossary applied to all transcriptions

        Returns:
            Dict mapping phonetic/incorrect patterns to correct terms
        """
        return {
            # XR Technologies project
            r'\b(eks ar|xr|ex ar|ecks ar)\b': 'XR',
            r'\b(you pee es eye|you pi es i|upset|up si)\b': 'UPSI',
            r'\b(pit tool|pitt tool)\b': 'PIT tool',
            r'\b(en es di el|ns dl)\b': 'NSDL',

            # Names
            r'\bvikas\b': 'Vikas',
            r'\bnuresh\b': 'Nuresh',
            r'\blydia\b': 'Lydia',
            r'\barnaud\b': 'Arnaud',
            r'\bamit\b': 'Amit',
            r'\bpriyanka\b': 'Priyanka',

            # Companies
            r'\bhexaware\b': 'Hexaware',
            r'\bvolaris\b': 'Volaris',
            r'\btrue logic\b': 'TrueLogic',

            # Technical terms
            r'\binfo sec\b': 'InfoSec',
            r'\byou a tee\b': 'UAT',
            r'\bjay dee\b': 'JD',
            r'\ba p a\b': 'APA',

            # Common transcription errors
            r'\bpiesd\b': 'PIESD',
            r'\bauth prod path\b': 'AuthProdpath',
            r'\bcompliance piesd\b': 'CompliancePIESD',

            # Business terms
            r'\bdesignated person\b': 'Designated Person',
            r'\binsider trading\b': 'Insider Trading',
            r'\btrading window\b': 'Trading Window',
        }

    def add_project_glossary(self, project_id: str, glossary: Dict[str, str]) -> None:
        """
        Add or update a project-specific glossary

        Args:
            project_id: Unique project identifier
            glossary: Dict mapping patterns to replacements
        """
        try:
            self.glossaries[project_id] = glossary
            self._save_glossaries()
            logger.info(f"Added glossary for project '{project_id}' with {len(glossary)} entries")
        except Exception as e:
            logger.error(f"Failed to add project glossary: {e}")

    def _save_glossaries(self) -> None:
        """Save glossaries to JSON file"""
        try:
            with open(self.glossary_file, 'w', encoding='utf-8') as f:
                json.dump(self.glossaries, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save glossaries: {e}")

    def apply_glossary(
        self,
        text: str,
        project_id: Optional[str] = None,
        case_sensitive: bool = False
    ) -> str:
        """
        Apply glossary corrections to text

        Args:
            text: Input text to correct
            project_id: Optional project ID for project-specific glossary
            case_sensitive: Whether to apply case-sensitive matching

        Returns:
            Corrected text
        """
        try:
            corrected_text = text
            corrections_made = []

            # Apply global glossary
            for pattern, replacement in self.global_glossary.items():
                flags = 0 if case_sensitive else re.IGNORECASE
                matches = re.findall(pattern, corrected_text, flags=flags)

                if matches:
                    corrected_text = re.sub(pattern, replacement, corrected_text, flags=flags)
                    corrections_made.append(f"{matches[0]} → {replacement}")

            # Apply project-specific glossary if provided
            if project_id and project_id in self.glossaries:
                project_glossary = self.glossaries[project_id]
                for pattern, replacement in project_glossary.items():
                    flags = 0 if case_sensitive else re.IGNORECASE
                    matches = re.findall(pattern, corrected_text, flags=flags)

                    if matches:
                        corrected_text = re.sub(pattern, replacement, corrected_text, flags=flags)
                        corrections_made.append(f"{matches[0]} → {replacement}")

            if corrections_made:
                logger.info(f"Applied {len(corrections_made)} glossary corrections")
                logger.debug(f"Corrections: {corrections_made}")

            return corrected_text

        except Exception as e:
            logger.error(f"Glossary application failed: {e}, returning original text")
            return text

    def get_project_terms(self, project_id: str) -> List[str]:
        """
        Get list of terms for a project

        Args:
            project_id: Project identifier

        Returns:
            List of terms (replacements)
        """
        if project_id in self.glossaries:
            return list(self.glossaries[project_id].values())
        return []

    def search_glossary(self, search_term: str) -> List[tuple]:
        """
        Search for a term across all glossaries

        Args:
            search_term: Term to search for

        Returns:
            List of (project_id, pattern, replacement) tuples
        """
        results = []

        # Search global glossary
        for pattern, replacement in self.global_glossary.items():
            if search_term.lower() in replacement.lower() or search_term.lower() in pattern.lower():
                results.append(("global", pattern, replacement))

        # Search project glossaries
        for project_id, glossary in self.glossaries.items():
            for pattern, replacement in glossary.items():
                if search_term.lower() in replacement.lower() or search_term.lower() in pattern.lower():
                    results.append((project_id, pattern, replacement))

        return results


# Default glossary templates for common industries
INDUSTRY_TEMPLATES = {
    "finance": {
        r'\bebitda\b': 'EBITDA',
        r'\bgaap\b': 'GAAP',
        r'\bifrs\b': 'IFRS',
        r'\broe\b': 'ROE',
        r'\broi\b': 'ROI',
        r'\bnpv\b': 'NPV',
        r'\birr\b': 'IRR',
        r'\bcapex\b': 'CAPEX',
        r'\bopex\b': 'OPEX',
    },

    "technology": {
        r'\bapi\b': 'API',
        r'\brest\b': 'REST',
        r'\bsql\b': 'SQL',
        r'\baws\b': 'AWS',
        r'\bgcp\b': 'GCP',
        r'\bci cd\b': 'CI/CD',
        r'\bkubernetes\b': 'Kubernetes',
        r'\bdocker\b': 'Docker',
    },

    "legal": {
        r'\bnda\b': 'NDA',
        r'\bgdpr\b': 'GDPR',
        r'\bhipaa\b': 'HIPAA',
        r'\bsox\b': 'SOX',
        r'\bsla\b': 'SLA',
    }
}


def create_industry_glossary(industry: str) -> Optional[Dict[str, str]]:
    """
    Create a glossary template for an industry

    Args:
        industry: Industry name (finance, technology, legal)

    Returns:
        Glossary dict or None if industry not found
    """
    return INDUSTRY_TEMPLATES.get(industry.lower())


if __name__ == "__main__":
    # Test glossary manager
    manager = GlossaryManager()

    test_text = """
    Today we had a meeting with vikas from eks ar technologies.
    We discussed the you pee es eye compliance and the pit tool.
    Also talked with nuresh about hexaware and the auth prod path.
    """

    print("Original text:")
    print(test_text)

    corrected = manager.apply_glossary(test_text)

    print("\nCorrected text:")
    print(corrected)

    # Add project glossary
    manager.add_project_glossary("project_alpha", {
        r'\balpha tool\b': 'Alpha Tool',
        r'\bbeta system\b': 'Beta System'
    })

    print(f"\nGlossaries loaded: {list(manager.glossaries.keys())}")
