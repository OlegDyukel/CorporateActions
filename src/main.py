import os
import sys
from dotenv import load_dotenv
import asyncio
from typing import List
import telegram
import yagmail
from pathlib import Path

# Add project root to sys.path to allow for absolute imports
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.models.filing import CorporateActionFiling
from src.sources.master_index import get_recent_8k_filings
from src.processors.filing_processor import fetch_filing_text
from src.processors.filing_parser import parse_filing_header, classify_action_type
from src.utils.cik_mapper import CIKMapper


def format_filing_for_display(filing: CorporateActionFiling) -> str:
    """Formats a single filing for a readable display."""
    return (
        f"<b>Company:</b> {filing.company_name} ({filing.ticker})\n"
        f"<b>Action Type:</b> {filing.action_type}\n"
        f"<b>Form Type:</b> {filing.form_type}\n"
        f"<b>Filed Date:</b> {filing.filed_as_of_date}\n"
        f"<b>Accession No.:</b> {filing.accession_number}\n"
        f"<a href='https://www.sec.gov/Archives/edgar/data/{filing.file_name}'>Link to Filing</a>"
    )


async def send_to_telegram(filings: List[CorporateActionFiling]):
    """Sends the list of processed filings to a Telegram channel."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    channel_id = os.getenv('TELEGRAM_CHANNEL_ID')

    if not bot_token or not channel_id:
        print("Telegram bot token or channel ID not found in .env file. Skipping.")
        return

    bot = telegram.Bot(token=bot_token)
    print("\n--- Sending filings to Telegram ---")
    for filing in filings:
        message = format_filing_for_display(filing)
        await bot.send_message(chat_id=channel_id, text=message, parse_mode='HTML')
        await asyncio.sleep(1)  # Avoid hitting rate limits
    print("-----------------------------------")


def send_to_email(filings: List[CorporateActionFiling]):
    """Sends the list of processed filings to an email list."""
    sender_email = os.getenv('EMAIL_SENDER_ADDRESS')
    sender_password = os.getenv('EMAIL_SENDER_PASSWORD')
    recipients = os.getenv('EMAIL_RECIPIENTS')

    if not sender_email or not sender_password or not recipients:
        print("Email credentials or recipients not found in .env file. Skipping.")
        return

    yag = yagmail.SMTP(sender_email, sender_password)
    
    subject = "Daily Corporate Actions Digest"
    html_body = "<h1>Latest Corporate Action Filings</h1>"
    html_body += "<hr>".join([format_filing_for_display(f) for f in filings])

    print("\n--- Sending filings to Email ---")
    yag.send(
        to=recipients.split(','),
        subject=subject,
        contents=html_body
    )
    print("--------------------------------")


async def main():
    load_dotenv()
    identity = os.getenv("EDGAR_IDENTITY")
    email = os.getenv("EDGAR_EMAIL")
    user_agent = f"{identity} {email}"

    if not identity or not email:
        raise ValueError("EDGAR_IDENTITY and EDGAR_EMAIL must be set in .env")

    user_agent = f"{identity} {email}"
    cik_mapper = CIKMapper(user_agent=user_agent)

    print("Fetching recent 8-K filings...")
    # We are using a fixed date here for testing since the system clock is set to the future.
    # This ensures we can test with real, historical data.
    recent_filings_df = get_recent_8k_filings(base_date_str="2025-06-28", days_ago=0, user_agent=user_agent)

    if recent_filings_df.empty:
        print("No recent 8-K filings found.")
        return

    print(f"Found {len(recent_filings_df)} filings. Processing first 5...")
    processed_filings = []

    for i, (_, row) in enumerate(recent_filings_df.head().iterrows()):
        file_name = row['file_name']
        content = fetch_filing_text(file_name, user_agent)

        if not content:
            print(f"Skipping {file_name} due to content retrieval failure.")
            continue

        header_data = parse_filing_header(content)

        action_type = classify_action_type(content)

        cik = header_data.get('cik', '')
        ticker = cik_mapper.get_ticker(cik) if cik else 'N/A'

        filing = CorporateActionFiling(
            accession_number=header_data.get('accession_number', 'N/A'),
            company_name=header_data.get('company_name', 'N/A'),
            ticker=ticker,
            form_type=header_data.get('form_type', 'N/A'),
            filed_as_of_date=header_data.get('filed_as_of_date', 'N/A'),
            date_as_of_change=header_data.get('date_as_of_change', 'N/A'),
            action_type=action_type,
            file_name=file_name,
            content=content
        )
        processed_filings.append(filing)

    print("\n--- Processed Corporate Action Filings ---")
    for filing in processed_filings:
        print(f"\nCompany: {filing.company_name} ({filing.ticker})")
        print(f"Action Type: {filing.action_type}")
        print(f"Form Type: {filing.form_type}")
        print(f"Filed Date: {filing.filed_as_of_date}")
        print(f"Accession No.: {filing.accession_number}")
        print("Content Snippet:")
        print(f"{filing.content[:200]}...")
    print("-----------------------------------------")

    # Send notifications
    await send_to_telegram(processed_filings)
    # send_to_email(processed_filings)


if __name__ == "__main__":
    asyncio.run(main())
