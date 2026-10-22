@echo off
rem Run dbt for this project. Usage (inside this folder):  .\dbt build   /   .\dbt build --select chain_summary
rem - turns off "dbt State", a dbt Cloud feature of dbt 1.12 that otherwise opens a browser login (not needed here)
rem - uses the dbt installed in ..\.venv-dbt (Python 3.11) and the connection settings in this folder (profiles.yml)
set DBT_ENGINE_MANAGE_STATE=false
"%~dp0..\.venv-dbt\Scripts\dbt.exe" %* --profiles-dir "%~dp0."
