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
from src.processors.llm_extractor import llm_extract, apply_llm_to_corporate_action
from src.utils.exchange_resolver import get_exchange_resolver
from src.core.ca_repository import persist_corporate_actions
from src.processors.effective_date_resolver import (
    resolve_effective_date,
    format_estimate_for_display,
)
from src.sources.sec_submissions import get_recent_company_filings
from src.utils.metrics import Metrics

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


def _to_mic(exchange_name: Optional[str]) -> Optional[str]:
    if not exchange_name:
        return None
    resolver = get_exchange_resolver()
    return resolver.to_mic(exchange_name)


def _mic_to_exchange_name(mic: Optional[str]) -> Optional[str]:
    if not mic:
        return None
    resolver = get_exchange_resolver()
    return resolver.mic_to_name(mic)


def _first_source(filing: CorporateAction) -> Optional[SourceInfo]:
    return filing.sources[0] if filing.sources else None


def _merge_extras(base: Optional[dict], patch: Optional[dict]) -> Optional[dict]:
    if not patch:
        return base
    if not base:
        return dict(patch)
    merged = dict(base)
    merged.update(patch)
    return merged


def format_filing_for_display(filing: CorporateAction) -> str:
    """Formats a single CorporateAction for a readable display."""
    src = _first_source(filing)
    doc_type = src.doc_type if src else "N/A"
    filed_date = src.filing_date.isoformat() if (src and src.filing_date) else "N/A"
    accession = src.reference_id if src and src.reference_id else "N/A"
    link = src.source_url if src and src.source_url else "#"
    classification_note = filing.notes or ""
    # Determine effective/estimated text
    effective_line = (
        f"<b>Effective Date:</b> {filing.effective_date.isoformat()}\n"
        if filing.effective_date
        else (
            (lambda est: f"<b>Estimated Effective:</b> {est}\n" if est else "")(
                format_estimate_for_display(getattr(filing, "extras", None))
            )
        )
    )
    return (
        f"<b>Company:</b> {filing.issuer.name or 'N/A'}\n"
        f"<b>Trading Ticker:</b> {filing.security.ticker or 'N/A'}\n"
        f"<b>Exchange:</b> {_mic_to_exchange_name(filing.security.exchange_mic) if filing.security.exchange_mic else 'N/A'}\n"
        ""
        + (f"<b>Classification:</b> {classification_note}\n" if classification_note else "")
        + f"<b>Form Type:</b> {doc_type}\n"
        + f"<b>Filed Date:</b> {filed_date}\n"
        + effective_line
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
        est_txt = None
        if not f.effective_date:
            est_txt = format_estimate_for_display(getattr(f, "extras", None))
        lines.append(
            "\n".join([
                f"Company: {f.issuer.name or 'N/A'} ({f.security.ticker or 'N/A'})",
                f"Filed Date: {filed_date}",
                (
                    f"Effective Date: {f.effective_date.isoformat()}"
                    if f.effective_date
                    else (f"Estimated Effective: {est_txt}" if est_txt else "")
                ),
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
    recent_filings_df = get_recent_8k_filings(days_ago=0, user_agent=user_agent)

    if recent_filings_df.empty:
        print("No recent 8-K filings found.")
        return

    print(f"Found {len(recent_filings_df)} filings. Processing first 5...")
    processed_filings: List[CorporateAction] = []
    metrics = Metrics()

    for i, (_, row) in enumerate(recent_filings_df.head().iterrows()):
        file_name = row['file_name']
        content = fetch_filing_text(file_name, user_agent)

        if not content:
            print(f"Skipping {file_name} due to content retrieval failure.")
            continue

        header_data = parse_filing_header(content)

        classification = classify_action_type(content)

        cik = header_data.get('CENTRAL INDEX KEY', 'N/A')
        print(f"Processing {header_data.get('COMPANY CONFORMED NAME', 'N/A')} with CIK {cik}")
        ticker = cik_mapper.get_ticker_by_cik(cik) or 'N/A'
        exchange = cik_mapper.get_exchange_by_cik(cik) or None
        exchange_mic = _to_mic(exchange) if exchange else None
        print(f"Found Ticker: {ticker}, Exchange: {exchange} -> MIC: {exchange_mic}")

        # Collect all tickers for this CIK and compute extras for details
        all_tickers = cik_mapper.get_all_tickers_by_cik(cik) or []
        primary = None if ticker == 'N/A' else ticker
        extra_tickers = [t for t in all_tickers if (primary and t != primary)]
        if all_tickers:
            print(f"Tickers for CIK {cik}: all={all_tickers} primary={primary} extras={extra_tickers}")

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
            extras={
                "all_tickers": all_tickers,
                "extra_tickers": extra_tickers,
                "primary_ticker": primary,
            } if all_tickers else None,
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
            notes=(classification if classification else None),
        )
        
        # LLM extraction pass (safe/no-op if disabled or not configured)
        llm_res = None
        if parsed_text:
            try:
                llm_res = llm_extract(parsed_text, company=header_data.get('COMPANY CONFORMED NAME', None))
                if llm_res:
                    ca = apply_llm_to_corporate_action(ca, llm_res)
            except Exception as e:
                print(f"LLM extraction skipped due to error: {e}")

        # Phase 1: If effective_date is still missing, try date enrichment using LLM estimates
        try:
            enrich_enabled = os.getenv("LLM_DATE_ENRICHMENT_ENABLED", "true").strip().lower() in {"1", "true", "yes"}
            followup_enabled = os.getenv("SEC_FOLLOWUP_ENABLED", "true").strip().lower() in {"1", "true", "yes"}
        except Exception:
            enrich_enabled, followup_enabled = True, True

        candidates = []
        promoted_date = None
        followup_used_flag = False
        if enrich_enabled and not ca.effective_date:
            # From primary LLM pass
            if llm_res and getattr(llm_res, "effective_date_estimates", None):
                try:
                    for c in llm_res.effective_date_estimates or []:
                        candidates.append({**c.model_dump(exclude_none=True), "method": "llm_primary"})
                except Exception:
                    pass

            # Phase 2 (optional): SEC submissions follow-up across a few recent filings
            if followup_enabled and cik and cik != 'N/A':
                try:
                    followups = get_recent_company_filings(cik, user_agent, limit=3, form_filter=[
                        "8-K", "8-K/A", "DEFM14A", "DEFA14A", "S-4", "S-4/A", "425", "424B2", "424B3"
                    ])
                    for fu in followups:
                        fu_url = fu.get("html_url") or fu.get("txt_url")
                        if not fu_url or fu_url == (html_link or txt_url):
                            continue
                        fu_text = parse_html_to_text(fu_url, user_agent)
                        if not fu_text:
                            continue
                        fu_res = llm_extract(fu_text, company=header_data.get('COMPANY CONFORMED NAME', None))
                        if not fu_res:
                            continue
                        if getattr(fu_res, "effective_date", None):
                            candidates.append({
                                "kind": "definitive",
                                "date": fu_res.effective_date,
                                "qualifier": "from follow-up filing",
                                "confidence": 0.9,
                                "method": "llm_followup",
                                "source_url": fu_url,
                            })
                        if getattr(fu_res, "effective_date_estimates", None):
                            for c in fu_res.effective_date_estimates or []:
                                cand = {**c.model_dump(exclude_none=True), "method": "llm_followup", "source_url": fu_url}
                                candidates.append(cand)
                except Exception as e:
                    print(f"[Follow-up] Skipped due to error: {e}")

            # Resolve and possibly promote
            if candidates:
                try:
                    promoted_date, extras_patch = resolve_effective_date(candidates=candidates)
                    if promoted_date:
                        ca = ca.model_copy(update={"effective_date": promoted_date})
                    # Attach extras for display/persistence
                    new_extras = _merge_extras(ca.extras, {
                        **extras_patch,
                        "date_enrichment": True,
                        "followup_used": any((c.get("method") == "llm_followup") for c in candidates),
                        "followup_candidates": len(candidates),
                    })
                    ca = ca.model_copy(update={"extras": new_extras})
                except Exception as e:
                    print(f"[Resolver] Error resolving effective date: {e}")
        # Record metrics for this filing
        try:
            followup_used_flag = any((c.get("method") == "llm_followup") for c in candidates)
            metrics.record(
                effective_date=bool(ca.effective_date),
                had_estimate=bool(candidates),
                promoted=bool(promoted_date),
                followup_used=followup_used_flag,
            )
        except Exception:
            pass
        processed_filings.append(ca)

    # Persist results to the database (public schema)
    try:
        saved = persist_corporate_actions(processed_filings)
        print(f"\n[DB] Persisted {saved} corporate actions to the database.")
    except Exception as e:
        print(f"[DB Error] Failed to persist filings: {e}")

    print("\n--- Processed Corporate Action Filings ---")
    for ca in processed_filings:
        src = _first_source(ca)
        doc_type = src.doc_type if src else 'N/A'
        filed_date = src.filing_date.isoformat() if (src and src.filing_date) else 'N/A'
        accession = src.reference_id if (src and src.reference_id) else 'N/A'
        print(f"\nCompany: {ca.issuer.name or 'N/A'} ({(ca.security.ticker or 'N/A')}:{(_mic_to_exchange_name(ca.security.exchange_mic) if ca.security.exchange_mic else 'N/A')})")
        print(f"Action Type: {ca.action_type} | {ca.notes or ''}")
        print(f"Form Type: {doc_type}")
        print(f"Filed Date: {filed_date}")
        print(f"Accession No.: {accession}")
        if src and src.text_excerpt:
            print("Parsed Text Snippet:")
            print(f"{src.text_excerpt[:200]}...")
    print("-----------------------------------------")

    # Send notifications via Telegram
    await send_to_telegram(processed_filings)

    # Send notifications via Gmail
    await asyncio.to_thread(send_gmail_email, processed_filings)

    # Metrics summary and optional persistence
    try:
        metrics.print_summary()
        metrics_file = os.getenv("METRICS_FILE")
        if metrics_file:
            metrics.save_jsonl(metrics_file)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
