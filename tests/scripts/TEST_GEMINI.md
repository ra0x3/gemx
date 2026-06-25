# Gemini.py Selector Testing & Recovery Guide

## Quick Fix Process

When gemini.py breaks due to UI changes:

### 1. Debug in Browser Console
```bash
# Open Chrome, navigate to gemini.google.com, sign in
# Paste entire test_gemini_console.js into console
# Run: testSelectors()
# Copy the output showing which selectors work/fail
```

### 2. Test New Selectors
```javascript
# Run the test function to verify selectors:
testUpdatedSelectors()
# Watch for "Response growing" messages
# Confirm full response is captured
```

### 3. Update Code
Once selectors are confirmed working:
1. Update `test_gemini_console.js` with new selectors
2. Update `gemini.py` with matching selectors
3. Run mock tests: `./arb-py/bot/venv/bin/pytest -sv ./arb-py/bot/test_gemini_mock.py`

## Current Working Selectors (Jan 2025)
- **Input**: `.ql-editor[contenteditable="true"]`
- **Send button**: `button[aria-label="Send message"]`
- **Response**: `.markdown`

## Key Implementation Details

### Response Detection Logic
1. Count initial `.markdown` elements before sending
2. Wait for NEW `.markdown` element to appear
3. Monitor text length until it stops growing
4. Wait 6 seconds after stabilization before extracting
5. Extract full text from the last (newest) element

### Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Response truncated | Wait for content to stabilize (not just container to appear) |
| Wrong response captured | Count initial elements, only get NEW ones |
| Partial text | Monitor length growth, wait for stability |
| Sign-in required | Ensure Chrome profile has saved auth |

## Test Files
- `test_gemini_console.js` - Browser console debugging tool
- `test_gemini_mock.py` - Unit tests with mocked responses (no auth needed)
- `test_gemini.py` - Integration tests (requires Gemini auth)