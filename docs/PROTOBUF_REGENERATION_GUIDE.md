# 🔧 Protobuf Regeneration Guide

## ❌ Current Issue

**Xcode Errors:**
```
Value of type 'Eater_ModifyFoodRecordRequest' has no member 'isTryAgain'
Value of type 'Eater_ModifyFoodRecordRequest' has no member 'imageID'
Value of type 'Eater_ModifyFoodRecordRequest' has no member 'addedSugarTsp'
```

**Root Cause:**
The `.proto` file was updated with new fields, but the generated code (Python & Swift) was not regenerated.

## ✅ Solution: Regenerate Protobuf Files

### Step 1: Update Backend Proto (✅ DONE)

File: `chater_ui/eater/proto/modify_food_record.proto`

```protobuf
message ModifyFoodRecordRequest {
  int64 time = 1;
  string user_email = 2;
  int32 percentage = 3;
  bool is_try_again = 4;               // NEW
  string manual_food_name = 5;
  string manual_insight = 6;
  repeated string manual_components = 7;
  string image_id = 8;                 // NEW
  float added_sugar_tsp = 9;           // NEW
}
```

### Step 2: Regenerate Backend Python Bindings

#### Option A: Using grpcio-tools (Recommended)

```bash
# Install grpcio-tools if not installed
pip install grpcio-tools

# Navigate to proto directory
cd /Users/iva/Documents/Eateria/chater_new/chater_ui/eater/proto

# Regenerate Python bindings
python3 -m grpc_tools.protoc \
  -I. \
  --python_out=. \
  modify_food_record.proto
```

#### Option B: Using protoc directly

```bash
# Install protoc if not installed
# On macOS:
brew install protobuf

# Navigate to proto directory
cd /Users/iva/Documents/Eateria/chater_new/chater_ui/eater/proto

# Regenerate Python bindings
protoc -I. --python_out=. modify_food_record.proto
```

**Expected Output:**
- Updated `modify_food_record_pb2.py` with new fields

### Step 3: Copy Proto to iOS Project

**You need to copy the updated proto file to your iOS project:**

```bash
# Copy from backend to iOS
cp /Users/iva/Documents/Eateria/chater_new/chater_ui/eater/proto/modify_food_record.proto \
   /path/to/your/iOS/project/eater/Services/
```

**Note:** Replace `/path/to/your/iOS/project/` with actual iOS project path.

### Step 4: Regenerate iOS Swift Protobuf

#### Install Swift Protobuf Plugin (if not installed)

```bash
# Using Homebrew
brew install swift-protobuf

# Or using Mint
mint install apple/swift-protobuf
```

#### Generate Swift Code

```bash
# Navigate to iOS proto directory
cd /path/to/your/iOS/project/eater/Services/

# Generate Swift protobuf
protoc --swift_out=. modify_food_record.proto
```

**Expected Output:**
- Updated `modify_food_record.pb.swift` with new properties:
  - `isTryAgain`
  - `imageID`
  - `addedSugarTsp`

### Step 5: Add Generated File to Xcode

1. Open Xcode project
2. If `modify_food_record.pb.swift` is not in the project, drag it into the Xcode project
3. Ensure "Copy items if needed" is checked
4. Add to correct target

### Step 6: Build & Verify

```bash
# In Xcode, clean build folder
⌘ + Shift + K

# Build project
⌘ + B
```

**Verify the errors are gone:**
- ✅ `modifyFoodRequest.isTryAgain = isTryAgain`
- ✅ `modifyFoodRequest.imageID = imageId`
- ✅ `modifyFoodRequest.addedSugarTsp = addedSugarTsp`

## 📋 Quick Checklist

### Backend (Python):
- [x] Updated `modify_food_record.proto` with new fields
- [ ] Regenerated `modify_food_record_pb2.py`
- [ ] Verified backend code compiles
- [ ] Deployed updated backend

### iOS (Swift):
- [ ] Copied updated `.proto` to iOS project
- [ ] Regenerated `.pb.swift` file
- [ ] Added generated file to Xcode
- [ ] Built project successfully
- [ ] Tested new features:
  - [ ] "Try Again" button works
  - [ ] "Add 1 tsp sugar" works
  - [ ] UI shows increased calories

## 🔍 Troubleshooting

### Issue: "protoc: command not found"

**Solution:**
```bash
# macOS
brew install protobuf

# Or install grpcio-tools
pip install grpcio-tools
```

### Issue: Swift protobuf plugin not found

**Solution:**
```bash
# Install swift-protobuf
brew install swift-protobuf

# Or add to PATH
export PATH="$PATH:/path/to/protoc-gen-swift"
```

### Issue: Generated file has old fields

**Solution:**
```bash
# Delete old generated file
rm modify_food_record_pb2.py  # Backend
rm modify_food_record.pb.swift  # iOS

# Regenerate
protoc --python_out=. modify_food_record.proto  # Backend
protoc --swift_out=. modify_food_record.proto   # iOS
```

### Issue: Xcode still shows errors after regeneration

**Solution:**
1. Clean build folder: ⌘ + Shift + K
2. Delete derived data:
   ```bash
   rm -rf ~/Library/Developer/Xcode/DerivedData/*
   ```
3. Restart Xcode
4. Build again: ⌘ + B

## 📝 Field Details

### New Proto Fields:

| Field | Type | Number | Purpose |
|-------|------|--------|---------|
| `is_try_again` | bool | 4 | Trigger AI re-analysis |
| `manual_food_name` | string | 5 | User manual input |
| `manual_insight` | string | 6 | User manual insight |
| `manual_components` | repeated string | 7 | User manual components |
| `image_id` | string | 8 | MinIO path for re-analysis |
| `added_sugar_tsp` | float | 9 | Added sugar in teaspoons |

### Swift Property Names (after generation):

| Proto Field | Swift Property |
|-------------|----------------|
| `is_try_again` | `isTryAgain` |
| `image_id` | `imageID` |
| `added_sugar_tsp` | `addedSugarTsp` |

### Python Property Names:

| Proto Field | Python Property |
|-------------|-----------------|
| `is_try_again` | `is_try_again` |
| `image_id` | `image_id` |
| `added_sugar_tsp` | `added_sugar_tsp` |

## 🚀 After Regeneration

### Backend Usage:

```python
from eater.proto import modify_food_record_pb2

request = modify_food_record_pb2.ModifyFoodRecordRequest()
request.time = 1234567890
request.user_email = "user@example.com"
request.percentage = 100
request.is_try_again = True  # ✅ NEW
request.image_id = "minio/path/to/image.jpg"  # ✅ NEW
request.added_sugar_tsp = 1.0  # ✅ NEW
```

### iOS Usage:

```swift
import Foundation

var request = Eater_ModifyFoodRecordRequest()
request.time = 1234567890
request.userEmail = "user@example.com"
request.percentage = 100
request.isTryAgain = true  // ✅ NEW
request.imageID = "minio/path/to/image.jpg"  // ✅ NEW
request.addedSugarTsp = 1.0  // ✅ NEW
```

## ✅ Success Criteria

After regeneration, you should be able to:
1. ✅ Backend accepts new fields in `ModifyFoodRecordRequest`
2. ✅ iOS compiles without errors
3. ✅ "Try Again" button sends `is_try_again: true`
4. ✅ "Add 1 tsp sugar" sends `added_sugar_tsp: 1.0`
5. ✅ UI updates correctly after modifications

## 📚 References

- Protocol Buffers: https://developers.google.com/protocol-buffers
- Swift Protobuf: https://github.com/apple/swift-protobuf
- grpcio-tools: https://pypi.org/project/grpcio-tools/

---

**Status:** ✅ Proto file updated, awaiting regeneration
**Next Step:** Run Step 2 (Backend) and Steps 3-6 (iOS)
