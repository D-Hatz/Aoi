docker run -d \
--name kokoro-postgres \
-e POSTGRES_USER=postgres \
-e POSTGRES_PASSWORD=postgres \
-p 5432:5432 \
postgres:16


# Create second database
docker exec kokoro-postgres psql -U postgres -c "CREATE DATABASE other_db;"


# LOGGING 

docker exec kokoro-postgres psql -U postgres -c "ALTER SYSTEM SET log_statement = 'all';"
docker exec kokoro-postgres psql -U postgres -c "SELECT pg_reload_conf();"
docker logs -f kokoro-postgres

# APP 

OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES gunicorn 'kokoro.app:app' -c gunicorn.conf.py --capture-output