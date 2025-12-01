"""Utility to upload aggregated pattern rows to a Google Sheet.

Entrypoints:
- `push_rows`: legacy single-range writer.
- `push_pattern_sheets`: create/update one sheet per pattern/topic.
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
PROBLEM_HEADERS = ["Problem", "Difficulty", "URL", "Solved (Me)", "Solved (Friend)"]


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


def build_pattern_sheet_rows(record: Mapping[str, str], problems: Sequence[Mapping[str, str]]) -> List[List[str]]:
    """Build rows for a single pattern tab: summary + problem list with solved columns."""
    rows: List[List[str]] = [
        ["Pattern", record.get("pattern", "")],
        ["URL", record.get("url", "")],
        ["Summary", record.get("summary", "")],
    ]
    if record.get("notes"):
        rows.append(["Notes", record["notes"]])
    rows.append([])  # spacer
    rows.append(list(PROBLEM_HEADERS))
    for p in problems:
        rows.append(
            [
                p.get("title", ""),
                p.get("difficulty", ""),
                p.get("url", ""),
                "",  # Solved (Me)
                "",  # Solved (Friend)
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


def push_pattern_sheets(
    spreadsheet_id: str,
    pattern_records: Iterable[Mapping[str, object]],
    *,
    token_path: str = "token.json",
    credentials_path: str = "credentials.json",
    clear_first: bool = True,
) -> None:
    """Create/overwrite one sheet per pattern/topic and populate problems with solved columns."""
    creds = get_credentials(token_path=token_path, credentials_path=credentials_path)
    service = build("sheets", "v4", credentials=creds)

    # Fetch existing sheet names once
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_titles = {
        sheet["properties"]["title"] for sheet in meta.get("sheets", []) if "properties" in sheet
    }

    for record in pattern_records:
        title = sanitize_title(record.get("pattern") or "Pattern")
        problems = record.get("problems") or []
        rows = build_pattern_sheet_rows(record, problems)
        range_name = f"'{title}'!A1"

        if title not in existing_titles:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
            ).execute()
            existing_titles.add(title)

        if clear_first:
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id, range=range_name
            ).execute()

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()


def sanitize_title(title: str) -> str:
    """Sheets tab titles cannot contain / \\ ? * [ ] and must be <= 100 chars."""
    banned = "/\\?*[]"
    sanitized = "".join(ch for ch in str(title) if ch not in banned).strip()
    return sanitized[:90] or "Pattern"


__all__ = [
    "build_sheet_rows",
    "build_pattern_sheet_rows",
    "push_rows",
    "push_pattern_sheets",
    "get_credentials",
    "sanitize_title",
    "DEFAULT_HEADERS",
    "PROBLEM_HEADERS",
    "SCOPES",
]
