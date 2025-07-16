import re
import requests
from typing import Optional

def convert_txt_link_to_html(txt_url: str, user_agent: str) -> Optional[str]:
    """
    Converts a .txt SEC filing link to its corresponding .htm/.html link.

    Args:
        txt_url: The URL of the .txt filing.
        user_agent: The User-Agent string for the request.

    Returns:
        The URL of the .html filing, or None if not found.
    """
    try:
        headers = {'User-Agent': user_agent}
        response = requests.get(txt_url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        content = response.text

        # Regex to find the primary HTML file name from various patterns
        # e.g., <FILENAME>my-document.htm, instance="my-document.htm", etc.
        patterns = [
            r'<FILENAME>(.*\.htm[l]?)',
            r'instance="([^"]+\.htm[l]?)"',
            r'original="([^"]+\.htm[l]?)"',
            r'"baseRef":\s*"([^"]+\.htm[l]?)"'
        ]
        
        html_filename = None
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                html_filename = match.group(1).strip()
                break

        if not html_filename:
            # A more generic fallback if specific patterns fail
            match = re.search(r'([a-zA-Z0-9_.-]+\.htm[l]?)', content)
            if match:
                html_filename = match.group(1).strip()

        if not html_filename:
            print(f"Could not find HTML filename in {txt_url}")
            return None

        # Construct the HTML URL:
        #   txt_url  -> https://.../data/CIK/ACCESSION-NUMBER.txt
        #   html_url -> https://.../data/CIK/ACCESSIONNUMBER/filename.htm
        base_path, accession_txt = txt_url.rsplit('/', 1)
        accession_clean = accession_txt.replace('.txt', '').replace('-', '')
        html_url = f"{base_path}/{accession_clean}/{html_filename}"

        return html_url

    except requests.exceptions.RequestException as e:
        print(f"Error fetching {txt_url}: {e}")
        return None
    except Exception as e:
        print(f"An error occurred while processing {txt_url}: {e}")
        return None
