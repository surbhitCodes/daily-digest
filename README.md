# AI Daily Digest

A Python application that fetches the latest tech/AI articles from RSS feeds, summarizes them using OpenAI's GPT-4 model, and sends the digest to Slack.

## Features

- Fetches latest articles from multiple RSS feeds
- Summarizes articles using OpenAI's GPT-4 model
- Sends daily digest to Slack
- Web interface with manual trigger option
- Scheduled daily runs at 8:00 AM

## Prerequisites

- Python 3.8+
- OpenAI API key
- Slack Webhook URL (for notifications)
- Gmail account (optional, for email notifications)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/daily-digest.git
   cd daily-digest
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your configuration:
   ```env
   OPENAI_API_KEY=your_openai_api_key
   SLACK_WEBHOOK_URL=your_slack_webhook_url
   EMAIL_FROM=your_email@gmail.com
   EMAIL_TO=recipient@example.com
   ```

## Usage

1. Run the application:
   ```bash
   python main.py
   ```

2. Access the web interface at `http://localhost:8000`

3. Manually trigger a digest by visiting `http://localhost:8000/trigger`

## Configuration

Edit `rss_sources.py` to add or modify the list of RSS feeds to monitor.

## Scheduled Runs

The application is configured to run automatically at 8:00 AM daily. You can modify this in `main.py` by changing the cron schedule in the `start_scheduler` function.

## License

Copyright (c) 2025 Surbhit Kumar

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.
