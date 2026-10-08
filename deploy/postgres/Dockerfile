# The postgis/postgis images are amd64-only, and production runs on ARM (t4g),
# so PostGIS comes from the PostgreSQL apt repository, which ships both architectures.
FROM postgres:17-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-17-postgis-3 \
 && rm -rf /var/lib/apt/lists/*
COPY init.sql /docker-entrypoint-initdb.d/10-postgis.sql
