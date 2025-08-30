from typing import Optional
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Global instances
_connection_pool: Optional[AsyncConnectionPool] = None
_checkpointer_instance: Optional[AsyncPostgresSaver] = None

async def get_postgres_checkpointer() -> AsyncPostgresSaver:
    """
    Get AsyncPostgresSaver with proper connection pool management
    """
    global _connection_pool, _checkpointer_instance
    
    if _checkpointer_instance is None:
        try:
            # Create connection pool if not exists
            if _connection_pool is None:
                logger.info("Creating connection pool...")
                _connection_pool = AsyncConnectionPool(
                    conninfo=settings.database_url,
                    max_size=20,
                    open=False,  # Don't open in constructor
                    kwargs={
                        "autocommit": True,
                        "prepare_threshold": 0,
                    }
                )
                logger.info("Opening connection pool...")
                await _connection_pool.open()
                logger.info("Connection pool opened successfully")
            
            # Create checkpointer with connection pool
            _checkpointer_instance = AsyncPostgresSaver(_connection_pool)
            
            # Setup tables - check if they exist first
            async with _connection_pool.connection() as conn:
                async with conn.cursor() as cur:
                    try:
                        await cur.execute("""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_schema = 'public' 
                                AND table_name = 'checkpoints'
                            );
                        """)
                        table_exists = (await cur.fetchone())[0]
                        
                        if not table_exists:
                            logger.info("Checkpoints table does not exist. Running setup...")
                            await _checkpointer_instance.setup()
                        else:
                            logger.info("Checkpoints table already exists. Skipping setup.")
                            
                    except Exception as setup_error:
                        logger.error(f"Error during setup: {setup_error}")
                        # Try to run setup anyway
                        await _checkpointer_instance.setup()
            
            logger.info("AsyncPostgresSaver initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize checkpointer: {e}")
            raise Exception(f"Database connection failed: {str(e)}")
    
    return _checkpointer_instance

async def close_checkpointer():
    """Close checkpointer connections - call this on app shutdown"""
    global _connection_pool, _checkpointer_instance
    
    if _connection_pool:
        try:
            await _connection_pool.close()
            logger.info("Connection pool closed")
        except Exception as e:
            logger.error(f"Error closing connection pool: {e}")
        finally:
            _connection_pool = None
            _checkpointer_instance = None