## Runtime Configuration
Execute python scripts inside the virtual environment. Activation command is source env/bin/activate.

Re-use virtual environment if one is already activated.

## Database Notes
- SQLite database at `data/runrepeat_lab_tests.sqlite`
- Schema: shoes table with JSON lab_test_results column
- Use `pd.read_sql_query()` + `json_normalize()` for ML data
- Crawler uses INSERT OR REPLACE for incremental updates 
