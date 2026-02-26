@echo off
cd /d "%~dp0.."
python news/run_list_monitor.py --config news/monitor_config.json
