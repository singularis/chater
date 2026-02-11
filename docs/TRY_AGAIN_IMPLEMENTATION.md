# Try Again Feature - Implementation Plan

## 📋 Поточний статус

✅ **Готово:**
- Протобуф поля `is_try_again`, `image_id` додані
- iOS відправляє прапорець `is_try_again = true`
- Backend зберігає прапорець в Kafka і БД
- Поле `image_id` зберігається в `dishes_day`

❌ **Не реалізовано:**
- Фактична повторна AI-аналітика фото
- Завантаження оригінального фото з MinIO
- Відправлення контексту "попередній результат був невірний"

---

## 🎯 Що треба зробити

### 1. Розширити логіку в `eater/eater.py`

**Файл:** `/Users/iva/Documents/Eateria/chater_new/eater/eater.py`

**Локація:** Kafka consumer для топіку `modify_food_record`

**Поточна логіка:**
```python
# In consume_modify_food_record():
is_try_again = message_value.get("is_try_again", False)
image_id = message_value.get("image_id", "")

if is_try_again:
    logger.info(f"Try Again requested for {time_value}")
    # TODO: Implement re-analysis logic
```

**Що додати:**

#### Крок 1.1: Завантажити фото з MinIO
```python
from minio_client import get_minio_client  # Потрібно імпортувати

if is_try_again and image_id:
    try:
        # Get original photo from MinIO
        minio = get_minio_client()
        photo_data = minio.get_object("food-photos", f"{image_id}.jpg")
        photo_bytes = photo_data.read()
        
        logger.info(f"Loaded photo {image_id} for re-analysis")
    except Exception as e:
        logger.error(f"Failed to load photo from MinIO: {e}")
        return  # Cannot re-analyze without photo
```

#### Крок 1.2: Отримати попередні результати
```python
# Get previous analysis results for context
previous_food_name = message_value.get("manual_food_name", "")
previous_insight = message_value.get("manual_insight", "")

if not previous_food_name:
    # Fallback: fetch from database
    from postgres import get_food_record_by_time
    previous_record = get_food_record_by_time(time_value, user_email)
    if previous_record:
        previous_food_name = previous_record.dish_name
        previous_insight = previous_record.ingredients
```

#### Крок 1.3: Створити enhanced AI prompt
```python
# Build enhanced prompt for Vision AI
context_message = f"""
IMPORTANT: This is a re-analysis request. The user indicated that the previous result was incorrect.

Previous analysis was: {previous_food_name}
User's correction context: {previous_insight or 'No additional context provided'}

Please analyze this food photo again carefully, considering that the previous identification may have been wrong.
"""

# Load base prompt from prompt.yaml
with open("/app/prompt.yaml", "r", encoding="utf-8") as f:
    base_prompt = yaml.safe_load(f)["prompt"]

full_prompt = context_message + "\n\n" + base_prompt
```

#### Крок 1.4: Викликати Vision AI
```python
# Send to Vision AI (Gemini/GPT-4 Vision)
from vision_ai import analyze_food_photo  # Потрібно імпортувати правильний модуль

try:
    ai_response = analyze_food_photo(
        photo_bytes=photo_bytes,
        prompt=full_prompt,
        user_email=user_email
    )
    
    # Parse AI response
    new_dish_name = ai_response.get("dish_name")
    new_calories = ai_response.get("calories")
    new_components = ai_response.get("components")
    new_ingredients = ai_response.get("ingredients")
    # ... інші поля
    
    logger.info(f"Re-analysis complete: {previous_food_name} -> {new_dish_name}")
    
except Exception as e:
    logger.error(f"Vision AI re-analysis failed: {e}")
    return
```

#### Крок 1.5: Оновити запис в БД
```python
# Update the dish record with new AI results
from postgres import update_food_record_full

update_data = {
    "time": time_value,
    "user_email": user_email,
    "dish_name": new_dish_name,
    "estimated_avg_calories": new_calories,
    "ingredients": new_ingredients,
    "components": new_components,
    "health_rating": ai_response.get("health_rating"),
    "total_avg_weight": ai_response.get("weight"),
    "contains": ai_response.get("contains"),
}

update_food_record_full(update_data, user_email)

logger.info(f"Try Again completed for {time_value}: {previous_food_name} -> {new_dish_name}")
```

---

### 2. Додати допоміжну функцію в `eater/postgres.py`

**Новий метод:**
```python
def get_food_record_by_time(time_value: int, user_email: str):
    """Get a single food record by timestamp"""
    try:
        with get_db_session() as session:
            record = (
                session.query(DishesDay)
                .filter(DishesDay.time == time_value)
                .filter(DishesDay.user_email == user_email)
                .first()
            )
            return record
    except Exception as e:
        logger.error(f"Failed to get food record: {e}")
        return None

def update_food_record_full(data: dict, user_email: str):
    """Fully replace a food record (for Try Again re-analysis)"""
    try:
        with get_db_session() as session:
            time_value = data.get("time")
            record = (
                session.query(DishesDay)
                .filter(DishesDay.time == time_value)
                .filter(DishesDay.user_email == user_email)
                .first()
            )
            
            if not record:
                logger.error(f"No record found for time {time_value}")
                return
            
            # Update all fields
            record.dish_name = data.get("dish_name", record.dish_name)
            record.estimated_avg_calories = data.get("estimated_avg_calories", record.estimated_avg_calories)
            record.ingredients = data.get("ingredients", record.ingredients)
            record.total_avg_weight = data.get("total_avg_weight", record.total_avg_weight)
            record.health_rating = data.get("health_rating", record.health_rating)
            record.contains = data.get("contains", record.contains)
            # Keep added_sugar_tsp, image_id as-is
            
            session.commit()
            logger.info(f"Updated food record at {time_value}")
            
            # Trigger daily totals recalculation
            write_to_dish_day(recalculate=True, user_email=user_email)
            
    except Exception as e:
        logger.error(f"Failed to update food record: {e}")
```

---

### 3. Перевірити MinIO клієнт

**Файл:** Знайти де ініціалізується MinIO (може бути `minio_client.py` або в `chater_ui`)

**Переконатися:**
- MinIO bucket `food-photos` існує
- Є метод для завантаження фото по `image_id`
- Credentials налаштовані в `eater` сервісі

**Якщо MinIO в іншому сервісі:**
- Можна викликати HTTP API до `chater_ui` для отримання фото
- Або скопіювати MinIO credentials в `eater` environment

---

### 4. Тестування

#### 4.1 Unit тести
```python
# Test re-analysis flow
def test_try_again_flow():
    # Mock MinIO client
    # Mock Vision AI
    # Simulate Kafka message with is_try_again=True
    # Assert database updated
    pass
```

#### 4.2 Integration тест
1. Завантажити фото чаю
2. AI розпізнало як "Coffee" (помилка)
3. Натиснути "Try Again" в iOS
4. Backend має:
   - Завантажити фото
   - Відправити на AI з контекстом "previous was Coffee"
   - Оновити запис на "Tea"
5. iOS має показати оновлений результат

---

## 📦 Необхідні залежності

Перевірити що є:
- `minio` Python library в `eater/requirements.txt`
- Доступ до Vision AI API (Gemini/GPT-4 Vision)
- `prompt.yaml` доступний в `/app/` в Docker контейнері

---

## ⏱ Оцінка часу

- **Крок 1 (eater.py логіка):** 45-60 хв
- **Крок 2 (postgres.py методи):** 15-20 хв
- **Крок 3 (MinIO setup):** 10-15 хв
- **Крок 4 (тестування):** 30-40 хв

**Загалом:** ~2 години

---

## 🔍 Питання до вирішення

1. **Vision AI:** Який саме сервіс використовується? (Gemini, GPT-4 Vision, інше?)
2. **MinIO:** Чи є MinIO client в `eater` сервісі, чи треба викликати API?
3. **Prompt location:** Де зараз зберігається базовий prompt для аналізу фото?
4. **Response format:** Який формат відповіді від Vision AI? (JSON structure)

---

## 📝 Приклад використання

**iOS:**
```swift
// User taps "Try Again" button
var request = Eater_ModifyFoodRecordRequest()
request.time = foodItem.timestamp
request.userEmail = userEmail
request.percentage = 100
request.isTryAgain = true  // Key flag
request.imageID = foodItem.imageId  // Original photo ID
request.manualFoodName = foodItem.dishName  // Previous result for context

grpcService.modifyFoodRecord(request: request)
```

**Backend flow:**
```
1. Kafka: modify_food_record message (is_try_again=true)
2. eater.py: Detect is_try_again flag
3. Load photo from MinIO using image_id
4. Build enhanced AI prompt with previous result
5. Call Vision AI
6. Parse new results
7. Update dishes_day record
8. Recalculate daily totals
9. iOS fetches updated data
```

---

## ✅ Checklist для реалізації

- [ ] Додати MinIO client import в `eater/eater.py`
- [ ] Реалізувати завантаження фото з MinIO
- [ ] Додати `get_food_record_by_time()` в `postgres.py`
- [ ] Додати `update_food_record_full()` в `postgres.py`
- [ ] Створити enhanced AI prompt з контекстом
- [ ] Інтегрувати Vision AI виклик
- [ ] Оновлювати БД з новими результатами
- [ ] Протестувати повний flow (iOS -> Backend -> AI -> DB -> iOS)
- [ ] Додати логування для дебагу
- [ ] Додати error handling (photo not found, AI timeout, etc.)

---

## 📄 Корисні файли

- `chater_new/eater/eater.py` - Kafka consumer (головна логіка)
- `chater_new/eater/postgres.py` - БД операції
- `chater_new/chater_ui/eater/prompt.yaml` - AI prompt
- `chater_new/chater_ui/eater/proto/modify_food_record.proto` - Protobuf schema
- `eater/eater/Services/GRPCService.swift` - iOS gRPC client
