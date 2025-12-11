from typing import Optional, Any, List, Dict
import httpx

SLACK_API_BASE_URL = "https://slack.com/api"

class slackApiError(Exception):
    
    def __init__(self, message:str, slack_error:Optional[str]=None):
        super().__init__(message)
        self.slack_error = slack_error
        
