ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
GRANT pg_read_all_stats TO text2sql_readonly;