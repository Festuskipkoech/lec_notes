# test_db.py
import asyncio
from app.config import settings

async def test_connection():
    try:
        from psycopg_pool import AsyncConnectionPool
        
        print("Testing database connection...")
        print(f"Database URL: {settings.database_url[:50]}...")
        
        pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=1,  # Add this
            max_size=2,  # Increase this
            open=False
        )
        
        print("Opening connection...")
        await asyncio.wait_for(pool.open(), timeout=10)
        print("Connection successful!")
        
        await pool.close()
        
    except asyncio.TimeoutError:
        print("ERROR: Database connection timed out")
    except Exception as e:
        print(f"ERROR: Database connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())