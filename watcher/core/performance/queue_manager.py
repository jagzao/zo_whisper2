import json
import redis
import logging
import threading
import time
from typing import Dict, List, Optional, Callable
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class JobStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class Job:
    id: str
    task_type: str
    file_path: str
    project_name: str
    created_at: datetime
    status: JobStatus = JobStatus.QUEUED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        # Convert datetime objects to ISO strings
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, JobStatus):
                data[key] = value.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Job':
        # Convert ISO strings back to datetime objects
        for key in ['created_at', 'started_at', 'completed_at']:
            if data.get(key):
                data[key] = datetime.fromisoformat(data[key])
        if 'status' in data:
            data['status'] = JobStatus(data['status'])
        return cls(**data)

class QueueManager:
    """Redis-based queue manager for processing jobs"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", max_workers: int = 3):
        self.redis_url = redis_url
        self.max_workers = max_workers
        self.redis_client = None
        self._connected = False
        self._workers_running = False
        self._executor = None
        self._job_handlers: Dict[str, Callable] = {}
        
        # Queue names
        self.pending_queue = "jobs:pending"
        self.processing_queue = "jobs:processing"
        self.completed_queue = "jobs:completed"
        self.failed_queue = "jobs:failed"
        self.job_data_key = "jobs:data"
        
        self._connect()
    
    def _connect(self) -> bool:
        """Connect to Redis"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.redis_url}")
            return True
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}. Running in local mode.")
            self._connected = False
            return False
    
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        return self._connected and self.redis_client is not None
    
    def register_handler(self, task_type: str, handler: Callable) -> None:
        """Register a handler function for a specific task type"""
        self._job_handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")
    
    def enqueue_job(self, job: Job) -> bool:
        """Add a job to the queue"""
        if not self.is_connected():
            logger.warning("Redis not connected, processing job directly")
            return self._process_job_directly(job)
        
        try:
            # Store job data
            self.redis_client.hset(self.job_data_key, job.id, json.dumps(job.to_dict()))
            
            # Add to pending queue
            self.redis_client.lpush(self.pending_queue, job.id)
            
            logger.info(f"Job {job.id} enqueued successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error enqueuing job {job.id}: {e}")
            return self._process_job_directly(job)
    
    def _process_job_directly(self, job: Job) -> bool:
        """Process job directly without queue (fallback)"""
        try:
            if job.task_type in self._job_handlers:
                handler = self._job_handlers[job.task_type]
                handler(job.file_path)
                logger.info(f"Job {job.id} processed directly")
                return True
            else:
                logger.error(f"No handler found for task type: {job.task_type}")
                return False
        except Exception as e:
            logger.error(f"Error processing job directly {job.id}: {e}")
            return False
    
    def start_workers(self) -> None:
        """Start worker threads to process jobs"""
        if self._workers_running or not self.is_connected():
            logger.warning("Workers already running or Redis not connected")
            return
        
        self._workers_running = True
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="QueueWorker")
        
        # Start worker threads
        for i in range(self.max_workers):
            self._executor.submit(self._worker_loop, f"worker-{i}")
        
        logger.info(f"Started {self.max_workers} queue workers")
    
    def stop_workers(self) -> None:
        """Stop all worker threads"""
        if not self._workers_running:
            return
        
        self._workers_running = False
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
        
        logger.info("Stopped all queue workers")
    
    def _worker_loop(self, worker_name: str) -> None:
        """Main loop for worker threads"""
        logger.info(f"Worker {worker_name} started")
        
        while self._workers_running:
            try:
                # Get job from queue (blocking with timeout)
                job_id = self.redis_client.brpop(self.pending_queue, timeout=5)
                
                if job_id is None:
                    continue  # Timeout, continue loop
                
                job_id = job_id[1]  # brpop returns (queue_name, value)
                
                # Get job data
                job_data = self.redis_client.hget(self.job_data_key, job_id)
                if not job_data:
                    logger.error(f"Job data not found for job {job_id}")
                    continue
                
                job = Job.from_dict(json.loads(job_data))
                
                # Move to processing queue
                self.redis_client.lpush(self.processing_queue, job_id)
                
                # Process the job
                success = self._process_job(job, worker_name)
                
                # Remove from processing queue
                self.redis_client.lrem(self.processing_queue, 1, job_id)
                
                # Move to appropriate completion queue
                if success:
                    job.status = JobStatus.COMPLETED
                    job.completed_at = datetime.now()
                    self.redis_client.lpush(self.completed_queue, job_id)
                else:
                    if job.retry_count < job.max_retries:
                        job.retry_count += 1
                        job.status = JobStatus.RETRYING
                        self.redis_client.lpush(self.pending_queue, job_id)
                        logger.info(f"Job {job_id} requeued for retry ({job.retry_count}/{job.max_retries})")
                    else:
                        job.status = JobStatus.FAILED
                        job.completed_at = datetime.now()
                        self.redis_client.lpush(self.failed_queue, job_id)
                
                # Update job data
                self.redis_client.hset(self.job_data_key, job_id, json.dumps(job.to_dict()))
                
            except Exception as e:
                logger.error(f"Error in worker {worker_name}: {e}")
                time.sleep(1)  # Brief pause on error
        
        logger.info(f"Worker {worker_name} stopped")
    
    def _process_job(self, job: Job, worker_name: str) -> bool:
        """Process a single job"""
        try:
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.now()
            
            logger.info(f"Worker {worker_name} processing job {job.id}: {job.file_path}")
            
            # Get handler for task type
            if job.task_type not in self._job_handlers:
                raise Exception(f"No handler found for task type: {job.task_type}")
            
            handler = self._job_handlers[job.task_type]
            
            # Execute the handler
            handler(job.file_path)
            
            logger.info(f"Worker {worker_name} completed job {job.id}")
            return True
            
        except Exception as e:
            job.error_message = str(e)
            logger.error(f"Worker {worker_name} failed job {job.id}: {e}")
            return False
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Get statistics about queue status"""
        if not self.is_connected():
            return {"error": "Redis not connected"}
        
        try:
            return {
                "pending": self.redis_client.llen(self.pending_queue),
                "processing": self.redis_client.llen(self.processing_queue),
                "completed": self.redis_client.llen(self.completed_queue),
                "failed": self.redis_client.llen(self.failed_queue),
                "total_jobs": self.redis_client.hlen(self.job_data_key)
            }
        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")
            return {"error": str(e)}
    
    def get_job_status(self, job_id: str) -> Optional[Job]:
        """Get status of a specific job"""
        if not self.is_connected():
            return None
        
        try:
            job_data = self.redis_client.hget(self.job_data_key, job_id)
            if job_data:
                return Job.from_dict(json.loads(job_data))
            return None
        except Exception as e:
            logger.error(f"Error getting job status for {job_id}: {e}")
            return None
    
    def get_recent_jobs(self, limit: int = 50) -> List[Job]:
        """Get recent jobs from all queues"""
        if not self.is_connected():
            return []
        
        try:
            all_jobs = []
            
            # Get job IDs from all queues
            for queue in [self.completed_queue, self.failed_queue, self.processing_queue, self.pending_queue]:
                job_ids = self.redis_client.lrange(queue, 0, limit)
                for job_id in job_ids:
                    job_data = self.redis_client.hget(self.job_data_key, job_id)
                    if job_data:
                        all_jobs.append(Job.from_dict(json.loads(job_data)))
            
            # Sort by created_at (most recent first)
            all_jobs.sort(key=lambda x: x.created_at, reverse=True)
            
            return all_jobs[:limit]
            
        except Exception as e:
            logger.error(f"Error getting recent jobs: {e}")
            return []
    
    def clear_completed_jobs(self, older_than_hours: int = 24) -> int:
        """Clear completed jobs older than specified hours"""
        if not self.is_connected():
            return 0
        
        try:
            cutoff_time = datetime.now().timestamp() - (older_than_hours * 3600)
            cleared_count = 0
            
            # Get all completed job IDs
            job_ids = self.redis_client.lrange(self.completed_queue, 0, -1)
            
            for job_id in job_ids:
                job_data = self.redis_client.hget(self.job_data_key, job_id)
                if job_data:
                    job = Job.from_dict(json.loads(job_data))
                    if job.completed_at and job.completed_at.timestamp() < cutoff_time:
                        # Remove from queue and data
                        self.redis_client.lrem(self.completed_queue, 1, job_id)
                        self.redis_client.hdel(self.job_data_key, job_id)
                        cleared_count += 1
            
            logger.info(f"Cleared {cleared_count} completed jobs older than {older_than_hours} hours")
            return cleared_count
            
        except Exception as e:
            logger.error(f"Error clearing completed jobs: {e}")
            return 0

# Global queue manager instance (will be initialized with config)
queue_manager: Optional[QueueManager] = None