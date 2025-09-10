#!/usr/bin/env python3
"""
Database Memory Content Checker
Direct database queries to examine stored memory chunks
"""

import sys
import asyncio

sys.path.append('/home/festus/note-gen/backend')

from app.database import SessionLocal
from sqlalchemy import text

def check_database_content():
    """Check what content is actually stored in the database"""
    db = SessionLocal()
    
    print("=== DATABASE MEMORY CONTENT CHECK ===")
    
    # Check topics
    print("\n1. TOPICS:")
    topics = db.execute(text("SELECT id, title, level, total_subtopics FROM topics")).fetchall()
    for topic in topics:
        print(f"   Topic {topic[0]}: {topic[1]} ({topic[2]}) - {topic[3]} subtopics")
    
    if not topics:
        print("   No topics found")
        return
    
    # Check subtopics 
    print("\n2. SUBTOPICS:")
    subtopics = db.execute(text("""
        SELECT s.id, s.topic_id, s.order, s.title, s.is_published,
               LENGTH(s.content) as content_length
        FROM subtopics s 
        ORDER BY s.topic_id, s.order
    """)).fetchall()
    
    for sub in subtopics:
        status = "Published" if sub[4] else "Draft"
        print(f"   Subtopic {sub[0]} (Topic {sub[1]}): Order {sub[2]} - {sub[3]}")
        print(f"      Status: {status}, Content: {sub[5]} chars")
    
    # Check content chunks (the memory)
    print("\n3. MEMORY CHUNKS:")
    chunks = db.execute(text("""
        SELECT cc.id, cc.subtopic_id, cc.chunk_type, 
               LENGTH(cc.content) as content_length,
               s.title as subtopic_title, s.topic_id
        FROM content_chunks cc
        JOIN subtopics s ON cc.subtopic_id = s.id
        ORDER BY s.topic_id, s.order, cc.id
    """)).fetchall()
    
    if not chunks:
        print("   No memory chunks found!")
        print("   This means the memory system has no data to work with.")
        return
    
    # Group by topic
    current_topic = None
    for chunk in chunks:
        topic_id = chunk[5]
        if current_topic != topic_id:
            current_topic = topic_id
            print(f"\n   Topic {topic_id} Memory:")
        
        print(f"      Chunk {chunk[0]}: [{chunk[2]}] from '{chunk[4]}'")
        print(f"         Content: {chunk[3]} chars")
    
    # Summary
    total_chunks = len(chunks)
    chunk_types = db.execute(text("""
        SELECT chunk_type, COUNT(*) 
        FROM content_chunks 
        GROUP BY chunk_type
    """)).fetchall()
    
    print(f"\n4. MEMORY SUMMARY:")
    print(f"   Total chunks: {total_chunks}")
    print("   Chunk types:")
    for chunk_type, count in chunk_types:
        print(f"      {chunk_type}: {count}")
    
    # Test a specific topic (useState/useEffect if it exists)
    react_topic = None
    for topic in topics:
        if 'react' in topic[1].lower() or 'usestate' in topic[1].lower():
            react_topic = topic[0]
            break
    
    if react_topic:
        print(f"\n5. DETAILED VIEW - Topic {react_topic}:")
        detailed_chunks = db.execute(text("""
            SELECT cc.chunk_type, cc.content, s.title, s.order
            FROM content_chunks cc
            JOIN subtopics s ON cc.subtopic_id = s.id  
            WHERE s.topic_id = :topic_id
            ORDER BY s.order, cc.id
        """), {"topic_id": react_topic}).fetchall()
        
        for chunk in detailed_chunks:
            print(f"\n   [{chunk[0]}] From: {chunk[2]} (Order {chunk[3]})")
            print(f"   Content: {chunk[1][:200]}...")
    
    db.close()

async def test_vector_search():
    """Test vector similarity search on existing data"""
    print("\n=== VECTOR SEARCH TEST ===")
    
    try:
        from app.services.vector_service import vector_service
        
        db = SessionLocal()
        
        # Find a topic with chunks
        result = db.execute(text("""
            SELECT DISTINCT s.topic_id 
            FROM subtopics s 
            JOIN content_chunks cc ON s.id = cc.subtopic_id 
            LIMIT 1
        """)).fetchone()
        
        if not result:
            print("No topics with memory chunks found")
            return
            
        topic_id = result[0]
        
        # Test queries
        test_queries = [
            "useState hook",
            "React state management", 
            "useEffect side effects",
            "form handling",
            "component rendering"
        ]
        
        for query in test_queries:
            print(f"\nTesting query: '{query}'")
            
            chunks = await vector_service.find_relevant_context(
                db=db,
                topic_id=26,
                query_text=query,
                current_subtopic_index=999,
                limit=3
            )
            
            if chunks:
                print(f"Found {len(chunks)} relevant chunks:")
                for i, chunk in enumerate(chunks, 1):
                    print(f"   {i}. Score: {chunk['similarity_score']:.3f}")
                    print(f"      Type: {chunk['type']}")
                    print(f"      From: {chunk['subtopic_title']}")
                    print(f"      Content: {chunk['content'][:100]}...")
            else:
                print("   No relevant chunks found")
        
        db.close()
        
    except Exception as e:
        print(f"Vector search test failed: {e}")

if __name__ == "__main__":
    check_database_content()
    asyncio.run(test_vector_search())