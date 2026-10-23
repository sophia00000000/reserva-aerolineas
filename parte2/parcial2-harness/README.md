# Parcial 2 - test harness
Setup (once):
```
pip install -r requirements.txt && playwright install chromium
cp config.example.yaml config.yaml      # set your seed, backend/frontend URLs, Athena database and tables
```
Generate your raw data with your team's seed:
```
python -m airline_data.generate --seed <YOUR_SEED> --rows 2000000 --out raw/
```
Run the checks (writes report.json and report.md):
```
pytest
```
Contracts (API, tables, frontend selectors, cost file) are in `contract/`. Do not edit `thresholds.yaml`
or anything under `harness/` or `tests/`: the instructor runs his own copy.
Use your normal AWS credentials (environment or ~/.aws). Never commit them.
