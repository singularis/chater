package com.chamini;

import java.io.IOException;
import java.util.Properties;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.json.JSONObject;
import com.google.genai.Client;
import com.google.genai.types.GenerateContentResponse;

public class GoogleGemini {

    private static final Logger LOGGER = Logger.getLogger(GoogleGemini.class.getName());
    private static final String API_MODEL = System.getenv("GEMINI_MODEL");
    private static final String GOOGLE_API_KEY = System.getenv("GOOGLE_API_KEY");
    private static final String BOOTSTRAP_SERVER = System.getenv("BOOTSTRAP_SERVER");
    private static final boolean IS_DEV = "true".equalsIgnoreCase(System.getenv("IS_DEV"));
    private static final String TOPIC = IS_DEV ? "gemini-send_dev" : "gemini-send";
    private static final String OUTPUT_TOPIC = IS_DEV ? "gemini-response_dev" : "gemini-response";
    private static final String GROUP_ID = IS_DEV ? "chamini-dev" : "chamini";
    private static final String GEMINI_THINK_MODEL = System.getenv("GEMINI_THINK_MODEL");

    public static void main(String[] args) {
        if (GOOGLE_API_KEY == null || GOOGLE_API_KEY.isEmpty()) {
            LOGGER.log(Level.SEVERE, "GOOGLE_API_KEY environment variable is not set");
            return;
        }

        KafkaConsumer consumer = new KafkaConsumer(BOOTSTRAP_SERVER, GROUP_ID, TOPIC);
        KafkaProducerUtil producer = new KafkaProducerUtil(BOOTSTRAP_SERVER) {
            @Override
            protected KafkaProducer<String, String> createProducer(Properties props) {
                return null;
            }
        };

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            LOGGER.info("Shutdown initiated...");
            consumer.close();
            producer.close();
        }));

        while (true) {
            String message = consumer.consumeMessage();
            if (message != null && !message.isEmpty()) {
                processMessage(message, producer);
            }
        }
    }

    private static void processMessage(String message, KafkaProducerUtil producer) {
        String uuid;
        String question;
        String model;
        boolean think;
        String userEmail = null;

        try {
            JSONObject jsonObject = new JSONObject(message);
            uuid = jsonObject.getString("key");
            Object value = jsonObject.get("value");

            // Handle both string and JSON object values
            if (value instanceof String) {
                question = (String) value;
                think = false;
            } else {
                JSONObject valueObject = (JSONObject) value;
                question = valueObject.getString("question");
                think = Boolean.parseBoolean(valueObject.optString("think", "false"));
                if (valueObject.has("user_email")) {
                    userEmail = valueObject.getString("user_email");
                }
            }

            if (think) {
                model = GEMINI_THINK_MODEL;
            } else {
                model = API_MODEL;
            }
            LOGGER.log(Level.INFO, "Model: {0}", model);
        } catch (Exception e) {
            LOGGER.log(Level.SEVERE, "Failed to extract question from message", e);
            return;
        }

        try {
            GenerateContentResponse response = getHttpURLConnection(question, model);

            String text = response.text();
            LOGGER.log(Level.INFO, "Response Text: {0}", text);
            if (text != null) {
                String cleanedText = text.replace("```json", "").replace("```", "").trim();

                if (userEmail != null) {
                    try {
                        JSONObject valueResponse = new JSONObject(cleanedText);
                        valueResponse.put("user_email", userEmail);
                        producer.sendMessage(OUTPUT_TOPIC, uuid, valueResponse);
                    } catch (Exception e) {
                        JSONObject valueResponse = new JSONObject();
                        valueResponse.put("response", cleanedText);
                        valueResponse.put("user_email", userEmail);
                        producer.sendMessage(OUTPUT_TOPIC, uuid, valueResponse);
                    }
                } else {
                    try {
                        producer.sendMessage(OUTPUT_TOPIC, uuid, new JSONObject(cleanedText));
                    } catch (Exception e) {
                        producer.sendMessage(OUTPUT_TOPIC, uuid, cleanedText);
                    }
                }
            }
        } catch (Exception e) {
            LOGGER.log(Level.SEVERE, "Exception occurred", e);
        }
    }

    public static GenerateContentResponse getHttpURLConnection(String question, String model) throws IOException {
        Client client = new Client();
        GenerateContentResponse response = client.models.generateContent(
                model,
                question,
                null);
        return response;
    }
}
