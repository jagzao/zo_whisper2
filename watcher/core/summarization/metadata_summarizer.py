"""
Metadata-aware Summarizer - Resumenes estructurados con contexto
Integra diarizacion, timestamps, keywords y deteccion de temas
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class MetadataAwareSummarizer:
    """
    Sistema de resumenes estructurados con metadata

    Caracteristicas:
    - Integra speaker diarization
    - Usa timestamps precisos
    - Detecta cambios de tema
    - Extrae keywords y entidades
    - Genera timeline navegable
    - Formato tipo "meeting minutes"
    """

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: Cliente LLM (OpenAI, DeepSeek, etc.)
        """
        self.llm = llm_client

    def create_structured_summary(
        self,
        transcription_data: Dict,
        include_timeline: bool = True,
        include_speakers: bool = True,
        include_action_items: bool = True
    ) -> Dict:
        """
        Crear resumen estructurado con metadata

        Args:
            transcription_data: Dict con transcripcion completa
                {
                    'text': str,
                    'segments': [...],
                    'language': str,
                    'metadata': {...}
                }
            include_timeline: Incluir linea de tiempo
            include_speakers: Incluir analisis por speaker
            include_action_items: Detectar action items

        Returns:
            Dict con resumen estructurado
        """
        logger.info("[SUMMARY] Creando resumen estructurado...")

        # 1. Preparar contexto
        context = self._prepare_context(transcription_data)

        # 2. Agrupar por speakers si disponible
        speaker_contributions = {}
        if include_speakers and 'segments' in transcription_data:
            speaker_contributions = self._group_by_speaker(
                transcription_data['segments']
            )

        # 3. Detectar secciones tematicas
        sections = self._detect_sections(transcription_data['segments'])

        # 4. Extraer keywords
        keywords = self._extract_keywords(transcription_data['text'])

        # 5. Detectar entidades
        entities = self._extract_entities(transcription_data['text'])

        # 6. Crear prompt enriquecido para LLM
        prompt = self._build_enriched_prompt(
            transcription_data,
            speaker_contributions,
            sections,
            keywords,
            entities
        )

        # 7. Generar resumen con LLM
        if self.llm:
            summary_text = self._generate_summary_with_llm(prompt)
        else:
            summary_text = self._generate_basic_summary(transcription_data)

        # 8. Crear timeline si se solicita
        timeline = []
        if include_timeline:
            timeline = self._create_timeline(sections)

        # 9. Detectar action items
        action_items = []
        if include_action_items:
            action_items = self._extract_action_items(
                transcription_data['text'],
                speaker_contributions
            )

        # 10. Construir resultado estructurado
        result = {
            'executive_summary': summary_text,
            'metadata': {
                'duration': transcription_data.get('metadata', {}).get('duration', 0),
                'date': datetime.now().isoformat(),
                'language': transcription_data.get('language', 'unknown'),
                'num_speakers': len(speaker_contributions),
                'num_sections': len(sections)
            },
            'speakers': list(speaker_contributions.keys()),
            'speaker_contributions': speaker_contributions,
            'sections': sections,
            'keywords': keywords,
            'entities': entities,
            'timeline': timeline,
            'action_items': action_items,
            'full_text': transcription_data['text']
        }

        logger.info(f"[SUMMARY] Resumen creado:")
        logger.info(f"  Speakers: {len(speaker_contributions)}")
        logger.info(f"  Secciones: {len(sections)}")
        logger.info(f"  Keywords: {len(keywords)}")
        logger.info(f"  Action items: {len(action_items)}")

        return result

    def _prepare_context(self, transcription_data: Dict) -> str:
        """Preparar contexto para el resumen"""
        metadata = transcription_data.get('metadata', {})

        context = f"""
Transcripcion de audio:
- Duracion: {metadata.get('duration', 'unknown')}
- Idioma: {transcription_data.get('language', 'unknown')}
- Fecha: {metadata.get('date', 'unknown')}
        """
        return context.strip()

    def _group_by_speaker(self, segments: List[Dict]) -> Dict:
        """Agrupar contribuciones por speaker"""
        speaker_contributions = {}

        for seg in segments:
            speaker = seg.get('speaker', 'Unknown')

            if speaker not in speaker_contributions:
                speaker_contributions[speaker] = {
                    'segments': [],
                    'total_words': 0,
                    'speaking_time': 0,
                    'key_points': []
                }

            # Agregar segmento
            speaker_contributions[speaker]['segments'].append(seg)

            # Contar palabras
            words = seg.get('text', '').split()
            speaker_contributions[speaker]['total_words'] += len(words)

            # Tiempo de habla
            duration = seg.get('end', 0) - seg.get('start', 0)
            speaker_contributions[speaker]['speaking_time'] += duration

        return speaker_contributions

    def _detect_sections(self, segments: List[Dict]) -> List[Dict]:
        """
        Detectar cambios de tema/seccion

        Usa simple heuristica basada en:
        - Pausas largas (>2s)
        - Cambios de speaker
        - Palabras clave de transicion
        """
        sections = []
        current_section = {
            'start': 0,
            'end': 0,
            'topic': 'Introduccion',
            'text': '',
            'speaker': None
        }

        transition_keywords = [
            'siguiente tema', 'ahora vamos', 'pasando a', 'cambiando de tema',
            'en otro tema', 'por otro lado', 'ademas', 'tambien'
        ]

        for i, seg in enumerate(segments):
            text = seg.get('text', '').lower()
            start = seg.get('start', 0)
            end = seg.get('end', 0)

            # Detectar transicion
            is_transition = False

            # 1. Pausa larga antes de este segmento
            if i > 0:
                prev_end = segments[i-1].get('end', 0)
                pause = start - prev_end
                if pause > 2.0:
                    is_transition = True

            # 2. Palabras clave de transicion
            if any(keyword in text for keyword in transition_keywords):
                is_transition = True

            # 3. Cambio de speaker
            if i > 0:
                prev_speaker = segments[i-1].get('speaker')
                curr_speaker = seg.get('speaker')
                if prev_speaker != curr_speaker and current_section['text']:
                    is_transition = True

            if is_transition and current_section['text']:
                # Finalizar seccion actual
                sections.append(current_section)

                # Iniciar nueva seccion
                current_section = {
                    'start': start,
                    'end': end,
                    'topic': self._infer_topic(text),
                    'text': text,
                    'speaker': seg.get('speaker')
                }
            else:
                # Continuar seccion actual
                current_section['end'] = end
                current_section['text'] += ' ' + text

        # Agregar ultima seccion
        if current_section['text']:
            sections.append(current_section)

        return sections

    def _infer_topic(self, text: str) -> str:
        """Inferir tema de un segmento (simplificado)"""
        # Tomar primeras palabras como tema
        words = text.split()[:5]
        topic = ' '.join(words)
        return topic.capitalize() if topic else 'Tema'

    def _extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """Extraer keywords principales (TF-IDF simplificado)"""
        # Normalizar
        text_lower = text.lower()

        # Palabras comunes a ignorar
        stopwords = {'el', 'la', 'de', 'que', 'y', 'a', 'en', 'un', 'ser',
                    'para', 'con', 'no', 'una', 'su', 'al', 'por', 'como',
                    'es', 'del', 'los', 'se', 'las', 'este', 'esta'}

        # Contar palabras
        words = re.findall(r'\b\w+\b', text_lower)
        word_freq = {}

        for word in words:
            if len(word) > 3 and word not in stopwords:
                word_freq[word] = word_freq.get(word, 0) + 1

        # Ordenar por frecuencia
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)

        # Top N keywords
        keywords = [word for word, freq in sorted_words[:top_n]]

        return keywords

    def _extract_entities(self, text: str) -> Dict:
        """Extraer entidades nombradas (simplificado)"""
        # Patrones simples para nombres y fechas
        entities = {
            'nombres': [],
            'fechas': [],
            'numeros': []
        }

        # Detectar nombres propios (palabras capitalizadas)
        names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        entities['nombres'] = list(set(names))[:10]

        # Detectar fechas
        dates = re.findall(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', text)
        entities['fechas'] = list(set(dates))

        # Detectar numeros importantes
        numbers = re.findall(r'\b\d+(?:\.\d+)?\b', text)
        entities['numeros'] = list(set(numbers))[:5]

        return entities

    def _create_timeline(self, sections: List[Dict]) -> List[Dict]:
        """Crear linea de tiempo navegable"""
        timeline = []

        for i, section in enumerate(sections):
            timeline.append({
                'index': i + 1,
                'timestamp': section['start'],
                'duration': section['end'] - section['start'],
                'title': section['topic'][:50],
                'preview': section['text'][:100] + '...'
            })

        return timeline

    def _extract_action_items(
        self,
        text: str,
        speaker_contributions: Dict
    ) -> List[Dict]:
        """Detectar action items y tareas"""
        action_items = []

        # Patrones de action items
        patterns = [
            r'(hay que|debemos|tenemos que|necesitamos|vamos a)\s+([^.]+)',
            r'(accion|tarea|pendiente):\s*([^.]+)',
            r'(responsable|encargado):\s*([^.]+)',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                action_text = match.group(0).strip()

                # Intentar inferir responsable
                responsible = 'Sin asignar'
                for speaker in speaker_contributions.keys():
                    if speaker.lower() in action_text.lower():
                        responsible = speaker
                        break

                action_items.append({
                    'text': action_text,
                    'responsible': responsible,
                    'status': 'Pendiente'
                })

        return action_items[:10]  # Top 10

    def _build_enriched_prompt(
        self,
        transcription_data: Dict,
        speaker_contributions: Dict,
        sections: List[Dict],
        keywords: List[str],
        entities: Dict
    ) -> str:
        """Construir prompt enriquecido para LLM"""
        prompt = f"""
Analiza esta transcripcion y genera un resumen estructurado tipo "meeting minutes":

## METADATA
- Duracion: {transcription_data.get('metadata', {}).get('duration', 'unknown')}
- Idioma: {transcription_data.get('language', 'unknown')}
- Participantes: {', '.join(speaker_contributions.keys())}

## KEYWORDS DETECTADAS
{', '.join(keywords)}

## ENTIDADES MENCIONADAS
{entities}

## SECCIONES DETECTADAS
{len(sections)} secciones tematicas identificadas

## TRANSCRIPCION COMPLETA
{transcription_data['text']}

---

GENERA UN RESUMEN EN ESTE FORMATO:

# Resumen Ejecutivo
[2-3 oraciones del tema principal y conclusiones]

# Puntos Clave
- [Punto importante 1]
- [Punto importante 2]
- [Punto importante 3]

# Discusion por Participante
{self._format_speaker_sections(speaker_contributions)}

# Decisiones Tomadas
- [Decision 1]
- [Decision 2]

# Proximos Pasos
[Lo que sigue despues de esta reunion/conversacion]
"""
        return prompt

    def _format_speaker_sections(self, speaker_contributions: Dict) -> str:
        """Formatear secciones por speaker"""
        sections = []
        for speaker, data in speaker_contributions.items():
            sections.append(f"""
## {speaker}
- Tiempo de habla: {data['speaking_time']:.1f}s
- Palabras: {data['total_words']}
- [Principales contribuciones de {speaker}]
""")
        return '\n'.join(sections)

    def _generate_summary_with_llm(self, prompt: str) -> str:
        """Generar resumen usando LLM"""
        if not self.llm:
            return "LLM no configurado"

        try:
            # Llamar a tu cliente LLM (OpenAI, DeepSeek, etc.)
            # Esto dependera de tu implementacion actual
            response = self.llm.complete(prompt)
            return response
        except Exception as e:
            logger.error(f"[SUMMARY] Error generando con LLM: {e}")
            return "Error generando resumen"

    def _generate_basic_summary(self, transcription_data: Dict) -> str:
        """Generar resumen basico sin LLM"""
        text = transcription_data['text']
        words = text.split()

        # Resumen simple: primeras y ultimas oraciones
        sentences = text.split('.')
        if len(sentences) > 3:
            summary = f"{sentences[0]}. {sentences[-2]}."
        else:
            summary = text[:200] + "..."

        return summary

    def export_to_notion(self, structured_summary: Dict, notion_client=None):
        """Exportar resumen estructurado a Notion"""
        if not notion_client:
            logger.warning("[SUMMARY] Notion client no configurado")
            return None

        # Crear pagina Notion con formato rico
        # (Implementacion especifica para tu integracion Notion actual)
        pass


def create_structured_summary(
    transcription_data: Dict,
    llm_client=None
) -> Dict:
    """
    Helper function para crear resumen estructurado

    Args:
        transcription_data: Datos de transcripcion
        llm_client: Cliente LLM opcional

    Returns:
        Dict con resumen estructurado
    """
    summarizer = MetadataAwareSummarizer(llm_client)
    return summarizer.create_structured_summary(transcription_data)
