# Corporate Actions Notifier

This project automates the process of tracking and reporting corporate action events from U.S. Securities and Exchange Commission (SEC) EDGAR filings. It fetches daily 8-K filings, parses them to identify significant corporate events, and sends notifications via Telegram and email.

## How It Works

The application follows a simple data processing pipeline:

1.  **Fetch Index Files**: It starts by downloading the daily master index file from the SEC EDGAR database. These files contain a list of all filings submitted on a given day.
2.  **Identify 8-K Filings**: From the master index, it filters for Form 8-K filings, which are used to announce major events that shareholders should know about.
3.  **Fetch Filing Content**: For each 8-K filing identified, it fetches the full text content from the SEC archives.
4.  **Parse and Classify**: The content of each filing is then parsed to extract key metadata from the header (e.g., company name, CIK, filing date). The system also scans the text to classify the type of corporate action (e.g., Merger/Acquisition, Dividend, Bankruptcy).
5.  **Enrich Data**: The company's Central Index Key (CIK) is used to look up its stock ticker symbol, providing more context.
6.  **Send Notifications**: Finally, formatted summaries of the processed filings are sent out to a configured Telegram channel and/or a list of email recipients.

## Features

- **Automated 8-K Filings Retrieval**: Automatically fetches the latest 8-K filings from the SEC.
- **Corporate Action Classification**: Intelligently classifies filings into categories like 'Merger/Acquisition', 'Dividend', 'Stock Split', and more.
- **CIK to Ticker Mapping**: Enriches filing data with stock ticker symbols.
- **Multi-Channel Notifications**: Delivers alerts via Telegram and email.
- **Extensible**: Designed with a modular structure to easily support new data sources or notification channels.
- **Resilient**: Includes logic to handle days with no SEC filings (e.g., weekends and holidays).

## Project Structure

```
.env.example         # Example environment variables
README.md            # This file
requirements.txt     # Python dependencies
src/
├── main.py            # Main application entry point
├── models/
│   └── filing.py      # Defines the CorporateActionFiling data model
├── processors/
│   ├── filing_parser.py   # Parses filing content and classifies actions
│   └── filing_processor.py# Fetches full filing text
├── sources/
│   └── master_index.py  # Fetches and parses the SEC master index
└── utils/
    └── cik_mapper.py    # Utility for mapping CIKs to tickers
```

## Setup and Usage

### 1. Prerequisites

- Python 3.9+
- An account with the SEC EDGAR system to get a User-Agent string.
- A Telegram Bot Token and Channel ID (optional).
- An email account for sending notifications (optional).

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

1.  **Create a `.env` file** in the project root by copying the example:
    ```bash
    cp .env.example .env
    ```

2.  **Edit the `.env` file** with your credentials. The `EDGAR_IDENTITY` and `EDGAR_EMAIL` are required for making requests to the SEC.

    ```env
    # SEC EDGAR Credentials (Required)
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
