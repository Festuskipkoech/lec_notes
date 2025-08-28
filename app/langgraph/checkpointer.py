# app/langgraph/checkpointer.py
from typing import Optional, Dict, Any, List, Tuple, Iterator, AsyncIterator
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple
from app.config import settings
import asyncio
import asyncpg
import json
import uuid
from datetime import datetime


class PostgreSQLCheckpointer(BaseCheckpointSaver):
    """
    A PostgreSQL checkpointer that actually implements the async methods
    by writing direct SQL queries instead of relying on PostgresSaver.
    """
    
    def __init__(self):
        self._conn_string = settings.database_url
        self.pool = None
        self._initialized = False
        self._setup_called = False
    
    async def _ensure_pool(self):
        """Ensure database connection pool is initialized"""
        if not self._initialized:
            try:
                self.pool = await asyncpg.create_pool(self._conn_string)
                await self._setup_tables()
                self._initialized = True
            except Exception as e:
                print(f"Failed to initialize PostgreSQL pool: {e}")
                raise
    
    async def _setup_tables(self):
        """Create the checkpoints table if it doesn't exist"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    checkpoint_data JSONB NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (thread_id, checkpoint_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_created 
                ON checkpoints(thread_id, created_at DESC);
            ''')
    
    def setup(self) -> None:
        """Initialize the checkpointer - but don't actually initialize async resources here"""
        # Just mark that setup was called - actual initialization happens lazily
        self._setup_called = True
    
    # Synchronous methods (required by base class) - simplified implementations
    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """Get the latest checkpoint tuple for a thread - not implemented in sync mode"""
        # This method is required by the interface but we'll only use async methods
        # LangGraph should use the async versions when available
        print("Warning: Sync get_tuple called - use async version instead")
        return None
    
    def list(self, config: Dict[str, Any], *, filter: Optional[Dict[str, Any]] = None, 
             before: Optional[str] = None, limit: Optional[int] = None) -> Iterator[CheckpointTuple]:
        """List checkpoint tuples for a thread - not implemented in sync mode"""
        print("Warning: Sync list called - use async version instead")
        return iter([])
    
    def put(self, config: Dict[str, Any], checkpoint: Checkpoint, metadata: CheckpointMetadata) -> str:
        """Save a checkpoint - not implemented in sync mode"""
        print("Warning: Sync put called - use async version instead")
        return str(uuid.uuid4())
    
    def put_writes(self, config: Dict[str, Any], writes: List[Tuple[str, Any]], task_id: str) -> None:
        """Save writes for a checkpoint - not implemented in sync mode"""
        print("Warning: Sync put_writes called - use async version instead")
        pass
    
    # Async methods (the actual implementations)
    async def aget_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """Get the latest checkpoint tuple for a thread"""
        await self._ensure_pool()
        
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT checkpoint_id, checkpoint_data, metadata, created_at
                FROM checkpoints 
                WHERE thread_id = $1 
                ORDER BY created_at DESC 
                LIMIT 1
            ''', thread_id)
            
            if not row:
                return None
            
            # Reconstruct CheckpointTuple
            checkpoint_data = json.loads(row['checkpoint_data'])
            metadata = json.loads(row['metadata']) if row['metadata'] else {}
            
            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": row['checkpoint_id']
                    }
                },
                checkpoint=checkpoint_data,
                metadata=metadata,
                parent_config=None  # Simplified - you might need to track parent relationships
            )
    
    async def alist(self, config: Dict[str, Any], *, filter: Optional[Dict[str, Any]] = None,
                   before: Optional[str] = None, limit: Optional[int] = None) -> AsyncIterator[CheckpointTuple]:
        """List checkpoint tuples for a thread"""
        await self._ensure_pool()
        
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return
        
        # Build query with optional filters
        query = '''
            SELECT checkpoint_id, checkpoint_data, metadata, created_at
            FROM checkpoints 
            WHERE thread_id = $1
        '''
        params = [thread_id]
        
        if before:
            query += ' AND checkpoint_id < $2'
            params.append(before)
        
        query += ' ORDER BY created_at DESC'
        
        if limit:
            query += f' LIMIT ${len(params) + 1}'
            params.append(limit)
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            
            for row in rows:
                checkpoint_data = json.loads(row['checkpoint_data'])
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                
                yield CheckpointTuple(
                    config={
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_id": row['checkpoint_id']
                        }
                    },
                    checkpoint=checkpoint_data,
                    metadata=metadata,
                    parent_config=None
                )
    
    async def aput(self, config: Dict[str, Any], checkpoint: Checkpoint, metadata: CheckpointMetadata) -> str:
        """Save a checkpoint"""
        await self._ensure_pool()
        
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            raise ValueError("thread_id is required in config")
        
        # Generate checkpoint ID if not provided
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        if not checkpoint_id:
            checkpoint_id = f"{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"
        
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO checkpoints (thread_id, checkpoint_id, checkpoint_data, metadata)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (thread_id, checkpoint_id) 
                DO UPDATE SET 
                    checkpoint_data = EXCLUDED.checkpoint_data,
                    metadata = EXCLUDED.metadata,
                    created_at = NOW()
            ''', 
                thread_id,
                checkpoint_id,
                json.dumps(checkpoint, default=str),  # Handle datetime serialization
                json.dumps(metadata, default=str)
            )
        
        return checkpoint_id
    
    async def aput_writes(self, config: Dict[str, Any], writes: List[Tuple[str, Any]], task_id: str) -> None:
        """Save writes for a checkpoint"""
        # For simplicity, we'll store writes as part of checkpoint metadata
        # In a more sophisticated implementation, you might have a separate writes table
        await self._ensure_pool()
        
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            raise ValueError("thread_id is required in config")
        
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id", task_id)
        
        writes_data = [{"channel": channel, "value": value} for channel, value in writes]
        
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO checkpoints (thread_id, checkpoint_id, checkpoint_data, metadata)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (thread_id, checkpoint_id) 
                DO UPDATE SET 
                    metadata = EXCLUDED.metadata,
                    created_at = NOW()
            ''', 
                thread_id,
                checkpoint_id,
                json.dumps({"writes": writes_data}, default=str),
                json.dumps({"task_id": task_id, "type": "writes"}, default=str)
            )
    
    # Context manager support
    async def __aenter__(self):
        await self._ensure_pool()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.pool:
            await self.pool.close()
    
    # Additional utility methods
    async def delete_thread(self, thread_id: str) -> bool:
        """Delete all checkpoints for a thread"""
        try:
            await self._ensure_pool()
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    'DELETE FROM checkpoints WHERE thread_id = $1', 
                    thread_id
                )
                return True
        except Exception as e:
            print(f"Failed to delete thread {thread_id}: {e}")
            return False
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information for debugging"""
        return {
            "database_url": self._conn_string.split("@")[-1] if self._conn_string else "Not configured",
            "pool_initialized": self._initialized,
            "pool_size": self.pool.get_size() if self.pool else 0,
            "implementation": "Custom PostgreSQL with asyncpg"
        }


# Factory function
def create_postgresql_checkpointer() -> PostgreSQLCheckpointer:
    """Factory function to create and setup a PostgreSQL checkpointer"""
    checkpointer = PostgreSQLCheckpointer()
    checkpointer.setup()
    return checkpointer


# Singleton management
class CheckpointerSingleton:
    _instance = None
    
    @classmethod
    def get_instance(cls) -> PostgreSQLCheckpointer:
        if cls._instance is None:
            cls._instance = create_postgresql_checkpointer()
        return cls._instance


def get_checkpointer() -> PostgreSQLCheckpointer:
    """Get or create the global checkpointer instance"""
    return CheckpointerSingleton.get_instance()