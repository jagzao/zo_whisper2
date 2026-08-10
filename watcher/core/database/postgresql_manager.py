import os
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import threading
import structlog
from contextlib import contextmanager

logger = structlog.get_logger("postgresql_manager")

@dataclass
class TranscriptionJob:
    """PostgreSQL version of TranscriptionJob with enhanced fields"""
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
    
    # Enhanced fields for PostgreSQL
    transcription_model: Optional[str] = None
    transcription_language: Optional[str] = None
    transcription_confidence: Optional[float] = None
    word_count: Optional[int] = None
    audio_duration_seconds: Optional[float] = None
    quality_score: Optional[float] = None
    
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
        datetime_fields = ['created_at', 'started_at', 'completed_at']
        for field in datetime_fields:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
        
        if data.get('metadata') and isinstance(data['metadata'], str):
            data['metadata'] = json.loads(data['metadata'])
        
        return cls(**data)

class PostgreSQLManager:
    """PostgreSQL database manager with connection pooling and advanced features"""
    
    def __init__(self, 
                 host: str = "localhost",
                 port: int = 5432,
                 database: str = "whisper_transcription",
                 user: str = "whisper_user",
                 password: str = "whisper_password",
                 min_connections: int = 1,
                 max_connections: int = 10):
        
        self.connection_params = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password
        }
        
        self.min_connections = min_connections
        self.max_connections = max_connections
        self._pool = None
        self._lock = threading.Lock()
        
        self._init_connection_pool()
        self._init_database()
    
    def _init_connection_pool(self):
        """Initialize PostgreSQL connection pool"""
        try:
            self._pool = ThreadedConnectionPool(
                self.min_connections,
                self.max_connections,
                **self.connection_params
            )
            logger.info("PostgreSQL connection pool initialized", 
                       min_connections=self.min_connections,
                       max_connections=self.max_connections)
        except Exception as e:
            logger.error("Failed to initialize PostgreSQL connection pool", error=str(e))
            raise
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool"""
        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                self._pool.putconn(conn)
    
    def _init_database(self):
        """Initialize database with required tables and indexes"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor()
                
                # Create transcription_jobs table with enhanced fields
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS transcription_jobs (
                        id VARCHAR(255) PRIMARY KEY,
                        file_path TEXT NOT NULL,
                        project_name VARCHAR(255) NOT NULL,
                        file_name VARCHAR(255) NOT NULL,
                        status VARCHAR(50) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        started_at TIMESTAMP WITH TIME ZONE,
                        completed_at TIMESTAMP WITH TIME ZONE,
                        file_size_bytes BIGINT,
                        processing_time_seconds REAL,
                        error_message TEXT,
                        transcription_path TEXT,
                        summary_path TEXT,
                        file_hash VARCHAR(64),
                        metadata JSONB,
                        transcription_model VARCHAR(100),
                        transcription_language VARCHAR(10),
                        transcription_confidence REAL,
                        word_count INTEGER,
                        audio_duration_seconds REAL,
                        quality_score REAL
                    )
                """)
                
                # Create processing_stats table with more detailed metrics
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS processing_stats (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                        files_processed INTEGER,
                        files_failed INTEGER,
                        average_processing_time REAL,
                        queue_size INTEGER,
                        system_memory_mb REAL,
                        system_cpu_percent REAL,
                        disk_free_gb REAL,
                        active_workers INTEGER,
                        total_processing_time REAL,
                        average_quality_score REAL
                    )
                """)
                
                # Create project_stats materialized view for fast analytics
                cursor.execute("""
                    CREATE MATERIALIZED VIEW IF NOT EXISTS project_stats AS
                    SELECT 
                        project_name,
                        COUNT(*) as total_jobs,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_jobs,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_jobs,
                        AVG(processing_time_seconds) as avg_processing_time,
                        SUM(file_size_bytes) as total_file_size,
                        AVG(quality_score) as avg_quality_score,
                        MAX(created_at) as last_activity
                    FROM transcription_jobs 
                    GROUP BY project_name
                """)
                
                # Create indexes for better performance
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON transcription_jobs(status)",
                    "CREATE INDEX IF NOT EXISTS idx_jobs_created ON transcription_jobs(created_at DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_jobs_project ON transcription_jobs(project_name)",
                    "CREATE INDEX IF NOT EXISTS idx_jobs_hash ON transcription_jobs(file_hash)",
                    "CREATE INDEX IF NOT EXISTS idx_jobs_status_project ON transcription_jobs(status, project_name)",
                    "CREATE INDEX IF NOT EXISTS idx_stats_timestamp ON processing_stats(timestamp DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_jobs_metadata_gin ON transcription_jobs USING GIN(metadata)",
                ]
                
                for index_sql in indexes:
                    cursor.execute(index_sql)
                
                conn.commit()
                logger.info("PostgreSQL database initialized successfully")
                
            except Exception as e:
                conn.rollback()
                logger.error("Error initializing PostgreSQL database", error=str(e))
                raise
    
    def create_job(self, job: TranscriptionJob) -> bool:
        """Create a new transcription job"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor()
                
                job_data = job.to_dict()
                columns = list(job_data.keys())
                placeholders = ['%s' for _ in columns]
                values = list(job_data.values())
                
                cursor.execute(
                    f"INSERT INTO transcription_jobs ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                    values
                )
                conn.commit()
                
                logger.info("Job created in PostgreSQL", job_id=job.id, file_path=job.file_path)
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error("Error creating job in PostgreSQL", job_id=job.id, error=str(e))
                return False
    
    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing job"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor()
                
                # Convert datetime objects to ISO strings
                for key, value in updates.items():
                    if isinstance(value, datetime):
                        updates[key] = value.isoformat()
                    elif key == 'metadata' and isinstance(value, dict):
                        updates[key] = json.dumps(value)
                
                set_clause = ', '.join([f"{key} = %s" for key in updates.keys()])
                values = list(updates.values()) + [job_id]
                
                cursor.execute(
                    f"UPDATE transcription_jobs SET {set_clause} WHERE id = %s",
                    values
                )
                conn.commit()
                
                if cursor.rowcount == 0:
                    logger.warning("Job not found for update", job_id=job_id)
                    return False
                
                logger.info("Job updated in PostgreSQL", job_id=job_id, updates=list(updates.keys()))
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error("Error updating job in PostgreSQL", job_id=job_id, error=str(e))
                return False
    
    def get_job(self, job_id: str) -> Optional[TranscriptionJob]:
        """Get a job by ID"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                
                cursor.execute("SELECT * FROM transcription_jobs WHERE id = %s", (job_id,))
                row = cursor.fetchone()
                
                if row:
                    return TranscriptionJob.from_dict(dict(row))
                return None
                
            except Exception as e:
                logger.error("Error getting job from PostgreSQL", job_id=job_id, error=str(e))
                return None
    
    def get_jobs_by_status(self, status: str, limit: int = 100) -> List[TranscriptionJob]:
        """Get jobs by status with pagination"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                
                cursor.execute(
                    "SELECT * FROM transcription_jobs WHERE status = %s ORDER BY created_at DESC LIMIT %s",
                    (status, limit)
                )
                rows = cursor.fetchall()
                
                return [TranscriptionJob.from_dict(dict(row)) for row in rows]
                
            except Exception as e:
                logger.error("Error getting jobs by status from PostgreSQL", status=status, error=str(e))
                return []
    
    def get_recent_jobs(self, limit: int = 50) -> List[TranscriptionJob]:
        """Get recent jobs"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                
                cursor.execute(
                    "SELECT * FROM transcription_jobs ORDER BY created_at DESC LIMIT %s",
                    (limit,)
                )
                rows = cursor.fetchall()
                
                return [TranscriptionJob.from_dict(dict(row)) for row in rows]
                
            except Exception as e:
                logger.error("Error getting recent jobs from PostgreSQL", error=str(e))
                return []
    
    def get_jobs_by_project(self, project_name: str, limit: int = 100) -> List[TranscriptionJob]:
        """Get jobs by project name"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                
                cursor.execute(
                    "SELECT * FROM transcription_jobs WHERE project_name = %s ORDER BY created_at DESC LIMIT %s",
                    (project_name, limit)
                )
                rows = cursor.fetchall()
                
                return [TranscriptionJob.from_dict(dict(row)) for row in rows]
                
            except Exception as e:
                logger.error("Error getting jobs by project from PostgreSQL", project_name=project_name, error=str(e))
                return []
    
    def check_duplicate_file(self, file_hash: str) -> Optional[TranscriptionJob]:
        """Check if a file with the same hash has been processed"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                
                cursor.execute(
                    "SELECT * FROM transcription_jobs WHERE file_hash = %s AND status = 'completed' ORDER BY created_at DESC LIMIT 1",
                    (file_hash,)
                )
                row = cursor.fetchone()
                
                if row:
                    return TranscriptionJob.from_dict(dict(row))
                return None
                
            except Exception as e:
                logger.error("Error checking duplicate file in PostgreSQL", file_hash=file_hash, error=str(e))
                return None
    
    def get_processing_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Get advanced processing statistics"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                
                # Calculate date range
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days)
                
                # Get comprehensive job statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_jobs,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_jobs,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_jobs,
                        COUNT(CASE WHEN status = 'processing' THEN 1 END) as processing_jobs,
                        COUNT(CASE WHEN status = 'queued' THEN 1 END) as queued_jobs,
                        AVG(CASE WHEN processing_time_seconds IS NOT NULL THEN processing_time_seconds END) as avg_processing_time,
                        MAX(processing_time_seconds) as max_processing_time,
                        MIN(processing_time_seconds) as min_processing_time,
                        SUM(CASE WHEN file_size_bytes IS NOT NULL THEN file_size_bytes END) as total_size_bytes,
                        AVG(quality_score) as avg_quality_score,
                        AVG(transcription_confidence) as avg_transcription_confidence,
                        SUM(word_count) as total_words,
                        SUM(audio_duration_seconds) as total_audio_duration
                    FROM transcription_jobs 
                    WHERE created_at >= %s
                """, (start_date,))
                
                job_stats = cursor.fetchone()
                
                # Get project breakdown with enhanced metrics
                cursor.execute("""
                    SELECT 
                        project_name,
                        COUNT(*) as job_count,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_count,
                        AVG(quality_score) as avg_quality,
                        AVG(processing_time_seconds) as avg_processing_time,
                        SUM(file_size_bytes) as total_size
                    FROM transcription_jobs 
                    WHERE created_at >= %s
                    GROUP BY project_name
                    ORDER BY job_count DESC
                """, (start_date,))
                
                project_stats = cursor.fetchall()
                
                # Get quality trends over time
                cursor.execute("""
                    SELECT 
                        DATE_TRUNC('day', created_at) as date,
                        AVG(quality_score) as avg_quality,
                        COUNT(*) as job_count
                    FROM transcription_jobs 
                    WHERE created_at >= %s AND quality_score IS NOT NULL
                    GROUP BY DATE_TRUNC('day', created_at)
                    ORDER BY date DESC
                """, (start_date,))
                
                quality_trends = cursor.fetchall()
                
                return {
                    "period_days": days,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "total_jobs": job_stats["total_jobs"] or 0,
                    "completed_jobs": job_stats["completed_jobs"] or 0,
                    "failed_jobs": job_stats["failed_jobs"] or 0,
                    "processing_jobs": job_stats["processing_jobs"] or 0,
                    "queued_jobs": job_stats["queued_jobs"] or 0,
                    "success_rate": ((job_stats["completed_jobs"] or 0) / (job_stats["total_jobs"] or 1)) * 100,
                    "average_processing_time": round(job_stats["avg_processing_time"] or 0, 2),
                    "max_processing_time": round(job_stats["max_processing_time"] or 0, 2),
                    "min_processing_time": round(job_stats["min_processing_time"] or 0, 2),
                    "total_size_mb": round((job_stats["total_size_bytes"] or 0) / (1024**2), 2),
                    "average_quality_score": round(job_stats["avg_quality_score"] or 0, 2),
                    "average_transcription_confidence": round(job_stats["avg_transcription_confidence"] or 0, 2),
                    "total_words_transcribed": job_stats["total_words"] or 0,
                    "total_audio_hours": round((job_stats["total_audio_duration"] or 0) / 3600, 2),
                    "projects": [
                        {
                            "name": row["project_name"],
                            "total_jobs": row["job_count"],
                            "completed_jobs": row["completed_count"],
                            "success_rate": (row["completed_count"] / row["job_count"]) * 100,
                            "average_quality": round(row["avg_quality"] or 0, 2),
                            "average_processing_time": round(row["avg_processing_time"] or 0, 2),
                            "total_size_mb": round((row["total_size"] or 0) / (1024**2), 2)
                        }
                        for row in project_stats
                    ],
                    "quality_trends": [
                        {
                            "date": row["date"].isoformat(),
                            "average_quality": round(row["avg_quality"] or 0, 2),
                            "job_count": row["job_count"]
                        }
                        for row in quality_trends
                    ]
                }
                
            except Exception as e:
                logger.error("Error getting processing statistics from PostgreSQL", error=str(e))
                return {"error": str(e)}
    
    def cleanup_old_jobs(self, days_to_keep: int = 90) -> int:
        """Clean up old completed jobs"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor()
                
                cutoff_date = datetime.now() - timedelta(days=days_to_keep)
                
                cursor.execute("""
                    DELETE FROM transcription_jobs 
                    WHERE status = 'completed' AND completed_at < %s
                """, (cutoff_date,))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                # Refresh materialized view
                cursor.execute("REFRESH MATERIALIZED VIEW project_stats")
                conn.commit()
                
                logger.info("Cleaned up old jobs from PostgreSQL", 
                           deleted_count=deleted_count, 
                           days_to_keep=days_to_keep)
                return deleted_count
                
            except Exception as e:
                conn.rollback()
                logger.error("Error cleaning up old jobs from PostgreSQL", error=str(e))
                return 0
    
    def get_database_size(self) -> Dict[str, Any]:
        """Get database size information"""
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                
                # Get database size
                cursor.execute("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as db_size,
                           pg_database_size(current_database()) as db_size_bytes
                """)
                db_info = cursor.fetchone()
                
                # Get table counts
                cursor.execute("SELECT COUNT(*) FROM transcription_jobs")
                jobs_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM processing_stats")
                stats_count = cursor.fetchone()[0]
                
                # Get table sizes
                cursor.execute("""
                    SELECT 
                        schemaname,
                        tablename,
                        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                        pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
                    FROM pg_tables 
                    WHERE schemaname = 'public' 
                    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                """)
                table_sizes = cursor.fetchall()
                
                return {
                    "database_size": db_info["db_size"],
                    "database_size_bytes": db_info["db_size_bytes"],
                    "size_mb": round(db_info["db_size_bytes"] / (1024**2), 2),
                    "jobs_count": jobs_count,
                    "stats_count": stats_count,
                    "table_sizes": [dict(row) for row in table_sizes],
                    "connection_info": {
                        "host": self.connection_params["host"],
                        "port": self.connection_params["port"],
                        "database": self.connection_params["database"],
                        "pool_min": self.min_connections,
                        "pool_max": self.max_connections
                    }
                }
                
            except Exception as e:
                logger.error("Error getting database size from PostgreSQL", error=str(e))
                return {"error": str(e)}
    
    def close(self):
        """Close all connections in the pool"""
        if self._pool:
            self._pool.closeall()
            logger.info("PostgreSQL connection pool closed")

# Global PostgreSQL manager instance (will be initialized with config)
postgresql_manager: Optional[PostgreSQLManager] = None