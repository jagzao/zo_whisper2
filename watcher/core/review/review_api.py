"""
Review API - API REST para el sistema de revision manual
Expone endpoints para frontend de revision
"""

import logging
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from typing import Dict, List
import os

from .review_queue import ReviewQueue, should_flag_for_review

logger = logging.getLogger(__name__)


def create_review_api(queue_file: str = "./review_queue.json", port: int = 5050) -> Flask:
    """
    Crear aplicacion Flask con API de revision

    Args:
        queue_file: Path al archivo de cola
        port: Puerto para el servidor

    Returns:
        Flask app configurada
    """
    app = Flask(__name__)
    CORS(app)  # Enable CORS for frontend

    # Inicializar queue
    queue = ReviewQueue(queue_file)

    @app.route('/')
    def index():
        """Servir pagina principal"""
        return """
        <html>
        <head><title>Review UI</title></head>
        <body>
            <h1>Whisper Review UI</h1>
            <p>API funcionando correctamente</p>
            <p>Endpoints disponibles:</p>
            <ul>
                <li>GET /api/queue - Obtener cola de revision</li>
                <li>GET /api/stats - Estadisticas</li>
                <li>POST /api/review/submit - Enviar revision</li>
                <li>GET /api/audio/{filename} - Obtener audio</li>
            </ul>
        </body>
        </html>
        """

    @app.route('/api/queue', methods=['GET'])
    def get_queue():
        """
        Obtener segmentos pendientes de revision

        Query params:
            limit: Maximo de segmentos (default: 50)
        """
        try:
            limit = int(request.args.get('limit', 50))
            pending = queue.get_pending_segments(limit=limit)

            # Convertir a dict
            segments = [seg.to_dict() for seg in pending]

            return jsonify({
                'success': True,
                'segments': segments,
                'count': len(segments)
            })

        except Exception as e:
            logger.error(f"[API] Error obteniendo cola: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/queue/next', methods=['GET'])
    def get_next():
        """Obtener siguiente segmento pendiente"""
        try:
            segment = queue.get_next_pending()

            if segment:
                return jsonify({
                    'success': True,
                    'segment': segment.to_dict()
                })
            else:
                return jsonify({
                    'success': True,
                    'segment': None,
                    'message': 'No hay segmentos pendientes'
                })

        except Exception as e:
            logger.error(f"[API] Error obteniendo siguiente: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/stats', methods=['GET'])
    def get_stats():
        """Obtener estadisticas de la cola"""
        try:
            stats = queue.get_stats()

            return jsonify({
                'success': True,
                'stats': stats
            })

        except Exception as e:
            logger.error(f"[API] Error obteniendo stats: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/review/submit', methods=['POST'])
    def submit_review():
        """
        Enviar revision de un segmento

        Body JSON:
            segment_id: ID del segmento
            corrected_text: Texto corregido
            user_id: Usuario que revisa
        """
        try:
            data = request.json

            if not data:
                return jsonify({
                    'success': False,
                    'error': 'No data provided'
                }), 400

            segment_id = data.get('segment_id')
            corrected_text = data.get('corrected_text')
            user_id = data.get('user_id', 'anonymous')

            if not segment_id or not corrected_text:
                return jsonify({
                    'success': False,
                    'error': 'segment_id and corrected_text required'
                }), 400

            # Marcar como revisado
            success = queue.mark_as_reviewed(
                segment_id=segment_id,
                corrected_text=corrected_text,
                reviewed_by=user_id
            )

            if success:
                return jsonify({
                    'success': True,
                    'message': 'Revision guardada exitosamente'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'No se pudo guardar la revision'
                }), 400

        except Exception as e:
            logger.error(f"[API] Error enviando revision: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/audio/<path:filename>', methods=['GET'])
    def get_audio(filename):
        """
        Servir archivo de audio

        URL params:
            start: Tiempo de inicio (opcional)
            end: Tiempo de fin (opcional)
        """
        try:
            # Extraer directorio del filename
            audio_dir = os.path.dirname(filename)
            audio_file = os.path.basename(filename)

            if not audio_dir:
                audio_dir = './audio'

            return send_from_directory(audio_dir, audio_file)

        except Exception as e:
            logger.error(f"[API] Error sirviendo audio: {e}")
            return jsonify({
                'success': False,
                'error': 'Audio no encontrado'
            }), 404

    @app.route('/api/segment/<segment_id>', methods=['GET'])
    def get_segment(segment_id):
        """Obtener informacion de un segmento especifico"""
        try:
            segment = queue.get_segment_by_id(segment_id)

            if segment:
                return jsonify({
                    'success': True,
                    'segment': segment.to_dict()
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Segmento no encontrado'
                }), 404

        except Exception as e:
            logger.error(f"[API] Error obteniendo segmento: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/queue/clear-reviewed', methods=['POST'])
    def clear_reviewed():
        """Limpiar segmentos ya revisados"""
        try:
            removed = queue.clear_reviewed()

            return jsonify({
                'success': True,
                'removed': removed,
                'message': f'{removed} segmentos eliminados'
            })

        except Exception as e:
            logger.error(f"[API] Error limpiando cola: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/add-segment', methods=['POST'])
    def add_segment():
        """
        Agregar segmento manualmente a la cola

        Body JSON:
            transcription_id, audio_path, start_time, end_time,
            text, confidence, flagged_reason, metadata
        """
        try:
            data = request.json

            required = ['transcription_id', 'audio_path', 'start_time',
                       'end_time', 'text', 'confidence', 'flagged_reason']

            for field in required:
                if field not in data:
                    return jsonify({
                        'success': False,
                        'error': f'Campo requerido: {field}'
                    }), 400

            segment = queue.add_segment(
                transcription_id=data['transcription_id'],
                audio_path=data['audio_path'],
                start_time=float(data['start_time']),
                end_time=float(data['end_time']),
                text=data['text'],
                confidence=float(data['confidence']),
                flagged_reason=data['flagged_reason'],
                metadata=data.get('metadata', {})
            )

            return jsonify({
                'success': True,
                'segment': segment.to_dict(),
                'message': 'Segmento agregado a la cola'
            })

        except Exception as e:
            logger.error(f"[API] Error agregando segmento: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    logger.info(f"[API] Review API creada en puerto {port}")

    return app


def run_review_server(
    queue_file: str = "./review_queue.json",
    port: int = 5050,
    host: str = '0.0.0.0',
    debug: bool = False
):
    """
    Ejecutar servidor de revision

    Args:
        queue_file: Path al archivo de cola
        port: Puerto del servidor
        host: Host (0.0.0.0 para acceso externo)
        debug: Modo debug de Flask
    """
    app = create_review_api(queue_file, port)

    logger.info(f"\n{'='*70}")
    logger.info(f"Review UI Server")
    logger.info(f"{'='*70}")
    logger.info(f"  URL: http://localhost:{port}")
    logger.info(f"  Queue file: {queue_file}")
    logger.info(f"{'='*70}\n")

    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    # Ejecutar servidor standalone
    run_review_server(debug=True)
