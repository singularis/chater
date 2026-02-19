# Use a known-good Maven + Eclipse Temurin variant
FROM maven:3.8.8-eclipse-temurin-21-alpine AS build

# Set the working directory in the container
WORKDIR /app

# Copy the pom.xml file and install dependencies
COPY pom.xml .
RUN mvn dependency:go-offline -B

# Copy the source code to the container
COPY src ./src

# Package the application
RUN mvn package -DskipTests

# Use a known-good Eclipse Temurin runtime (Alpine)
FROM eclipse-temurin:21-jre-alpine

# Set the working directory in the container
WORKDIR /app

# Copy the jar file from the build stage
COPY --from=build /app/target/chater-gemini-1.0-SNAPSHOT.jar /app/app.jar

# Specify the command to run the jar file
ENTRYPOINT ["java", "-jar", "app.jar"]
