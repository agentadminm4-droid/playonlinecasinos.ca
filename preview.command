#!/bin/bash
# Local preview launcher for playonlinecasinos.ca
# Starts an HTTP server on port 8785 and opens the site in your default browser.
# Run with: bash ~/Desktop/playonlinecasinos/preview.command

DIR="$HOME/Desktop/playonlinecasinos"
PORT=8785

cd "$DIR"

# Check if port is in use; if so, kill the previous server
if lsof -ti :$PORT >/dev/null 2>&1; then
  kill $(lsof -ti :$PORT) 2>/dev/null
  sleep 1
fi

# Start the server in the background
python3 -m http.server $PORT > /tmp/playonlinecasinos-preview.log 2>&1 &
SERVER_PID=$!
sleep 1

# Open the browser
open "http://localhost:$PORT/"

echo "============================================================"
echo "PlayOnlineCasinos.ca — Local Preview"
echo "============================================================"
echo "URL:      http://localhost:$PORT/"
echo "Server:   PID $SERVER_PID (logs: /tmp/playonlinecasinos-preview.log)"
echo "Source:   $DIR"
echo "Deploy:   $HOME/Desktop/playonlinecasinos-deploy"
echo ""
echo "To stop the server, run: kill $SERVER_PID"
echo "To stop later:           lsof -ti :$PORT | xargs kill"
echo "============================================================"

# Keep the script running so the terminal stays open
wait $SERVER_PID
