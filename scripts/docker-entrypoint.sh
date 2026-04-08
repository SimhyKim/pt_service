#!/bin/sh
set -e
cd /app
if [ ! -f "artifacts/tfidf_vectorizer.joblib" ]; then
  echo "[entrypoint] No model in artifacts/; training from mounted datasets..."
  python scripts/train_model.py
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
