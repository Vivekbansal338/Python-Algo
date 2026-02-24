# Running TradingBot V6 in Google Colab

## Can You Run This in Colab?

✅ **YES - for Backtesting**  
❌ **NO - for Live Paper Trading**

---

## What WORKS in Colab ✅

### Backtest Mode

- Read historical parquet data from `backtest_v6/data/`
- Run strategy analysis and signal generation
- Simulate trades without live connections
- Export results to CSV
- One-time runs up to a few hours

### Example

```python
!pip install pandas numpy
!cd /content/TradingBot && python backtest_v6/sector_engine_v6.py --start 2026-02-01 --end 2026-02-23 --export
```

---

## What WON'T WORK in Colab ❌

### Live Paper Trading Bot (`v6/main.py`)

**Reason 1: WebSocket Persistence**

- Requires continuous Zerodha API WebSocket connection
- Colab sessions disconnect after ~12 hours of inactivity
- Market hours (9:15 AM - 3:30 PM IST) = only ~6 hours
- WebSocket needs manual restart per session

**Reason 2: State Persistence**

- Trading state saved to local files
- Colab's local filesystem resets per session
- Live positions/orders lost after disconnect

**Reason 3: Timing Requirements**

- Bot must run continuously during market hours
- Colab is designed for sporadic, not persistent execution
- Automatic timeouts break long-running processes

---

## Minimal Dependencies for Backtest

For backtest-only mode, you need **only 2 packages**:

```python
!pip install pandas numpy
```

| Package         | Needed? | Why                                         |
| --------------- | ------- | ------------------------------------------- |
| `pandas`        | ✅ YES  | Read/write parquet files                    |
| `numpy`         | ✅ YES  | Indicator calculations (ATR, HMA, StochRSI) |
| `kiteconnect`   | ❌ NO   | Only for live API connections               |
| `python-dotenv` | ❌ NO   | Only for loading `.env` credentials         |

---

## Folder Structure to Upload

Upload **only ~10% of the project**:

```
TradingBot/
├── backtest_v6/              ← MUST HAVE
│   ├── sector_engine_v6.py
│   ├── data_miner_v6.py
│   ├── __init__.py
│   └── data/
│       ├── daily/            ← Your parquet files
│       └── 5minute/          ← Your parquet files
├── v6/                       ← MUST HAVE
│   ├── config.py
│   ├── brain.py
│   ├── data_engine.py
│   ├── execution.py
│   └── __init__.py
└── config/
    └── universe.json         ← MUST HAVE
```

**Skip uploading:**

- ❌ `backtest_v5/` (old version)
- ❌ `zerodha_docs_python/` (documentation)
- ❌ `zerodha_tests/` (tests)
- ❌ `docs/`, `issues/` (documentation folders)
- ❌ `data/` (live trading state files)
- ❌ `.venv/` (Colab has its own Python)
- ❌ `__pycache__/` (cache directories)
- ❌ Debug/utility scripts

**Size reduction: ~90% smaller**

---

## Step-by-Step Colab Setup

### Option 0: Upload Directly from Desktop (Simplest)

**Best for:** Quick testing, one-time backtests, no Google Drive needed

#### Step 1: Create Colab notebook

1. Go to [colab.research.google.com](https://colab.research.google.com)
2. Click **File → New notebook**

#### Step 2: Upload your folder to Colab

```python
# In first cell of Colab, run this:
from google.colab import files
uploaded = files.upload()

# A file picker will appear
# Select your TradingBot folder (or a zip of it)
```

#### Step 3: Extract and navigate

```python
import os
import shutil

# If you uploaded a zip file:
!unzip -q "TradingBot.zip"

# Navigate to project
os.chdir('/content/TradingBot')
!ls -la
```

#### Step 4: Install dependencies

```python
!pip install pandas numpy -q
```

#### Step 5: Run backtest

```python
!python backtest_v6/sector_engine_v6.py \
  --start 2026-02-01 \
  --end 2026-02-23 \
  --export
```

#### Step 6: Download results back to desktop

```python
from google.colab import files

# Download backtest results
files.download('backtest_v6/data/backtest_trades_v6.csv')

# Or download entire results folder
!zip -r results.zip backtest_v6/data/
files.download('results.zip')
```

---

**Pros:**

- ✅ No Google Drive login needed
- ✅ Fastest setup (5 minutes)
- ✅ Upload/download via browser
- ✅ Isolated work (won't clutter Drive)

**Cons:**

- ❌ Files deleted when Colab session ends
- ❌ Can't reuse between sessions
- ❌ Slower for repeated runs

---

### Option 1: Upload Minimal Folder (Recommended for repeated use)

```python
# 1. Mount Google Drive
from google.colab import drive
drive.mount('/content/drive')

# 2. Copy minimal folder structure
# Upload your TradingBot folder via:
# Files → Upload folder
# (Select only backtest_v6/, v6/, config/)

# 3. Install dependencies
!pip install pandas numpy

# 4. Run backtest
import os
os.chdir('/content/drive/My Drive/TradingBot')
!python backtest_v6/sector_engine_v6.py --start 2026-02-01 --end 2026-02-23 --export

# 5. View results
import pandas as pd
trades = pd.read_csv('backtest_v6/data/backtest_trades_v6.csv')
print(trades)
```

### Option 2: Git Clone (if repo is public)

```python
!git clone https://github.com/yourusername/TradingBot.git
%cd TradingBot

!pip install pandas numpy

!python backtest_v6/sector_engine_v6.py --start 2026-02-01 --end 2026-02-23 --export
```

### Option 3: Download from Drive

```python
from google.colab import drive
drive.mount('/content/drive')

# Store parquet files in Drive
# Point to them in Colab
!python backtest_v6/sector_engine_v6.py \
  --start 2026-02-01 \
  --end 2026-02-23 \
  --data-root '/content/drive/My Drive/TradingBot/backtest_v6/data' \
  --export
```

---

## Backtest Example in Colab

```python
# Full example notebook cell:

!pip install pandas numpy -q

# Download or mount your data
from google.colab import drive
drive.mount('/content/drive')

import os
os.chdir('/content/drive/My Drive/TradingBot')

# Run backtest
!python backtest_v6/sector_engine_v6.py \
  --start 2026-02-01 \
  --end 2026-02-28 \
  --spread-bps 6.0 \
  --circuit-pct 0.10 \
  --export

# View results
import pandas as pd
results = pd.read_csv('backtest_v6/data/backtest_trades_v6.csv')
print(f"\n✅ Backtest Complete!")
print(f"Total Trades: {len(results)}")
print(f"Wins: {len(results[results['realized_pnl'] > 0])}")
print(f"Losses: {len(results[results['realized_pnl'] < 0])}")
print(f"\nTop 5 Trades:")
print(results.nlargest(5, 'realized_pnl')[['symbol', 'direction', 'realized_pnl']])
```

---

## Better Alternatives for Live Trading

### ❌ Don't Use Colab for Live Trading

| Option                   | Cost         | Setup  | Persistence    | Best For             |
| ------------------------ | ------------ | ------ | -------------- | -------------------- |
| **Colab**                | Free         | 5 min  | ❌ No          | Backtesting only     |
| **AWS EC2**              | $5-50/month  | 30 min | ✅ Yes         | Production trading   |
| **Google Cloud Compute** | $5-50/month  | 30 min | ✅ Yes         | Production trading   |
| **Local PC**             | $0           | 0 min  | ✅ Yes (if on) | Development/testing  |
| **Raspberry Pi**         | $50 one-time | 1 hr   | ✅ Yes         | Budget-friendly 24/7 |
| **VPS**                  | $3-10/month  | 15 min | ✅ Yes         | Budget live trading  |

---

## Summary

| Task                   | Colab? | Alternative            |
| ---------------------- | ------ | ---------------------- |
| **Backtest**           | ✅ YES | Local machine          |
| **Live Paper Trading** | ❌ NO  | AWS EC2, VPS, local PC |
| **Data Analysis**      | ✅ YES | Jupyter Local          |
| **Strategy Testing**   | ✅ YES | Local Jupyter          |
| **24/7 Trading**       | ❌ NO  | Cloud VM or VPS        |

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'v6'"

```python
import sys
sys.path.insert(0, '/content/TradingBot')
```

### "No such file: backtest_v6/data/daily/\*.parquet"

```python
# Ensure data files are uploaded
!ls -la /content/drive/My\ Drive/TradingBot/backtest_v6/data/
```

### "UNIVERSE_PATH not found"

```python
# Check config.py path is correct
import os
os.chdir('/content/TradingBot')  # Set working directory first
```

### Session Times Out

- Backtest runs can take 30-60 minutes for large date ranges
- Keep Colab tab open during execution
- Enable auto-play if notebook provides option
- Use `--start` and `--end` for smaller date ranges

---

## Key Takeaway

✅ **Use Colab For:** Backtesting, analysis, experimentation  
❌ **Don't Use Colab For:** Live trading, 24/7 bots

For production trading, use a persistent cloud server (EC2, VPS) or local machine.
