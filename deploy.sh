#!/bin/bash

APP_DIR="/root/campulse"

echo "🚀 Starting deployment..."

cd "$APP_DIR" || { echo "❌ Directory not found: $APP_DIR"; exit 1; }

echo "📥 Pulling latest code from Git..."
PREV_COMMIT=$(git rev-parse HEAD)

git fetch origin
git reset --hard origin/master
git pull origin master

NEW_COMMIT=$(git rev-parse HEAD)

if git diff --name-only $PREV_COMMIT $NEW_COMMIT | grep -q "requirements.txt"; then
    echo "📦 requirements.txt changed — rebuilding Docker image..."
    docker-compose build --no-cache
else
    echo "⚡ No dependency changes — skipping rebuild."
fi

echo "🔄 Restarting containers..."
docker-compose up -d

echo "🔃 Reloading Nginx..."
sudo systemctl reload nginx

echo "✅ Deployment completed!"
