from dataclasses import dataclass

@dataclass
class CorporateActionFiling:
    """
    Represents a corporate action filing with structured data.
    """
    accession_number: str
    company_name: str
    ticker: str
    form_type: str
    filed_as_of_date: str
    date_as_of_change: str
    action_type: str
    file_name: str
    content: str
