from flask import Flask
import os

# Initialize the Flask application
app = Flask(__name__)


@app.route("/")
def health_check():
    """
    Health Check URL.
    UptimeRobot or Render can visit this endpoint
    to confirm that the web server is responding.
    """
    return "AniToon_1Bot: All Systems Operational 🟢"


if __name__ == "__main__":
    # Render provides the PORT environment variable.
    port = int(os.environ.get("PORT", 8080))

    # Listen on all network interfaces.
    app.run(
        host="0.0.0.0",
        port=port
    )
