from flask import Flask, render_template, jsonify, request
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import structlog

# Add parent directory to path to import core modules
sys.path.append(str(Path(__file__).parent.parent))

from core.database.models import DatabaseManager
from core.monitoring.logger_config import app_metrics
from core.monitoring.health_check import health_checker
from core.file_manager import file_manager
from core.performance.queue_manager import queue_manager

app = Flask(__name__)
logger = structlog.get_logger("dashboard")

# Initialize database manager
db_manager = DatabaseManager()

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/overview')
def api_overview():
    """Get overview statistics"""
    try:
        # Get basic statistics
        stats = db_manager.get_processing_statistics(days=7)
        
        # Get recent jobs
        recent_jobs = db_manager.get_recent_jobs(limit=10)
        recent_jobs_data = []
        for job in recent_jobs:
            recent_jobs_data.append({
                'id': job.id,
                'file_name': job.file_name,
                'project_name': job.project_name,
                'status': job.status,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'processing_time': job.processing_time_seconds
            })
        
        # Get application metrics
        app_metrics_summary = app_metrics.get_summary()
        
        # Get health status
        health_status = health_checker.get_overall_health()
        
        return jsonify({
            'processing_stats': stats,
            'recent_jobs': recent_jobs_data,
            'app_metrics': app_metrics_summary,
            'health_status': health_status,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error("Error getting overview", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs')
def api_jobs():
    """Get jobs with pagination and filtering"""
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 25))
        status_filter = request.args.get('status', '')
        project_filter = request.args.get('project', '')
        
        # Get jobs based on filters
        if status_filter:
            jobs = db_manager.get_jobs_by_status(status_filter, limit=per_page * 5)
        elif project_filter:
            jobs = db_manager.get_jobs_by_project(project_filter, limit=per_page * 5)
        else:
            jobs = db_manager.get_recent_jobs(limit=per_page * 5)
        
        # Convert to JSON-serializable format
        jobs_data = []
        for job in jobs:
            jobs_data.append({
                'id': job.id,
                'file_name': job.file_name,
                'project_name': job.project_name,
                'status': job.status,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'processing_time': job.processing_time_seconds,
                'file_size_mb': round(job.file_size_bytes / (1024**2), 2) if job.file_size_bytes else None,
                'error_message': job.error_message
            })
        
        # Pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_jobs = jobs_data[start_idx:end_idx]
        
        return jsonify({
            'jobs': paginated_jobs,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': len(jobs_data),
                'has_next': end_idx < len(jobs_data),
                'has_prev': page > 1
            }
        })
        
    except Exception as e:
        logger.error("Error getting jobs", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/job/<job_id>')
def api_job_detail(job_id):
    """Get detailed information about a specific job"""
    try:
        job = db_manager.get_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        job_data = {
            'id': job.id,
            'file_path': job.file_path,
            'file_name': job.file_name,
            'project_name': job.project_name,
            'status': job.status,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'processing_time': job.processing_time_seconds,
            'file_size_bytes': job.file_size_bytes,
            'file_size_mb': round(job.file_size_bytes / (1024**2), 2) if job.file_size_bytes else None,
            'error_message': job.error_message,
            'transcription_path': job.transcription_path,
            'summary_path': job.summary_path,
            'file_hash': job.file_hash,
            'metadata': job.metadata
        }
        
        return jsonify(job_data)
        
    except Exception as e:
        logger.error("Error getting job detail", job_id=job_id, error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def api_health():
    """Get detailed health information"""
    try:
        health_info = health_checker.get_detailed_health()
        return jsonify(health_info)
        
    except Exception as e:
        logger.error("Error getting health info", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/metrics')
def api_metrics():
    """Get application metrics"""
    try:
        metrics = app_metrics.get_summary()
        health = app_metrics.get_health_status()
        
        return jsonify({
            'metrics': metrics,
            'health': health,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error("Error getting metrics", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue')
def api_queue_status():
    """Get queue status (if Redis is available)"""
    try:
        if queue_manager and queue_manager.is_connected():
            stats = queue_manager.get_queue_stats()
            recent_jobs = queue_manager.get_recent_jobs(limit=20)
            
            recent_jobs_data = []
            for job in recent_jobs:
                recent_jobs_data.append({
                    'id': job.id,
                    'file_path': job.file_path,
                    'project_name': job.project_name,
                    'status': job.status.value,
                    'created_at': job.created_at.isoformat(),
                    'started_at': job.started_at.isoformat() if job.started_at else None,
                    'error_message': job.error_message,
                    'retry_count': job.retry_count
                })
            
            return jsonify({
                'connected': True,
                'stats': stats,
                'recent_jobs': recent_jobs_data
            })
        else:
            return jsonify({
                'connected': False,
                'message': 'Queue manager not connected (running in direct mode)'
            })
            
    except Exception as e:
        logger.error("Error getting queue status", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/stats')
def api_file_stats():
    """Get file system statistics"""
    try:
        # Directory paths to check
        directories = [
            ('/app/Videos', 'Videos'),
            ('/app/audio', 'Audio'),
            ('/app/CarpetaTranscripciones', 'Transcriptions')
        ]
        
        stats = {}
        for path, name in directories:
            if os.path.exists(path):
                dir_stats = file_manager.get_file_stats(path)
                stats[name] = dir_stats
        
        # Get disk space info
        disk_stats = {}
        for path, name in directories:
            if os.path.exists(path):
                disk_info = file_manager.check_disk_space(path)
                disk_stats[name] = disk_info
                break  # Only need one disk space check
        
        return jsonify({
            'directory_stats': stats,
            'disk_stats': disk_stats,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error("Error getting file stats", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects')
def api_projects():
    """Get project statistics"""
    try:
        stats = db_manager.get_processing_statistics(days=30)
        projects = stats.get('projects', [])
        
        # Get recent activity per project
        project_details = []
        for project in projects:
            recent_jobs = db_manager.get_jobs_by_project(project['name'], limit=5)
            
            project_info = {
                'name': project['name'],
                'total_jobs': project['total_jobs'],
                'completed_jobs': project['completed_jobs'],
                'success_rate': project['success_rate'],
                'recent_jobs': []
            }
            
            for job in recent_jobs:
                project_info['recent_jobs'].append({
                    'id': job.id,
                    'file_name': job.file_name,
                    'status': job.status,
                    'created_at': job.created_at.isoformat() if job.created_at else None
                })
            
            project_details.append(project_info)
        
        return jsonify({
            'projects': project_details,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error("Error getting project stats", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/database')
def api_database_info():
    """Get database information"""
    try:
        db_info = db_manager.get_database_size()
        return jsonify(db_info)
        
    except Exception as e:
        logger.error("Error getting database info", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Start health checker
    health_checker.start()
    
    # Run Flask app
    app.run(host='0.0.0.0', port=8080, debug=False)