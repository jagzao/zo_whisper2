import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict
import threading
import structlog

logger = structlog.get_logger("database")

@dataclass
class TranscriptionJob:
    id: str
    file_path: str
    project_name: str
    file_name: str
    status: str  # queued, processing, completed, failed
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    file_size_bytes: Optional[int] = None
    processing_time_seconds: Optional[float] = None
    error_message: Optional[str] = None
    transcription_path: Optional[str] = None
    summary_path: Optional[str] = None
    file_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Convert datetime objects to ISO strings
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
        if self.metadata:
            data['metadata'] = json.dumps(self.metadata)
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TranscriptionJob':
        # Convert ISO strings back to datetime objects
        for key in ['created_at', 'started_at', 'completed_at']:
            if data.get(key):
                data[key] = datetime.fromisoformat(data[key])
        
        if data.get('metadata') and isinstance(data['metadata'], str):
            data['metadata'] = json.loads(data['metadata'])
        
        return cls(**data)

@dataclass 
class ProcessingStats:
    id: int
    timestamp: datetime
    files_processed: int
    files_failed: int
    average_processing_time: float
    queue_size: int
    system_memory_mb: float
    system_cpu_percent: float
    disk_free_gb: float

class DatabaseManager:
    """SQLite database manager for persistent storage"""
    
    def __init__(self, db_path: str = "/app/data/transcription.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize database with required tables"""
        with self._lock:
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    
                    # Create transcription_jobs table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS transcription_jobs (
                            id TEXT PRIMARY KEY,
                            file_path TEXT NOT NULL,
                            project_name TEXT NOT NULL,
                            file_name TEXT NOT NULL,
                            status TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            started_at TEXT,
                            completed_at TEXT,
                            file_size_bytes INTEGER,
                            processing_time_seconds REAL,
                            error_message TEXT,
                            transcription_path TEXT,
                            summary_path TEXT,
                            file_hash TEXT,
                            metadata TEXT
                        )
                    """)
                    
                    # Create processing_stats table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS processing_stats (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp TEXT NOT NULL,
                            files_processed INTEGER,
                            files_failed INTEGER,
                            average_processing_time REAL,
                            queue_size INTEGER,
                            system_memory_mb REAL,
                            system_cpu_percent REAL,
                            disk_free_gb REAL
                        )
                    """)
                    
                    # Create indexes for better performance
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON transcription_jobs(status)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON transcription_jobs(created_at)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_project ON transcription_jobs(project_name)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_hash ON transcription_jobs(file_hash)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stats_timestamp ON processing_stats(timestamp)")
                    
                    conn.commit()
                    
                logger.info("Database initialized successfully", db_path=str(self.db_path))
                
            except Exception as e:
                logger.error("Error initializing database", error=str(e), db_path=str(self.db_path))
                raise
    
    def create_job(self, job: TranscriptionJob) -> bool:
        """Create a new transcription job"""
        with self._lock:
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    
                    job_data = job.to_dict()
                    columns = list(job_data.keys())
                    placeholders = ['?' for _ in columns]
                    values = list(job_data.values())
                    
                    cursor.execute(
                        f"INSERT INTO transcription_jobs ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                        values
                    )
                    conn.commit()
                    
                logger.info("Job created in database", job_id=job.id, file_path=job.file_path)
                return True
                
            except Exception as e:
                logger.error("Error creating job", job_id=job.id, error=str(e))
                return False
    
    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing job"""
        with self._lock:
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    
                    # Convert datetime objects to ISO strings
                    for key, value in updates.items():
                        if isinstance(value, datetime):
                            updates[key] = value.isoformat()
                        elif key == 'metadata' and isinstance(value, dict):
                            updates[key] = json.dumps(value)
                    
                    set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
                    values = list(updates.values()) + [job_id]
                    
                    cursor.execute(
                        f"UPDATE transcription_jobs SET {set_clause} WHERE id = ?",
                        values
                    )
                    conn.commit()
                    
                    if cursor.rowcount == 0:
                        logger.warning("Job not found for update", job_id=job_id)
                        return False
                    
                logger.info("Job updated in database", job_id=job_id, updates=list(updates.keys()))
                return True
                
            except Exception as e:
                logger.error("Error updating job", job_id=job_id, error=str(e))
                return False
    
    def get_job(self, job_id: str) -> Optional[TranscriptionJob]:
        """Get a job by ID"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM transcription_jobs WHERE id = ?", (job_id,))
                row = cursor.fetchone()
                
                if row:
                    return TranscriptionJob.from_dict(dict(row))
                return None
                
        except Exception as e:
            logger.error("Error getting job", job_id=job_id, error=str(e))
            return None
    
    def get_jobs_by_status(self, status: str, limit: int = 100) -> List[TranscriptionJob]:
        """Get jobs by status"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT * FROM transcription_jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                )
                rows = cursor.fetchall()
                
                return [TranscriptionJob.from_dict(dict(row)) for row in rows]
                
        except Exception as e:
            logger.error("Error getting jobs by status", status=status, error=str(e))
            return []
    
    def get_recent_jobs(self, limit: int = 50) -> List[TranscriptionJob]:
        """Get recent jobs"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT * FROM transcription_jobs ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
                rows = cursor.fetchall()
                
                return [TranscriptionJob.from_dict(dict(row)) for row in rows]
                
        except Exception as e:
            logger.error("Error getting recent jobs", error=str(e))
            return []
    
    def get_jobs_by_project(self, project_name: str, limit: int = 100) -> List[TranscriptionJob]:
        """Get jobs by project name"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT * FROM transcription_jobs WHERE project_name = ? ORDER BY created_at DESC LIMIT ?",
                    (project_name, limit)
                )
                rows = cursor.fetchall()
                
                return [TranscriptionJob.from_dict(dict(row)) for row in rows]
                
        except Exception as e:
            logger.error("Error getting jobs by project", project_name=project_name, error=str(e))
            return []
    
    def check_duplicate_file(self, file_hash: str) -> Optional[TranscriptionJob]:
        """Check if a file with the same hash has been processed"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT * FROM transcription_jobs WHERE file_hash = ? AND status = 'completed'",
                    (file_hash,)
                )
                row = cursor.fetchone()
                
                if row:
                    return TranscriptionJob.from_dict(dict(row))
                return None
                
        except Exception as e:
            logger.error("Error checking duplicate file", file_hash=file_hash, error=str(e))
            return None
    
    def get_processing_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Get processing statistics for the last N days"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Calculate date range
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days)
                
                # Get job statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_jobs,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_jobs,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_jobs,
                        AVG(CASE WHEN processing_time_seconds IS NOT NULL THEN processing_time_seconds END) as avg_processing_time,
                        SUM(CASE WHEN file_size_bytes IS NOT NULL THEN file_size_bytes END) as total_size_bytes
                    FROM transcription_jobs 
                    WHERE created_at >= ?
                """, (start_date.isoformat(),))
                
                job_stats = cursor.fetchone()
                
                # Get project breakdown
                cursor.execute("""
                    SELECT 
                        project_name,
                        COUNT(*) as job_count,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_count
                    FROM transcription_jobs 
                    WHERE created_at >= ?
                    GROUP BY project_name
                    ORDER BY job_count DESC
                """, (start_date.isoformat(),))
                
                project_stats = cursor.fetchall()
                
                return {
                    "period_days": days,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "total_jobs": job_stats[0] or 0,
                    "completed_jobs": job_stats[1] or 0,
                    "failed_jobs": job_stats[2] or 0,
                    "success_rate": ((job_stats[1] or 0) / (job_stats[0] or 1)) * 100,
                    "average_processing_time": round(job_stats[3] or 0, 2),
                    "total_size_mb": round((job_stats[4] or 0) / (1024**2), 2),
                    "projects": [
                        {
                            "name": row[0],
                            "total_jobs": row[1],
                            "completed_jobs": row[2],
                            "success_rate": (row[2] / row[1]) * 100
                        }
                        for row in project_stats
                    ]
                }
                
        except Exception as e:
            logger.error("Error getting processing statistics", error=str(e))
            return {"error": str(e)}
    
    def record_stats(self, stats: ProcessingStats) -> bool:
        """Record processing statistics"""
        with self._lock:
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT INTO processing_stats 
                        (timestamp, files_processed, files_failed, average_processing_time, 
                         queue_size, system_memory_mb, system_cpu_percent, disk_free_gb)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        stats.timestamp.isoformat(),
                        stats.files_processed,
                        stats.files_failed,
                        stats.average_processing_time,
                        stats.queue_size,
                        stats.system_memory_mb,
                        stats.system_cpu_percent,
                        stats.disk_free_gb
                    ))
                    conn.commit()
                    
                return True
                
            except Exception as e:
                logger.error("Error recording stats", error=str(e))
                return False
    
    def cleanup_old_jobs(self, days_to_keep: int = 90) -> int:
        """Clean up old completed jobs"""
        with self._lock:
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    
                    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
                    
                    cursor.execute("""
                        DELETE FROM transcription_jobs 
                        WHERE status = 'completed' AND completed_at < ?
                    """, (cutoff_date.isoformat(),))
                    
                    deleted_count = cursor.rowcount
                    conn.commit()
                    
                    logger.info("Cleaned up old jobs", deleted_count=deleted_count, days_to_keep=days_to_keep)
                    return deleted_count
                    
            except Exception as e:
                logger.error("Error cleaning up old jobs", error=str(e))
                return 0
    
    def get_database_size(self) -> Dict[str, Any]:
        """Get database size information"""
        try:
            db_size_bytes = self.db_path.stat().st_size
            
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Get table counts
                cursor.execute("SELECT COUNT(*) FROM transcription_jobs")
                jobs_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM processing_stats")
                stats_count = cursor.fetchone()[0]
                
            return {
                "size_bytes": db_size_bytes,
                "size_mb": round(db_size_bytes / (1024**2), 2),
                "jobs_count": jobs_count,
                "stats_count": stats_count,
                "path": str(self.db_path)
            }
            
        except Exception as e:
            logger.error("Error getting database size", error=str(e))
            return {"error": str(e)}

# Global database manager instance
db_manager: Optional[DatabaseManager] = None

from datetime import timedelta