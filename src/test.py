import requests
import json
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import time

def get_latest_8k_filings(filing_date: Optional[str] = None, max_entries: int = 100, max_days_back: int = 7) -> List[Dict]:
    """
    Fetch the latest 8-K filings from SEC EDGAR database using the modern API.
    Will search backwards from the specified date to find the most recent business day with filings.
    
    Args:
        filing_date (str, optional): Date in YYYY-MM-DD format. Defaults to today.
        max_entries (int): Maximum number of entries to return. Defaults to 100.
        max_days_back (int): Maximum number of days to search backwards. Defaults to 7.
    
    Returns:
        List[Dict]: List of 8-K filings with company info and filing details
    """
    
    # Set default date to today if not provided
    if filing_date is None:
        filing_date = date.today().strftime('%Y-%m-%d')
    
    # SEC requires a User-Agent header identifying your application
    headers = {
        'User-Agent': 'Corporate Actions Monitor 1.0 (oleg.dyukel@gmail.com)',
        'Accept': 'application/json',
        'Host': 'data.sec.gov'
    }
    
    # Try to find filings starting from the specified date and going backwards
    search_date = datetime.strptime(filing_date, '%Y-%m-%d').date()
    
    for days_back in range(max_days_back + 1):
        current_date = search_date - timedelta(days=days_back)
        current_date_str = current_date.strftime('%Y-%m-%d')
        
        # Skip weekends (Saturday=5, Sunday=6)
        if current_date.weekday() >= 5:
            continue
            
        try:
            print(f"Searching for 8-K filings on {current_date_str}...")
            
            # Format date for SEC daily index (YYYY/QTR#/YYYYMMDD)
            year = current_date_str[:4]
            month = int(current_date_str[5:7])
            quarter = f"QTR{(month - 1) // 3 + 1}"
            date_formatted = current_date_str.replace('-', '')
            
            # SEC daily index URL
            daily_index_url = f"https://www.sec.gov/Archives/edgar/daily-index/{year}/{quarter}/master.{date_formatted}.idx"
            
            # Try to get the daily index file
            response = requests.get(daily_index_url, headers=headers)
            
            if response.status_code == 404:
                print(f"No filings found for {current_date_str} (weekend/holiday)")
                continue
            
            response.raise_for_status()
            
            # Parse the index file
            filings = parse_daily_index(response.text, max_entries)
            
            # Filter for 8-K filings only
            eight_k_filings = [f for f in filings if f['form_type'] == '8-K']
            
            if eight_k_filings:
                print(f"Found {len(eight_k_filings)} 8-K filings for {current_date_str}")
                return eight_k_filings[:max_entries]
            else:
                print(f"No 8-K filings found for {current_date_str}")
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data for {current_date_str}: {e}")
            continue
        except Exception as e:
            print(f"Unexpected error for {current_date_str}: {e}")
            continue
    
    # If no filings found in the date range, try alternative methods
    print(f"No 8-K filings found in the last {max_days_back} business days. Trying alternative method...")
    return get_recent_8k_alternative(headers, max_entries)

def parse_daily_index(index_content: str, max_entries: int) -> List[Dict]:
    """
    Parse SEC daily index file to extract filing information.
    """
    filings = []
    lines = index_content.strip().split('\n')
    
    # Skip header lines (usually first 11 lines contain metadata)
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith('-----'):
            data_start = i + 1
            break
    
    # Parse each filing entry
    for line in lines[data_start:data_start + max_entries * 2]:  # Get more than needed, filter later
        if not line.strip():
            continue
            
        # Index file format: CIK|Company Name|Form Type|Date Filed|Filename
        parts = line.split('|')
        if len(parts) >= 5:
            try:
                filing = {
                    'cik': parts[0].strip(),
                    'company_name': parts[1].strip(),
                    'form_type': parts[2].strip(),
                    'date_filed': parts[3].strip(),
                    'filename': parts[4].strip(),
                    'link': f"https://www.sec.gov/Archives/{parts[4].strip()}"
                }
                filings.append(filing)
            except Exception as e:
                print(f"Error parsing line: {line[:50]}... - {e}")
                continue
    
    return filings

def get_recent_8k_alternative(headers: Dict, max_entries: int) -> List[Dict]:
    """
    Alternative method to get recent 8-K filings using search API.
    """
    try:
        # Use SEC's search API for recent filings
        search_url = "https://efts.sec.gov/LATEST/search-index"
        
        # Search parameters for 8-K forms
        search_params = {
            'q': 'formType:8-K',
            'from': 0,
            'size': max_entries,
            'sort': 'filedAt:desc'
        }
        
        response = requests.get(search_url, params=search_params, headers=headers)
        
        if response.status_code != 200:
            print("Search API not available, using fallback method...")
            return get_fallback_filings()
        
        data = response.json()
        filings = []
        
        if 'hits' in data and 'hits' in data['hits']:
            for hit in data['hits']['hits'][:max_entries]:
                source = hit.get('_source', {})
                filing = {
                    'cik': source.get('cik', ''),
                    'company_name': source.get('displayNames', ['Unknown'])[0],
                    'form_type': source.get('formType', '8-K'),
                    'date_filed': source.get('filedAt', ''),
                    'filename': source.get('id', ''),
                    'link': f"https://www.sec.gov/Archives/edgar/data/{source.get('cik', '')}/{source.get('accessionNumber', '').replace('-', '')}/{source.get('primaryDocumentFilename', '')}"
                }
                filings.append(filing)
        
        return filings
        
    except Exception as e:
        print(f"Alternative method failed: {e}")
        return get_fallback_filings()

def get_fallback_filings() -> List[Dict]:
    """
    Fallback method with sample data structure.
    """
    print("Using fallback method - returning sample structure")
    print("Note: You may need to implement a web scraping approach or use a paid data service")
    
    return [{
        'cik': 'SAMPLE',
        'company_name': 'Sample Corp (API limitations encountered)',
        'form_type': '8-K',
        'date_filed': date.today().strftime('%Y-%m-%d'),
        'filename': 'sample-filing',
        'link': 'https://www.sec.gov/edgar/search/'
    }]

def display_filings(filings: List[Dict]) -> None:
    """
    Display the filings in a readable format.
    """
    if not filings:
        print("No 8-K filings found for the specified date.")
        return
    
    print(f"\n{'='*80}")
    print(f"LATEST 8-K FILINGS ({len(filings)} found)")
    print(f"{'='*80}")
    
    for i, filing in enumerate(filings, 1):
        print(f"\n{i}. {filing.get('company_name', 'Unknown Company')}")
        print(f"   CIK: {filing.get('cik', 'N/A')}")
        print(f"   Form: {filing.get('form_type', '8-K')}")
        print(f"   Filed: {filing.get('date_filed', 'N/A')}")
        print(f"   Link: {filing.get('link', 'N/A')}")

def get_filing_details(filing_url: str) -> Dict:
    """
    Fetch additional details from a specific filing URL.
    """
    headers = {
        'User-Agent': 'Corporate Actions Monitor 1.0 (oleg.dyukel@gmail.com)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    
    try:
        response = requests.get(filing_url, headers=headers)
        response.raise_for_status()
        
        # Basic parsing of filing content
        content = response.text
        
        # Extract key information (this is simplified - you'd want more robust parsing)
        details = {
            'content_length': len(content),
            'url': filing_url,
            'status': 'Retrieved successfully'
        }
        
        return details
        
    except Exception as e:
        return {
            'url': filing_url,
            'status': f'Error: {e}',
            'content_length': 0
        }

# Example usage
if __name__ == "__main__":
    # Get the latest available 8-K filings (searches backwards from today)
    latest_filings = get_latest_8k_filings()
    display_filings(latest_filings)
    
    # Example: Get latest filings with a custom search range
    # latest_filings = get_latest_8k_filings(max_days_back=10, max_entries=20)
    # display_filings(latest_filings)
    
    # Example: Start search from a specific date
    # filings_from_date = get_latest_8k_filings('2025-06-20', max_entries=10)
    # display_filings(filings_from_date)
    
    # Example: Get details for a specific filing
    if latest_filings:
        print(f"\n{'='*50}")
        print("TESTING FILING DETAILS")
        print(f"{'='*50}")
        first_filing = latest_filings[0]
        details = get_filing_details(first_filing['link'])
        print(f"Filing details: {details}")