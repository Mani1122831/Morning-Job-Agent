"""
Application-wide configuration variables and environment setup.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# File Paths
CSV_FILE_PATH = os.getenv("CSV_FILE_PATH", "data/jobs.csv")

# Constants
DEFAULT_SEARCH_TERMS = ["AI Engineer", "Machine Learning", "Generative AI", "LLM"]
DEFAULT_LOCATIONS = ["Remote", "Bengaluru", "Hyderabad"]

# Ensure data directory exists
os.makedirs(os.path.dirname(CSV_FILE_PATH), exist_ok=True)