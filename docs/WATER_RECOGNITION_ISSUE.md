# Water Recognition Issue

## ⚠️ Problem: Water Photos Get 504 Gateway Timeout or "Food Not Recognized"

**Status:** CRITICAL - User cannot track water via photo

**Last Updated:** 2026-02-02

---

## 🔴 Current Symptoms

1. **Timeout Issues:**
   - Water photos take 60+ seconds to analyze
   - Returns "504 Gateway Time-out" error
   - Sometimes "2 minutes analyzing"

2. **Recognition Failures:**
   - Glass of water → Not recognized
   - Highland Spring bottle (with label) → Not recognized
   - Even after AI prompt improvements (STEP 0)
   - Even after pre-AI pixel analysis

3. **Why Water is Special:**
   - Transparent liquids are hard for AI vision models
   - No distinct features (colors, shapes, textures)
   - Labels/hands/background confuse analysis
   - Glass reflections add noise

---

## 🔧 What We've Tried (Still Not Working)

### 1. ✅ AI Prompt Optimization (DONE - NOT ENOUGH)
**File:** `chater_new/chater_ui/eater/prompt.yaml`

```yaml
STEP 0 - WATER DETECTION (CHECK THIS FIRST, BEFORE ANYTHING ELSE):
Does photo contain glass/bottle/cup/pitcher with transparent/clear liquid inside?
Is liquid colorless or slightly tinted by glass/lighting?
Is there NO visible food particles, coffee grounds, tea leaves, milk cloudiness?

IF YES TO ALL 3 → RETURN Water IMMEDIATELY
```

**Result:** AI still takes 60+ seconds and often fails

### 2. ✅ Pre-AI Pixel Analysis (DONE - NOT WORKING)
**File:** `chater_new/chater_ui/eater/process_photo.py`

**Approach 1 (Simple):**
```python
# Whole image check
brightness = pixels.mean()
color_std = pixels.std()
if brightness > 180 and color_std < 40:
    return Water
```
**Problem:** Bottles with labels fail (Highland Spring has purple label)

**Approach 2 (Multi-Region):**
```python
# Check 4 regions for transparent areas
regions = [center, middle, top_half, bottom_3/4]
# Look for brightness 160-250, std <50, RGB balanced
if 2+ regions water-like:
    return Water
```
**Problem:** Still not detecting water reliably

### 3. ✅ iOS Client Timeout (DONE)
**File:** `eater/eater/Services/GRPCService.swift`
```swift
request.timeoutInterval = 45  // 45 seconds
```
**Result:** Prevents infinite waiting, but doesn't solve recognition

---

## 🎯 Root Cause Analysis

### The Real Problem Chain:

```
iOS Photo Upload
    ↓
Backend (Flask) receives photo
    ↓
Pre-check (pixel analysis) - NOT DETECTING
    ↓
Send to Kafka → AI Worker
    ↓
AI Model processes (60+ seconds for water!)
    ↓
Backend waits max 60s (get_user_message_response timeout=60)
    ↓
Nginx timeout < 60s (probably 30-45s)
    ↓
504 Gateway Timeout OR "Food Not Recognized"
```

### Why Pre-Check Fails:

**Problem with pixel-based detection:**
1. Water bottles have labels → colors vary widely
2. Background/hands in photo → affects region analysis
3. Lighting conditions → brightness/RGB inconsistent
4. Glass reflections → high color variance
5. Need SMARTER detection (not just pixel stats)

### Why AI Fails:

**Problem with AI model:**
1. Vision models struggle with transparent objects
2. Even with prompt "STEP 0 WATER FIRST", model still analyzes deeply
3. Possibly model ignores beginning of prompt
4. Or model doesn't trust simple water check → over-analyzes

---

## 💡 Potential Solutions (TO TRY TOMORROW)

### Option 1: Computer Vision Water Detection (RECOMMENDED)
Use OpenCV for better pre-AI detection:

```python
import cv2

def is_water_bottle_or_glass(image):
    # Edge detection for bottle/glass shape
    edges = cv2.Canny(image, 100, 200)
    
    # Look for vertical rectangular shapes (bottles)
    contours = cv2.findContours(edges)
    
    # Check for transparent regions using:
    # - Histogram analysis (light, low contrast)
    # - Shape detection (bottle/glass contours)
    # - Label/logo detection (OCR for "water", "spring", etc.)
    
    return confidence_score
```

**Pros:**
- More accurate than pixel stats
- Can detect bottle shapes
- Can read labels ("Highland Spring" → water!)

**Cons:**
- Requires opencv-python
- More complex code

### Option 2: Dedicated "Track Water" Button (QUICKEST FIX)
Add button in iOS app to track water WITHOUT photo:

```swift
Button("Track Water 💧") {
    // Directly add 250ml water, no photo, no AI
    GRPCService().addWaterDirectly(ml: 250)
}
```

**Pros:**
- Instant (no backend, no AI)
- 100% reliable
- Better UX for water tracking

**Cons:**
- No photo tracking (but do users really need water photos?)

### Option 3: Separate Fast Water Endpoint
Create `/eater_receive_water_photo` endpoint:

```python
@app.route("/eater_receive_water_photo", methods=["POST"])
def water_photo():
    # Simplified processing
    # No AI, just confirm + return water response
    return water_json
```

**Pros:**
- Bypasses AI entirely for water
- Still allows photo upload (for history)

**Cons:**
- User must choose "water mode" before taking photo

### Option 4: Use Faster AI Model for Water
Deploy lightweight vision model ONLY for water detection:

- MobileNet or similar (fast, <1s)
- Train on water images
- Use as pre-filter before main AI

**Pros:**
- Accurate
- Fast (<1s)

**Cons:**
- Requires ML model training
- Infrastructure setup

### Option 5: OCR Label Detection
Read text from labels:

```python
import pytesseract

text = pytesseract.image_to_string(image)
if "water" in text.lower() or "spring" in text.lower():
    return Water
```

**Pros:**
- Works for branded water bottles
- Fast

**Cons:**
- Requires pytesseract
- Misses plain glasses

---

## 🧪 Debug Steps for Tomorrow

### 1. Check Backend Logs
```bash
cd /Users/iva/Documents/Eateria/chater_new/chater_ui
# Check what pre-check says
tail -f logs/*.log | grep "Quick water check"
```

Look for:
- "Region X: WATER-like" messages
- Final count: "X/4 regions water-like"
- Why it's not triggering (< 2 regions?)

### 2. Test Pre-Check Locally
```python
from PIL import Image
import numpy as np

# Load test images
img_glass = Image.open("glass_water.jpg")
img_bottle = Image.open("highland_spring.jpg")

# Run detection logic
# Print brightness, std, rgb_diff for each region
```

### 3. Test AI Prompt Directly
```bash
curl -X POST https://chater.singularis.work/eater_receive_photo \
  -H "Authorization: Bearer TOKEN" \
  -F "photo=@water_test.jpg"
```

Check:
- How long does it take?
- What does AI return?

### 4. Check Nginx Timeout
```bash
# SSH to server
grep timeout /etc/nginx/sites-enabled/chater

# Look for:
proxy_read_timeout 30s;  # ← This might be too low!
```

---

## 📝 Files Involved

### Backend (Python):
- `chater_new/chater_ui/eater/process_photo.py` - Photo processing + pre-check
- `chater_new/chater_ui/eater/prompt.yaml` - AI prompt with STEP 0
- `chater_new/chater_ui/requirements.txt` - Dependencies (PIL, numpy)
- `chater_new/chater_ui/gunicorn.conf.py` - Worker timeout (60s)

### iOS (Swift):
- `eater/eater/Services/GRPCService.swift` - Client timeout (45s)
- `eater/eater/Views/CameraButtonView.swift` - Photo capture

### Infrastructure:
- Nginx config - Gateway timeout
- Kafka AI worker - Actual AI processing

---

## 🎯 Recommended Next Steps

1. **QUICK WIN (5 min):** Add "Track Water" button without photo
2. **DEBUG (30 min):** Check backend logs, test pre-check with real images
3. **FIX (2-3 hours):** Implement OpenCV detection OR OCR label reading
4. **INFRASTRUCTURE (optional):** Increase nginx timeout to 90s as backup

---

## 🚨 Important Notes

- User confirmed problem happens with:
  - ✅ Glass of water (tested multiple times)
  - ✅ Highland Spring bottle (with label)
  - ✅ Different lighting conditions

- Current pre-AI check criteria may be TOO STRICT:
  - Brightness 160-250 (maybe too narrow?)
  - RGB diff <30 (maybe too strict?)
  - Need 2/4 regions (maybe lower threshold?)

- Timeout chain:
  - iOS: 45s
  - Backend: 60s (waiting for AI)
  - Nginx: ??? (probably 30-45s) ← CHECK THIS
  - AI: 60+ seconds for water ← MAIN PROBLEM

---

## 📊 Success Criteria

Water detection is FIXED when:
- ✅ Water photo returns response in <5 seconds
- ✅ No 504 timeout errors
- ✅ Works for glasses AND bottles
- ✅ Works with labels (Highland Spring, etc.)
- ✅ 95%+ accuracy for water photos
