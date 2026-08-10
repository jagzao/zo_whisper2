#!/usr/bin/env python3
"""
Improved Watcher Service with all new features integrated
"""

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# Initialize structured logging first
from core.config import config, ConfigurationError
from core.monitoring.logger_config import StructuredLogger, app_metrics
from core.monitoring.health_check import health_checker
from core.database.models import DatabaseManager, TranscriptionJob
from core.file_manager import FileManager, FileValidationError
from core.performance.queue_manager import QueueManager, Job, JobStatus

# Initialize logger
try:
    logger_config = StructuredLogger(
        log_level=config.log_level,
        log_format=config.log_format,
        log_file=config.log_file_path
    )
    logger = logger_config.get_logger("watcher")
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    exit(1)

# Initialize global components
db_manager = DatabaseManager()
file_manager = FileManager(
    max_size_mb=config.max_file_size_mb,
    cleanup_temp=config.cleanup_temp_files
)

# Initialize queue manager if Redis is enabled
queue_manager = None
if config.enable_redis_queue:
    try:
        queue_manager = QueueManager(
            redis_url=config.redis_url,
            max_workers=config.max_concurrent_jobs
        )
        logger.info("Queue manager initialized", redis_connected=queue_manager.is_connected())
    except Exception as e:
        logger.warning("Failed to initialize queue manager", error=str(e))

def process_file_with_validation(file_path: str) -> bool:
    """
    Process a file with full validation and error handling
    """
    start_time = datetime.now()
    job_id = str(uuid.uuid4())
    
    try:
        # Step 1: Validate file
        logger.info("Starting file validation", file_path=file_path, job_id=job_id)
        
        try:
            validation_result = file_manager.validate_file(file_path)
        except FileValidationError as e:
            logger.error("File validation failed", file_path=file_path, error=str(e))
            app_metrics.record_error("file_validation", str(e), {"file_path": file_path})
            return False
        
        # Extract project and file info
        file_path_obj = Path(file_path)
        project_name = file_path_obj.parent.name if file_path_obj.parent.name != "Videos" else "Default"
        
        # Step 2: Check for duplicates
        existing_job = db_manager.check_duplicate_file(validation_result['hash'])
        if existing_job:
            logger.info("Duplicate file detected, skipping processing", 
                       file_path=file_path, 
                       existing_job_id=existing_job.id,
                       existing_status=existing_job.status)
            return True
        
        # Step 3: Create database job
        job = TranscriptionJob(
            id=job_id,
            file_path=file_path,
            project_name=project_name,
            file_name=validation_result['name'],
            status="queued",
            created_at=start_time,
            file_size_bytes=validation_result['size_bytes'],
            file_hash=validation_result['hash'],
            metadata={
                'is_video': validation_result['is_video'],
                'is_audio': validation_result['is_audio'],
                'mime_type': validation_result['mime_type']
            }
        )
        
        if not db_manager.create_job(job):
            logger.error("Failed to create database job", job_id=job_id)
            return False
        
        # Step 4: Process via queue or directly
        success = False
        if queue_manager and queue_manager.is_connected():
            # Use queue system
            queue_job = Job(
                id=job_id,
                task_type="transcription",
                file_path=file_path,
                project_name=project_name,
                created_at=start_time
            )
            success = queue_manager.enqueue_job(queue_job)
            logger.info("Job enqueued for processing", job_id=job_id)
        else:
            # Process directly
            success = process_transcription_job(job)
        
        # Record metrics
        processing_time = (datetime.now() - start_time).total_seconds()
        app_metrics.record_file_processed(file_path, processing_time, success)
        
        return success
        
    except Exception as e:
        logger.error("Unexpected error in file processing", 
                    file_path=file_path, 
                    job_id=job_id, 
                    error=str(e))
        app_metrics.record_error("file_processing", str(e), {"file_path": file_path})
        
        # Update job status if it was created
        try:
            db_manager.update_job(job_id, {
                "status": "failed",
                "completed_at": datetime.now(),
                "error_message": str(e)
            })
        except:
            pass  # Job might not exist yet
        
        return False

def process_transcription_job(job: TranscriptionJob) -> bool:
    """
    Process transcription job with full workflow
    """
    try:
        # Update job status
        db_manager.update_job(job.id, {
            "status": "processing",
            "started_at": datetime.now()
        })
        
        logger.info("Processing transcription job", job_id=job.id, file_path=job.file_path)
        
        # Import processing modules (avoid circular imports)
        from services.watcher_and_processor import process_video
        
        # Call existing processing logic
        process_video(job.file_path)
        
        # Update job as completed
        db_manager.update_job(job.id, {
            "status": "completed",
            "completed_at": datetime.now(),
            "processing_time_seconds": (datetime.now() - job.started_at).total_seconds() if job.started_at else None
        })
        
        logger.info("Job completed successfully", job_id=job.id)
        return True
        
    except Exception as e:
        logger.error("Error processing transcription job", job_id=job.id, error=str(e))
        
        # Update job as failed
        db_manager.update_job(job.id, {
            "status": "failed",
            "completed_at": datetime.now(),
            "error_message": str(e)
        })
        
        return False

def setup_queue_handlers():
    """Setup queue handlers if queue manager is available"""
    if queue_manager:
        def transcription_handler(file_path: str):
            """Handler for transcription tasks"""
            # Find the job in database
            jobs = db_manager.get_recent_jobs(limit=100)
            target_job = None
            for job in jobs:
                if job.file_path == file_path and job.status in ["queued", "processing"]:
                    target_job = job
                    break
            
            if target_job:
                process_transcription_job(target_job)
            else:
                logger.warning("Could not find job for file", file_path=file_path)
        
        queue_manager.register_handler("transcription", transcription_handler)
        
        if queue_manager.is_connected():
            queue_manager.start_workers()
            logger.info("Queue workers started", max_workers=config.max_concurrent_jobs)

def start_monitoring():
    """Start monitoring services"""
    try:
        # Start health checker
        health_checker.start()
        logger.info("Health checker started")
        
        # Log configuration summary
        config_summary = config.get_summary()
        logger.info("Service configuration", **config_summary)
        
        # Setup queue handlers
        setup_queue_handlers()
        
    except Exception as e:
        logger.error("Error starting monitoring", error=str(e))

def main():
    """Main service entry point"""
    try:
        logger.info("🟢 Improved Watcher Service starting...")
        
        # Start monitoring
        start_monitoring()
        
        # Check disk space
        for directory in ["/app/Videos", "/app/audio", "/app/CarpetaTranscripciones"]:
            if Path(directory).exists():
                disk_info = file_manager.check_disk_space(directory, required_mb=1000)
                if not disk_info.get('sufficient_space', False):
                    logger.warning("Low disk space detected", directory=directory, **disk_info)
        
        # Import and start file watching
        from services.watcher_and_processor import start_watcher
        
        # Override the process_video function with our improved version
        import services.watcher_and_processor as watcher_module
        watcher_module.process_video = lambda path: process_file_with_validation(path)
        
        logger.info("🎯 Starting file watcher with improved processing...")
        start_watcher()
        
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as e:
        logger.error("Fatal error in main service", error=str(e))
        raise
    finally:
        # Cleanup
        if queue_manager:
            queue_manager.stop_workers()
        health_checker.stop()
        logger.info("Service shutdown complete")

if __name__ == "__main__":
    main()