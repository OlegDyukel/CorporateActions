import os
import tempfile
from datetime import datetime, timedelta

import os
import pandas as pd
import requests
from datetime import datetime, timedelta
from io import StringIO

from typing import Optional

def get_recent_8k_filings(days_ago: int = 1, base_date_str: Optional[str] = None, user_agent: str = "Mozilla/5.0"):
    """Fetches the master index file from the SEC for a specific day and parses 8-K filings."""
    # SEC doesn't publish on weekends, so we search backwards to find the last business day.
    if base_date_str:
        base_date = datetime.strptime(base_date_str, '%Y-%m-%d')
    else:
        base_date = datetime.now()

    # SEC doesn't publish on weekends, so we search backwards to find the last business day.
    for i in range(days_ago, days_ago + 10):
        current_date = base_date - timedelta(days=i)
        year = current_date.year
        quarter = (current_date.month - 1) // 3 + 1
        date_str = current_date.strftime('%Y%m%d')
        
        url = f"https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/master.{date_str}.idx"
        headers = {'User-Agent': user_agent}
        
        print(f"Trying to fetch index for {current_date.strftime('%Y-%m-%d')} from {url}")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            print("Successfully downloaded index file.")
            # The master.idx file has a header that needs to be skipped.
            # The actual data starts after a line of dashes '----------'.
            # We find the start of the data by looking for the header line.
            lines = response.text.split('\n')
            start_line = 0
            for i, line in enumerate(lines):
                if 'CIK|Company Name|Form Type|Date Filed|File Name' in line:
                    start_line = i + 1
                    break
            
            if start_line == 0:
                print("Could not find the start of the data in the index file.")
                continue

            # Read the data into a pandas DataFrame
            data = "\n".join(lines[start_line:])
            df = pd.read_csv(StringIO(data), sep='|', names=['cik', 'company', 'form_type', 'date_filed', 'file_name'])
            
            # Filter for 8-K filings
            df_8k = df[df['form_type'].str.strip() == '8-K'].copy()
            
            if df_8k.empty:
                print(f"No 8-K filings found for {current_date.strftime('%Y-%m-%d')}.")
                continue

            # Add accession_number from the file_name
            df_8k['accession_number'] = df_8k['file_name'].apply(lambda x: os.path.basename(x).replace('.txt', ''))
            print(f"Found {len(df_8k)} 8-K filings for {current_date.strftime('%Y-%m-%d')}.")
            return df_8k
        else:
            print(f"No index file found for {current_date.strftime('%Y-%m-%d')}. Trying previous day.")

    print("Could not find any recent index files.")
    return pd.DataFrame()
