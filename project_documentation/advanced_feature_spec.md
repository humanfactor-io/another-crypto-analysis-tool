Feature Specification: Session-Level Market Profile Enhancements
================================================================

Scope:
------
This specification outlines the requirements to derive and store three new market-profile-derived metrics at the session level, enabling precise statistical backtesting and trading strategy analysis.

New Features to be Added:
-------------------------
1. SessionASR (Average Session Range)
2. PoorHigh / PoorLow (unfinished session extremes)
3. SinglePrints (minimum 3 single prints threshold)

Detailed Definitions and Logic:
-------------------------------

1. SessionASR
-------------
Definition:
- SessionASR = SessionHigh - SessionLow
- Represents the full price range volatility within a clearly defined market trading session.

Calculation:
- For each clearly defined session (Asia, London, New York):
    SessionASR = [SessionHigh] - [SessionLow]

Example:
- SessionHigh: 94449.2
- SessionLow: 93258.8
- SessionASR = 1190.4

Data Type:
- Numeric (float, rounded to 1 decimal)

---

2. PoorHigh / PoorLow
---------------------
Definition:
- A PoorHigh (or PoorLow) indicates an unfinished auction at the session extreme (top or bottom).
- An auction is classified as "poor" if the session extreme lacks meaningful price excess, typically indicating price tested a particular price level multiple times but failed to move significantly beyond it.

Detection Logic:
- Poor High condition (boolean):  
  - TRUE if the session high price is revisited or touched multiple times (2 or more distinct TPO periods), forming a flat or very minimal excess at session highs.
  - FALSE otherwise.

- Poor Low condition (boolean):  
  - TRUE if the session low price is revisited or touched multiple times (2 or more distinct TPO periods), forming a flat or very minimal excess at session lows.
  - FALSE otherwise.

- Include Price Level clearly:
  - If PoorHigh = TRUE, record session high price.
  - If PoorLow = TRUE, record session low price.
  - If FALSE, no price needed.

Example Representation:
- PoorHigh: TRUE (94449.2)
- PoorLow: FALSE

Data Type:
- Boolean with conditional numeric price level (float)

---

3. SinglePrints
---------------
Definition:
- "Single Prints" represent price ranges in a session that were traded through only once, creating low-volume liquidity gaps indicating market imbalance.
- A meaningful Single Print area for statistical analysis is defined as:
  - **3 or more consecutive single-price increments** in the TPO profile.

Minimum Threshold:
- SinglePrints flagged as TRUE only if the single print area spans at least **3 consecutive price increments**.
- If fewer than 3 consecutive single prints exist, SinglePrints flagged as FALSE.

Example:
- Single prints found at prices 94000.0, 94010.0, 94020.0 (3 consecutive increments): SinglePrints = TRUE.
- Single prints found at prices 94000.0, 94010.0 only (2 increments): SinglePrints = FALSE.

Data Type:
- Boolean (TRUE/FALSE)

---

Example Updated Session Table Structure (not fully complete but showing the new additions):
----------------------------------------
| Date       | Sessions | SessionHigh | SessionLow | SessionASR | PoorHigh       | PoorLow | SinglePrints |
|------------|----------|-------------|------------|------------|----------------|---------|--------------|
| 2025-01-01 | London   | 94449.2     | 93258.8    | 1190.4     | TRUE (94449.2) | FALSE   | TRUE         |
| 2025-01-01 | NewYork  | 94520.0     | 93500.0    | 1020.0     | FALSE          | TRUE (93500.0) | FALSE   |

---

Implementation Notes:
---------------------
- Implement detection logic in Python or preferred programming language, processing data from your existing TPO-based data structure.
- Results should be clearly represented within the existing session summary table structure.

This completes the scope of this feature specification.
