"""
SECTOR SCORING SENSITIVITY ANALYSIS
===================================
Simulates various market scenarios to quantify the impact of each scoring component.
Formula: Score = (RS20 * 3) + (RS3 * 10) + (RS_Day * 20) + (Breadth * 40) + (Nifty% * 30)

Thresholds:
  > +10: LONG
  < -10: SHORT
  Else : NEUTRAL
"""

def calculate_score(rs20, rs3, rs_day, breadth, nifty_pct):
    w_rs20 = 3.0
    w_rs3 = 10.0
    w_rs_day = 20.0
    w_breadth = 40.0
    w_nifty = 30.0
    
    score = (rs20 * w_rs20) + \
            (rs3 * w_rs3) + \
            (rs_day * w_rs_day) + \
            (breadth * w_breadth) + \
            (nifty_pct * w_nifty)
            
    bias = "NEUTRAL"
    if score >= 10: bias = "LONG"
    elif score <= -10: bias = "SHORT"
    
    return score, bias

def print_scenario(name, rs20, rs3, rs_day, breadth, nifty_pct):
    score, bias = calculate_score(rs20, rs3, rs_day, breadth, nifty_pct)
    
    # Calculate Contribution
    c_rs20 = rs20 * 3.0
    c_rs3 = rs3 * 10.0
    c_day = rs_day * 20.0
    c_br = breadth * 40.0
    c_mkt = nifty_pct * 30.0
    
    print(f"\nScenario: {name}")
    print("-" * 60)
    print(f"{ 'Component':<15} | {'Value':<10} | {'Weight':<6} | {'Points':<8} | {'Impact'}")
    print("-" * 60)
    print(f"{ 'Structural RS':<15} | {rs20:<10.2f} | 3.0    | {c_rs20:<8.1f} | {c_rs20/abs(score)*100 if score!=0 else 0:.0f}%")
    print(f"{ 'Short-Term RS':<15} | {rs3:<10.2f} | 10.0   | {c_rs3:<8.1f} | {c_rs3/abs(score)*100 if score!=0 else 0:.0f}%")
    print(f"{ 'Intraday RS':<15} | {rs_day:<10.2f} | 20.0   | {c_day:<8.1f} | {c_day/abs(score)*100 if score!=0 else 0:.0f}%")
    print(f"{ 'Breadth':<15} | {breadth:<10.2f} | 40.0   | {c_br:<8.1f} | {c_br/abs(score)*100 if score!=0 else 0:.0f}%")
    print(f"{ 'Market (Nifty)':<15} | {nifty_pct:<10.2f} | 30.0   | {c_mkt:<8.1f} | {c_mkt/abs(score)*100 if score!=0 else 0:.0f}%")
    print("-" * 60)
    print(f"FINAL SCORE: {score:.2f}  ==>  BIAS: {bias}")

# 1. Standard Bullish Day
print_scenario("Classic Bull Sector", 
               rs20=2.0, rs3=1.0, rs_day=0.5, breadth=0.6, nifty_pct=0.5)

# 2. Bull Trap (Strong History, Weak Intraday)
print_scenario("Bull Trap (Weak Intraday)", 
               rs20=5.0, rs3=2.0, rs_day=-0.2, breadth=-0.3, nifty_pct=0.2)

# 3. Market Crash Override
print_scenario("Market Crash (Good Sector)", 
               rs20=2.0, rs3=1.0, rs_day=0.5, breadth=0.4, nifty_pct=-1.5)

# 4. Rotation (Weak History, Strong Intraday)
print_scenario("Fresh Breakout (Rotation)", 
               rs20=-2.0, rs3=0.5, rs_day=1.5, breadth=0.8, nifty_pct=0.5)
