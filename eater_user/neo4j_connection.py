import os

from neo4j import GraphDatabase


class Neo4jConnection:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD")
        self.driver = None

        if not self.password:
            raise ValueError("NEO4J_PASSWORD environment variable not set")

    def connect(self):
        try:
            self.driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            self.verify_connectivity()
        except Exception:
            raise

    def close(self):
        if self.driver:
            self.driver.close()

    def verify_connectivity(self):
        if not self.driver:
            raise Exception("Driver not initialized")

        with self.driver.session() as session:
            result = session.run("RETURN 1 as test")
            record = result.single()
            if not record or record["test"] != 1:
                raise Exception("Neo4j connectivity test failed")

    
    def _get_user_label(self):
        is_dev = os.getenv("IS_DEV", "false").lower() == "true"
        return "User_dev" if is_dev else "User"

    def add_friend_relationship(self, user_email: str, friend_email: str) -> bool:
        if not self.driver:
            raise Exception("Neo4j driver not initialized")
        
        label = self._get_user_label()

        with self.driver.session() as session:
            try:
                # Using string formatting for label because labels cannot be parameterized in Neo4j
                # This is safe because label is controlled by our code, not user input
                query = f"""
                MERGE (user:{label} {{email: $user_email}})
                MERGE (friend:{label} {{email: $friend_email}})
                MERGE (user)-[:FRIEND]->(friend)
                MERGE (friend)-[:FRIEND]->(user)
                RETURN user.email as user, friend.email as friend
                """

                result = session.run(
                    query, {"user_email": user_email, "friend_email": friend_email}
                )

                record = result.single()
                return bool(record)

            except Exception:
                return False

    def check_friendship_exists(self, user_email: str, friend_email: str) -> bool:
        if not self.driver:
            raise Exception("Neo4j driver not initialized")
        
        label = self._get_user_label()

        with self.driver.session() as session:
            try:
                query = f"""
                MATCH (user:{label} {{email: $user_email}})-[:FRIEND]-(friend:{label} {{email: $friend_email}})
                RETURN COUNT(*) as count
                """

                result = session.run(
                    query, {"user_email": user_email, "friend_email": friend_email}
                )

                record = result.single()
                return record and record["count"] > 0

            except Exception:
                return False

    def get_user_friends(self, user_email: str) -> list:
        if not self.driver:
            raise Exception("Neo4j driver not initialized")
        
        label = self._get_user_label()

        with self.driver.session() as session:
            try:
                query = f"""
                MATCH (user:{label} {{email: $user_email}})-[:FRIEND]->(friend:{label})
                RETURN DISTINCT friend.email as friend_email
                ORDER BY friend.email
                """

                result = session.run(query, {"user_email": user_email})

                friends = []
                for record in result:
                    friends.append(record["friend_email"])

                return friends

            except Exception:
                return []


neo4j_connection = Neo4jConnection()
