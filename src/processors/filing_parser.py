import re
from typing import Dict

def parse_filing_header(content: str) -> Dict[str, str]:
    """
    Parses the header of an SEC filing to extract key metadata.

    Args:
        content: The full text content of the filing.

    Returns:
        A dictionary with extracted fields.
    """
    data = {}
    try:
        header_parts = content.split('</SEC-HEADER>')
        if not header_parts:
            return data

        header_text = header_parts[0]

        patterns = {
            'accession_number': r'ACCESSION NUMBER:\s*(\S+)',
            'company_name': r'COMPANY CONFORMED NAME:\s*(.+)',
            'cik': r'CENTRAL INDEX KEY:\s*(\S+)',
            'form_type': r'CONFORMED SUBMISSION TYPE:\s*(\S+)',
            'filed_as_of_date': r'FILED AS OF DATE:\s*(\d+)',
            'date_as_of_change': r'DATE AS OF CHANGE:\s*(\d+)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, header_text, re.IGNORECASE)
            if match:
                data[key] = match.group(1).strip()

        # Fallback for company name if the primary pattern fails
        if 'company_name' not in data:
            match = re.search(r'COMPANY DATA:[\s\S]*?COMPANY CONFORMED NAME:\s*(.+)', header_text, re.IGNORECASE)
            if match:
                data['company_name'] = match.group(1).strip().split('\n')[0]

        return data
    except Exception as e:
        print(f"[Parser Error] An unexpected error occurred: {e}")
        return {}

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
