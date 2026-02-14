"""Checks if OS is running on Windows or on PA"""
import os

# THIS NO LONGER WORKS AS WRITTEN ASSUMES WINDOWS ALWAYS
if os.getcwd()[:2] == 'C:': # windows
    from settings_win import *
    filepath = lambda path : '/U'
else: # Ubuntu for Windows (WSL)
    from settings_ubuntu import *