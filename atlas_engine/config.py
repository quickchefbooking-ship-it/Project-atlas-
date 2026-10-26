import os

APP_NAME = "Project Atlas Learning Engine"
DB_PATH = os.environ.get("ATLAS_DB_PATH", "atlas.db")
API_KEY = os.environ.get("ATLAS_API_KEY")
ALLOWED_AI_PROVIDERS = ["local", "openai"]
USE_PAID_AI = os.environ.get("ATLAS_ENABLE_PAID_AI", "false").lower() == "true"
