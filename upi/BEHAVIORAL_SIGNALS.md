# UPI Fraud Detection - Behavioral Signal Enhancement

## Overview
Enhanced the UPI fraud detection system with sophisticated behavioral signal tracking and an improved user interface featuring a spinner-based submit flow with detailed risk analysis cards.

## Features Implemented

### 1. **Enhanced Transaction Form**
- **Payer UPI**: User's account identifier
- **Payee UPI**: Recipient's account identifier  
- **Amount**: Transaction amount in rupees
- **Merchant/Recipient Name**: Name of the recipient or merchant
- **Category**: Transaction type (Shopping, Bills, Food, Travel, etc.)
- **Location**: Geographic location of the transaction
- **Timestamp**: Auto-populated with current date/time (collected via JS)

### 2. **Behavioral Signal Tracking**
Tracks user behavior during form entry to identify suspicious patterns:

#### **Typing Metrics**
- **Typing Speed**: Average time between keystrokes (milliseconds)
  - Used to detect rushed vs. deliberate input
  - Measured across all form fields with `data-behavioral="true"` attribute

#### **Correction Patterns**
- **Backspace Ratio**: Number of backspaces / total characters entered
  - High ratio combined with paste detection = suspicious (fraud indicator +10 points)
  - Example: User pastes value, then heavily edits it

#### **Hesitation Analysis**
- **Hesitation Time**: Time before first character entered in each field (milliseconds)
  - Measures how long user thinks before typing
  - Longer hesitation may indicate uncertainty

#### **Paste Detection**
- **Paste Count**: Number of paste operations detected
  - Combined with high backspace ratio triggers "Suspicious Paste Pattern" indicator
  - Valid use case vs. fraudster copying data

#### **Focus Changes**
- **Focus Count**: Number of window blur/focus events
  - Tracks context switching (alt+tab, switching apps, etc.)
  - >5 focus changes triggers "Multiple Focus Changes" indicator (+5 points)
  - May indicate fraudster preparing multiple fraudulent submissions

#### **Device Fingerprinting**
- **Device ID**: Persistent device identifier (stored in localStorage)
- Used to track transactions from same device
- Combined with location-change and time indicators for better fraud scoring

### 3. **Fraud Scoring Enhancement**
Behavioral signals contribute to risk score:
- **Suspicious Paste Pattern**: +10 points (paste + high backspace ratio)
- **Multiple Focus Changes**: +5 points (>5 focus changes)
- **Device Change**: +15 points (different device within 2 hours, already implemented)
- **Location Change**: +20 points (different location within 2 hours)
- **Model Consensus**: +25 points (if >50% of ML models detect fraud)
- **High Amount** / **Late Night** / **Unknown Merchant**: Additional indicator scoring

### 4. **Improved Submit Flow**

#### **Spinner Animation**
- Full-screen overlay spinner displayed during transaction analysis
- Modal dialog showing "Analyzing transaction..." message
- CSS-based spinner circle with smooth rotation animation
- Submit button disabled during processing

#### **Enhanced Risk Card Display**
Risk card now shows:
- **Status**: 🚨 Fraud Detected or ✅ Legitimate Transaction
- **Risk Score**: 0-100 percentage
- **Transaction Details**:
  - Amount and time of transaction
  - Payer and Payee UPI addresses
- **Model Consensus**: How many ML models detected fraud (e.g., "2/4 models detect fraud")
- **Individual Model Predictions**: Per-model results with confidence scores
- **Risk Indicators**: Detailed list of indicators contributing to risk score
  - Each indicator shows: Name, description, and risk points added
  - Visual highlighting with colored left border

### 5. **Technical Implementation**

#### **Frontend (templates/index.html)**
- Added `data-behavioral="true"` attributes to tracked form fields
- JavaScript event listeners on keydown/keyup/paste/focus/blur events
- localStorage-based device ID persistence
- Form submission intercepted to calculate behavioral metrics
- Auto-population of timestamp fields before submission
- Hidden form fields to carry behavioral data to backend

#### **Backend (app.py)**
- `/predict` endpoint updated to accept behavioral signals
- Optional behavioral signal parameters:
  - `typing_speed`, `backspace_ratio`, `hesitation_time`, `paste_detected`, `focus_changes`, `device_id`
- Behavioral signals optionally boost fraud score
- Enhanced response to include all transaction details for rich UI display
- Backward compatible: works without behavioral data

#### **Styling (static/css/style.css)**
- Added `@keyframes spin` animation for spinner
- `.spinner` class: fixed overlay with semi-transparent background
- `.spinner-circle`: rotating border-based spinner design
- `.risk-card` classes for enhanced card layout
- `.meta-row` and `.indicator` classes for organized display

### 6. **Database Integration**
- Behavioral signals stored in transaction `features` JSON field
- Device ID stored for cross-transaction linking
- Audit logs track system-blocked transactions with full details

## User Experience Flow

1. **User enters transaction details**: 
   - Form fields track all behavioral metrics in background
   
2. **User submits form**:
   - Behavioral metrics calculated and attached to request
   - Spinner overlay appears with "Analyzing transaction..." message
   
3. **Backend analyzes transaction**:
   - Runs through 4 ML models
   - Calculates fraud indicators (amount, time, location, device, behavioral signals)
   - Combines scores into final risk score
   
4. **Results displayed in rich risk card**:
   - Shows fraud status, risk score, amount, time, parties
   - Lists all contributing indicators with risk points
   - Shows which ML models flagged the transaction
   - If fraud detected: triggers alert (siren, flash, notification)

## Security & Privacy Notes

- Device ID is local-only (localStorage), never transmitted to backend unless explicitly submitted
- Behavioral data is optional; system works fine without it
- All data persisted to SQLite for audit trail
- Behavioral signals are heuristic-based; combined scoring is required to flag fraud
- No keystroke logging; only timing and high-level metrics tracked

## Testing

- Full test suite passes: **8 passed, 2 skipped** ✅
- Tests validate:
  - Frequency features (count_1h, count_6h, count_24h, count_7d)
  - Location-change indicators
  - Device-change indicators
  - Audit logging
  - Token-protected endpoints
  - SHAP explainability (when available)

## Example Fraud Indicators Triggered

```
High Amount (₹50,000) → +40 points
Late Night Transaction (23:00) → +20 points
Unknown Merchant (first time) → +15 points
Device Changed (within 2h) → +15 points
Suspicious Paste Pattern (paste + backspace) → +10 points
Multiple Focus Changes (5+ switches) → +5 points

Total: 105 points → ⚠️ FRAUD DETECTED (>50 threshold)
```

## Future Enhancements

1. **Machine Learning Integration**: Use behavioral signals as features in model retraining
2. **Behavioral Profiles**: Build user profiles (normal typing speed, hesitation time) for personalized detection
3. **Velocity Checks**: Track transaction frequency per UPI per time window
4. **Geolocation**: Integrate IP-based location with transaction location
5. **Device Fingerprinting**: Enhance with browser/OS/screen resolution fingerprints
6. **Biometric Auth**: Optional fingerprint/face recognition for additional verification
7. **Admin Dashboard**: Real-time monitoring of suspicious transactions and behavioral patterns

## Files Modified

- `templates/index.html`: Form fields, behavioral tracking JS, enhanced risk card display, spinner
- `app.py`: Updated `/predict` endpoint, behavioral signal processing, enhanced response
- `static/css/style.css`: Spinner animations, risk card styling
- `database.py`: (already supports features JSON, no changes needed)

## Deployment Notes

1. Server runs on http://127.0.0.1:5000 by default
2. Uses Flask development server (not production-ready; use Gunicorn/uWSGI for production)
3. SQLite database at `upi.db` in project root
4. Models loaded from pickled files in project root
5. No external API dependencies (SHAP optional for explainability)

---

**Status**: ✅ Ready for demo and user testing
**Last Updated**: December 25, 2025
