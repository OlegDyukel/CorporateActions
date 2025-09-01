import re
from typing import Dict, List

def parse_filing_header(content: str) -> Dict[str, str]:
    """
    Parses the header of an SEC filing to extract key information.
    Finds the <SEC-HEADER> block and extracts key-value pairs from it.
    """
    header_data = {}
    header_match = re.search(r'<SEC-HEADER>(.*?)</SEC-HEADER>', content, re.DOTALL)
    
    if not header_match:
        return header_data

    header_text = header_match.group(1)
    
    # A more robust regex to capture all key-value pairs.
    pattern = re.compile(r'([A-Z][A-Z\s-]+):\s+(.+)')
    
    for line in header_text.split('\n'):
        match = pattern.match(line.strip())
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            header_data[key] = value
            
    return header_data

def classify_action_type(content: str) -> str:
    """
    Classifies the corporate action type based on keywords in the filing content.

    Args:
        content: The full text content of the filing.

    Returns:
        A string representing the classified action type.
    """
    content_lower = content.lower()

    if any(keyword in content_lower for keyword in ['merger', 'acquisition', 'acquire', 'combination']):
        return 'Merger/Acquisition'
    if any(keyword in content_lower for keyword in ['dividend', 'distribution']):
        return 'Dividend/Distribution'
    if any(keyword in content_lower for keyword in ['split', 'reverse stock split']):
        return 'Stock Split'
    if any(keyword in content_lower for keyword in ['spin-off', 'spinoff']):
        return 'Spin-Off'
    if 'bankruptcy' in content_lower:
        return 'Bankruptcy'
    if 'delisting' in content_lower:
        return 'Delisting'
    
    # Check for Item codes as a fallback
    if re.search(r'item\s+1\.01', content_lower):
        return 'Material Agreement (e.g., Merger)'
    if re.search(r'item\s+5\.02', content_lower):
        return 'Director/Officer Change'
    if re.search(r'item\s+2\.01', content_lower):
        return 'Completion of Acquisition/Disposition'

    return 'Unclassified'


def extract_8k_items(text: str) -> List[str]:
    """
    Extracts the set of 8-K Item numbers from filing text.

    Matches patterns like:
    - "Item 1.01", "ITEM 5.02.", "Items 9.01 (Financial Statements and Exhibits)"

    Returns a de-duplicated list preserving first-seen order, e.g. ["1.01", "5.02", "9.01"].
    """
    if not text:
        return []
    items: List[str] = []
    seen = set()
    # Case-insensitive match for 'Item' or 'Items' followed by X.YY where X in 1-9 and YY in 00-99
    pattern = re.compile(r"\bitems?\s+([1-9]\.[0-9]{2})\b", re.IGNORECASE)
    for m in pattern.finditer(text):
        code = m.group(1)
        if code not in seen:
            seen.add(code)
            items.append(code)
    return items
