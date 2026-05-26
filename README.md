# BDN Validation System

FastAPI service for BDN document extraction and validation against AIS telemetry.

## Database

The database layer uses PostgreSQL, SQLAlchemy, and Alembic.

1. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

2. Install PostgreSQL and make sure the server is running.

3. Copy `.env.example` to `.env` or `config/.env`, then update the credentials:

   ```env
   DATABASE_URL=postgresql+psycopg://geoloc_user:geoloc_password@localhost:5432/geoloc
   POSTGRES_ADMIN_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres
   ```

4. Create the database:

   ```powershell
   python scripts/create_database.py
   ```

5. Apply migrations:

   ```powershell
   alembic upgrade head
   ```

### Tables

- `vessels`: vessel identity and registry data, keyed by UUID with IMO and optional MMSI uniqueness.
- `ais_positions`: timestamped AIS telemetry linked to vessels when known, with MMSI/time uniqueness and range checks for coordinates, course, heading, and speed.
- `transactions`: BDN validation records linked to the receiving vessel and optional barge, with extracted document values, validation payloads, and verdict fields.
