package org.chater;

import java.io.IOException;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.json.JSONObject;

public class Main {
    private static final Logger logger = LogManager.getLogger(Main.class);

    // Configurable topics and groups
    private static String INPUT_TOPIC;
    private static String CONSUMER_GROUP;
    private static String GEMINI_RESPONSE_TOPIC;
    private static String GEMINI_RESPONSE_GROUP;
    private static String GEMINI_SEND_TOPIC;
    private static String PHOTO_ANALYSIS_RESPONSE_TOPIC;

    public static void main(String[] args) throws IOException, InterruptedException {
        logger.info("Chater vision starting...");

        // Initialize configuration
        boolean isDev = "true".equalsIgnoreCase(System.getenv("IS_DEV"));
        INPUT_TOPIC = isDev ? "chater-vision_dev" : "chater-vision";
        CONSUMER_GROUP = isDev ? "chater-vision-group-dev" : "chater-vision-group";

        GEMINI_RESPONSE_TOPIC = isDev ? "gemini-response_dev" : "gemini-response";
        // Assuming "chater" group is shared or should be distinct in dev.
        // Using "chater-vision-gemini-consumer" base to avoid conflicts if needed, or
        // stick to "chater" with dev suffix.
        // The original code used "chater".
        GEMINI_RESPONSE_GROUP = isDev ? "chater-dev" : "chater";

        GEMINI_SEND_TOPIC = isDev ? "gemini-send_dev" : "gemini-send";
        PHOTO_ANALYSIS_RESPONSE_TOPIC = isDev ? "photo-analysis-response_dev" : "photo-analysis-response";

        logger.info("Environment: " + (isDev ? "DEV" : "PROD"));
        logger.info("Input Topic: " + INPUT_TOPIC);
        logger.info("Gemini Response Topic: " + GEMINI_RESPONSE_TOPIC);

        KafkaConsume newConsumer = new KafkaConsume();
        newConsumer.CreateConsumer(INPUT_TOPIC, CONSUMER_GROUP);

        KafkaConsume visionConsumer = new KafkaConsume();
        visionConsumer.CreateConsumer(GEMINI_RESPONSE_TOPIC, GEMINI_RESPONSE_GROUP);

        KafkaProduce visionProducer = new KafkaProduce();
        visionProducer.CreateProducer();

        while (true) {
            try {
                String message = newConsumer.Consume();
                if (message != null && !message.isEmpty()) {
                    JSONObject initialMessage = new JSONObject(message);
                    // Check if value is a string that needs parsing (sometimes double encoded) or
                    // object
                    JSONObject valueObject;
                    if (initialMessage.get("value") instanceof String) {
                        valueObject = new JSONObject(initialMessage.getString("value"));
                    } else {
                        valueObject = initialMessage.getJSONObject("value");
                    }

                    String userEmail = valueObject.optString("user_email", "unknown");

                    processMessage(message, visionProducer, userEmail);
                    responder(visionProducer, visionConsumer, userEmail);
                }
            } catch (Exception e) {
                logger.error("Error in main loop", e);
                // Re-throw or handle? Original re-threw IOException wrapped.
                // It's a while loop, maybe we want to continue?
                // Original code: visionProducer.close(); throw...
                visionProducer.close();
                throw new IOException("Error consuming message", e);
            }
        }
    }

    public static void processMessage(String message, KafkaProduce visionProducer, String userEmail)
            throws IOException, InterruptedException {
        String text;
        JSONObject jsonObject = new JSONObject(message);

        JSONObject valueObject;
        if (jsonObject.get("value") instanceof String) {
            valueObject = new JSONObject(jsonObject.getString("value"));
        } else {
            valueObject = jsonObject.getJSONObject("value");
        }

        String prompt = valueObject.optString("prompt", "");
        String uuid = jsonObject.optString("key", "unknown");
        String photo = valueObject.optString("photo", "");

        if (photo.isEmpty()) {
            logger.warn("No photo found in message");
            return;
        }

        text = DetectText.detectText(photo);
        logger.info("Detected text: {}", text);

        JSONObject photoQuestion = new JSONObject();
        // Assuming prompt is just text to prepend
        String question = prompt + " " + text; // Added space for safety

        // Structure for gemini request might need to be specific
        // Original:
        // JSONObject photoQuestion = new JSONObject();
        // String question = prompt + text;
        // photoQuestion.put("key", uuid);
        // JSONObject addressObject = new JSONObject();
        // addressObject.put("question", question);
        // addressObject.put("user_email", userEmail);
        // photoQuestion.put("value", addressObject);
        // visionProducer.SendMessage(photoQuestion.toString(), "gemini-send");

        // Replicating original logic exactly but with safer JSON handling
        photoQuestion.put("key", uuid);
        JSONObject addressObject = new JSONObject();
        addressObject.put("question", question);
        addressObject.put("user_email", userEmail);
        photoQuestion.put("value", addressObject);

        visionProducer.SendMessage(photoQuestion.toString(), GEMINI_SEND_TOPIC);
    }

    public static void responder(KafkaProduce visionProducer, KafkaConsume visionConsumer, String userEmail)
            throws InterruptedException {
        String message;
        String cleanedJson;
        logger.info("Chater vision responder");
        long startTime = System.currentTimeMillis();
        while (true) {
            message = visionConsumer.Consume();
            if (message != null && !message.isEmpty()) {
                logger.info("Consumed message: {}", message);
                cleanedJson = message
                        .replace("```json", "")
                        .replace("```", "")
                        .trim();
                // logger.info("Cleaned json: {}", cleanedJson); // Can be noisy
                try {
                    JSONObject jsonObject = new JSONObject(cleanedJson);
                    String uuid = jsonObject.optString("key", "");

                    // The response from Gemini usually puts the answer in "value"
                    // We need to pass it forward
                    Object valueContent = jsonObject.get("value");

                    JSONObject responseObject = new JSONObject();
                    responseObject.put("key", uuid);
                    responseObject.put("value", valueContent);

                    logger.info("Sending response to UI");
                    visionProducer.SendMessage(responseObject.toString(), PHOTO_ANALYSIS_RESPONSE_TOPIC);
                    break;
                } catch (Exception e) {
                    logger.error("Error parsing response JSON", e);
                }
            }
            if (System.currentTimeMillis() - startTime > 60000) {
                logger.info("No message received within 60 seconds. Exiting and waiting for next photo");
                break;
            }
        }
    }
}