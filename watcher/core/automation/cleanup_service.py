import os
import threading
import time
import schedule
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
import structlog

logger = structlog.get_logger("cleanup_service")

class AutomatedCleanupService:
    """Automated cleanup service for old files and data"""
    
    def __init__(self, 
                 file_retention_days: int = 30,
                 db_retention_days: int = 90,
                 temp_file_retention_hours: int = 24,
                 cleanup_interval_hours: int = 6):
        
        self.file_retention_days = file_retention_days
        self.db_retention_days = db_retention_days
        self.temp_file_retention_hours = temp_file_retention_hours
        self.cleanup_interval_hours = cleanup_interval_hours
        self._running = False
        self._thread = None
        
        # Directories to clean
        self.cleanup_directories = [
            "/app/audio",
            "/app/CarpetaTranscripciones", 
            "/app/logs",
            "/app/.whisper_cache"  # Whisper model cache
        ]
        
        # Temporary directories
        self.temp_directories = [
            "/app/api_uploads",
            "/tmp",
            "/app/temp_processing"
        ]
    
    def start(self):
        """Start the automated cleanup service"""
        if self._running:
            logger.warning("Cleanup service is already running")
            return
        
        self._running = True
        
        # Schedule cleanup tasks
        schedule.every(self.cleanup_interval_hours).hours.do(self._run_full_cleanup)
        schedule.every().day.at("02:00").do(self._run_database_cleanup)
        schedule.every().hour.do(self._run_temp_cleanup)
        
        # Start scheduler thread
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.name = "CleanupScheduler"
        self._thread.start()
        
        logger.info("Automated cleanup service started", 
                   file_retention_days=self.file_retention_days,
                   cleanup_interval_hours=self.cleanup_interval_hours)
    
    def stop(self):
        """Stop the cleanup service"""
        self._running = False
        schedule.clear()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Cleanup service stopped")
    
    def _scheduler_loop(self):
        """Main scheduler loop"""
        while self._running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error("Error in cleanup scheduler", error=str(e))
                time.sleep(60)
    
    def _run_full_cleanup(self):
        """Run full cleanup of old files"""
        logger.info("Starting full cleanup cycle")
        
        total_freed_mb = 0
        total_files_deleted = 0
        
        try:
            # Clean old processed files
            for directory in self.cleanup_directories:
                if Path(directory).exists():
                    freed_mb, files_deleted = self._cleanup_old_files(
                        directory, 
                        self.file_retention_days
                    )
                    total_freed_mb += freed_mb
                    total_files_deleted += files_deleted
            
            # Clean temporary files
            temp_freed_mb, temp_files_deleted = self._cleanup_temp_files()
            total_freed_mb += temp_freed_mb
            total_files_deleted += temp_files_deleted
            
            logger.info("Full cleanup completed",
                       files_deleted=total_files_deleted,
                       space_freed_mb=round(total_freed_mb, 2))
            
        except Exception as e:
            logger.error("Error during full cleanup", error=str(e))
    
    def _run_database_cleanup(self):
        """Run database cleanup"""
        try:
            from core.database.models import db_manager
            
            # Clean old completed jobs
            deleted_jobs = db_manager.cleanup_old_jobs(days_to_keep=self.db_retention_days)
            
            # Clean old processing stats (keep last 30 days)
            # This would need to be implemented in the database manager
            
            logger.info("Database cleanup completed", deleted_jobs=deleted_jobs)
            
        except Exception as e:
            logger.error("Error during database cleanup", error=str(e))
    
    def _run_temp_cleanup(self):
        """Run temporary files cleanup"""
        try:
            freed_mb, files_deleted = self._cleanup_temp_files()
            
            if files_deleted > 0:
                logger.info("Temp cleanup completed", 
                           files_deleted=files_deleted,
                           space_freed_mb=round(freed_mb, 2))
            
        except Exception as e:
            logger.error("Error during temp cleanup", error=str(e))
    
    def _cleanup_old_files(self, directory: str, retention_days: int) -> tuple[float, int]:
        """Clean files older than retention_days in specified directory"""
        directory_path = Path(directory)
        if not directory_path.exists():
            return 0.0, 0
        
        cutoff_time = datetime.now() - timedelta(days=retention_days)
        total_size = 0
        files_deleted = 0
        
        try:
            for file_path in directory_path.rglob('*'):
                if file_path.is_file():
                    try:
                        # Get file modification time
                        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        
                        if file_mtime < cutoff_time:
                            # Skip if file is currently being processed
                            if self._is_file_in_use(file_path):
                                continue
                            
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            
                            total_size += file_size
                            files_deleted += 1
                            
                            logger.debug("Deleted old file", 
                                       file_path=str(file_path),
                                       age_days=(datetime.now() - file_mtime).days)
                    
                    except (OSError, PermissionError) as e:
                        logger.warning("Could not delete file", 
                                     file_path=str(file_path), 
                                     error=str(e))
            
            # Clean empty directories
            self._cleanup_empty_directories(directory_path)
            
            return total_size / (1024 * 1024), files_deleted  # Convert to MB
            
        except Exception as e:
            logger.error("Error cleaning directory", directory=directory, error=str(e))
            return 0.0, 0
    
    def _cleanup_temp_files(self) -> tuple[float, int]:
        """Clean temporary files"""
        cutoff_time = datetime.now() - timedelta(hours=self.temp_file_retention_hours)
        total_size = 0
        files_deleted = 0
        
        for temp_dir in self.temp_directories:
            temp_path = Path(temp_dir)
            if not temp_path.exists():
                continue
            
            try:
                for file_path in temp_path.rglob('*'):
                    if file_path.is_file():
                        try:
                            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                            
                            if file_mtime < cutoff_time:
                                if self._is_file_in_use(file_path):
                                    continue
                                
                                file_size = file_path.stat().st_size
                                file_path.unlink()
                                
                                total_size += file_size
                                files_deleted += 1
                        
                        except (OSError, PermissionError):
                            continue  # Skip files we can't access
                
            except Exception as e:
                logger.warning("Error cleaning temp directory", directory=temp_dir, error=str(e))
        
        return total_size / (1024 * 1024), files_deleted
    
    def _cleanup_empty_directories(self, root_path: Path):
        """Remove empty directories recursively"""
        try:
            for dir_path in sorted(root_path.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                if dir_path.is_dir() and dir_path != root_path:
                    try:
                        if not any(dir_path.iterdir()):  # Directory is empty
                            dir_path.rmdir()
                            logger.debug("Removed empty directory", directory=str(dir_path))
                    except OSError:
                        continue  # Directory not empty or permission denied
        except Exception as e:
            logger.warning("Error cleaning empty directories", error=str(e))
    
    def _is_file_in_use(self, file_path: Path) -> bool:
        """Check if file is currently being used/processed"""
        try:
            # Try to open file exclusively - if it fails, file is in use
            with open(file_path, 'r+b'):
                pass
            return False
        except (OSError, PermissionError):
            return True
    
    def get_cleanup_stats(self) -> Dict[str, Any]:
        """Get cleanup statistics"""
        stats = {
            "service_running": self._running,
            "next_cleanup": None,
            "directories_monitored": len(self.cleanup_directories),
            "temp_directories_monitored": len(self.temp_directories),
            "retention_policy": {
                "files_days": self.file_retention_days,
                "database_days": self.db_retention_days,
                "temp_files_hours": self.temp_file_retention_hours
            }
        }
        
        # Get next scheduled cleanup time
        try:
            next_run = schedule.next_run()
            if next_run:
                stats["next_cleanup"] = next_run.isoformat()
        except:
            pass
        
        return stats
    
    def force_cleanup(self, target: str = "all") -> Dict[str, Any]:
        """Force immediate cleanup"""
        logger.info("Force cleanup triggered", target=target)
        
        results = {"target": target, "timestamp": datetime.now().isoformat()}
        
        try:
            if target in ["all", "files"]:
                self._run_full_cleanup()
                results["files_cleanup"] = "completed"
            
            if target in ["all", "database"]:
                self._run_database_cleanup()
                results["database_cleanup"] = "completed"
            
            if target in ["all", "temp"]:
                self._run_temp_cleanup()
                results["temp_cleanup"] = "completed"
            
            results["status"] = "success"
            
        except Exception as e:
            results["status"] = "error"
            results["error"] = str(e)
            logger.error("Force cleanup failed", target=target, error=str(e))
        
        return results

# Global cleanup service instance
cleanup_service = AutomatedCleanupService()