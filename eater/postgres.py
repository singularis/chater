import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (ARRAY, JSON, BigInteger, Column, Date, Float, Integer,
                        PrimaryKeyConstraint, String, cast, create_engine,
                        func, text)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

db_user = os.environ.get("POSTGRES_USER")
db_password = os.environ.get("POSTGRES_PASSWORD")
db_host = os.environ.get("POSTGRES_HOST")
db_name = os.environ.get("POSTGRES_DB")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:5432/{db_name}"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
)

Base = declarative_base()


def current_date():
    return datetime.now().date()


def _health_rating_for_output(value):
    """Return health_rating 0-100 for API; -1 if missing."""
    if value is None:
        return -1
    return max(0, min(100, int(value)))


class DishesDay(Base):
    __tablename__ = "dishes_day"
    __table_args__ = {"schema": "public"}

    time = Column(BigInteger, primary_key=True)
    date = Column(Date)
    dish_name = Column(String)
    estimated_avg_calories = Column(Integer)
    ingredients = Column(ARRAY(String))
    total_avg_weight = Column(Integer)
    health_rating = Column(Integer)
    food_health_level = Column(String)
    contains = Column(JSON)
    user_email = Column(String, nullable=False)
    image_id = Column(String)
    added_sugar_tsp = Column(Float, default=0.0)


class TotalForDay(Base):
    __tablename__ = "total_for_day"
    __table_args__ = (PrimaryKeyConstraint("date", "user_email"), {"schema": "public"})

    date = Column(Date)
    today = Column(Date)
    total_calories = Column(Integer)
    ingredients = Column(ARRAY(String))
    dishes_of_day = Column(ARRAY(String))
    total_avg_weight = Column(Integer)
    contains = Column(JSON)
    user_email = Column(String, nullable=False)


class Weight(Base):
    __tablename__ = "weight"
    __table_args__ = {"schema": "public"}

    time = Column(BigInteger, primary_key=True)
    date = Column(String)
    weight = Column(Float)
    user_email = Column(String, nullable=False)


class AlcoholConsumption(Base):
    __tablename__ = "alcohol_consumption"
    __table_args__ = {"schema": "public"}

    time = Column(BigInteger, primary_key=True)
    date = Column(Date)
    drink_name = Column(String)
    calories = Column(Integer)
    quantity = Column(Integer)
    user_email = Column(String, nullable=False)


class AlcoholForDay(Base):
    __tablename__ = "alcohol_for_day"
    __table_args__ = (PrimaryKeyConstraint("date", "user_email"), {"schema": "public"})

    date = Column(Date)
    user_email = Column(String, nullable=False)
    total_drinks = Column(Integer)
    total_calories = Column(Integer)
    drinks_of_day = Column(ARRAY(String))


Session = sessionmaker(bind=engine)


@contextmanager
def get_db_session():
    session = Session()
    try:
        yield session
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        raise
    finally:
        session.close()


def write_to_dish_day(
    message=None, recalculate: Optional[bool] = False, user_email: str = None
):
    try:
        with get_db_session() as session:
            if not recalculate:
                dish_name = message.get("dish_name")
                estimated_avg_calories = message.get("estimated_avg_calories")
                ingredients = message.get("ingredients")
                total_avg_weight = message.get("total_avg_weight")
                raw_rating = message.get("health_rating", 0)
                health_rating = max(0, min(100, int(raw_rating))) if isinstance(raw_rating, (int, float)) else 0
                food_health_level_data = message.get("food_health_level")
                food_health_level_str = None
                if food_health_level_data:
                    import json

                    food_health_level_str = json.dumps(food_health_level_data)
                contains = message.get("contains")
                image_id = message.get("image_id")
                
                # Get date from message if present (e.g., from backdated photo upload)
                # Ensure it's in YYYY-MM-DD format for storage
                date_val = message.get("date")
                if date_val:
                    # Input expected: DD-MM-YYYY (from process_photo dispatch)
                    # Output wanted: YYYY-MM-DD (for Postgres date column standard)
                    try:
                        day, month, year = date_val.split("-")
                        storage_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    except ValueError:
                        # Fallback if format is unexpected
                        storage_date = current_date()
                else:
                    storage_date = current_date()

                # Get correct timestamp for time column
                # If message has timestamp, use it. Otherwise use now.
                timestamp_val = message.get("timestamp")
                if timestamp_val:
                    time_to_store = int(timestamp_val)
                else:
                    time_to_store = int(datetime.now().timestamp())

                # Upsert: overwrite existing record for same time/user (used by manual re-analysis)
                dish_day = (
                    session.query(DishesDay)
                    .filter(DishesDay.time == time_to_store)
                    .filter(DishesDay.user_email == user_email)
                    .first()
                )

                if dish_day:
                    dish_day.date = storage_date
                    dish_day.dish_name = dish_name
                    dish_day.estimated_avg_calories = estimated_avg_calories
                    dish_day.ingredients = ingredients
                    dish_day.total_avg_weight = total_avg_weight
                    dish_day.health_rating = health_rating
                    dish_day.food_health_level = food_health_level_str
                    dish_day.contains = contains
                    dish_day.image_id = image_id
                else:
                    dish_day = DishesDay(
                        time=time_to_store,
                        date=storage_date,
                        dish_name=dish_name,
                        estimated_avg_calories=estimated_avg_calories,
                        ingredients=ingredients,
                        total_avg_weight=total_avg_weight,
                        health_rating=health_rating,
                        food_health_level=food_health_level_str,
                        contains=contains,
                        user_email=user_email,
                        image_id=image_id,
                    )
                    session.add(dish_day)

                # If the dish is alcohol, record alcohol consumption
                try:
                    contains_obj = contains or {}
                    is_alcohol = bool(contains_obj.get("is_alcohol", False))
                except Exception:
                    is_alcohol = False

                if is_alcohol:
                    drink_name = dish_name
                    calories = estimated_avg_calories or 0
                    quantity = total_avg_weight or 0
                    alcohol_entry = AlcoholConsumption(
                        time=int(datetime.now().timestamp()),
                        date=current_date(),
                        drink_name=drink_name,
                        calories=int(calories),
                        quantity=int(quantity),
                        user_email=user_email,
                    )
                    session.add(alcohol_entry)
                    logger.debug(
                        f"Recorded alcohol consumption for user {user_email}: {drink_name}, cal {calories}, qty {quantity}"
                    )
                session.commit()
                
                logger.debug(f"Successfully wrote dish data to database: {dish_name}")

            # Determine which date to recalculate totals for
            # logic: if we just wrote, use storage_date. If generic recalc, try to infer or fallback.
            # But wait, storage_date is local to the block above. We need scope.
            # Best approach: if recalculating without message (generic), use current_date().
            # If message provided (even if recalculate=True logic path entered), try to extract date.
            
            recalc_date = current_date() # Default
            if message:
                 date_val = message.get("date")
                 if date_val:
                    try:
                        day, month, year = date_val.split("-")
                        recalc_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    except ValueError:
                         pass
            
            # Note: storage_date above was YYYY-MM-DD. current_date() returns user's notion of today YYYY-MM-DD.
            # We need to make sure we query consistently.
            
            # Query aggregated data for the *target* date
            logger.debug(f"Calculating total food data for {recalc_date}")

            # Get total_calories, total_weight, all_dishes, all_contains
            total_data = (
                session.query(
                    func.sum(DishesDay.estimated_avg_calories).label("total_calories"),
                    func.sum(DishesDay.total_avg_weight).label("total_weight"),
                    func.array_agg(DishesDay.dish_name).label("all_dishes"),
                    func.json_agg(DishesDay.contains).label("all_contains"),
                )
                .filter(DishesDay.date == recalc_date)
                .filter(DishesDay.user_email == user_email)
                .one()
            )

            ingredients_subq = (
                session.query(func.unnest(DishesDay.ingredients).label("ingredient"))
                .filter(DishesDay.date == recalc_date)
                .filter(DishesDay.user_email == user_email)
                .subquery()
            )

            all_ingredients_result = session.query(
                func.array_agg(ingredients_subq.c.ingredient).label("all_ingredients")
            ).one()

            all_ingredients = all_ingredients_result.all_ingredients or []

            total_calories = total_data.total_calories or 0
            total_weight = total_data.total_weight or 0
            all_dishes = (
                [dish for dish in total_data.all_dishes if dish]
                if total_data.all_dishes
                else []
            )

            all_contains = total_data.all_contains or []
            aggregated_contains = {
                "proteins": 0,
                "fats": 0,
                "carbohydrates": 0,
                "sugar": 0,
            }
            for entry in all_contains:
                for key in aggregated_contains:
                    aggregated_contains[key] += entry.get(key, 0)
            
            # Add sugar from added_sugar_tsp (1 tsp = ~5g)
            total_added_sugar_result = (
                session.query(func.sum(DishesDay.added_sugar_tsp))
                .filter(DishesDay.date == recalc_date)
                .filter(DishesDay.user_email == user_email)
                .scalar()
            )
            total_added_sugar_tsp = total_added_sugar_result or 0
            aggregated_contains["sugar"] += float(total_added_sugar_tsp) * 5  # Convert tsp to grams

            # Prepare data for total_for_day table
            total_for_day = TotalForDay(
                date=recalc_date,
                today=recalc_date,
                total_calories=total_calories,
                ingredients=all_ingredients,
                dishes_of_day=all_dishes,
                total_avg_weight=total_weight,
                contains=aggregated_contains,
                user_email=user_email,
            )

            # Check if there's an existing entry for today
            existing_entry = (
                session.query(TotalForDay)
                .filter(TotalForDay.date == recalc_date)
                .filter(TotalForDay.today == recalc_date)
                .filter(TotalForDay.user_email == user_email)
                .first()
            )
            if existing_entry:
                logger.debug("Updating existing entry in total_for_day table")
                existing_entry.total_calories = total_calories
                existing_entry.ingredients = all_ingredients
                existing_entry.dishes_of_day = all_dishes
                existing_entry.total_avg_weight = total_weight
                existing_entry.contains = aggregated_contains
            else:
                logger.debug("Inserting new entry in total_for_day table")
                session.add(total_for_day)

            session.commit()

            logger.debug(
                f"Successfully wrote aggregated data to total_for_day for {recalc_date}"
            )

            # Aggregate alcohol for the day
            try:
                alcohol_totals = (
                    session.query(
                        func.sum(AlcoholConsumption.calories).label("total_calories"),
                        func.count(AlcoholConsumption.time).label("total_drinks"),
                        func.array_agg(AlcoholConsumption.drink_name).label("drinks"),
                    )
                    .filter(AlcoholConsumption.date == recalc_date)
                    .filter(AlcoholConsumption.user_email == user_email)
                    .one()
                )

                total_alcohol_cal = int(alcohol_totals.total_calories or 0)
                total_drinks = int(alcohol_totals.total_drinks or 0)
                drinks_list = alcohol_totals.drinks or []

                existing_alcohol = (
                    session.query(AlcoholForDay)
                    .filter(AlcoholForDay.date == recalc_date)
                    .filter(AlcoholForDay.user_email == user_email)
                    .first()
                )
                if existing_alcohol:
                    existing_alcohol.total_calories = total_alcohol_cal
                    existing_alcohol.total_drinks = total_drinks
                    existing_alcohol.drinks_of_day = drinks_list
                else:
                    alcohol_for_day = AlcoholForDay(
                        date=recalc_date,
                        user_email=user_email,
                        total_calories=total_alcohol_cal,
                        total_drinks=total_drinks,
                        drinks_of_day=drinks_list,
                    )
                    session.add(alcohol_for_day)
                session.commit()
                logger.debug(
                    f"Updated alcohol_for_day for {recalc_date} user {user_email}"
                )
            except Exception as e:
                logger.warning(f"Failed to aggregate alcohol_for_day: {e}")
    except Exception as e:
        logger.error(f"Error writing to database: {e}")


def get_today_dishes(user_email: str = None):
    try:
        with get_db_session() as session:
            latest_weight_entry = (
                session.query(Weight)
                .filter(Weight.user_email == user_email)
                .order_by(Weight.time.desc())
                .first()
            )

            total_data = (
                session.query(TotalForDay)
                .filter(TotalForDay.today == current_date())
                .filter(TotalForDay.user_email == user_email)
                .first()
            )
            if not total_data:
                logger.debug(f"No data found in total_for_day for {current_date()}")
                total_for_day_data = {
                    "total_calories": 0,
                    "total_avg_weight": (
                        latest_weight_entry.weight if latest_weight_entry else 0
                    ),
                    "contains": [],
                }
                dishes_list = []
                result = {
                    "total_for_day": total_for_day_data,
                    "dishes_today": dishes_list,
                }
                if latest_weight_entry:
                    result["latest_weight"] = {
                        "time": latest_weight_entry.time,
                        "weight": latest_weight_entry.weight,
                    }
                return result
            total_for_day_data = {
                "total_calories": total_data.total_calories,
                "total_avg_weight": total_data.total_avg_weight,
                "contains": total_data.contains,
            }
            dishes_today = (
                session.query(DishesDay)
                .filter(DishesDay.date == current_date())
                .filter(DishesDay.user_email == user_email)
                .all()
            )
            dishes_list = [
                {
                    "time": dish.time,
                    "dish_name": dish.dish_name,
                    "estimated_avg_calories": dish.estimated_avg_calories,
                    "total_avg_weight": dish.total_avg_weight,
                    "health_rating": _health_rating_for_output(dish.health_rating),
                    "ingredients": dish.ingredients,
                    "image_id": dish.image_id,
                    "added_sugar_tsp": getattr(dish, 'added_sugar_tsp', 0.0) or 0.0,
                }
                for dish in dishes_today
            ]
            result = {
                "total_for_day": total_for_day_data,
                "dishes_today": dishes_list,
            }
            # Include today's alcohol summary
            try:
                alcohol = (
                    session.query(AlcoholForDay)
                    .filter(AlcoholForDay.date == current_date())
                    .filter(AlcoholForDay.user_email == user_email)
                    .first()
                )
                if alcohol:
                    result["alcohol_for_day"] = {
                        "total_drinks": alcohol.total_drinks,
                        "total_calories": alcohol.total_calories,
                        "drinks_of_day": alcohol.drinks_of_day or [],
                    }
            except Exception as e:
                logger.warning(f"Failed to fetch alcohol_for_day: {e}")
            if latest_weight_entry:
                result["latest_weight"] = {
                    "time": latest_weight_entry.time,
                    "weight": latest_weight_entry.weight,
                }

            logger.debug(f"Result of get_today_dishes {result}")
            return result
    except Exception as e:
        logger.error(f"Error retrieving today's dishes: {e}")
        return {}


def get_custom_date_dishes(custom_date: str, user_email: str = None):
    """
    Get dishes for a specific date in dd-mm-yyyy format
    """
    try:
        with get_db_session() as session:
            # Convert dd-mm-yyyy to yyyy-mm-dd format for database query
            day, month, year = custom_date.split("-")
            formatted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

            # Get the timestamp for the requested date to find closest weight entry
            requested_date = datetime.strptime(formatted_date, "%Y-%m-%d")
            requested_timestamp = int(requested_date.timestamp())

            # Find weight entry closest to the requested date
            # First try to get weight entries and find the one with minimum time difference
            weight_entries = (
                session.query(Weight).filter(Weight.user_email == user_email).all()
            )

            closest_weight_entry = None
            if weight_entries:
                closest_weight_entry = min(
                    weight_entries, key=lambda w: abs(w.time - requested_timestamp)
                )

            total_data = (
                session.query(TotalForDay)
                .filter(TotalForDay.today == formatted_date)
                .filter(TotalForDay.user_email == user_email)
                .first()
            )
            dishes_today = (
                session.query(DishesDay)
                .filter(DishesDay.date == formatted_date)
                .filter(DishesDay.user_email == user_email)
                .all()
            )
            dishes_list = [
                {
                    "time": dish.time,
                    "dish_name": dish.dish_name,
                    "estimated_avg_calories": dish.estimated_avg_calories,
                    "total_avg_weight": dish.total_avg_weight,
                    "health_rating": _health_rating_for_output(dish.health_rating),
                    "ingredients": dish.ingredients,
                    "food_health_level": dish.food_health_level,
                    "image_id": dish.image_id,
                    "added_sugar_tsp": getattr(dish, 'added_sugar_tsp', 0.0) or 0.0,
                }
                for dish in dishes_today
            ]

            if not total_data:
                logger.debug(f"No data found in total_for_day for {formatted_date}")
                # Calculate summary from dishes if total_for_day is missing
                cal_sum = sum(d.estimated_avg_calories for d in dishes_today)
                weight_sum = sum(d.total_avg_weight for d in dishes_today)

                total_for_day_data = {
                    "total_calories": cal_sum,
                    "total_avg_weight": weight_sum,
                    "contains": {},
                }
                result = {
                    "total_for_day": total_for_day_data,
                    "dishes_today": dishes_list,
                }
                if closest_weight_entry:
                    result["closest_weight"] = {
                        "time": closest_weight_entry.time,
                        "weight": closest_weight_entry.weight,
                        "date": closest_weight_entry.date,
                    }
                return result
            total_for_day_data = {
                "total_calories": total_data.total_calories,
                "total_avg_weight": total_data.total_avg_weight,
                "contains": total_data.contains,
            }
            # dishes_today and dishes_list already fetched above
            result = {
                "total_for_day": total_for_day_data,
                "dishes_today": dishes_list,
            }
            # Include alcohol summary for date
            try:
                alcohol = (
                    session.query(AlcoholForDay)
                    .filter(AlcoholForDay.date == formatted_date)
                    .filter(AlcoholForDay.user_email == user_email)
                    .first()
                )
                if alcohol:
                    result["alcohol_for_day"] = {
                        "total_drinks": alcohol.total_drinks,
                        "total_calories": alcohol.total_calories,
                        "drinks_of_day": alcohol.drinks_of_day or [],
                    }
            except Exception as e:
                logger.warning(
                    f"Failed to fetch alcohol_for_day for {formatted_date}: {e}"
                )

            # Return raw alcohol events in range if asked later via separate function
            if closest_weight_entry:
                result["closest_weight"] = {
                    "time": closest_weight_entry.time,
                    "weight": closest_weight_entry.weight,
                    "date": closest_weight_entry.date,
                }

            logger.debug(
                f"Result of get_custom_date_dishes for {formatted_date}: {result}"
            )
            return result
    except Exception as e:
        logger.error(f"Error retrieving dishes for date {custom_date}: {e}")
        return {}


def delete_food(time, user_email: str = None):
    logger.debug(f"Deleting food with time {time} from db")
    try:
        with get_db_session() as session:
            # Handle case where time is passed as a dictionary with time and user_email
            if isinstance(time, dict) and "time" in time:
                time_value = time["time"]
                user_email = time.get("user_email", user_email)
            else:
                time_value = time

            rows_deleted = (
                session.query(DishesDay)
                .filter(DishesDay.time == time_value)
                .filter(DishesDay.user_email == user_email)
                .delete()
            )
            session.commit()
            if rows_deleted > 0:
                logger.debug(
                    f"Successfully deleted {rows_deleted} food entries with time {time_value} from database"
                )
                write_to_dish_day(recalculate=True, user_email=user_email)
            else:
                logger.debug(f"No food entries found with time {time_value}")
    except Exception as e:
        logger.error(f"Error deleting food from database: {e}")


def modify_food(data, user_email: str = None):
    logger.debug(f"Modifying food record for user {user_email}")
    try:
        with get_db_session() as session:
            # Handle case where data is passed as a dictionary with time, user_email, and percentage
            if isinstance(data, dict):
                time_value = data.get("time")
                user_email = data.get("user_email", user_email)
                percentage = data.get("percentage", 100)
                added_sugar_tsp = float(data.get("added_sugar_tsp") or 0.0)
                is_try_again = data.get("is_try_again", False)
                image_id = data.get("image_id", "")
                manual_food_name = data.get("manual_food_name", "")
                manual_insight = data.get("manual_insight", "")
                manual_components = data.get("manual_components", [])
            else:
                logger.error(f"Invalid data format for modify_food: {data}")
                return

            # Find the food record to modify
            food_record = (
                session.query(DishesDay)
                .filter(DishesDay.time == time_value)
                .filter(DishesDay.user_email == user_email)
                .first()
            )

            if food_record:
                modified = False
                
                # Handle "Add Sugar" functionality
                if added_sugar_tsp > 0:
                    logger.info(f"Adding {added_sugar_tsp} tsp sugar to food at time={time_value}")
                    
                    # 1 tsp sugar = ~5g = ~20 kcal
                    sugar_calories = int(added_sugar_tsp * 20)
                    sugar_weight = int(added_sugar_tsp * 5)
                    
                    # Add to existing values
                    current_sugar = getattr(food_record, 'added_sugar_tsp', 0) or 0
                    food_record.added_sugar_tsp = current_sugar + added_sugar_tsp
                    food_record.estimated_avg_calories += sugar_calories
                    food_record.total_avg_weight += sugar_weight
                    
                    # Add "Sugar" to ingredients if not present
                    if food_record.ingredients and "Sugar" not in food_record.ingredients:
                        food_record.ingredients = list(food_record.ingredients) + ["Sugar"]
                    
                    # Update contains field for sugar
                    if food_record.contains:
                        if "sugars" in food_record.contains:
                            food_record.contains["sugars"] += sugar_weight
                        else:
                            food_record.contains["sugars"] = sugar_weight
                    
                    modified = True
                    logger.info(f"Sugar added: +{sugar_calories} kcal, +{sugar_weight}g")
                
                # Handle "Try Again" flag (store for later processing)
                if is_try_again and image_id:
                    logger.info(f"Try Again requested for time={time_value}, image_id={image_id}")
                    # TODO: Implement photo re-analysis logic
                    # For now, just log it - proper implementation needs Kafka message to vision AI
                    modified = True
                
                # Handle manual customization
                if manual_food_name:
                    food_record.dish_name = manual_food_name
                    modified = True
                    logger.info(f"Manual food name updated to: {manual_food_name}")
                
                if manual_components:
                    food_record.ingredients = manual_components
                    modified = True
                    logger.info(f"Manual ingredients updated: {manual_components}")

                # Added sugar: persist tsp and update calories/grams/contains/health rating.
                # (1 tsp sugar ≈ 5g, ≈ 20 kcal)
                if added_sugar_tsp and added_sugar_tsp > 0:
                    existing = float(getattr(food_record, "added_sugar_tsp", 0.0) or 0.0)
                    food_record.added_sugar_tsp = existing + added_sugar_tsp

                    # Update dish totals (do not scale existing dish; add on top)
                    food_record.estimated_avg_calories = int(
                        (food_record.estimated_avg_calories or 0) + (20 * added_sugar_tsp)
                    )
                    food_record.total_avg_weight = int(
                        (food_record.total_avg_weight or 0) + (5 * added_sugar_tsp)
                    )

                    # Update nutrition map if present
                    if food_record.contains and isinstance(food_record.contains, dict):
                        sugar_g = 5 * added_sugar_tsp
                        food_record.contains["sugar"] = float(food_record.contains.get("sugar", 0) or 0) + sugar_g
                        food_record.contains["carbohydrates"] = float(food_record.contains.get("carbohydrates", 0) or 0) + sugar_g

                    # Penalize health rating for added sugar (10 points per tsp)
                    try:
                        base = int(getattr(food_record, "health_rating", 0) or 0)
                        food_record.health_rating = max(0, min(100, base - int(10 * added_sugar_tsp)))
                    except Exception:
                        pass

                    modified = True
                    logger.info(f"Sugar added: +{added_sugar_tsp} tsp")
                
                # Handle percentage modification (original functionality)
                if percentage != 100:
                    factor = percentage / 100.0
                    
                    # Update the food record with the new percentage
                    food_record.estimated_avg_calories = int(
                        food_record.estimated_avg_calories * factor
                    )
                    food_record.total_avg_weight = int(
                        food_record.total_avg_weight * factor
                    )
                    
                    # Update nutritional values in the contains field
                    if food_record.contains:
                        for key in food_record.contains:
                            if isinstance(food_record.contains[key], (int, float)):
                                food_record.contains[key] = (
                                    food_record.contains[key] * factor
                                )
                    
                    modified = True
                    logger.debug(f"Portion adjusted by {percentage}%")

                if modified:
                    session.commit()
                    logger.debug(
                        f"Successfully modified food record with time {time_value} for user {user_email}"
                    )
                    
                    # Recalculate the totals for the day after modification
                    write_to_dish_day(recalculate=True, user_email=user_email)
                else:
                    logger.debug(f"No modifications applied for time {time_value}")
            else:
                logger.debug(
                    f"No food record found with time {time_value} for user {user_email}"
                )
    except Exception as e:
        logger.error(f"Error modifying food record: {e}")


def write_weight(weight, user_email: str = None):
    try:
        with get_db_session() as session:
            weight_entry = Weight(
                time=int(datetime.now().timestamp()),
                date=current_date(),
                weight=weight,
                user_email=user_email,
            )
            session.add(weight_entry)
            session.commit()
            logger.debug(f"Successfully wrote weight data to database: {weight}")
    except Exception as e:
        logger.error(f"Error writing weight to database: {e}")


def get_dishes(days, user_email: str = None):
    try:
        logger.debug(f"Starting get_dishes function with days={days}")
        with get_db_session() as session:
            logger.debug("Database session created successfully.")
            today = datetime.now()
            start_date = today - timedelta(days=days)
            dishes = (
                session.query(DishesDay)
                .filter(DishesDay.date.between(start_date, today))
                .filter(DishesDay.user_email == user_email)
                .all()
            )

            dishes_list = [
                {
                    "time": dish.time,
                    "date": dish.date,
                    "dish_name": dish.dish_name,
                    "estimated_avg_calories": dish.estimated_avg_calories,
                    "total_avg_weight": dish.total_avg_weight,
                    "health_rating": _health_rating_for_output(dish.health_rating),
                    "ingredients": dish.ingredients,
                    "contains": dish.contains,
                }
                for dish in dishes
            ]
            return dishes_list
    except Exception as e:
        logger.error(f"Error retrieving dishes from database: {e}", exc_info=True)
        return []


def get_alcohol_events_in_range(start_date: str, end_date: str, user_email: str = None):
    """
    Get alcohol events for a date range where dates are provided in dd-mm-yyyy format
    and converted to yyyy-mm-dd for DB filtering.
    """
    try:
        # Convert dd-mm-yyyy to yyyy-mm-dd
        def to_date(date_str: str):
            day, month, year = date_str.split("-")
            return datetime.strptime(
                f"{year}-{month.zfill(2)}-{day.zfill(2)}", "%Y-%m-%d"
            ).date()

        start_sql = to_date(start_date)
        end_sql = to_date(end_date)

        with get_db_session() as session:
            events_query = (
                session.query(AlcoholConsumption)
                .filter(AlcoholConsumption.user_email == user_email)
                .filter(AlcoholConsumption.date.between(start_sql, end_sql))
                .all()
            )
            if not events_query:
                try:
                    events_query = (
                        session.query(AlcoholConsumption)
                        .filter(AlcoholConsumption.user_email == user_email)
                        .filter(
                            cast(AlcoholConsumption.date, Date).between(
                                start_sql, end_sql
                            )
                        )
                        .all()
                    )
                except Exception:
                    pass
            events = []
            for ev in events_query:
                events.append(
                    {
                        "time": ev.time,
                        "date": (
                            ev.date.strftime("%Y-%m-%d")
                            if isinstance(ev.date, datetime)
                            else str(ev.date)
                        ),
                        "drink_name": ev.drink_name,
                        "calories": ev.calories,
                        "quantity": ev.quantity,
                    }
                )
            return events
    except Exception as e:
        logger.error(f"Error retrieving alcohol events: {e}")
        return []


def get_food_health_level(time_value: int, user_email: str = None):
    """
    Get the food_health_level for a specific dish by time.
    Returns None if not found or no health level stored.
    """
    try:
        with get_db_session() as session:
            dish = (
                session.query(DishesDay)
                .filter(DishesDay.time == time_value)
                .filter(DishesDay.user_email == user_email)
                .first()
            )
            if dish and dish.food_health_level:
                import json

                return json.loads(dish.food_health_level)
            return None
    except Exception as e:
        logger.error(f"Error retrieving food_health_level: {e}")
        return None


def record_chess_game(player_email: str, opponent_email: str, result: str, timestamp: int):
    """Record a chess game for both players (sync). result: win, loss, or draw."""
    try:
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO chess_games (player_email, opponent_email, result, timestamp)
                    VALUES (:player_email, :opponent_email, :result, :timestamp)
                """),
                {
                    "player_email": player_email,
                    "opponent_email": opponent_email,
                    "result": result,
                    "timestamp": timestamp,
                },
            )
            opponent_result = "loss" if result == "win" else ("win" if result == "loss" else "draw")
            session.execute(
                text("""
                    INSERT INTO chess_games (player_email, opponent_email, result, timestamp)
                    VALUES (:player_email, :opponent_email, :result, :timestamp)
                """),
                {
                    "player_email": opponent_email,
                    "opponent_email": player_email,
                    "result": opponent_result,
                    "timestamp": timestamp,
                },
            )
            session.commit()
        return True
    except Exception as e:
        logger.exception("record_chess_game failed: %s", e)
        return False


def get_chess_stats_sync(user_email: str, opponent_email: Optional[str] = None):
    """
    Return chess stats for user vs opponent. If opponent_email is None, use last opponent.
    Returns dict with score, opponent_name (email), last_game_date, or None on error.
    """
    try:
        with get_db_session() as session:
            if not opponent_email:
                last_row = session.execute(
                    text("""
                        SELECT opponent_email, timestamp
                        FROM chess_games
                        WHERE player_email = :user_email
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """),
                    {"user_email": user_email},
                ).fetchone()
                if not last_row:
                    return {"score": "0:0", "opponent_name": "", "last_game_date": "", "wins": 0, "losses": 0}
                opponent_email = last_row[0]
                last_ts = last_row[1]
            else:
                last_ts = None

            result = session.execute(
                text("""
                    SELECT
                        COUNT(*) FILTER (WHERE result = 'win') AS wins,
                        COUNT(*) FILTER (WHERE result = 'loss') AS losses,
                        MAX(timestamp) AS last_game_timestamp
                    FROM chess_games
                    WHERE player_email = :user_email AND opponent_email = :opponent_email
                """),
                {"user_email": user_email, "opponent_email": opponent_email},
            )
            row = result.fetchone()
            if not row:
                return {"score": "0:0", "opponent_name": opponent_email, "last_game_date": "", "wins": 0, "losses": 0}
            wins = row[0] or 0
            losses = row[1] or 0
            ts = last_ts or row[2]
            last_date = ""
            if ts:
                from datetime import datetime, timezone
                try:
                    dt = datetime.fromtimestamp(int(ts) / 1000.0, tz=timezone.utc)
                    last_date = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass
            return {
                "score": f"{wins}:{losses}",
                "opponent_name": opponent_email,
                "last_game_date": last_date,
                "wins": wins,
                "losses": losses,
            }
    except Exception as e:
        logger.exception("get_chess_stats_sync failed: %s", e)
        return None


def get_all_chess_data_sync(user_email: str):
    """Return total_wins and opponents dict {email: 'wins:losses'}. None on error."""
    try:
        with get_db_session() as session:
            total_row = session.execute(
                text("""
                    SELECT COUNT(*) FILTER (WHERE result = 'win') AS total_wins
                    FROM chess_games
                    WHERE player_email = :user_email
                """),
                {"user_email": user_email},
            ).fetchone()
            total_wins = int(total_row[0] or 0) if total_row else 0

            opp_rows = session.execute(
                text("""
                    SELECT opponent_email,
                           COUNT(*) FILTER (WHERE result = 'win') AS wins,
                           COUNT(*) FILTER (WHERE result = 'loss') AS losses
                    FROM chess_games
                    WHERE player_email = :user_email
                    GROUP BY opponent_email
                """),
                {"user_email": user_email},
            ).fetchall()
            opponents = {}
            for r in opp_rows:
                opponents[r[0]] = f"{r[1] or 0}:{r[2] or 0}"
            return {"total_wins": total_wins, "opponents": opponents}
    except Exception as e:
        logger.exception("get_all_chess_data_sync failed: %s", e)
        return None
