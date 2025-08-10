from typing import Optional
import requests
from bs4 import BeautifulSoup

def parse_html_to_text(url: str, user_agent: str) -> Optional[str]:
    """Fetches HTML from a URL and parses it to extract clean text."""
    if not url:
        return None

    try:
        headers = {"User-Agent": user_agent}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes

        soup = BeautifulSoup(response.content, 'html.parser')

        # Remove script and style elements
        for script_or_style in soup(['script', 'style']):
            script_or_style.decompose()

        # Get text and clean it up
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        cleaned_text = '\n'.join(chunk for chunk in chunks if chunk)

        return cleaned_text

    except requests.RequestException as e:
        print(f"[HTML Parser] Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"[HTML Parser] An unexpected error occurred while parsing {url}: {e}")
        return None
