import os
from dotenv import load_dotenv

load_dotenv()

class settings:
    def __init__(self):
        self.DATABASE_URL: str = os.getenv("DATABASE_URL","")
         
        self.SLACK_CLIENT_ID: str = os.getenv("SLACK_CLIENT_ID","")
        self.SLACK_CLIENT_SECRET: str = os.getenv("SLACK_CLIENT_SECRET","")
         
        self.APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY","")
        
        self.SLACK_REDIRECT_URI: str = os.getenv(
            "SLACK_REDIRECT_URI",
            "http://localhost:8000/auth/slack/callback"
        )

settings = settings()