import os
from pathlib import Path
from dotenv import load_dotenv

print("Loading configuration...")

# Try to load environment variables from .env file
try:
    load_dotenv()
    print("Successfully loaded .env file")
except Exception as e:
    print(f"Warning: Could not load .env file: {str(e)}")

# Base paths
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "demo_mode")

# Supabase configuration - improve handling of empty strings and placeholder values
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", os.getenv("SUPABASE_KEY", ""))
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_SERVICE_KEY", ""))
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "transcripts")

# Ensure no placeholder values are treated as real credentials
for placeholder in ["your-project-url", "your-anon-key", "your-service-role-key", "example.supabase.co"]:
    if placeholder in SUPABASE_URL:
        SUPABASE_URL = ""
        print(f"Warning: Found placeholder value in SUPABASE_URL")
    if placeholder in SUPABASE_ANON_KEY:
        SUPABASE_ANON_KEY = ""
        print(f"Warning: Found placeholder value in SUPABASE_ANON_KEY")
    if placeholder in SUPABASE_SERVICE_ROLE_KEY:
        SUPABASE_SERVICE_ROLE_KEY = ""
        print(f"Warning: Found placeholder value in SUPABASE_SERVICE_ROLE_KEY")

# Display loaded environment variables (safely)
print("\nEnvironment variables loaded:")
print(f"OPENAI_API_KEY = {'[SET]' if OPENAI_API_KEY and OPENAI_API_KEY != 'demo_mode' else '[NOT SET]'}")
print(f"SUPABASE_URL = {SUPABASE_URL[:20] + '...' if SUPABASE_URL else '[NOT SET]'}")
print(f"SUPABASE_ANON_KEY = {SUPABASE_ANON_KEY[:10] + '...' if SUPABASE_ANON_KEY else '[NOT SET]'}")
print(f"SUPABASE_SERVICE_ROLE_KEY = {SUPABASE_SERVICE_ROLE_KEY[:10] + '...' if SUPABASE_SERVICE_ROLE_KEY else '[NOT SET]'}")
print(f"SUPABASE_STORAGE_BUCKET = {SUPABASE_STORAGE_BUCKET}")

# Supported file formats - Extensive list
AUDIO_FORMATS = [
    ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".wma", ".aiff", ".alac", 
    ".opus", ".amr", ".3gp", ".aax", ".act", ".aa", ".ape", ".dss", ".dvf", 
    ".gsm", ".iklax", ".ivs", ".m4b", ".m4p", ".mmf", ".mpc", ".msv", ".nmf", 
    ".nsf", ".ra", ".raw", ".sln", ".tta", ".voc", ".vox", ".wave", ".wv"
]

VIDEO_FORMATS = [
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg", ".wmv", ".flv", 
    ".3gp", ".3g2", ".m4v", ".f4v", ".f4p", ".f4a", ".f4b", ".mts", ".m2ts",
    ".ts", ".vob", ".ogv", ".mxf", ".roq", ".nsv", ".rm", ".rmvb", ".asf", 
    ".amv", ".m2v", ".svi", ".viv", ".divx"
]

SUPPORTED_FORMATS = AUDIO_FORMATS + VIDEO_FORMATS

# Print configuration summary
print("\nConfiguration loaded:")
print(f"- Upload directory: {UPLOAD_DIR}")
print(f"- OpenAI mode: {'Production' if OPENAI_API_KEY != 'demo_mode' else 'Demo'}")
print(f"- Supabase configured: {'Yes' if SUPABASE_URL and SUPABASE_ANON_KEY else 'No'}")
print(f"- Supabase service role available: {'Yes' if SUPABASE_SERVICE_ROLE_KEY else 'No'}")
print(f"- Supported formats: {len(SUPPORTED_FORMATS)} ({', '.join(SUPPORTED_FORMATS[:5] + ['...'])})") 