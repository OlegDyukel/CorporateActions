from dataclasses import dataclass
from typing import Optional

@dataclass
class CorporateActionFiling:
    """
    Represents a corporate action filing with extracted details.
    """
    cik: str
    company_name: str
    form_type: str
    filed_as_of_date: str
    accession_number: str
    ticker: str
    action_type: str
    file_name: str
    content: str
    exchange: Optional[str] = None
