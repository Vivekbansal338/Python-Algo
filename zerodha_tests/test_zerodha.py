import os
import json
import logging
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from kiteconnect import KiteConnect, KiteTicker

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Output file path
OUTPUT_FILE = "zerodha_api_output.txt"

def log_output(header, data):
    """Write formatted output to file"""
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + "="*80 + "\n")
        f.write(f"TEST: {header}\n")
        f.write("="*80 + "\n")
        if isinstance(data, (dict, list)):
            f.write(json.dumps(data, indent=2, default=str))
        else:
            f.write(str(data))
        f.write("\n")
    print(f"Captured: {header}")

def main():
    # Load environment variables
    load_dotenv()
    api_key = os.getenv("KITE_API_KEY")
    access_token = os.getenv("KITE_ACCESS_TOKEN")

    if not api_key or not access_token:
        print("Error: KITE_API_KEY and KITE_ACCESS_TOKEN must be set in .env")
        return

    # Initialize KiteConnect
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    # Clear previous output
    with open(OUTPUT_FILE, "w") as f:
        f.write(f"Zerodha API Test Output - Generated at {datetime.now()}\n")

    try:
        # 1. User Profile
        profile = kite.profile()
        log_output("User Profile", profile)

        # 2. Margins
        margins = kite.margins()
        log_output("Margins", margins)

        # 3. Orders
        orders = kite.orders()
        log_output("Orders", orders)

        # 4. Positions
        positions = kite.positions()
        log_output("Positions", positions)

        # 5. Holdings
        holdings = kite.holdings()
        log_output("Holdings", holdings)

        # 6. Instruments (Sample)
        # We need to find tokens for VIX, NIFTY 50, and a Stock (e.g., RELIANCE, SBIN)
        # Instead of downloading all (heavy), we'll try to find specific ones if we can,
        # or just fetch NSE and filter locally.
        print("Fetching instruments (this might take a moment)...")
        instruments = kite.instruments("NSE")
        
        # Find tokens
        vix_token = None
        nifty_token = None
        stock_token = None # RELIANCE
        stock_symbol = "RELIANCE"
        
        # Note: NIFTY 50 and VIX might be in NSE-INDICES or similar, depending on how `instruments()` filters.
        # But commonly indices are in "NSE" file or separate "INDICES" segment.
        # Let's check 'NSE' first. If not found, we'll try to fetch 'INDICES' segment if supported,
        # but usually kite.instruments() returns a big list.
        
        # Searching in the fetched list
        sample_instruments = []
        for instr in instruments:
            if instr['tradingsymbol'] == 'INDIA VIX':
                vix_token = instr['instrument_token']
                sample_instruments.append(instr)
            elif instr['tradingsymbol'] == 'NIFTY 50':
                nifty_token = instr['instrument_token']
                sample_instruments.append(instr)
            elif instr['tradingsymbol'] == stock_symbol:
                stock_token = instr['instrument_token']
                sample_instruments.append(instr)
        
        # If VIX/NIFTY not found in 'NSE', fetch 'INDICES' if possible, or usually they are returned in full list?
        # Kite Connect `instruments(exchange)` usually filters. Indices might need `instruments()` (all) or specific exchange.
        # Let's try fetching generic `instruments()` if we missed something, but 'NSE' usually has stocks.
        # Indices are often separate.
        
        if not nifty_token or not vix_token:
            print("Fetching INDICES instruments...")
            indices_instruments = kite.instruments("INDICES") # Standard segment for indices
            for instr in indices_instruments:
                 if instr['tradingsymbol'] == 'INDIA VIX':
                    vix_token = instr['instrument_token']
                    sample_instruments.append(instr)
                 elif instr['tradingsymbol'] == 'NIFTY 50':
                    nifty_token = instr['instrument_token']
                    sample_instruments.append(instr)
        
        log_output("Sample Instruments (VIX, NIFTY, RELIANCE)", sample_instruments)
        
        tokens_to_test = []
        if vix_token: tokens_to_test.append(vix_token)
        if nifty_token: tokens_to_test.append(nifty_token)
        if stock_token: tokens_to_test.append(stock_token)
        
        symbols_to_quote = []
        if vix_token: symbols_to_quote.append("NSE:INDIA VIX") # Indices often formatted this way? or just token for some calls
        # Note: Quote usually takes "exchange:tradingsymbol" or "instrument_token"
        # Let's use tokens where possible or formatted strings.
        # For Quote, `kite.quote` docs say: list of instrument tokens or `exchange:tradingsymbol`
        
        quote_ids = [str(t) for t in tokens_to_test] # Using tokens is safer
        
        # 7. Quote
        if quote_ids:
            quotes = kite.quote(quote_ids)
            log_output(f"Quote (Full) for {quote_ids}", quotes)
            
            ohlc = kite.ohlc(quote_ids)
            log_output(f"Quote (OHLC) for {quote_ids}", ohlc)
            
            ltp = kite.ltp(quote_ids)
            log_output(f"Quote (LTP) for {quote_ids}", ltp)

        # 8. Historical Data
        # Test for Stock (RELIANCE)
        if stock_token:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=5)
            
            # Minute data
            hist_min = kite.historical_data(stock_token, from_date, to_date, "minute")
            log_output(f"Historical Data (Minute) - {stock_symbol}", hist_min[:5]) # Log first 5
            
            # Day data
            hist_day = kite.historical_data(stock_token, from_date - timedelta(days=30), to_date, "day")
            log_output(f"Historical Data (Day) - {stock_symbol}", hist_day[:5])

        # 9. WebSocket Test
        print("Starting WebSocket Test (listening for 5 seconds per mode)...")
        kws = KiteTicker(api_key, access_token)
        
        # Container for received ticks
        received_ticks = {"ltp": [], "quote": [], "full": []}
        
        def on_ticks(ws, ticks):
            mode = "unknown"
            if not ticks: return
            
            # Guess mode based on fields
            first = ticks[0]
            if "depth" in first:
                mode = "full"
            elif "volume" in first: # Quote has volume, LTP doesn't
                mode = "quote"
            else:
                mode = "ltp"
            
            received_ticks[mode].extend(ticks)
            # print(f"Received {len(ticks)} ticks in {mode} mode")

        def on_connect(ws, response):
            print("WebSocket Connected!")
            if not tokens_to_test:
                print("No tokens to subscribe!")
                return
                
            # Test Mode: LTP
            print(f"Subscribing to {tokens_to_test} in LTP mode")
            ws.subscribe(tokens_to_test)
            ws.set_mode(ws.MODE_LTP, tokens_to_test)
            
            # Wait 5 seconds
            time.sleep(5)
            
            # Test Mode: QUOTE
            print(f"Switching to QUOTE mode")
            ws.set_mode(ws.MODE_QUOTE, tokens_to_test)
            time.sleep(5)
            
            # Test Mode: FULL
            print(f"Switching to FULL mode")
            ws.set_mode(ws.MODE_FULL, tokens_to_test)
            time.sleep(5)
            
            print("WebSocket Test Complete - Closing")
            ws.close()

        def on_error(ws, code, reason):
            print(f"WebSocket Error: {code} - {reason}")

        kws.on_ticks = on_ticks
        kws.on_connect = on_connect
        kws.on_error = on_error

        # Connect (threaded=True is easier for simple script control flow here? 
        # actually docs say connect() is blocking unless threaded=True. 
        # But we need to sleep/change modes inside the loop or callbacks.
        # The `on_connect` runs in the reactor loop. `time.sleep` there blocks the reactor!
        # BAD IDEA to sleep in on_connect.
        
        # Better approach for testing script:
        # Run threaded, control from main thread.
        kws.connect(threaded=True)
        
        # Main thread control
        # Wait for connection
        timeout = 10
        while not kws.is_connected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
            
        if kws.is_connected():
            if tokens_to_test:
                # Sequence
                print("Main Thread: Setting LTP mode")
                kws.subscribe(tokens_to_test)
                kws.set_mode(kws.MODE_LTP, tokens_to_test)
                time.sleep(5)
                
                print("Main Thread: Setting QUOTE mode")
                kws.set_mode(kws.MODE_QUOTE, tokens_to_test)
                time.sleep(5)
                
                print("Main Thread: Setting FULL mode")
                kws.set_mode(kws.MODE_FULL, tokens_to_test)
                time.sleep(5)
            
            kws.close()
        else:
            print("WebSocket failed to connect within timeout")

        # Log gathered ticks
        log_output("WebSocket Ticks (LTP Mode Sample)", received_ticks["ltp"][:3] if received_ticks["ltp"] else "No Data")
        log_output("WebSocket Ticks (QUOTE Mode Sample)", received_ticks["quote"][:3] if received_ticks["quote"] else "No Data")
        log_output("WebSocket Ticks (FULL Mode Sample)", received_ticks["full"][:3] if received_ticks["full"] else "No Data")

    except Exception as e:
        print(f"An error occurred: {e}")
        log_output("Error", str(e))

    print(f"\nTest complete! Check {OUTPUT_FILE} for details.")

if __name__ == "__main__":
    main()
