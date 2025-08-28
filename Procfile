web: uvicorn main:app --host 0.0.0.0 --port $PORT
worker: python -c "from main import run_daily_job; run_daily_job()"
