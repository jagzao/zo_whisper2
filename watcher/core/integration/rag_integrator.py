import os
import logging
from pathlib import Path
import shutil
from typing import Dict, Optional

class RAGIntegrator:
    """Integra transcripciones de reuniones con el sistema RAG"""
    
    def __init__(self):
        self.rag_base_path = Path("C:/Dev/Triger/Automation/Rag/ragia_app/_transcripciones")
        
    def should_integrate_with_rag(self, content_type: str, project_name: str) -> bool:
        """Determina si el contenido debe integrarse con RAG"""
        return content_type == 'meeting' and self._is_project_meeting(project_name)
    
    def _is_project_meeting(self, project_name: str) -> bool:
        """Verifica si es una reunión de proyecto basado en el nombre"""
        project_indicators = [
            'reunion', 'meeting', 'proyecto', 'sprint', 'standup',
            'planning', 'review', 'retrospective', 'daily'
        ]
        
        project_lower = project_name.lower()
        return any(indicator in project_lower for indicator in project_indicators)
    
    def integrate_meeting_transcription(self, 
                                      transcription_content: str,
                                      analysis_result: Dict,
                                      project_name: str,
                                      file_name: str) -> bool:
        """Integra transcripción de reunión en el sistema RAG"""
        
        try:
            # Crear estructura de carpetas en RAG
            project_folder = self.rag_base_path / project_name / "transcripciones"
            project_folder.mkdir(parents=True, exist_ok=True)
            
            # Generar nombre corto de reunión
            short_meeting_name = self._generate_short_meeting_name(file_name, analysis_result)
            
            # Archivo de transcripción
            transcription_file = project_folder / f"{short_meeting_name}.txt"
            
            # Crear contenido enriquecido para RAG
            enriched_content = self._create_enriched_content(
                transcription_content, 
                analysis_result, 
                project_name
            )
            
            # Guardar transcripción enriquecida
            with open(transcription_file, 'w', encoding='utf-8') as f:
                f.write(enriched_content)
            
            logging.info(f"✅ Transcripción integrada en RAG: {transcription_file}")
            
            # Crear archivo de metadatos
            self._create_metadata_file(project_folder, short_meeting_name, analysis_result)
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Error integrando con RAG: {e}")
            return False
    
    def _generate_short_meeting_name(self, original_filename: str, analysis: Dict) -> str:
        """Genera nombre corto para la reunión basado en contenido"""
        
        # Obtener nombre base sin extensión
        base_name = Path(original_filename).stem
        
        # Extraer tipo de reunión si está disponible
        topics = analysis.get('key_topics', [])
        
        if topics:
            primary_topic = topics[0].lower()
            # Mapear temas a nombres cortos
            topic_mapping = {
                'proyecto': 'proyecto',
                'desarrollo': 'dev',
                'diseño': 'design',
                'testing': 'test',
                'deployment': 'deploy',
                'presupuesto': 'budget',
                'timeline': 'planning',
                'recursos': 'recursos',
                'equipo': 'team',
                'cliente': 'cliente'
            }
            short_topic = topic_mapping.get(primary_topic, primary_topic[:6])
            return f"{short_topic}_{base_name[:10]}"
        
        # Si no hay temas, usar fecha/hora si está disponible
        if len(base_name) > 15:
            return base_name[:15]
        
        return base_name
    
    def _create_enriched_content(self, 
                               transcription: str, 
                               analysis: Dict, 
                               project_name: str) -> str:
        """Crea contenido enriquecido para RAG con metadatos estructurados"""
        
        enriched_content = f"""# REUNIÓN - {project_name.upper()}

## RESUMEN EJECUTIVO
{analysis.get('meeting_summary', 'No disponible')}

## METADATOS
- **Proyecto**: {project_name}
- **Tipo**: {analysis.get('type', 'meeting')}
- **Fecha de procesamiento**: {self._get_current_date()}
- **Participantes**: {len(analysis.get('participants_mentioned', []))}
- **Decisiones tomadas**: {len(analysis.get('decisions_made', []))}
- **Tareas identificadas**: {len(analysis.get('action_items', []))}

## DECISIONES TOMADAS
"""
        
        # Agregar decisiones
        decisions = analysis.get('decisions_made', [])
        if decisions:
            for i, decision in enumerate(decisions, 1):
                enriched_content += f"{i}. {decision}\n"
        else:
            enriched_content += "No se identificaron decisiones específicas.\n"
        
        enriched_content += "\n## TAREAS Y RESPONSABLES\n"
        
        # Agregar action items
        action_items = analysis.get('action_items', [])
        if action_items:
            for item in action_items:
                responsible = item.get('responsible', 'No asignado')
                task = item.get('task', '')
                priority = item.get('priority', 'Media')
                enriched_content += f"- **{responsible}**: {task} (Prioridad: {priority})\n"
        else:
            enriched_content += "No se identificaron tareas específicas.\n"
        
        enriched_content += "\n## FECHAS Y DEADLINES\n"
        
        # Agregar deadlines
        deadlines = analysis.get('deadlines', [])
        if deadlines:
            for deadline in deadlines:
                enriched_content += f"- {deadline.get('type', 'Deadline')}: {deadline.get('deadline', 'No especificado')}\n"
        else:
            enriched_content += "No se identificaron deadlines específicos.\n"
        
        enriched_content += "\n## PARTICIPANTES\n"
        participants = analysis.get('participants_mentioned', [])
        if participants:
            enriched_content += ", ".join(participants) + "\n"
        else:
            enriched_content += "No se identificaron participantes específicos.\n"
        
        enriched_content += "\n## PRÓXIMA REUNIÓN\n"
        next_meeting = analysis.get('next_meeting', 'No especificado')
        enriched_content += f"{next_meeting}\n"
        
        enriched_content += "\n## TEMAS PRINCIPALES\n"
        topics = analysis.get('key_topics', [])
        if topics:
            enriched_content += ", ".join(topics) + "\n"
        
        enriched_content += "\n" + "="*50 + "\n"
        enriched_content += "## TRANSCRIPCIÓN COMPLETA\n\n"
        enriched_content += transcription
        
        return enriched_content
    
    def _create_metadata_file(self, project_folder: Path, meeting_name: str, analysis: Dict):
        """Crea archivo de metadatos JSON para el RAG"""
        
        metadata_file = project_folder / f"{meeting_name}_metadata.json"
        
        import json
        
        metadata = {
            "meeting_name": meeting_name,
            "content_type": "meeting_transcription",
            "analysis_summary": {
                "decisions_count": len(analysis.get('decisions_made', [])),
                "action_items_count": len(analysis.get('action_items', [])),
                "deadlines_count": len(analysis.get('deadlines', [])),
                "participants_count": len(analysis.get('participants_mentioned', [])),
                "key_topics": analysis.get('key_topics', [])
            },
            "processing_date": self._get_current_date(),
            "rag_integration": True
        }
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    def _get_current_date(self) -> str:
        """Obtiene fecha actual en formato legible"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def check_rag_path_exists(self) -> bool:
        """Verifica si la ruta del RAG existe"""
        return self.rag_base_path.exists()
    
    def create_rag_structure_if_needed(self):
        """Crea estructura básica del RAG si no existe"""
        if not self.check_rag_path_exists():
            try:
                self.rag_base_path.mkdir(parents=True, exist_ok=True)
                logging.info(f"✅ Estructura RAG creada en: {self.rag_base_path}")
                
                # Crear archivo README explicativo
                readme_file = self.rag_base_path / "README.md"
                readme_content = """# Transcripciones para RAG

Este directorio contiene transcripciones de reuniones organizadas por proyecto.

## Estructura:
```
_transcripciones/
├── {proyecto}/
│   ├── transcripciones/
│   │   ├── reunion1.txt
│   │   ├── reunion1_metadata.json
│   │   └── ...
│   └── ...
```

## Contenido de archivos:
- `.txt`: Transcripción enriquecida con metadatos estructurados
- `_metadata.json`: Metadatos en formato JSON para procesamiento automático

Generado automáticamente por Whisper Transcription System.
"""
                with open(readme_file, 'w', encoding='utf-8') as f:
                    f.write(readme_content)
                    
            except Exception as e:
                logging.error(f"❌ Error creando estructura RAG: {e}")
                return False
        
        return True