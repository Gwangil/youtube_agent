"""
데이터베이스 모델 정의
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, Float, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from datetime import datetime
import os

Base = declarative_base()

class Channel(Base):
    __tablename__ = 'channels'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    url = Column(String(500), nullable=False, unique=True)
    platform = Column(String(50), nullable=False)  # 'youtube' (only YouTube supported)
    category = Column(String(100))
    description = Column(Text)
    language = Column(String(10), default='ko')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    content = relationship("Content", back_populates="channel")

class Content(Base):
    __tablename__ = 'content'

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey('channels.id'))
    external_id = Column(String(255), nullable=False)  # YouTube video ID
    title = Column(String(500), nullable=False)
    url = Column(String(500))
    description = Column(Text)
    duration = Column(Integer)  # seconds
    publish_date = Column(DateTime)
    views_count = Column(Integer, default=0)
    transcript_available = Column(Boolean, default=False)
    transcript_type = Column(String(50))  # 'auto', 'manual', 'stt_whisper'
    language = Column(String(10), default='ko')
    is_podcast = Column(Boolean, default=False)  # 팟캐스트 여부
    processed_at = Column(DateTime)
    vector_stored = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    channel = relationship("Channel", back_populates="content")
    transcripts = relationship("Transcript", back_populates="content")
    processing_jobs = relationship("ProcessingJob", back_populates="content")
    vector_mappings = relationship("VectorMapping", back_populates="content")

class Transcript(Base):
    __tablename__ = 'transcripts'

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer, ForeignKey('content.id'))
    text = Column(Text, nullable=False)
    start_time = Column(Float)
    end_time = Column(Float)
    speaker = Column(String(100))
    confidence = Column(Float)
    segment_order = Column(Integer)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    content = relationship("Content", back_populates="transcripts")

class ProcessingJob(Base):
    __tablename__ = 'processing_jobs'

    id = Column(Integer, primary_key=True)
    job_type = Column(String(50), nullable=False)  # 'extract_transcript', 'vectorize', 'process_audio'
    content_id = Column(Integer, ForeignKey('content.id'))
    status = Column(String(20), default='pending')  # 'pending', 'processing', 'completed', 'failed'
    priority = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    content = relationship("Content", back_populates="processing_jobs")

class VectorMapping(Base):
    __tablename__ = 'vector_mappings'

    id = Column(Integer, primary_key=True)
    content_id = Column(Integer, ForeignKey('content.id'))
    chunk_id = Column(String(100), nullable=False)
    vector_collection = Column(String(100), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_order = Column(Integer)
    chunk_metadata = Column(JSON)  # metadata -> chunk_metadata로 변경
    created_at = Column(DateTime, default=func.now())

    # Relationships
    content = relationship("Content", back_populates="vector_mappings")

# Database connection
def get_database_url():
    return os.getenv(
        'DATABASE_URL',
        'postgresql://podcast_user:podcast_pass@localhost:5432/podcast_agent'
    )

def create_engine_instance():
    return create_engine(get_database_url())

def get_session_maker():
    engine = create_engine_instance()
    return sessionmaker(bind=engine)

def get_db_session():
    SessionLocal = get_session_maker()
    session = SessionLocal()
    try:
        return session
    finally:
        pass  # Context manager will handle closing