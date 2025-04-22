- Overall objective 
o Conduct TPO back-testing against BTCUSDT.P pair 
o I am aiming to quantitatively establish probabilities (edge) regarding when specific Market Profile (TPO) and Volume Profile elements are revisited, challenged, or repaired within certain time frames. These probabilities need to be translated into actionable, statistically-grounded statements—exactly like your example: “There’s an 83% probability that a poor low will be repaired within 48 hours.”

o This is precisely the kind of research-driven edge institutional traders often build their strategies on, which allows for entering the market with clear expectations, placing me significantly ahead of most retail participants.

- Scope of Backtesting
o TPO Value Area (VA)
* Testing reactions when price trades into or out of the previous day's Value Area.
* Price acceptance/rejection at VA High (VAH) and VA Low (VAL).
o Volume Point of Control (vPOC) and Naked vPOC (NVPOC)
* Testing strategies based on revisits of previous day(s) vPOCs (including naked vPOCs).
* Frequency, timing, and accuracy of NVPOC revisits.
o Initial Balance (IB)
* Testing breakouts/failures at initial balance extremes.
* Identifying days that extend IB vs. days that revert to IB midpoints.
o Failed Auctions
* Testing reliability of signals when price briefly moves beyond recent highs/lows without attracting follow-through volume.
* Identifying potential reversals or momentum exhaustion based on failed auction signals.
o ATR / ASR (Average True Range / Average Session Range)
* Using ATR/ASR to gauge expected volatility ranges and confirming range expansion/contraction signals.
* Identifying when market exceeds or falls short of expected ranges.
o Single Prints
* Backtesting potential reactions when single prints are revisited, signaling trapped buyers/sellers or potential liquidity gaps.
o Overlapping Value Areas
* Detecting directional bias or choppiness based on overlapping value areas from consecutive sessions
o Excess Tails
* Measuring reversals or continuation based on excess (long tails at extremes), indicating completed auctions.
o Poor vs. Good Highs/Lows
* Distinguishing between well-defined (excess) versus poor (flat, unfinished) extremes to anticipate reversals or retests.

- Tools and preferences:
o Python (Pandas & NumPy libraries), we will (1) create aggregated session-based data from your raw intraday OHLCV data. (2) Derive the Market Profile and Volume Profile metrics explicitly. (3) Statistically measure revisit probabilities of key levels and events within your chosen timeframes.
o Visualise results and see numerical performance data and summaries 
- Available dataset:
o Date, Time: To accurately timestamp and organize each bar.
o Open, High, Low, Last (Close): OHLC price data, critical for defining price action and structural references.
o Volume, NumberOfTrades: Volume data, useful for volume profiling and identifying significant market activity.
o BidVolume, AskVolume: Essential to compute delta, cumulative delta, and order flow imbalance.
- MVP:
* Pick one event first (for example, Poor Lows or NVPOCs).
* Export a clear sample dataset from Sierra Charts.
* Load and process that data in Python, identifying and classifying events clearly.
* Perform a statistical analysis on that event to demonstrate this approach practically.
- How to use the data
o Step 1: Create Derived Metrics: 
* We'll derive the critical elements of your Market Profile analysis directly from OHLC and volume data, including:
* Session TPO Levels: Compute session-based TPO Value Area, POC, and Initial Balance from OHLC.
* Volume POC and Naked Volume POC: Use volume data to find each session’s highest-volume price (vPOC). Track historical NVPOCs.
* ATR/ASR Calculation: Calculate daily ATR using session highs/lows.
* Bid-Ask Data: Compute Delta and cumulative delta.
o Step 3: Identify Specific Events (Statistical Targets
* Programmatically identify:
* Poor highs/lows (by comparing bar extremes).
* Revisits of NVPOCs.
* Failed auctions (quickly reversed breakouts).
* IB extremes retesting.
o Step 4: Perform Statistical Analysis
o Compute statistical probabilities of revisiting each event within defined timeframes.
