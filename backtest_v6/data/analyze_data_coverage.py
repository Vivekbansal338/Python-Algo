import json
import os
from datetime import datetime
import pandas as pd
from pathlib import Path

def get_parquet_info(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        df = pd.read_parquet(file_path)
        if 'date' not in df.columns:
            return None
        dates = pd.to_datetime(df['date'])
        return {
            'first_date': dates.min().strftime('%Y-%m-%d %H:%M:%S'),
            'last_date': dates.max().strftime('%Y-%m-%d %H:%M:%S'),
            'total_records': int(len(df))
        }
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

def main():
    config_path = r'C:\Users\VIVEK BANSAL\Desktop\Python_Algo\TradingBot\config\universe.json'
    data_dir = r'C:\Users\VIVEK BANSAL\Desktop\Python_Algo\TradingBot\backtest_v6\data'
    output_path = r'C:\Users\VIVEK BANSAL\Desktop\Python_Algo\TradingBot\backtest_v6\data\data_coverage_report.json'
    
    minute_5_dir = os.path.join(data_dir, '5minute')
    daily_dir = os.path.join(data_dir, 'daily')
    
    print("Loading universe.json...")
    with open(config_path, 'r') as f:
        universe = json.load(f)
    
    indices = universe.get('indices', [])
    stocks = universe.get('stocks', [])
    
    print(f"Found {len(indices)} indices and {len(stocks)} stocks in universe.json")
    
    indices_results = []
    stocks_results = []
    
    indices_with_5min = 0
    indices_with_daily = 0
    indices_with_both = 0
    stocks_with_5min = 0
    stocks_with_daily = 0
    stocks_with_both = 0
    indices_missing = []
    stocks_missing = []
    
    print("\nProcessing indices...")
    for idx, index_data in enumerate(indices):
        symbol = index_data['symbol']
        name = index_data['name']
        token = index_data['token']
        
        if (idx + 1) % 5 == 0:
            print(f"  Processing index {idx + 1}/{len(indices)}: {symbol}")
        
        minute_5_file = os.path.join(minute_5_dir, f"{symbol}.parquet")
        daily_file = os.path.join(daily_dir, f"{symbol}.parquet")
        
        minute_5_info = get_parquet_info(minute_5_file)
        daily_info = get_parquet_info(daily_file)
        
        has_5min = minute_5_info is not None
        has_daily = daily_info is not None
        
        if has_5min:
            indices_with_5min += 1
        if has_daily:
            indices_with_daily += 1
        if has_5min and has_daily:
            indices_with_both += 1
        if not has_5min and not has_daily:
            indices_missing.append(symbol)
        
        indices_results.append({
            'name': name,
            'symbol': symbol,
            'token': token,
            '5minute': minute_5_info,
            'daily': daily_info
        })
    
    print(f"\nProcessing {len(stocks)} stocks...")
    for idx, stock_data in enumerate(stocks):
        symbol = stock_data['symbol']
        name = stock_data['name']
        token = stock_data['token']
        stock_indices = stock_data.get('indices', [])
        
        if (idx + 1) % 50 == 0:
            print(f"  Processing stock {idx + 1}/{len(stocks)}: {symbol}")
        
        minute_5_file = os.path.join(minute_5_dir, f"{symbol}.parquet")
        daily_file = os.path.join(daily_dir, f"{symbol}.parquet")
        
        minute_5_info = get_parquet_info(minute_5_file)
        daily_info = get_parquet_info(daily_file)
        
        has_5min = minute_5_info is not None
        has_daily = daily_info is not None
        
        if has_5min:
            stocks_with_5min += 1
        if has_daily:
            stocks_with_daily += 1
        if has_5min and has_daily:
            stocks_with_both += 1
        if not has_5min and not has_daily:
            stocks_missing.append(symbol)
        
        stocks_results.append({
            'name': name,
            'symbol': symbol,
            'token': token,
            'indices': stock_indices,
            '5minute': minute_5_info,
            'daily': daily_info
        })
    
    report = {
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_indices': len(indices),
            'total_stocks': len(stocks),
            'indices_with_5min_data': indices_with_5min,
            'indices_with_daily_data': indices_with_daily,
            'indices_with_both_data': indices_with_both,
            'stocks_with_5min_data': stocks_with_5min,
            'stocks_with_daily_data': stocks_with_daily,
            'stocks_with_both_data': stocks_with_both,
            'indices_missing_data': indices_missing,
            'stocks_missing_data': stocks_missing
        },
        'indices': indices_results,
        'stocks': stocks_results
    }
    
    print(f"\nWriting report to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total Indices: {len(indices)}")
    print(f"Total Stocks: {len(stocks)}")
    print(f"\nIndices:")
    print(f"  - With 5min data: {indices_with_5min}")
    print(f"  - With daily data: {indices_with_daily}")
    print(f"  - With both: {indices_with_both}")
    print(f"  - Missing data: {len(indices_missing)}")
    print(f"\nStocks:")
    print(f"  - With 5min data: {stocks_with_5min}")
    print(f"  - With daily data: {stocks_with_daily}")
    print(f"  - With both: {stocks_with_both}")
    print(f"  - Missing data: {len(stocks_missing)}")
    print("="*60)
    print(f"\nReport saved to: {output_path}")

if __name__ == '__main__':
    main()
