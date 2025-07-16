import sys
from pathlib import Path

# This block must be the first thing in the file to ensure
# that the 'src' module can be found by Python.
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Now that the path is set, we can import our modules
import asyncio
import os
from typing import List
import telegram
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

from src.models.filing import CorporateActionFiling
from src.sources.master_index import get_recent_8k_filings
from src.processors.filing_processor import fetch_filing_text
from src.processors.filing_parser import parse_filing_header, classify_action_type
from src.utils.cik_mapper import CIKMapper
from src.utils.filing_link_converter import convert_txt_link_to_html

# Load environment variables from the .env file in the project root
dotenv_path = project_root / ".env"
# Use override=True to ensure .env variables take precedence over system variables
load_dotenv(dotenv_path=dotenv_path, override=True)


def format_filing_for_display(filing: CorporateActionFiling) -> str:
    """Formats a single filing for a readable display."""
    return (
        f"<b>Company:</b> {filing.company_name}\n"
        f"<b>Trading Ticker:</b> {filing.ticker}\n"
        f"<b>Exchange:</b> {filing.exchange}\n"
        f"<b>Action Type:</b> {filing.action_type}\n"
        f"<b>Form Type:</b> {filing.form_type}\n"
        f"<b>Filed Date:</b> {filing.filed_as_of_date}\n"
        f"<b>Accession No.:</b> {filing.accession_number}\n"
        f"<a href='{filing.html_link}'>Link to Filing</a>"
    )


async def send_to_telegram(filings: List[CorporateActionFiling]):
    """Sends the list of processed filings to a Telegram channel."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")

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


def send_gmail_email(filings: List[CorporateActionFiling]):
    """Sends the list of processed filings via Gmail SMTP."""
    # --- Get Gmail credentials from environment variables ---
    sender_address = os.getenv("EMAIL_SENDER_ADDRESS")
    sender_password = os.getenv("EMAIL_SENDER_PASSWORD")
    recipients = os.getenv("EMAIL_RECIPIENTS")

    if not all([sender_address, sender_password, recipients]):
        print("Gmail credentials or recipients not found in .env file. Skipping.")
        return

    # --- Format the email content ---
    subject = "Daily Corporate Actions Digest (via Gmail)"
    html_body = "<h1>Latest Corporate Action Filings</h1>"
    html_body += "<hr>".join([format_filing_for_display(f) for f in filings])
    
    # Create the plain text version as a fallback
    text_body = "Latest Corporate Action Filings\n\n"
    text_body += "\n---\n".join([
        f"Company: {f.company_name} ({f.ticker})\n"
        f"Action Type: {f.action_type}\n"
        f"Filed Date: {f.filed_as_of_date}"
        for f in filings
    ])

    # --- Create and send the email message ---
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_address
    msg["To"] = recipients
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype='html')

    print("\n--- Sending filings to Gmail ---")
    try:
        # Use SMTP with STARTTLS for port 587
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()  # Secure the connection
            server.login(sender_address, sender_password)
            server.send_message(msg)
        print("Email sent successfully via Gmail!")
        print("--------------------------------")
    except smtplib.SMTPException as e:
        print(f"[Gmail Error] Failed to send email: {e}")


async def main():
    # Load EDGAR identity from environment variables for the User-Agent string.
    identity = os.getenv("EDGAR_IDENTITY")
    email = os.getenv("EDGAR_EMAIL")

    if not identity or not email:
        print("EDGAR_IDENTITY or EDGAR_EMAIL not found in .env file. Exiting.")
        return
    user_agent = f"{identity} {email}"
    cik_mapper = CIKMapper(user_agent=user_agent)

    print("Fetching recent 8-K filings...")
    # Fetches filings from the most recent business day.
    # The function will search backwards from yesterday to find the last day with available data.
    recent_filings_df = get_recent_8k_filings(days_ago=1, user_agent=user_agent)

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

        cik = header_data.get('CENTRAL INDEX KEY', 'N/A')
        print(f"DEBUG: Processing {header_data.get('COMPANY CONFORMED NAME', 'N/A')} with CIK {cik}")
        ticker = cik_mapper.get_ticker_by_cik(cik) or 'N/A'
        exchange = cik_mapper.get_exchange_by_cik(cik) or 'N/A'
        print(f"DEBUG: Found Ticker: {ticker}, Exchange: {exchange}")

        # Construct the full .txt URL to pass to the converter
        txt_url = f"https://www.sec.gov/Archives/{file_name}"
        html_link = convert_txt_link_to_html(txt_url, user_agent)

        filing = CorporateActionFiling(
            cik=cik,
            company_name=header_data.get('COMPANY CONFORMED NAME', 'N/A'),
            form_type=header_data.get('CONFORMED SUBMISSION TYPE', 'N/A'),
            filed_as_of_date=header_data.get('FILED AS OF DATE', 'N/A'),
            accession_number=header_data.get('ACCESSION NUMBER', 'N/A'),
            ticker=ticker,
            exchange=exchange,
            action_type=action_type,
            file_name=file_name,
            content=content,
            html_link=html_link or txt_url  # Fallback to .txt link if conversion fails
        )
        processed_filings.append(filing)

    print("\n--- Processed Corporate Action Filings ---")
    for filing in processed_filings:
        print(f"\nCompany: {filing.company_name} ({filing.ticker}:{filing.exchange})")
        print(f"Action Type: {filing.action_type}")
        print(f"Form Type: {filing.form_type}")
        print(f"Filed Date: {filing.filed_as_of_date}")
        print(f"Accession No.: {filing.accession_number}")
        print("Content Snippet:")
        print(f"{filing.content[:200]}...")
    print("-----------------------------------------")

    # Send notifications
    await send_to_telegram(processed_filings)

    # Send notifications via Gmail
    await asyncio.to_thread(send_gmail_email, processed_filings)


if __name__ == "__main__":
    asyncio.run(main())
