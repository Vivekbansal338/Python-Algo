import sys
sys.path.insert(0, r'C:\Users\VIVEK BANSAL\Desktop\Python_Algo\Project3\TradingBot')

from v6 import config
import json

with open(config.UNIVERSE_PATH, 'r') as f:
    u = json.load(f)

stocks = u.get('stocks', [])

# Build sector_map like the bot does
sector_map = {}
for stock in stocks:
    symbol = stock.get('symbol', '')
    for sector in stock.get('indices', []):
        if sector not in sector_map:
            sector_map[sector] = []
        sector_map[sector].append(symbol)

print('Built sector_map keys:', list(sector_map.keys())[:10])
print()

# Find HCLTECH
hcl = [s for s in stocks if 'HCLTECH' in s.get('symbol', '')]
if hcl:
    print('HCLTECH stock data:', hcl[0])
    print('HCLTECH indices:', hcl[0].get('indices', []))

# Check if NIFTY IT exists in sector_map
if 'NIFTY IT' in sector_map:
    print('NIFTY IT stocks count:', len(sector_map['NIFTY IT']))
    print('First 5:', sector_map['NIFTY IT'][:5])
else:
    print('NIFTY IT NOT FOUND in sector_map')
    print('Available keys:', list(sector_map.keys()))
