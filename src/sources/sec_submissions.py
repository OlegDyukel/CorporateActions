from __future__ import annotations

"""
SEC submissions helper.

Fetches recent company submissions JSON and constructs URLs for recent filings.
We avoid third-party libraries and use the official data.sec.gov endpoint.
"""

from typing import Dict, List, Optional
import requests


def _pad_cik(cik: str) -> str:
    s = (cik or "").strip()
    if not s:
        return s
    s = s.lstrip("0")
    if not s:
        s = "0"
    return s.zfill(10)


def get_company_submissions(cik: str, user_agent: str) -> Optional[Dict]:
    """Return the JSON submissions for a CIK, or None on error."""
    try:
        pcik = _pad_cik(cik)
        url = f"https://data.sec.gov/submissions/CIK{pcik}.json"
        headers = {"User-Agent": user_agent, "Accept": "application/json"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[SEC Submissions] Failed to fetch submissions for CIK {cik}: {e}")
        return None


def get_recent_company_filings(
    cik: str,
    user_agent: str,
    limit: int = 5,
    form_filter: Optional[List[str]] = None,
) -> List[Dict]:
    """Return a small list of recent filings with basic URLs.

    Each item contains: form, filingDate, accessionNumber, primaryDoc, html_url, txt_url.
    """
    data = get_company_submissions(cik, user_agent)
    if not data:
        return []

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accs = filings.get("accessionNumber", [])
    dates = filings.get("filingDate", [])
    prims = filings.get("primaryDocument", [])

    items: List[Dict] = []
    for form, acc, dt, prim in zip(forms, accs, dates, prims):
        f = (form or "").strip()
        if form_filter:
            if f not in form_filter:
                continue
        # Build URLs
        try:
            cik_int = int((cik or "").lstrip("0") or "0")
        except Exception:
            continue
        acc_nodash = (acc or "").replace("-", "")
        base_dir = f"https://www.sec.gov/Archives/edgar/data/{cik_int}"
        html_url = f"{base_dir}/{acc_nodash}/{prim}" if prim else None
        txt_url = f"{base_dir}/{acc}.txt" if acc else None
        items.append(
            {
                "form": f,
                "filingDate": dt,
                "accessionNumber": acc,
                "primaryDoc": prim,
                "html_url": html_url,
                "txt_url": txt_url,
            }
        )
        if len(items) >= limit:
            break
    return items
