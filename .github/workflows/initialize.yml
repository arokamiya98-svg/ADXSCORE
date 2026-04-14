name: Initialize History (Run Once)

on:
  workflow_dispatch:   # 手動実行のみ（自動実行なし）

permissions:
  contents: write

jobs:
  init:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install requests

      - name: Run History Initialization
        env:
          TWELVE_DATA_API_KEY: ${{ secrets.TWELVE_DATA_API_KEY }}
        run: python scripts/initialize_history.py

      - name: Generate HTML Report
        run: python scripts/generate_html.py

      - name: Commit & Push
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/scores.json docs/index.html
          git diff --cached --quiet || git commit -m "init: historical ADX scores from 2025-01-01"
          git push
