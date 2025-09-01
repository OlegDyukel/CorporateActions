# Corporate Actions Notifier

This project tracks and reports corporate action events across multiple markets (U.S., Europe, Japan, etc.). It currently ships with a U.S. SEC EDGAR connector and a pluggable architecture to add others. It fetches recent announcements/filings, parses them, classifies the event, and sends notifications via Telegram, email, Slack and API (Slack/webhooks planned).

## How It Works

The application follows a simple data processing pipeline:

1.  **Discover sources**: Iterate over the enabled market connectors (e.g., SEC EDGAR, EU/JP sources).
2.  **Fetch listings/feeds**: Download daily indexes or RSS/JSON feeds for recent announcements/filings.
3.  **Fetch full content**: Retrieve the full text or HTML for each item.
4.  **Parse & normalize**: Extract headers/metadata and normalize into the internal `CorporateAction` model.
5.  **Classify corporate actions**: Determine event types (e.g., merger, dividend, split).
6.  **Enrich**: Map to tickers/exchanges and add context as available per market.
7.  **Notify**: Load into a database and (optionally) send formatted summaries to configured channels.

## Features

- **Pluggable source connectors**: SEC EDGAR implemented; add EU/JP/etc. by creating new modules in `src/sources/`.
- **Corporate action classification**: Classifies events such as mergers, dividends, splits, and more.
- **Normalization to a common model**: Everything is mapped to `CorporateAction` (Pydantic v2) for consistent processing.
- **Enrichment**: CIK → ticker/exchange via `src/utils/cik_mapper.py` (US); additional mappers can be added per market.
- **Multi-channel notifications**: Telegram and Gmail supported today; Slack/webhooks are on the roadmap.
- **Resilient**: Handles days with no data and works across market holidays.

## Project Structure

```
README.md                      # Project overview
requirements.txt               # Python dependencies
.env                           # Environment variables (create manually)
src/
├── main.py                    # Entry point; runs the default SEC pipeline
├── config.py                  # Loads environment variables
├── core/                      # Future orchestrators/pipelines
├── models/
│   ├── corporate_action_model.py  # CorporateAction data model (Pydantic v2)
│   └── filing.py                  # Legacy simple model (deprecated)
├── processors/
│   ├── filing_processor.py    # Fetches full filing text/content
│   ├── filing_parser.py       # Parses content and classifies actions
│   └── html_parser.py         # Converts SEC HTML to clean text
├── sources/
│   └── master_index.py        # SEC EDGAR connector (daily master index)
├── utils/
│   ├── cik_mapper.py          # Maps CIK -> ticker/exchange (US)
│   └── filing_link_converter.py # Converts .txt to HTML filing link
└── notifiers/                 # Placeholder for future notifier modules
tests/                         # Test suite (WIP)
```

## Setup and Usage

### 1. Prerequisites

- Python 3.9+
- Internet access; respect each source’s terms of use and robots policies.
- For the default U.S. SEC connector: `EDGAR_IDENTITY` and `EDGAR_EMAIL` to form a compliant User-Agent.
- Optional: Telegram Bot Token and Channel ID for Telegram notifications.
- Optional: Gmail account (or SMTP app password) for email notifications.

### 2. Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/CorporateActions.git
    cd CorporateActions
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

### 3. Configuration

1.  **Create a `.env` file** in the project root.

2.  **Populate** it with the following keys (EDGAR is required for the default U.S. SEC connector):

    ```env
    # SEC EDGAR Credentials (Required for default U.S. SEC connector)
    EDGAR_IDENTITY="Your Name or Company"
    EDGAR_EMAIL="your.email@example.com"

    # Telegram Bot Credentials (Optional)
    TELEGRAM_BOT_TOKEN="your-bot-token"
    TELEGRAM_CHANNEL_ID="@your-channel-id"

    # Email Credentials (Optional)
    EMAIL_SENDER_ADDRESS="your-email@gmail.com"
    EMAIL_SENDER_PASSWORD="your-app-password"
    EMAIL_RECIPIENTS="recipient1@example.com,recipient2@example.com"
    ```

### 4. Running the Application

Execute the `main.py` script to start the process:

```bash
python src/main.py
```

The script will fetch filings for the most recent business day, process them, print the results to the console, and send notifications if configured.
