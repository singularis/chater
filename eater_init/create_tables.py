import logging
import os
import time

from sqlalchemy import (ARRAY, JSON, Column, Date, Float, ForeignKey, Integer,
                        PrimaryKeyConstraint, String, create_engine, text)
from sqlalchemy.orm import declarative_base, sessionmaker

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

Base = declarative_base()


class User(Base):
    __tablename__ = "user"
    __table_args__ = {"schema": "public"}

    email = Column(String, primary_key=True)
    register_date = Column(String, nullable=True)
    last_activity = Column(String, nullable=True)
    language = Column(String, nullable=True)


class Dishes(Base):
    __tablename__ = "dishes"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    calories = Column(Integer, nullable=False)
    weight = Column(Integer, nullable=False)
    ingredients = Column(ARRAY(String), nullable=False)
    contains = Column(JSON, nullable=False)
    user_email = Column(String, nullable=False)


class DishesDay(Base):
    __tablename__ = "dishes_day"
    __table_args__ = (
        PrimaryKeyConstraint("time"),
        {"schema": "public"},
    )

    time = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    dish_name = Column(String, nullable=False)
    estimated_avg_calories = Column(Integer, nullable=False)
    ingredients = Column(ARRAY(String), nullable=False)
    total_avg_weight = Column(Integer, nullable=False)
    health_rating = Column(Integer, nullable=True)
    food_health_level = Column(String, nullable=True)
    contains = Column(JSON, nullable=False)
    user_email = Column(String, nullable=False)
    image_id = Column(String, nullable=True)


class TotalForDay(Base):
    __tablename__ = "total_for_day"
    __table_args__ = (PrimaryKeyConstraint("date", "user_email"), {"schema": "public"})

    date = Column(Date, nullable=False)
    user_email = Column(String, nullable=False)
    total_calories = Column(Integer, nullable=False)
    ingredients = Column(ARRAY(String), nullable=False)
    dishes_of_day = Column(ARRAY(String), nullable=False)
    total_avg_weight = Column(Integer, nullable=False)
    contains = Column(JSON, nullable=False)
    today = Column(Date, nullable=False)


class Weight(Base):
    __tablename__ = "weight"
    __table_args__ = (PrimaryKeyConstraint("time"), {"schema": "public"})

    time = Column(Integer, primary_key=True)
    date = Column(String, nullable=False)
    weight = Column(Float, nullable=False)
    user_email = Column(String, nullable=False)


class AlcoholConsumption(Base):
    __tablename__ = "alcohol_consumption"
    __table_args__ = (PrimaryKeyConstraint("time"), {"schema": "public"})

    time = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    drink_name = Column(String, nullable=False)
    calories = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    user_email = Column(String, nullable=False)


class AlcoholForDay(Base):
    __tablename__ = "alcohol_for_day"
    __table_args__ = (PrimaryKeyConstraint("date", "user_email"), {"schema": "public"})

    date = Column(Date, nullable=False)
    user_email = Column(String, nullable=False)
    total_drinks = Column(Integer, nullable=False)
    total_calories = Column(Integer, nullable=False)
    drinks_of_day = Column(ARRAY(String), nullable=False)


def verify_indexes(connection):
    """Verify that all expected indexes were created successfully"""
    try:
        # First check which tables exist
        existing_tables = []
        for table_name in [
            "user",
            "dishes_day",
            "total_for_day",
            "weight",
            "dishes",
            "admin_data",
            "feedbacks",
            "alcohol_consumption",
            "alcohol_for_day",
        ]:
            result = connection.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = '{table_name}'
                )
            """))
            if result.fetchone()[0]:
                existing_tables.append(table_name)

        logger.info(f"Tables found: {existing_tables}")

        # Check user table indexes
        if "user" in existing_tables:
            user_indexes = [
                "idx_users_email_gin",
                "idx_users_email",
                "idx_users_last_activity",
                "idx_users_register_date",
            ]
            logger.info("Verifying user table indexes...")
            for index_name in user_indexes:
                result = connection.execute(text(f"""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                """))
                if result.fetchone():
                    logger.info(f"✓ Index {index_name} verified")
                else:
                    logger.warning(f"⚠ Index {index_name} not found")

        # Check DishesDay table indexes
        if "dishes_day" in existing_tables:
            dishes_day_indexes = [
                "idx_dishes_day_user_email",
                "idx_dishes_day_date",
                "idx_dishes_day_time",
                "idx_dishes_day_user_date",
                "idx_dishes_day_user_time",
            ]
            logger.info("Verifying dishes_day table indexes...")
            for index_name in dishes_day_indexes:
                result = connection.execute(text(f"""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                """))
                if result.fetchone():
                    logger.info(f"✓ Index {index_name} verified")
                else:
                    logger.warning(f"⚠ Index {index_name} not found")

        # Check TotalForDay table indexes
        if "total_for_day" in existing_tables:
            total_for_day_indexes = [
                "idx_total_for_day_user_email",
                "idx_total_for_day_today",
                "idx_total_for_day_user_today",
            ]
            logger.info("Verifying total_for_day table indexes...")
            for index_name in total_for_day_indexes:
                result = connection.execute(text(f"""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                """))
                if result.fetchone():
                    logger.info(f"✓ Index {index_name} verified")
                else:
                    logger.warning(f"⚠ Index {index_name} not found")

        # Check Weight table indexes
        if "weight" in existing_tables:
            weight_indexes = [
                "idx_weight_user_email",
                "idx_weight_time",
                "idx_weight_date",
                "idx_weight_user_time",
            ]
            logger.info("Verifying weight table indexes...")
            for index_name in weight_indexes:
                result = connection.execute(text(f"""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                """))
                if result.fetchone():
                    logger.info(f"✓ Index {index_name} verified")
                else:
                    logger.warning(f"⚠ Index {index_name} not found")

        # Check Alcohol tables indexes
        if "alcohol_consumption" in existing_tables:
            alcohol_consumption_indexes = [
                "idx_alcohol_consumption_user_email",
                "idx_alcohol_consumption_date",
                "idx_alcohol_consumption_time",
                "idx_alcohol_consumption_user_time",
            ]
            logger.info("Verifying alcohol_consumption table indexes...")
            for index_name in alcohol_consumption_indexes:
                result = connection.execute(text(f"""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                """))
                if result.fetchone():
                    logger.info(f"✓ Index {index_name} verified")
                else:
                    logger.warning(f"⚠ Index {index_name} not found")

        if "alcohol_for_day" in existing_tables:
            alcohol_for_day_indexes = [
                "idx_alcohol_for_day_user_email",
                "idx_alcohol_for_day_date",
                "idx_alcohol_for_day_user_date",
            ]
            logger.info("Verifying alcohol_for_day table indexes...")
            for index_name in alcohol_for_day_indexes:
                result = connection.execute(text(f"""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                """))
                if result.fetchone():
                    logger.info(f"✓ Index {index_name} verified")
                else:
                    logger.warning(f"⚠ Index {index_name} not found")

        # Check Dishes table indexes
        if "dishes" in existing_tables:
            dishes_indexes = ["idx_dishes_user_email", "idx_dishes_name"]
            logger.info("Verifying dishes table indexes...")
            for index_name in dishes_indexes:
                result = connection.execute(text(f"""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                """))
                if result.fetchone():
                    logger.info(f"✓ Index {index_name} verified")
                else:
                    logger.warning(f"⚠ Index {index_name} not found")

        # Check Admin_data table indexes
        if "admin_data" in existing_tables:
            admin_data_indexes = ["idx_admin_data_user_email"]
            logger.info("Verifying admin_data table indexes...")
            for index_name in admin_data_indexes:
                result = connection.execute(text(f"""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                """))
                if result.fetchone():
                    logger.info(f"✓ Index {index_name} verified")
                else:
                    logger.warning(f"⚠ Index {index_name} not found")

        # Check Feedbacks table indexes
        if "feedbacks" in existing_tables:
            feedbacks_indexes = ["idx_feedbacks_user_email"]
            logger.info("Verifying feedbacks table indexes...")
            for index_name in feedbacks_indexes:
                result = connection.execute(text(f"""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                """))
                if result.fetchone():
                    logger.info(f"✓ Index {index_name} verified")
                else:
                    logger.warning(f"⚠ Index {index_name} not found")

        logger.info("Index verification completed")

    except Exception as e:
        logger.error(f"Error during index verification: {str(e)}")


def create_tables():
    try:
        db_user = os.environ.get("POSTGRES_USER")
        db_password = os.environ.get("POSTGRES_PASSWORD")
        db_host = os.environ.get("POSTGRES_HOST")
        db_name = os.environ.get("POSTGRES_DB")

        if not all([db_user, db_password, db_host, db_name]):
            raise ValueError("Missing required database environment variables")

        logger.info(
            f"Database configuration: host={db_host}, user={db_user}, db={db_name}"
        )

        db_url = f"postgresql://{db_user}:{db_password}@{db_host}:5432/{db_name}"
        logger.info(f"Attempting to connect to database at {db_host}")

        # Test connection with retries
        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                engine = create_engine(db_url)
                with engine.connect() as connection:
                    # Test connection with a simple query
                    connection.execute(text("SELECT 1"))
                    logger.info("Successfully connected to database")
                    break
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to connect to database after {max_retries} attempts: {str(e)}"
                    )
                    raise
                logger.warning(
                    f"Connection attempt {attempt + 1} failed: {str(e)}. Retrying in {retry_delay} seconds..."
                )
                time.sleep(retry_delay)

        Session = sessionmaker(bind=engine)

        with engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            logger.info("Creating schema and setting up user...")
            try:
                # Create schema and set up user
                connection.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
                logger.info("Schema created successfully")

            except Exception as e:
                logger.error(f"Error during schema/user setup: {str(e)}")
                raise

            # Create tables
            logger.info("Creating tables...")
            try:
                Base.metadata.create_all(engine, checkfirst=True)
                logger.info("Tables created/updated successfully")
            except Exception as e:
                logger.error(f"Error during table creation: {str(e)}")
                raise

            # Ensure all required columns exist in each table
            logger.info("Checking and adding required columns...")
            try:
                connection.execute(text("""
                    DO $$
                    BEGIN
                        -- Check and add columns to user table
                        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'user') THEN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'user' AND column_name = 'language') THEN
                                ALTER TABLE public.user ADD COLUMN language VARCHAR;
                                UPDATE public.user SET language = 'en' WHERE language IS NULL;
                            END IF;
                        END IF;

                        -- Check and add columns to dishes table
                        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'dishes') THEN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'dishes' AND column_name = 'user_email') THEN
                                ALTER TABLE public.dishes ADD COLUMN user_email VARCHAR NOT NULL;
                            END IF;
                        END IF;

                        -- Check and add columns to dishes_day table
                        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'dishes_day') THEN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'dishes_day' AND column_name = 'user_email') THEN
                                ALTER TABLE public.dishes_day ADD COLUMN user_email VARCHAR NOT NULL;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'dishes_day' AND column_name = 'health_rating') THEN
                                ALTER TABLE public.dishes_day ADD COLUMN health_rating INTEGER;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'dishes_day' AND column_name = 'food_health_level') THEN
                                ALTER TABLE public.dishes_day ADD COLUMN food_health_level VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'dishes_day' AND column_name = 'image_id') THEN
                                ALTER TABLE public.dishes_day ADD COLUMN image_id VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'dishes_day' AND column_name = 'added_sugar_tsp') THEN
                                ALTER TABLE public.dishes_day ADD COLUMN added_sugar_tsp REAL DEFAULT 0.0;
                            END IF;
                        END IF;

                        -- Check and add columns to total_for_day table
                        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'total_for_day') THEN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'total_for_day' AND column_name = 'user_email') THEN
                                ALTER TABLE public.total_for_day ADD COLUMN user_email VARCHAR NOT NULL;
                            END IF;
                        END IF;

                        -- Check and add columns to weight table
                        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'weight') THEN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'weight' AND column_name = 'user_email') THEN
                                ALTER TABLE public.weight ADD COLUMN user_email VARCHAR NOT NULL;
                            END IF;
                        END IF;
                    END $$;
                """))
                logger.info("Column checks completed successfully")
            except Exception as e:
                logger.error(f"Error during column checks: {str(e)}")
                raise

            # Create indexes after ensuring columns exist
            logger.info("Creating indexes...")
            try:
                # Enable pg_trgm extension for trigram searches
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
                logger.info("pg_trgm extension enabled")

                # Check which tables actually exist before creating indexes
                logger.info("Checking existing tables...")
                existing_tables = []
                for table_name in [
                    "user",
                    "dishes_day",
                    "total_for_day",
                    "weight",
                    "dishes",
                    "admin_data",
                    "feedbacks",
                    "alcohol_consumption",
                    "alcohol_for_day",
                ]:
                    result = connection.execute(text(f"""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = '{table_name}'
                        )
                    """))
                    if result.fetchone()[0]:
                        existing_tables.append(table_name)
                        logger.info(f"✓ Table {table_name} exists")
                    else:
                        logger.info(f"⚠ Table {table_name} does not exist")

                # User table indexes (if table exists)
                if "user" in existing_tables:
                    try:
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_users_email_gin ON public.user USING gin(email gin_trgm_ops);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_users_email ON public.user USING btree(email);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_users_last_activity ON public.user USING btree(last_activity);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_users_register_date ON public.user USING btree(register_date);"
                            )
                        )
                        logger.info("User table indexes created successfully")
                    except Exception as e:
                        logger.warning(f"Failed to create user table indexes: {e}")
                else:
                    logger.info("Skipping user table indexes - table does not exist")

                # DishesDay table indexes (if table exists)
                if "dishes_day" in existing_tables:
                    try:
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_dishes_day_user_email ON public.dishes_day USING btree(user_email);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_dishes_day_date ON public.dishes_day USING btree(date);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_dishes_day_time ON public.dishes_day USING btree(time);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_dishes_day_user_date ON public.dishes_day USING btree(user_email, date);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_dishes_day_user_time ON public.dishes_day USING btree(user_email, time);"
                            )
                        )
                        logger.info("DishesDay table indexes created successfully")
                    except Exception as e:
                        logger.warning(
                            f"Failed to create dishes_day table indexes: {e}"
                        )
                else:
                    logger.info(
                        "Skipping dishes_day table indexes - table does not exist"
                    )

                # TotalForDay table indexes (if table exists)
                if "total_for_day" in existing_tables:
                    try:
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_total_for_day_user_email ON public.total_for_day USING btree(user_email);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_total_for_day_today ON public.total_for_day USING btree(today);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_total_for_day_user_today ON public.total_for_day USING btree(user_email, today);"
                            )
                        )
                        logger.info("TotalForDay table indexes created successfully")
                    except Exception as e:
                        logger.warning(
                            f"Failed to create total_for_day table indexes: {e}"
                        )
                else:
                    logger.info(
                        "Skipping total_for_day table indexes - table does not exist"
                    )

                # Weight table indexes (if table exists)
                if "weight" in existing_tables:
                    try:
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_weight_user_email ON public.weight USING btree(user_email);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_weight_time ON public.weight USING btree(time);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_weight_date ON public.weight USING btree(date);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_weight_user_time ON public.weight USING btree(user_email, time);"
                            )
                        )
                        logger.info("Weight table indexes created successfully")
                    except Exception as e:
                        logger.warning(f"Failed to create weight table indexes: {e}")
                else:
                    logger.info("Skipping weight table indexes - table does not exist")

                # AlcoholConsumption table indexes (if table exists)
                if "alcohol_consumption" in existing_tables:
                    try:
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_alcohol_consumption_user_email ON public.alcohol_consumption USING btree(user_email);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_alcohol_consumption_date ON public.alcohol_consumption USING btree(date);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_alcohol_consumption_time ON public.alcohol_consumption USING btree(time);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_alcohol_consumption_user_time ON public.alcohol_consumption USING btree(user_email, time);"
                            )
                        )
                        logger.info(
                            "AlcoholConsumption table indexes created successfully"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to create alcohol_consumption table indexes: {e}"
                        )
                else:
                    logger.info(
                        "Skipping alcohol_consumption table indexes - table does not exist"
                    )

                # AlcoholForDay table indexes (if table exists)
                if "alcohol_for_day" in existing_tables:
                    try:
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_alcohol_for_day_user_email ON public.alcohol_for_day USING btree(user_email);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_alcohol_for_day_date ON public.alcohol_for_day USING btree(date);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_alcohol_for_day_user_date ON public.alcohol_for_day USING btree(user_email, date);"
                            )
                        )
                        logger.info("AlcoholForDay table indexes created successfully")
                    except Exception as e:
                        logger.warning(
                            f"Failed to create alcohol_for_day table indexes: {e}"
                        )
                else:
                    logger.info(
                        "Skipping alcohol_for_day table indexes - table does not exist"
                    )

                # Dishes table indexes (if table exists)
                if "dishes" in existing_tables:
                    try:
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_dishes_user_email ON public.dishes USING btree(user_email);"
                            )
                        )
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_dishes_name ON public.dishes USING btree(name);"
                            )
                        )
                        logger.info("Dishes table indexes created successfully")
                    except Exception as e:
                        logger.warning(f"Failed to create dishes table indexes: {e}")
                else:
                    logger.info("Skipping dishes table indexes - table does not exist")

                # Admin_data table indexes (if table exists)
                if "admin_data" in existing_tables:
                    try:
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_admin_data_user_email ON public.admin_data USING btree(user_email);"
                            )
                        )
                        logger.info("Admin_data table indexes created successfully")
                    except Exception as e:
                        logger.warning(
                            f"Failed to create admin_data table indexes: {e}"
                        )
                else:
                    logger.info(
                        "Skipping admin_data table indexes - table does not exist"
                    )

                # Feedbacks table indexes (if table exists)
                if "feedbacks" in existing_tables:
                    try:
                        connection.execute(
                            text(
                                "CREATE INDEX IF NOT EXISTS idx_feedbacks_user_email ON public.feedbacks USING btree(user_email);"
                            )
                        )
                        logger.info("Feedbacks table indexes created successfully")
                    except Exception as e:
                        logger.warning(f"Failed to create feedbacks table indexes: {e}")
                else:
                    logger.info(
                        "Skipping feedbacks table indexes - table does not exist"
                    )

                logger.info("Index creation completed")

                logger.info("Verifying index creation...")
                verify_indexes(connection)

                logger.info("Updating table statistics...")
                for table_name in existing_tables:
                    try:
                        connection.execute(text(f"ANALYZE public.{table_name};"))
                        logger.info(f"✓ Statistics updated for {table_name}")
                    except Exception as e:
                        logger.warning(
                            f"Failed to update statistics for {table_name}: {e}"
                        )
                logger.info("Table statistics updated")

                # Test query performance
                logger.info("Testing query performance...")
                test_query_performance(connection)

            except Exception as e:
                logger.error(f"Error during index creation: {str(e)}")
                raise

    except Exception as error:
        logger.error(f"Error while connecting to PostgreSQL: {error}")
        raise


def test_query_performance(connection):
    """Test the performance of key queries to ensure indexes are working"""
    try:
        logger.info("Testing query performance...")

        # Check which tables exist
        existing_tables = []
        for table_name in [
            "user",
            "dishes_day",
            "total_for_day",
            "weight",
            "dishes",
            "admin_data",
            "feedbacks",
            "alcohol_consumption",
            "alcohol_for_day",
        ]:
            result = connection.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = '{table_name}'
                )
            """))
            if result.fetchone()[0]:
                existing_tables.append(table_name)

        # Test 1: Email search with GIN index (if user table exists)
        if "user" in existing_tables:
            logger.info("Testing email search query...")
            try:
                result = connection.execute(text("""
                    EXPLAIN (ANALYZE, BUFFERS) 
                    SELECT email, register_date, last_activity 
                    FROM public."user" 
                    WHERE email LIKE '%test%'
                """))

                explain_plan = result.fetchall()
                logger.info("Email search query plan:")
                for row in explain_plan:
                    logger.info(row[0])
            except Exception as e:
                logger.warning(f"Failed to test email search: {e}")

        # Test 2: User-specific dishes query (if dishes_day table exists)
        if "dishes_day" in existing_tables:
            logger.info("Testing user dishes query...")
            try:
                result = connection.execute(text("""
                    EXPLAIN (ANALYZE, BUFFERS) 
                    SELECT * FROM public.dishes_day 
                    WHERE user_email = 'test@example.com' 
                    AND date = CURRENT_DATE
                """))

                explain_plan = result.fetchall()
                logger.info("User dishes query plan:")
                for row in explain_plan:
                    logger.info(row[0])
            except Exception as e:
                logger.warning(f"Failed to test dishes query: {e}")

        logger.info("Query performance testing completed")

    except Exception as e:
        logger.error(f"Error during performance testing: {str(e)}")


if __name__ == "__main__":
    create_tables()
