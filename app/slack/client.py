from typing import Optional, Any, List, Dict
import httpx

SLACK_API_BASE_URL = "https://slack.com/api"


class SlackApiError(Exception):
    """Exception raised when Slack API returns an error."""

    def __init__(self, message: str, slack_error: Optional[str] = None):
        super().__init__(message)
        self.slack_error = slack_error


class SlackClient:
    """
    Thin wrapper around Slack web API using a bot access token.
    """

    def __init__(self, bot_access_token: str):
        if not bot_access_token:
            raise ValueError("bot_access_token is required")
        self.bot_access_token = bot_access_token

    def _request(
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Internal helper to send a HTTP request to Slack API and handle basic errors.
        """
        url = f"{SLACK_API_BASE_URL}/{endpoint}"

        headers = {
            "Authorization": f"Bearer {self.bot_access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # Slack expects form-encoded for most web API endpoints
        with httpx.Client() as client:
            if method.upper() == "POST":
                resp = client.post(url, data=data or {}, headers=headers)
            else:
                resp = client.get(url, params=data or {}, headers=headers)

        resp_data = resp.json()

        if not resp_data.get("ok"):
            error_code = resp_data.get("error", "unknown_error")
            raise SlackApiError(f"Slack API Error: {error_code}", slack_error=error_code)

        return resp_data

    # Public methods

    def send_message(
        self,
        channel_id: str,
        text: str,
        thread_ts: Optional[str] = None,
        reply_broadcast: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to a channel or thread using chat.postMessage.
        Returns Slack's response JSON (already checked ok==True).
        """
        data: Dict[str, Any] = {
            "channel": channel_id,
            "text": text,
        }

        if thread_ts:
            data["thread_ts"] = thread_ts
        if reply_broadcast is not None:
            data["reply_broadcast"] = reply_broadcast

        return self._request("POST", "chat.postMessage", data=data)

    def list_channels(
        self,
        limit: int = 100,
        cursor: Optional[str] = None,
        include_private: bool = False,
    ) -> Dict[str, Any]:
        """
        List conversations (channels) using conversations.list.
        Returns Slack's raw response JSON (ok already checked).
        """
        # Slack 'types' parameter controls which kinds of conversations are returned
        types = ["public_channel"]
        if include_private:
            types.append("private_channel")

        data: Dict[str, Any] = {
            "limit": limit,
            "types": ",".join(types),
        }

        if cursor:
            data["cursor"] = cursor

        return self._request("GET", "conversations.list", data=data)
