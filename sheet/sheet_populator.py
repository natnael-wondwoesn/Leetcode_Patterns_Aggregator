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
    rows.append(["Problems", "", "", "", ""])
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
    resources_rows: List[List[str]] | None = None,
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

        apply_formatting(service, spreadsheet_id, title, rows)

    if resources_rows:
        push_resources_sheet(service, spreadsheet_id, resources_rows)


def apply_formatting(service, spreadsheet_id: str, title: str, rows: List[List[str]]) -> None:
    """Set column widths and apply difficulty-based coloring for a sheet."""
    # Column widths: A wider for problem titles, C wider for URLs.
    requests_body = [
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": _get_sheet_id(service, spreadsheet_id, title),
                    "dimension": "COLUMNS",
                    "startIndex": 0,  # A
                    "endIndex": 1,
                },
                "properties": {"pixelSize": 280},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": _get_sheet_id(service, spreadsheet_id, title),
                    "dimension": "COLUMNS",
                    "startIndex": 2,  # C
                    "endIndex": 3,
                },
                "properties": {"pixelSize": 260},
                "fields": "pixelSize",
            }
        },
    ]

    header_row_index = _find_header_row_index(rows)
    if header_row_index is not None:
        data_row_start = header_row_index + 1
        # Header background.
        requests_body.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": _get_sheet_id(service, spreadsheet_id, title),
                        "startRowIndex": header_row_index,
                        "endRowIndex": header_row_index + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 5,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.9, "green": 0.95, "blue": 1.0},
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }
        )

        # Difficulty conditional formatting on column B.
        sheet_id = _get_sheet_id(service, spreadsheet_id, title)
        data_row_end = data_row_start + max(1, len(rows) - data_row_start)
        requests_body += _difficulty_format_rules(sheet_id, data_row_start, data_row_end)

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests_body}
    ).execute()


def _get_sheet_id(service, spreadsheet_id: str, title: str) -> int:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == title:
            return props.get("sheetId")
    raise RuntimeError(f"Sheet '{title}' not found.")


def _find_header_row_index(rows: List[List[str]]) -> int | None:
    for idx, row in enumerate(rows):
        if row == PROBLEM_HEADERS:
            return idx
    return None


def _difficulty_format_rules(sheet_id: int, start_row: int, end_row: int) -> List[dict]:
    # Column B (index 1) contains difficulty.
    rules = []
    color_map = {
        "Easy": {"red": 0.82, "green": 0.94, "blue": 0.82},
        "Medium": {"red": 0.98, "green": 0.93, "blue": 0.82},
        "Hard": {"red": 0.98, "green": 0.82, "blue": 0.82},
    }
    for label, color in color_map.items():
        rules.append(
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": sheet_id,
                                "startRowIndex": start_row,
                                "endRowIndex": end_row,
                                "startColumnIndex": 1,
                                "endColumnIndex": 2,
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": label}],
                            },
                            "format": {"backgroundColor": color},
                        },
                    },
                    "index": 0,
                }
            }
    )
    return rules


def sanitize_title(title: str) -> str:
    """Sheets tab titles cannot contain / \\ ? * [ ] and must be <= 100 chars."""
    banned = "/\\?*[]"
    sanitized = "".join(ch for ch in str(title) if ch not in banned).strip()
    return sanitized[:90] or "Pattern"


def push_resources_sheet(service, spreadsheet_id: str, rows: List[List[str]]) -> None:
    """Create/overwrite a 'Resources' tab with curated resources and hints."""
    title = "Resources"
    try:
        sheet_id = _get_sheet_id(service, spreadsheet_id, title)
    except RuntimeError:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        ).execute()
        sheet_id = _get_sheet_id(service, spreadsheet_id, title)

    range_name = f"'{title}'!A1"
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range=range_name
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    # Simple formatting: widen columns and bold headers.
    requests_body = [
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 3,
                },
                "properties": {"pixelSize": 260},
                "fields": "pixelSize",
            }
        }
    ]
    tech_header_idx = next(
        (i for i, r in enumerate(rows) if r and r[0] == "Techniques & Hints"), None
    )
    hint_header_idx = tech_header_idx + 1 if tech_header_idx is not None else None
    header_rows = [0] + [idx for idx in (tech_header_idx, hint_header_idx) if idx is not None]
    for hr in header_rows:
        requests_body.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": hr,
                        "endRowIndex": hr + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 4,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.93, "green": 0.93, "blue": 0.98},
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }
        )
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests_body}
    ).execute()


__all__ = [
    "build_sheet_rows",
    "build_pattern_sheet_rows",
    "push_rows",
    "push_pattern_sheets",
    "push_resources_sheet",
    "get_credentials",
    "sanitize_title",
    "DEFAULT_HEADERS",
    "PROBLEM_HEADERS",
    "SCOPES",
]
