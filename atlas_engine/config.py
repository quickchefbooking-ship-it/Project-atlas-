import os

from dotenv import load_dotenv

# Load the local .env file before any settings are read. Environment variables
# already supplied by the process take precedence over values in the file.
load_dotenv()

APP_NAME = "AtlasOnePro — Professor Core"
DB_PATH = os.environ.get("ATLAS_DB_PATH", "atlas.db")
API_KEY = os.environ.get("ATLAS_API_KEY")
API_REQUIRE_AUTH = os.environ.get("ATLAS_API_REQUIRE_AUTH", "true").lower() == "true"
ALLOWED_AI_PROVIDERS = ["local", "openai"]
USE_PAID_AI = os.environ.get("ATLAS_ENABLE_PAID_AI", "false").lower() == "true"
