# Corporate_AI

## Project Structure

```
├── configs/               # Central configuration files
├── data/                  # Local data storage
│   ├── processed/         # Processed data
│   ├── raw/               # Raw inputs (not tracked by Git)
│   └── synthetic/         # Generated synthetic datasets
├── notebooks/             # Research & exploration notebooks
├── src/                   # Core source code
│   ├── ingestion/         # Multi-format data parser, vault & extractor
│   ├── synthesis/         # Local Ollama & statistical synthesis engine
│   └── agent/             # Downstream enterprise AI agent
├── pyproject.toml         # UV project configuration
└── requirements.txt       # Python dependencies
```
