import requests

# Base URL for SEC filings
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/"

def fetch_filing_text(file_name: str, user_agent: str) -> str:
    """
    Fetches the text content of a single SEC filing.

    Args:
        file_name (str): The file name path from the master index.
        user_agent (str): The User-Agent header for the request.

    Returns:
        str: The text content of the filing, or an empty string if fetching fails.
    """
    if not user_agent:
        raise ValueError("A User-Agent is required for SEC requests.")

    filing_url = f"{SEC_ARCHIVES_URL}{file_name}"
    headers = {"User-Agent": user_agent}

    try:
        response = requests.get(filing_url, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch filing {file_name}: {e}")
        return ""

