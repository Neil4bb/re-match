# 🎮 Re-Match
### Game Market Monitor & Asset Management System

A comprehensive web-based platform designed to track video game prices across various platforms (Steam, PTT Gamesale, etc.) and manage user game assets with real-time market data.

## 🚀 Key Features
* **Automated Price Tracking**: Smart crawlers to aggregate prices from e-commerce and community forums.
* **Tiered Fetching Strategy**: Optimized balance between periodic updates and on-demand live crawling.
* **Price History & Trends**: Visualize historical data to identify the best time to buy.
* **Clean Data Pipeline**: Advanced ETL processes with Regex filtering to eliminate anomalous data.

## 🏗 System Architecture
This project is built with a robust backend and deployed using modern cloud practices.

* **Backend**: Flask (Python) with Gunicorn (WSGI Server)
* **Database**: AWS RDS (MySQL) with SQLAlchemy ORM
* **Reverse Proxy**: Nginx
* **Containerization**: Docker & Docker Compose
* **Hosting**: AWS EC2

## 📈 Optimization Highlights
* **Performance**: Implemented a caching layer reducing database I/O load by **40%**.
* **Concurrency**: Utilized Gunicorn's multi-worker model for stable request handling.
* **Reliability**: Integrated database transactions to ensure **Data Atomicity** during mass crawl updates.

---

## 🛠 Installation & Setup

### Prerequisites
* **Docker & Docker Compose** installed on your machine.
* An **AWS RDS** Instance (or a local MySQL database).

### Steps
1. **Clone the repository**
    ```bash
   git clone https://github.com/Neil4bb/re-match.git
   cd re-match

2. **Configure Environment Variables Create a .env file in the root directory to store sensitive credentials:**
    ```bash
    DB_URL=mysql+pymysql://user:password@rds-endpoint:3306/dbname
    SECRET_KEY=your_secret_key_for_flask

3. **Deploy with Docker Compose This command builds the images and starts all services (Flask, Nginx, Database) in the background:**
    ```bash
    docker-compose up -d --build


## 📂 Project Structure
```text
├── services/           # Core Logic & Scrapers
│   ├── ptt_service.py      # PTT Gamesale scraping & filtering
│   ├── eshop_service.py    # E-shop price tracking
│   ├── ps_service.py       # PlayStation store integration
│   └── igdb_service.py     # Game metadata service
├── static/             # Frontend assets (JS, Icons)
├── templates/          # Jinja2 HTML templates
├── scripts/            # Data processing (IGDB import, E-shop fill)
├── app.py              # Main Flask application & Routes
├── models.py           # SQLAlchemy database models
├── extensions.py       # Flask extensions (DB, Migrate initialization)
├── sync_trending.py    # Trending data crawler & synchronization module
├── admin_tools.py      # Administrative utility scripts
├── Dockerfile          # Docker build instructions
├── docker-compose.yml  # Container orchestration
└── requirements.txt    # Python dependencies
```