-- 채널/팟캐스트 관리 테이블
CREATE TABLE IF NOT EXISTS channels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(500) NOT NULL UNIQUE,
    platform VARCHAR(50) NOT NULL, -- 'youtube', 'spotify', 'apple_podcasts'
    category VARCHAR(100),
    description TEXT,
    language VARCHAR(10) DEFAULT 'ko',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 콘텐츠 메타데이터 테이블
CREATE TABLE IF NOT EXISTS content (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    external_id VARCHAR(255) NOT NULL, -- YouTube video ID, Spotify episode ID
    title VARCHAR(500) NOT NULL,
    url VARCHAR(500),
    description TEXT,
    duration INTEGER, -- seconds
    publish_date TIMESTAMP,
    views_count INTEGER DEFAULT 0,
    transcript_available BOOLEAN DEFAULT false,
    transcript_type VARCHAR(50), -- 'auto', 'manual', 'stt_whisper'
    language VARCHAR(10) DEFAULT 'ko',
    is_podcast BOOLEAN DEFAULT false, -- 팟캐스트 여부
    processed_at TIMESTAMP,
    vector_stored BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(channel_id, external_id)
);

-- 트랜스크립트 데이터 테이블
CREATE TABLE IF NOT EXISTS transcripts (
    id SERIAL PRIMARY KEY,
    content_id INTEGER REFERENCES content(id),
    text TEXT NOT NULL,
    start_time FLOAT,
    end_time FLOAT,
    speaker VARCHAR(100),
    confidence FLOAT,
    segment_order INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 처리 작업 큐 테이블
CREATE TABLE IF NOT EXISTS processing_jobs (
    id SERIAL PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL, -- 'extract_transcript', 'vectorize', 'process_audio'
    content_id INTEGER REFERENCES content(id),
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed'
    priority INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 벡터 저장소 매핑 테이블
CREATE TABLE IF NOT EXISTS vector_mappings (
    id SERIAL PRIMARY KEY,
    content_id INTEGER REFERENCES content(id),
    chunk_id VARCHAR(100) NOT NULL,
    vector_collection VARCHAR(100) NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_order INTEGER,
    chunk_metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_channels_platform ON channels(platform);
CREATE INDEX IF NOT EXISTS idx_channels_active ON channels(is_active);
CREATE INDEX IF NOT EXISTS idx_content_channel_id ON content(channel_id);
CREATE INDEX IF NOT EXISTS idx_content_processed ON content(processed_at);
CREATE INDEX IF NOT EXISTS idx_content_vector_stored ON content(vector_stored);
CREATE INDEX IF NOT EXISTS idx_transcripts_content_id ON transcripts(content_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_time ON transcripts(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON processing_jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_vector_content_id ON vector_mappings(content_id);

-- 샘플 데이터 삽입
INSERT INTO channels (name, url, platform, category, description, language) VALUES
('슈카월드', 'https://www.youtube.com/@syukaworld', 'youtube', 'finance', '슈카월드 유튜브 채널', 'ko'),
('조코딩 JoCoding', 'https://www.youtube.com/@jocoding', 'youtube', 'tech', '조코딩 유튜브 채널', 'ko')
ON CONFLICT (url) DO NOTHING;