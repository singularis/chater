# Chater UI Service

Main web application providing the user interface for the Chater platform, combining chat functionality with food tracking capabilities.

## 🎯 Purpose

The Chater UI Service serves as the primary user interface for the platform, providing:
- Web-based chat interface with AI integration
- Food tracking dashboard and photo analysis
- User authentication and session management
- Real-time messaging and notifications
- Google OAuth integration
- File upload and image processing

## 🏗️ Architecture

### Core Components
- **Flask Web Application**: Main web server with templating
- **Authentication Module**: Google OAuth and session management
- **Chat Interface**: Real-time messaging with AI services
- **Food Tracking**: Photo analysis and nutritional insights
- **Kafka Consumer Service**: Background message processing
- **File Management**: Image upload and storage handling

### Dependencies
- **Apache Kafka**: Message broker for AI service communication
- **Redis**: Session storage and caching
- **PostgreSQL**: Data persistence (via other services)
- **Google Cloud Services**: OAuth, Vision API, DLP
- **AI Services**: OpenAI GPT and Google Gemini integration

## 🔧 Configuration

### Environment Variables
```bash
# Authentication
USERNAME=your-username
PASSWORD_HASH=your-password-hash
SECRET_KEY=your-secret-key
GOOGLE_OAUTH_CLIENT_ID=your-oauth-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-oauth-client-secret

# Session Management
SESSION_LIFETIME=8
REDIS_ENDPOINT=your-redis-host

# AI Services
BOOTSTRAP_SERVER=your-kafka-broker:port
DAILY_REQUEST_LIMIT=20

# Google Cloud
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GCP_PROJECT_ID=your-project-id

# Security
ALLOWED_EMAILS=email1@example.com,email2@example.com
EATER_SECRET_KEY=your-eater-secret

# Development
FLASK_DEBUG=true
```

### Kafka Topics
- **Produces**: `gpt-send`, `gemini-send`, `auth_requires_token`
- **Consumes**: `gpt-response`, `gemini-response`, `send_today_data`, `add_auth_token`

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Redis server
- Apache Kafka broker
- Google Cloud Project with enabled APIs
- Service account credentials

### Installation
1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   # Copy example environment file
   cp .env.example .env
   
   # Edit .env with your configuration
   nano .env
   ```

3. **Set up Google Cloud credentials**
   ```bash
   # Place service account JSON file
   export GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
   ```

4. **Run the service**
   ```bash
   python app/app.py
   ```

### Development Setup
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run in development mode
export FLASK_DEBUG=true
python app/app.py
```

## 📋 Features & Routes

### Authentication Routes
- **GET** `/login` - Login page
- **POST** `/login` - Process login
- **GET** `/logout` - Logout user
- **GET** `/google_login/login` - Google OAuth login
- **GET** `/google_login/authorize` - OAuth callback

### Chat Interface
- **GET** `/` - Main chat interface
- **POST** `/submit` - Submit chat message
- **GET** `/chater` - Chat page with target selection
- **POST** `/clear_chat` - Clear chat history

### Food Tracking
- **GET** `/eater` - Food tracking dashboard
- **POST** `/eater/photo` - Upload food photo for analysis
- **GET** `/eater/today` - Today's food data
- **GET** `/eater/date/{date}` - Specific date food data
- **POST** `/eater/delete` - Delete food record
- **POST** `/eater/modify` - Modify food record
- **POST** `/eater/weight` - Manual weight entry
- **GET** `/eater/recommendations` - Get meal recommendations
- **POST** `/eater/feedback` - Submit feedback
- **GET** `/alcohol_latest` - Get today's alcohol summary (drinks count, calories, list)
- **POST** `/alcohol_range` - Get alcohol events between start_date and end_date

### File Management
- **POST** `/upload` - Upload files
- **GET** `/static/{filename}` - Serve static files
- **POST** `/gphoto` - Google Photos integration

## 🔄 Background Services

### Kafka Consumer Service
Handles real-time message processing:
```python
class KafkaConsumerService:
    def __init__(self):
        # Initialize Redis client
        # Configure topic subscriptions
        # Set up consumer groups
    
    def consume_topic_messages(self, topics):
        # Process messages from AI services
        # Store responses in Redis
        # Handle message acknowledgment
```

### Session Management
- Redis-based session storage
- Configurable session lifetime
- Secure cookie handling
- Session cleanup and management

## 🎨 Frontend Components

### Chat Interface
- Real-time messaging UI
- AI provider selection (GPT/Gemini)
- Message history and context
- File upload integration
- Response streaming

### Food Tracking Dashboard
- Photo upload and preview
- Nutritional information display
- Calendar-based food history
- Meal recommendations
- Weight tracking graphs

### Loading overlay (manual dish name / long requests)
For endpoints that can take several seconds (e.g. `POST /modify_food_manual`), show a loading state so the user sees that the request is in progress:

1. Include assets (adjust base URL if using a dev/prod prefix):
   ```html
   <link rel="stylesheet" href="/static/css/loading-overlay.css">
   <script src="/static/js/loading-overlay.js"></script>
   ```
2. Before calling the API, show the overlay; in `finally()`, hide it:
   ```javascript
   loadingOverlay.show('Обробка запиту…');  // or your message
   fetch('/modify_food_manual', { method: 'POST', ... })
     .then(function (r) { ... })
     .catch(function (e) { ... })
     .finally(function () { loadingOverlay.hide(); });
   ```

### Authentication UI
- Login/logout forms
- Google OAuth integration
- User profile management
- Session status indicators

## 🗄️ Data Flow

### Chat Flow
1. User submits message via web form
2. Message sent to appropriate Kafka topic
3. AI service processes and responds
4. Response cached in Redis
5. UI retrieves and displays response

### Food Tracking Flow
1. User uploads food photo
2. Image processed by vision service
3. Nutritional data analyzed
4. Results stored and displayed
5. Recommendations generated

## 🔒 Security

### Authentication
- Multi-factor authentication support
- Google OAuth 2.0 integration
- Session-based authentication
- JWT token validation

### Data Protection
- Input validation and sanitization
- CSRF protection
- Secure cookie configuration
- Rate limiting on API endpoints

### Privacy
- Email-based access control
- Data encryption in transit
- Secure file upload handling
- Session timeout management

## 🐳 Deployment

### Docker
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app/app.py"]
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chater-ui
spec:
  replicas: 2
  selector:
    matchLabels:
      app: chater-ui
  template:
    spec:
      containers:
      - name: chater-ui
        image: your-registry/chater-ui:latest
        ports:
        - containerPort: 5000
        env:
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: chater-secrets
              key: SECRET_KEY
        - name: REDIS_ENDPOINT
          value: "redis-service:6379"
        - name: BOOTSTRAP_SERVER
          value: "kafka-service:9092"
        volumeMounts:
        - name: storage
          mountPath: /app/data
        - name: gcp-credentials
          mountPath: /var/secrets/google
```

## 📊 Monitoring

### Health Checks
- Service health endpoint
- Database connectivity
- Kafka broker connectivity
- Redis availability

### Metrics
- Request rate and response times
- Authentication success/failure rates
- File upload statistics
- Session metrics

### Logging
- Structured application logs
- Request/response logging
- Error tracking
- Performance monitoring

## 🧪 Testing

### Unit Tests
```bash
# Run unit tests
python -m pytest tests/unit/

# Run with coverage
python -m pytest tests/unit/ --cov=app/
```

### Integration Tests
```bash
# Run integration tests
python -m pytest tests/integration/

# Run end-to-end tests
python -m pytest tests/e2e/
```

### Manual Testing
- Authentication flow testing
- Chat functionality testing
- Food tracking feature testing
- File upload validation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

### Development Guidelines
- Follow Flask best practices
- Use proper error handling
- Add comprehensive logging
- Include unit tests for new features
- Update documentation as needed

 