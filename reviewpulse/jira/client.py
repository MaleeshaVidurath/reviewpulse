"""Thin Jira Cloud REST v3 client -- just the two calls ticket sync needs
(create an issue, comment on one). No search/update/transition support;
add it if a later stage actually needs it.

Jira Cloud requires issue description/comment bodies in Atlassian Document
Format (ADF), not plain strings -- `_to_adf()` wraps plain text into the
minimal single-paragraph doc shape the API accepts.
"""

from __future__ import annotations

from reviewpulse.config import JIRA_API_TOKEN, JIRA_BASE_URL, JIRA_EMAIL, JIRA_PROJECT_KEY

REQUEST_TIMEOUT_S = 10


def _to_adf(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        ],
    }


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str, project_key: str):
        self.base_url = base_url.rstrip("/")
        self.auth = (email, api_token)
        self.project_key = project_key

    @classmethod
    def from_env(cls) -> "JiraClient":
        required = {
            "JIRA_BASE_URL": JIRA_BASE_URL,
            "JIRA_EMAIL": JIRA_EMAIL,
            "JIRA_API_TOKEN": JIRA_API_TOKEN,
            "JIRA_PROJECT_KEY": JIRA_PROJECT_KEY,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                f"Missing Jira config: {', '.join(missing)} (set as environment variables)"
            )
        return cls(JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY)

    def create_issue(self, summary: str, description: str) -> str:
        """Create a Bug issue in the configured project. Returns the new
        issue's key (e.g. "RP-123").
        """
        import requests

        resp = requests.post(
            f"{self.base_url}/rest/api/3/issue",
            auth=self.auth,
            json={
                "fields": {
                    "project": {"key": self.project_key},
                    "summary": summary,
                    "description": _to_adf(description),
                    "issuetype": {"name": "Bug"},
                }
            },
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.json()["key"]

    def add_comment(self, issue_key: str, body: str) -> None:
        import requests

        resp = requests.post(
            f"{self.base_url}/rest/api/3/issue/{issue_key}/comment",
            auth=self.auth,
            json={"body": _to_adf(body)},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
