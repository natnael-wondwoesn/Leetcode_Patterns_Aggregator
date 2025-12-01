"""Utility to upload aggregated pattern rows to a Google Sheet.

The main entrypoints are:
- `build_sheet_rows(records)` -> list[list[str]] for sheets API
- `push_rows(spreadsheet_id, range_name, records, ...)` to append/update rows.

Expected record shape (e.g. from GeminiSummarizer):
{
    "pattern": str,
    "url": str,
    "summary": str,
    "top_problems": str,
}
"""

from __future__ import annotations

import os
from typing import Iterable, List, Mapping, Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Full read/write scope to allow appending/replacing rows.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DEFAULT_HEADERS = ["Pattern", "URL", "Summary", "Top Problems"]


def get_credentials(
    *,
    token_path: str = "token.json",
    credentials_path: str = "credentials.json",
    scopes: Sequence[str] = SCOPES,
) -> Credentials:
    """Load or acquire OAuth credentials for Sheets."""
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
    return creds


def build_sheet_rows(
    records: Iterable[Mapping[str, str]],
    *,
    include_header: bool = True,
    headers: Sequence[str] = DEFAULT_HEADERS,
) -> List[List[str]]:
    """Turn record dicts into row lists for the Sheets API."""
    rows: List[List[str]] = []
    if include_header:
        rows.append(list(headers))
    for rec in records:
        rows.append(
            [
                rec.get("pattern", ""),
                rec.get("url", ""),
                rec.get("summary", ""),
                rec.get("top_problems", ""),
            ]
        )
    return rows


def push_rows(
    spreadsheet_id: str,
    range_name: str,
    records: Iterable[Mapping[str, str]],
    *,
    token_path: str = "token.json",
    credentials_path: str = "credentials.json",
    clear_first: bool = False,
) -> None:
    """Append or replace rows in a Google Sheet."""
    creds = get_credentials(token_path=token_path, credentials_path=credentials_path)
    service = build("sheets", "v4", credentials=creds)
    rows = build_sheet_rows(records, include_header=True)

    try:
        sheet = service.spreadsheets()
        if clear_first:
            sheet.values().clear(spreadsheetId=spreadsheet_id, range=range_name).execute()
        sheet.values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()
    except HttpError as err:
        # Surface the API error for callers; logging can be added by caller.
        raise RuntimeError(f"Google Sheets API error: {err}") from err


__all__ = ["build_sheet_rows", "push_rows", "get_credentials", "DEFAULT_HEADERS", "SCOPES"]
