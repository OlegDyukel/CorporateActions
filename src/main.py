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
from typing import List, Optional
import telegram
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

from src.models.corporate_action_model import (
    CorporateAction,
    ActionType,
    DocType,
    SourceSystem,
    IssuerRef,
    SecurityRef,
    SourceInfo,
)
from src.sources.master_index import get_recent_8k_filings
from src.processors.filing_processor import fetch_filing_text
from src.processors.filing_parser import parse_filing_header, classify_action_type
from src.processors.html_parser import parse_html_to_text
from src.utils.cik_mapper import CIKMapper
from src.utils.filing_link_converter import convert_txt_link_to_html

# Load environment variables from the .env file in the project root
dotenv_path = project_root / ".env"
# Use override=True to ensure .env variables take precedence over system variables
load_dotenv(dotenv_path=dotenv_path, override=True)

def _map_form_to_doc_type(form_type: str) -> str:
    form = (form_type or "").upper()
    if form.startswith("8-K"):
        return DocType.EIGHT_K
    if form.startswith("6-K"):
        return DocType.SIX_K
    if form == "10-K":
        return DocType.TEN_K
    if form == "10-Q":
        return DocType.TEN_Q
    return DocType.OTHER


def _map_classification_to_action_type(classification: str) -> str:
    c = (classification or "").lower()
    if "bankruptcy" in c:
        return ActionType.BANKRUPTCY
    # For now, default to OTHER to avoid strict term validators when details are missing
    return ActionType.OTHER


def _parse_filed_date(date_str: str):
    from datetime import datetime
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _to_mic(exchange_name: str) -> str:
    if not exchange_name:
        return None
    # Minimal heuristic mapping; extend as needed
    mapping = {
        "NASDAQ": "XNAS",
        "NYSE": "XNYS",
        "NYSE AMERICAN": "XASE",
        "NYSE MKT": "XASE",
        "NYSE ARCA": "ARCX",
        "CBOE BZX": "BATS",
        "CBOE BYX": "BATY",
        "CBOE EDGX": "EDGX",
        "CBOE EDGA": "EDGA",
        "OTC": "OTCM",
    }
    key = exchange_name.strip().upper()
    return mapping.get(key)


def _first_source(filing: CorporateAction) -> Optional[SourceInfo]:
    return filing.sources[0] if filing.sources else None


def format_filing_for_display(filing: CorporateAction) -> str:
    """Formats a single CorporateAction for a readable display."""
    src = _first_source(filing)
    doc_type = src.doc_type if src else "N/A"
    filed_date = src.filing_date.isoformat() if (src and src.filing_date) else "N/A"
    accession = src.reference_id if src and src.reference_id else "N/A"
    link = src.source_url if src and src.source_url else "#"
    classification_note = filing.notes or ""
    return (
        f"<b>Company:</b> {filing.issuer.name or 'N/A'}\n"
        f"<b>Trading Ticker:</b> {filing.security.ticker or 'N/A'}\n"
        f"<b>Exchange:</b> {filing.security.exchange_mic or 'N/A'}\n"
        f"<b>Action Type:</b> {filing.action_type}\n"
        + (f"<b>Classification:</b> {classification_note}\n" if classification_note else "")
        + f"<b>Form Type:</b> {doc_type}\n"
        + f"<b>Filed Date:</b> {filed_date}\n"
        + f"<b>Accession No.:</b> {accession}\n"
        + f"<a href='{link}'>Link to Filing</a>"
    )


async def send_to_telegram(filings: List[CorporateAction]):
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


def send_gmail_email(filings: List[CorporateAction]):
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
    lines = []
    for f in filings:
        src = _first_source(f)
        filed_date = src.filing_date.isoformat() if (src and src.filing_date) else "N/A"
        lines.append(
            "\n".join([
                f"Company: {f.issuer.name or 'N/A'} ({f.security.ticker or 'N/A'})",
                f"Action Type: {f.action_type}",
                f"Filed Date: {filed_date}",
            ])
        )
    text_body += "\n---\n".join(lines)

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
    processed_filings: List[CorporateAction] = []

    for i, (_, row) in enumerate(recent_filings_df.head().iterrows()):
        file_name = row['file_name']
        content = fetch_filing_text(file_name, user_agent)

        if not content:
            print(f"Skipping {file_name} due to content retrieval failure.")
            continue

        header_data = parse_filing_header(content)

        classification = classify_action_type(content)

        cik = header_data.get('CENTRAL INDEX KEY', 'N/A')
        print(f"DEBUG: Processing {header_data.get('COMPANY CONFORMED NAME', 'N/A')} with CIK {cik}")
        ticker = cik_mapper.get_ticker_by_cik(cik) or 'N/A'
        exchange = cik_mapper.get_exchange_by_cik(cik) or None
        exchange_mic = _to_mic(exchange) if exchange else None
        print(f"DEBUG: Found Ticker: {ticker}, Exchange: {exchange} -> MIC: {exchange_mic}")

        # Construct the full .txt URL to pass to the converter
        txt_url = f"https://www.sec.gov/Archives/{file_name}"
        html_link = convert_txt_link_to_html(txt_url, user_agent)

        # Parse the HTML content to get clean text
        parsed_text = parse_html_to_text(html_link, user_agent)

        form_type_str = header_data.get('CONFORMED SUBMISSION TYPE', 'N/A')
        filed_as_of = header_data.get('FILED AS OF DATE', '')
        accession_number = header_data.get('ACCESSION NUMBER', 'N/A')

        ca = CorporateAction(
            action_type=_map_classification_to_action_type(classification),
            issuer=IssuerRef(
                name=header_data.get('COMPANY CONFORMED NAME', None),
                cik=cik if cik and cik != 'N/A' else None,
            ),
            security=SecurityRef(
                ticker=ticker if ticker and ticker != 'N/A' else None,
                exchange_mic=exchange_mic,
            ),
            sources=[
                SourceInfo(
                    source=SourceSystem.SEC_EDGAR,
                    doc_type=_map_form_to_doc_type(form_type_str),
                    source_url=html_link or txt_url,
                    filing_date=_parse_filed_date(filed_as_of),
                    reference_id=accession_number if accession_number and accession_number != 'N/A' else None,
                    text_excerpt=(parsed_text[:300] if parsed_text else None),
                )
            ],
            notes=(f"classification: {classification}" if classification else None),
        )
        processed_filings.append(ca)

    print("\n--- Processed Corporate Action Filings ---")
    for ca in processed_filings:
        src = _first_source(ca)
        doc_type = src.doc_type if src else 'N/A'
        filed_date = src.filing_date.isoformat() if (src and src.filing_date) else 'N/A'
        accession = src.reference_id if (src and src.reference_id) else 'N/A'
        print(f"\nCompany: {ca.issuer.name or 'N/A'} ({(ca.security.ticker or 'N/A')}:{(ca.security.exchange_mic or 'N/A')})")
        print(f"Action Type: {ca.action_type} | {ca.notes or ''}")
        print(f"Form Type: {doc_type}")
        print(f"Filed Date: {filed_date}")
        print(f"Accession No.: {accession}")
        if src and src.text_excerpt:
            print("Parsed Text Snippet:")
            print(f"{src.text_excerpt[:200]}...")
    print("-----------------------------------------")

    # Send notifications
    await send_to_telegram(processed_filings)

    # Send notifications via Gmail
    await asyncio.to_thread(send_gmail_email, processed_filings)


if __name__ == "__main__":
    asyncio.run(main())
