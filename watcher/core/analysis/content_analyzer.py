import re
import logging
from typing import Dict, List, Tuple

class ContentAnalyzer:
    """Analiza el contenido transcrito para determinar el tipo y generar análisis específicos"""
    
    def __init__(self):
        self.interview_keywords = [
            'entrevista', 'pregunta', 'respuesta', 'candidato', 'experiencia',
            'cuéntame', 'háblame', 'por qué', 'cómo', 'trabajaste', 'proyecto anterior',
            'fortalezas', 'debilidades', 'logros', 'retos', 'equipo', 'liderazgo'
        ]
        
        self.tutorial_keywords = [
            'tutorial', 'paso', 'primero', 'segundo', 'tercero', 'siguiente',
            'ahora', 'después', 'luego', 'procedimiento', 'instrucciones',
            'cómo hacer', 'guía', 'ejemplo', 'demo', 'demostración', 'práctica'
        ]
        
        self.meeting_keywords = [
            'reunión', 'agenda', 'proyecto', 'deadline', 'entregables', 'tareas',
            'acción', 'responsable', 'seguimiento', 'status', 'avance',
            'decisiones', 'acuerdos', 'próximos pasos', 'timeline', 'planning'
        ]

    def detect_content_type(self, transcription: str) -> str:
        """Detecta el tipo de contenido basado en palabras clave"""
        text_lower = transcription.lower()
        
        interview_score = sum(1 for keyword in self.interview_keywords if keyword in text_lower)
        tutorial_score = sum(1 for keyword in self.tutorial_keywords if keyword in text_lower)
        meeting_score = sum(1 for keyword in self.meeting_keywords if keyword in text_lower)
        
        scores = {
            'interview': interview_score,
            'tutorial': tutorial_score,
            'meeting': meeting_score
        }
        
        max_type = max(scores, key=scores.get)
        max_score = scores[max_type]
        
        # Si el score es muy bajo, considerar como 'general'
        if max_score < 3:
            return 'general'
            
        return max_type

    def analyze_interview(self, transcription: str, project_name: str) -> Dict:
        """Análisis específico para entrevistas con feedback de mejora"""
        
        # Extraer preguntas y respuestas
        questions = self._extract_questions(transcription)
        
        # Análisis de performance
        performance_analysis = self._analyze_interview_performance(transcription)
        
        # Recomendaciones de mejora
        improvements = self._generate_interview_improvements(transcription, performance_analysis)
        
        # Calcular probabilidad de éxito
        success_probability = self._calculate_interview_success_probability(transcription, performance_analysis)
        
        # Generar resumen de la entrevista
        interview_summary = self._generate_interview_summary(transcription, performance_analysis, project_name)
        
        return {
            'type': 'interview',
            'questions_identified': len(questions),
            'questions': questions[:10],  # Limitar a las primeras 10
            'performance_analysis': performance_analysis,
            'recommendations': improvements,
            'overall_score': performance_analysis.get('overall_score', 'N/A'),
            'strengths': performance_analysis.get('strengths', []),
            'areas_to_improve': performance_analysis.get('weaknesses', []),
            'success_probability': success_probability,
            'interview_summary': interview_summary
        }

    def analyze_tutorial(self, transcription: str, project_name: str) -> Dict:
        """Análisis específico para tutoriales con pasos estructurados"""
        
        # Extraer pasos del tutorial
        steps = self._extract_tutorial_steps(transcription)
        
        # Extraer conceptos clave
        key_concepts = self._extract_key_concepts(transcription)
        
        # Generar checklist de aplicación
        checklist = self._generate_tutorial_checklist(steps)
        
        return {
            'type': 'tutorial',
            'total_steps': len(steps),
            'steps': steps,
            'key_concepts': key_concepts,
            'application_checklist': checklist,
            'estimated_completion_time': self._estimate_tutorial_time(transcription),
            'difficulty_level': self._assess_difficulty(transcription),
            'prerequisites': self._extract_prerequisites(transcription)
        }

    def analyze_meeting(self, transcription: str, project_name: str) -> Dict:
        """Análisis específico para reuniones de proyecto"""
        
        # Extraer decisiones y acuerdos
        decisions = self._extract_decisions(transcription)
        
        # Extraer tareas y responsables
        action_items = self._extract_action_items(transcription)
        
        # Extraer fechas y deadlines
        deadlines = self._extract_deadlines(transcription)
        
        # Generar resumen ejecutivo de la reunión
        meeting_summary = self._generate_meeting_summary(transcription, project_name, decisions, action_items)
        
        return {
            'type': 'meeting',
            'project': project_name,
            'decisions_made': decisions,
            'action_items': action_items,
            'deadlines': deadlines,
            'participants_mentioned': self._extract_participants(transcription),
            'next_meeting': self._extract_next_meeting(transcription),
            'key_topics': self._extract_meeting_topics(transcription),
            'meeting_summary': meeting_summary
        }

    def _extract_questions(self, text: str) -> List[str]:
        """Extrae preguntas del texto"""
        # Buscar patrones de preguntas
        question_patterns = [
            r'[¿]([^?]+)[?]',  # Preguntas con ¿?
            r'([A-Z][^.!?]*\?)',  # Preguntas que terminan en ?
            r'(cuéntame[^.!?]*[.!?])',  # Preguntas imperativas
            r'(háblame[^.!?]*[.!?])',
            r'(explícame[^.!?]*[.!?])'
        ]
        
        questions = []
        for pattern in question_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            questions.extend(matches)
        
        return [q.strip() for q in questions if len(q.strip()) > 10][:15]

    def _analyze_interview_performance(self, text: str) -> Dict:
        """Analiza el performance en la entrevista"""
        
        # Indicadores positivos
        positive_indicators = [
            'experiencia', 'proyecto', 'logré', 'implementé', 'desarrollé',
            'lideré', 'coordiné', 'resultados', 'éxito', 'mejora'
        ]
        
        # Indicadores de nerviosismo/debilidad
        weak_indicators = [
            'no sé', 'no estoy seguro', 'tal vez', 'creo que',
            'mmm', 'ehh', 'bueno', 'este'
        ]
        
        text_lower = text.lower()
        
        positive_score = sum(1 for indicator in positive_indicators if indicator in text_lower)
        weak_score = sum(1 for indicator in weak_indicators if indicator in text_lower)
        
        # Calcular score general (1-10)
        total_words = len(text.split())
        confidence_ratio = max(0, positive_score - weak_score) / max(total_words / 100, 1)
        overall_score = min(10, max(1, 5 + confidence_ratio))
        
        strengths = []
        weaknesses = []
        
        if positive_score > 5:
            strengths.append("Buena articulación de experiencias")
        if 'proyecto' in text_lower:
            strengths.append("Menciona proyectos específicos")
        if any(word in text_lower for word in ['logré', 'implementé', 'desarrollé']):
            strengths.append("Enfoque en logros concretos")
            
        if weak_score > total_words / 50:  # Muchas muletillas
            weaknesses.append("Reducir muletillas y expresiones de duda")
        if positive_score < 3:
            weaknesses.append("Incluir más ejemplos específicos de experiencia")
            
        return {
            'overall_score': round(overall_score, 1),
            'confidence_level': 'Alta' if overall_score > 7 else 'Media' if overall_score > 4 else 'Baja',
            'strengths': strengths,
            'weaknesses': weaknesses,
            'positive_indicators_count': positive_score,
            'improvement_areas_count': weak_score
        }

    def _generate_interview_improvements(self, text: str, performance: Dict) -> List[str]:
        """Genera recomendaciones específicas de mejora"""
        improvements = []
        
        if performance['overall_score'] < 6:
            improvements.append("📈 Practica respuestas con ejemplos STAR (Situación, Tarea, Acción, Resultado)")
            
        if performance['improvement_areas_count'] > 10:
            improvements.append("🗣️ Reduce muletillas practicando pausas conscientes")
            
        if 'proyecto' not in text.lower():
            improvements.append("💼 Prepara 3-4 ejemplos específicos de proyectos relevantes")
            
        if performance['confidence_level'] == 'Baja':
            improvements.append("🎯 Practica frente al espejo para mejorar confianza")
            
        improvements.append("⏱️ Estructura respuestas en 2-3 minutos máximo")
        improvements.append("❓ Prepara preguntas inteligentes sobre la empresa/rol")
        
        return improvements

    def _extract_tutorial_steps(self, text: str) -> List[Dict]:
        """Extrae pasos estructurados del tutorial"""
        steps = []
        
        # Patrones para identificar pasos
        step_patterns = [
            r'paso (\d+)[:\.]?\s*([^.!?]+[.!?])',
            r'(\d+)[.\)]\s*([^.!?]+[.!?])',
            r'(primero|segundo|tercero|cuarto|quinto)[,:]?\s*([^.!?]+[.!?])',
            r'(ahora|después|luego)[,:]?\s*([^.!?]+[.!?])'
        ]
        
        step_number = 1
        for pattern in step_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple) and len(match) == 2:
                    step_indicator, step_content = match
                    steps.append({
                        'step': step_number,
                        'indicator': step_indicator,
                        'content': step_content.strip(),
                        'estimated_time': '5-10 min'  # Estimación por defecto
                    })
                    step_number += 1
        
        return steps[:20]  # Limitar a 20 pasos

    def _extract_key_concepts(self, text: str) -> List[str]:
        """Extrae conceptos clave del tutorial"""
        # Buscar palabras técnicas o conceptos importantes (mayúsculas, términos repetidos)
        words = text.split()
        word_freq = {}
        
        for word in words:
            clean_word = re.sub(r'[^\w]', '', word).lower()
            if len(clean_word) > 4 and clean_word not in ['este', 'esta', 'para', 'como', 'hacer']:
                word_freq[clean_word] = word_freq.get(clean_word, 0) + 1
        
        # Obtener las palabras más frecuentes
        key_concepts = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        return [concept[0].capitalize() for concept in key_concepts if concept[1] > 2]

    def _generate_tutorial_checklist(self, steps: List[Dict]) -> List[str]:
        """Genera checklist para aplicar el tutorial"""
        checklist = []
        
        for step in steps[:10]:  # Primeros 10 pasos
            checklist.append(f"☐ {step['content'][:100]}...")
            
        checklist.append("☐ Verificar que todo funciona correctamente")
        checklist.append("☐ Documentar cualquier problema encontrado")
        checklist.append("☐ Practicar el proceso completo una vez más")
        
        return checklist

    def _estimate_tutorial_time(self, text: str) -> str:
        """Estima tiempo de completar el tutorial"""
        word_count = len(text.split())
        
        if word_count < 500:
            return "15-30 minutos"
        elif word_count < 1500:
            return "30-60 minutos"
        elif word_count < 3000:
            return "1-2 horas"
        else:
            return "2+ horas"

    def _assess_difficulty(self, text: str) -> str:
        """Evalúa el nivel de dificultad del tutorial"""
        complex_terms = ['configuración', 'instalación', 'código', 'programar', 'terminal', 'comando']
        complex_count = sum(1 for term in complex_terms if term in text.lower())
        
        if complex_count < 2:
            return "Principiante"
        elif complex_count < 5:
            return "Intermedio"
        else:
            return "Avanzado"

    def _extract_prerequisites(self, text: str) -> List[str]:
        """Extrae prerequisitos del tutorial"""
        prereq_patterns = [
            r'necesitas?\s+([^.!?]+)',
            r'requiere\s+([^.!?]+)',
            r'antes\s+de[^,]*,?\s*([^.!?]+)'
        ]
        
        prerequisites = []
        for pattern in prereq_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            prerequisites.extend([match.strip() for match in matches])
        
        return prerequisites[:5]

    def _extract_decisions(self, text: str) -> List[str]:
        """Extrae decisiones tomadas en la reunión"""
        decision_patterns = [
            r'decidimos\s+([^.!?]+)',
            r'acordamos\s+([^.!?]+)',
            r'se\s+decidió\s+([^.!?]+)'
        ]
        
        decisions = []
        for pattern in decision_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            decisions.extend([match.strip() for match in matches])
        
        return decisions

    def _extract_action_items(self, text: str) -> List[Dict]:
        """Extrae tareas y responsables"""
        action_patterns = [
            r'(\w+)\s+va\s+a\s+([^.!?]+)',
            r'(\w+)\s+se\s+encarga\s+de\s+([^.!?]+)',
            r'tarea\s+para\s+(\w+)[:\s]+([^.!?]+)'
        ]
        
        actions = []
        for pattern in action_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) == 2:
                    responsible, task = match
                    actions.append({
                        'responsible': responsible.capitalize(),
                        'task': task.strip(),
                        'priority': 'Media'
                    })
        
        return actions

    def _extract_deadlines(self, text: str) -> List[Dict]:
        """Extrae fechas y deadlines"""
        date_patterns = [
            r'para\s+el\s+(\d{1,2}\s+de\s+\w+)',
            r'deadline\s+(\d{1,2}/\d{1,2})',
            r'entrega\s+([^.!?]+fecha[^.!?]+)'
        ]
        
        deadlines = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                deadlines.append({
                    'deadline': match,
                    'type': 'Entrega'
                })
        
        return deadlines

    def _extract_participants(self, text: str) -> List[str]:
        """Extrae participantes mencionados"""
        # Buscar nombres propios (palabras capitalizadas que no sean inicio de oración)
        words = text.split()
        participants = set()
        
        for i, word in enumerate(words):
            if word[0].isupper() and i > 0 and words[i-1][-1] not in '.!?':
                clean_name = re.sub(r'[^\w]', '', word)
                if len(clean_name) > 2:
                    participants.add(clean_name)
        
        return list(participants)[:10]

    def _calculate_interview_success_probability(self, text: str, performance: Dict) -> Dict:
        """Calcula la probabilidad de éxito en la entrevista"""
        
        # Factores positivos
        positive_factors = 0
        total_factors = 10
        
        # Factor 1: Score general (peso: 30%)
        overall_score = performance.get('overall_score', 5)
        if overall_score >= 8:
            positive_factors += 3
        elif overall_score >= 6:
            positive_factors += 2
        elif overall_score >= 4:
            positive_factors += 1
            
        # Factor 2: Confianza en respuestas (peso: 20%)
        confidence = performance.get('confidence_level', 'Media')
        if confidence == 'Alta':
            positive_factors += 2
        elif confidence == 'Media':
            positive_factors += 1
            
        # Factor 3: Ejemplos específicos mencionados (peso: 15%)
        text_lower = text.lower()
        if any(word in text_lower for word in ['proyecto', 'implementé', 'desarrollé', 'logré']):
            positive_factors += 1.5
            
        # Factor 4: Preguntas inteligentes al entrevistador (peso: 10%)
        if any(phrase in text_lower for phrase in ['mi pregunta es', 'me gustaría saber', 'quisiera preguntar']):
            positive_factors += 1
            
        # Factor 5: Conocimiento técnico demostrado (peso: 15%)
        tech_indicators = ['tecnología', 'herramienta', 'metodología', 'framework', 'lenguaje']
        if any(indicator in text_lower for indicator in tech_indicators):
            positive_factors += 1.5
            
        # Factor 6: Enfoque en resultados (peso: 10%)
        result_indicators = ['resultado', 'impacto', 'mejora', 'éxito', 'beneficio']
        if any(indicator in text_lower for indicator in result_indicators):
            positive_factors += 1
            
        # Calcular porcentaje
        probability_percentage = min(95, max(5, (positive_factors / total_factors) * 100))
        
        # Determinar nivel de probabilidad
        if probability_percentage >= 75:
            probability_level = "Alta"
            recommendation = "Excelente desempeño. Muy probable que avances al siguiente proceso."
        elif probability_percentage >= 60:
            probability_level = "Media-Alta"
            recommendation = "Buen desempeño. Buenas posibilidades de continuar en el proceso."
        elif probability_percentage >= 40:
            probability_level = "Media"
            recommendation = "Desempeño moderado. Resultado incierto, depende de otros candidatos."
        elif probability_percentage >= 25:
            probability_level = "Media-Baja"
            recommendation = "Desempeño por debajo del promedio. Pocas posibilidades de avanzar."
        else:
            probability_level = "Baja"
            recommendation = "Desempeño deficiente. Muy pocas posibilidades de continuar."
            
        return {
            'percentage': round(probability_percentage, 1),
            'level': probability_level,
            'recommendation': recommendation,
            'factors_analyzed': total_factors,
            'positive_factors_count': round(positive_factors, 1)
        }

    def _generate_interview_summary(self, text: str, performance: Dict, project_name: str) -> str:
        """Genera un resumen ejecutivo de la entrevista"""
        
        summary_parts = []
        
        # Información básica
        summary_parts.append(f"Entrevista para el proyecto/posición: {project_name}")
        
        # Performance general
        overall_score = performance.get('overall_score', 'N/A')
        confidence = performance.get('confidence_level', 'N/A')
        summary_parts.append(f"Score general: {overall_score}/10 con nivel de confianza {confidence}")
        
        # Fortalezas principales
        strengths = performance.get('strengths', [])
        if strengths:
            summary_parts.append(f"Principales fortalezas: {', '.join(strengths[:3])}")
        
        # Áreas de mejora
        weaknesses = performance.get('weaknesses', [])
        if weaknesses:
            summary_parts.append(f"Áreas de mejora identificadas: {', '.join(weaknesses[:2])}")
        
        # Temas clave mencionados
        key_topics = self._extract_interview_topics(text)
        if key_topics:
            summary_parts.append(f"Temas principales discutidos: {', '.join(key_topics[:3])}")
        
        return ". ".join(summary_parts) + "."

    def _extract_interview_topics(self, text: str) -> List[str]:
        """Extrae temas principales mencionados en la entrevista"""
        topics = []
        text_lower = text.lower()
        
        topic_keywords = {
            'Experiencia técnica': ['programación', 'desarrollo', 'código', 'tecnología'],
            'Liderazgo': ['liderazgo', 'equipo', 'dirigir', 'coordiné'],
            'Proyectos': ['proyecto', 'implementación', 'desarrollo'],
            'Resolución de problemas': ['problema', 'solución', 'resolví', 'desafío'],
            'Comunicación': ['comunicación', 'presentación', 'reunión'],
            'Aprendizaje': ['aprendí', 'capacitación', 'curso', 'certificación']
        }
        
        for topic, keywords in topic_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                topics.append(topic)
        
        return topics

    def _generate_meeting_summary(self, text: str, project_name: str, decisions: List[str], action_items: List[Dict]) -> str:
        """Genera un resumen ejecutivo de la reunión"""
        
        summary_parts = []
        
        # Información básica
        summary_parts.append(f"Reunión del proyecto {project_name}")
        
        # Estadísticas de la reunión
        decisions_count = len(decisions)
        tasks_count = len(action_items)
        
        if decisions_count > 0:
            summary_parts.append(f"Se tomaron {decisions_count} decisiones importantes")
        
        if tasks_count > 0:
            summary_parts.append(f"Se identificaron {tasks_count} tareas/acciones a realizar")
        
        # Decisiones más importantes (primeras 2)
        if decisions:
            key_decisions = decisions[:2]
            summary_parts.append(f"Decisiones clave: {'; '.join(key_decisions)}")
        
        # Tareas urgentes o importantes
        urgent_tasks = []
        for item in action_items[:3]:
            responsible = item.get('responsible', 'Sin asignar')
            task = item.get('task', '')[:50] + "..." if len(item.get('task', '')) > 50 else item.get('task', '')
            urgent_tasks.append(f"{responsible}: {task}")
        
        if urgent_tasks:
            summary_parts.append(f"Tareas principales: {'; '.join(urgent_tasks)}")
        
        # Próximos pasos
        next_meeting = self._extract_next_meeting(text)
        if next_meeting and next_meeting != "No especificado":
            summary_parts.append(f"Próxima reunión: {next_meeting}")
        
        # Estado general del proyecto
        progress_indicators = self._assess_project_progress(text)
        if progress_indicators:
            summary_parts.append(f"Estado del proyecto: {progress_indicators}")
        
        return ". ".join(summary_parts) + "."

    def _assess_project_progress(self, text: str) -> str:
        """Evalúa el estado general del proyecto basado en la reunión"""
        text_lower = text.lower()
        
        positive_indicators = ['avance', 'progreso', 'completado', 'éxito', 'logrado', 'terminado']
        negative_indicators = ['retraso', 'problema', 'bloqueado', 'pendiente', 'atrasado', 'dificultad']
        neutral_indicators = ['revisión', 'planificación', 'discusión', 'análisis']
        
        positive_count = sum(1 for indicator in positive_indicators if indicator in text_lower)
        negative_count = sum(1 for indicator in negative_indicators if indicator in text_lower)
        neutral_count = sum(1 for indicator in neutral_indicators if indicator in text_lower)
        
        if positive_count > negative_count and positive_count > 0:
            return "En progreso positivo"
        elif negative_count > positive_count and negative_count > 0:
            return "Con desafíos/retrasos"
        elif neutral_count > 0:
            return "En fase de planificación/revisión"
        else:
            return "Estado regular"

    def _extract_next_meeting(self, text: str) -> str:
        """Extrae información de próxima reunión"""
        next_meeting_patterns = [
            r'próxima\s+reunión\s+([^.!?]+)',
            r'nos\s+vemos\s+([^.!?]+)',
            r'siguiente\s+meeting\s+([^.!?]+)'
        ]
        
        for pattern in next_meeting_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return "No especificado"

    def _extract_meeting_topics(self, text: str) -> List[str]:
        """Extrae temas principales de la reunión"""
        # Buscar temas comunes de reuniones
        topic_keywords = [
            'proyecto', 'desarrollo', 'diseño', 'testing', 'deployment',
            'presupuesto', 'timeline', 'recursos', 'equipo', 'cliente'
        ]
        
        topics = []
        text_lower = text.lower()
        
        for keyword in topic_keywords:
            if keyword in text_lower:
                topics.append(keyword.capitalize())
        
        return topics