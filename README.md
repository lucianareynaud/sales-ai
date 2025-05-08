# Whisper Transcription App

A FastAPI application that transcribes audio and video files using OpenAI's Whisper API and stores the transcriptions in Supabase.

## Requirements

- Docker CLI
- Docker Compose or docker-compose plugin
- Either Docker Desktop or Colima (recommended for macOS users)
- OpenAI API key
- Supabase account and project

## Features

### Transcription

- Upload audio and video files for transcription
- Supports multiple file formats (MP3, WAV, MP4, etc.)
- Advanced audio processing with automatic extraction from video files
- Multi-step audio optimization pipeline for improved transcription quality
- Intelligent chunking for handling large files
- Adaptive compression based on file size
- Error resilience with retry mechanisms
- Stores transcripts in a Supabase database
- View and manage all transcriptions

### Sales Intelligence Analysis

The application includes an AI-powered sales intelligence feature that can analyze meeting transcripts to extract:

- Client company name
- Stakeholder names and roles
- Pain points mentioned by clients
- Sales opportunities
- Research triggers for follow-up
- Contextual information for personalization
- SPIN and BANT frameworks analysis

To use the feature:
1. View a transcript
2. Click the "Analyze Sales Intelligence" button
3. The AI will process the transcript and display structured insights

This feature helps sales teams quickly extract actionable intelligence from sales calls and meetings.

## Architecture

### System Overview

The application follows a modular, microservices-inspired architecture with clear separation of concerns. It's built using FastAPI for the backend, with a modern single-page frontend, and leverages several key services for its core functionality.

### Component Architecture

```mermaid
graph TB
    subgraph Frontend
        UI[Web Interface]
        Templates[HTML Templates]
        Static[Static Assets]
    end

    subgraph Backend
        API[FastAPI Application]
        Transcribe[Transcription Service]
        Media[Media Processing]
        Analysis[Sales Analysis Service]
        DB[(Supabase Database)]
    end

    subgraph External Services
        Whisper[OpenAI Whisper API]
        GPT[OpenAI GPT API]
    end

    UI --> API
    Templates --> UI
    Static --> UI
    
    API --> Transcribe
    API --> Analysis
    API --> DB
    
    Transcribe --> Media
    Transcribe --> Whisper
    Media --> Transcribe
    Analysis --> GPT
    
    DB --> Analysis
    Transcribe --> DB

    classDef service fill:#f9f,stroke:#333,stroke-width:2px
    classDef database fill:#bbf,stroke:#333,stroke-width:2px
    classDef external fill:#bfb,stroke:#333,stroke-width:2px
    
    class Transcribe,Analysis,Media service
    class DB database
    class Whisper,GPT external
```

### Core Components

1. **Frontend Layer**
   - Single-page web interface built with HTML, CSS, and JavaScript
   - Responsive design for desktop and mobile use
   - Real-time feedback for file uploads and processing
   - Interactive transcript viewer with analysis capabilities
   - Error handling and recovery

2. **API Layer (FastAPI)**
   - RESTful API endpoints for all operations
   - File upload handling with validation
   - Authentication and authorization (via Supabase)
   - Request validation using Pydantic models

3. **Media Processing Service**
   - Advanced audio extraction from video files
   - Multi-step audio optimization pipeline:
     - High-quality audio extraction (16kHz mono)
     - Volume normalization
     - Noise reduction when needed
   - Adaptive compression based on file size
   - Intelligent chunking system for handling large files
   - Format conversion between audio formats

4. **Transcription Service**
   - Handles audio/video file processing
   - Integrates with OpenAI's Whisper API
   - Supports multiple file formats
   - Manages temporary file storage
   - Handles language detection and transcription
   - Progress tracking for multi-chunk transcriptions
   - Intelligent merging of transcript chunks
   - Error recovery with retry mechanisms

5. **Sales Analysis Service**
   - LLM-powered analysis pipeline
   - Extracts structured data from transcripts
   - Identifies key sales intelligence points
   - Generates actionable insights
   - Uses GPT-4 for advanced analysis
   - SPIN and BANT framework analysis

6. **Data Layer**
   - Supabase PostgreSQL database for transcript storage
   - Efficient indexing for quick transcript retrieval
   - Secure file access control

### Data Flow

1. **File Upload Process**
   ```
   Client -> FastAPI -> Media Processing -> Chunking (if needed) -> Whisper API -> Database
   ```

2. **Video Processing Flow**
   ```
   Video File -> Audio Extraction -> Audio Optimization -> Size Check -> Chunking (if needed) -> Transcription
   ```

3. **Transcription Analysis**
   ```
   Database -> Analysis Service -> GPT API -> Structured Data -> Client
   ```

### Intelligent Chunking System

The application includes a sophisticated chunking system to handle files of any size:

1. **Adaptive Compression**
   - Uses progressively lower bitrates for larger files
   - Implements multiple compression attempts
   - Includes safety margins to stay under API limits

2. **Size-based Processing**
   - Automatic detection of file size
   - Optimized processing paths for different file sizes
   - Emergency fallback options for problematic files

3. **Chunk Management**
   - Overlap between chunks for better transcript merging
   - Tracking and logging of chunk processing
   - Retry mechanisms for failed chunks

### Security Architecture

- Environment-based configuration
- Secure API key management
- File type validation
- Size limits and rate limiting
- Supabase authentication integration
- Secure file storage with access controls

### Scalability Considerations

- Containerized deployment for easy scaling
- Stateless API design
- Efficient file handling
- Database indexing for performance
- Caching strategies for frequently accessed data

### Development Workflow

- Docker-based development environment
- Hot-reloading for frontend changes
- Comprehensive logging
- Error tracking and monitoring
- CI/CD ready structure

> The choice of each library balances productivity (FastAPI, Pydantic), scalability (async/await, Uvicorn), portability (Supabase), and observability (detailed tracebacks) – resulting in an elegant, modular, and production-ready stack.

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/whisper-transcription.git
cd whisper-transcription
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```
# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini  # Optional, defaults to gpt-4o-mini

# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
SUPABASE_STORAGE_BUCKET=transcripts
```

### 3. Set up Supabase

1. Create a new project in Supabase
2. Create a storage bucket named "transcripts"
3. Create a table named "transcripts" with the following schema:

```sql
create table if not exists public.transcripts (
  id               uuid primary key default gen_random_uuid(),
  transcript       text       not null,
  storage_path     text       not null,
  duration_seconds integer    not null,
  language         text       default 'en',
  created_at       timestamptz default now()
);
```

### 4. Docker Environment Setup (for macOS users)

You can use either Docker Desktop or Colima:

#### Using Colima (Recommended for macOS)

Install Colima if you haven't already:

```bash
# Install Colima and Docker CLI
brew install colima docker docker-compose

# Start Colima with recommended settings
colima start --cpu 4 --memory 8 --disk 60 --mount-type virtiofs
```

The start.sh script will automatically detect and use Colima if installed.

## Running the Application

```bash
# Start the application
./start.sh
```

The application will be available at http://localhost:8081

```bash
# View logs
docker compose logs -f
# or
docker-compose logs -f

# Stop the application
docker compose down
# or
docker-compose down
```
