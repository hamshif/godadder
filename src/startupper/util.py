import os
import sys
from pyhocon import ConfigFactory


def get_project_path():
    current_path = __file__
    while not current_path.endswith('src'):
        current_path = '/'.join(current_path.split('/')[:-1])
    current_path = '/'.join(current_path.split('/')[:-1])
    return current_path


def get_db_full_path(__file__):
    if getattr(sys, 'frozen', False):
        SCRIPT_DIR = os.path.dirname(sys.executable)
    else:
        try:
            SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

    DB_FILE = os.path.join(SCRIPT_DIR, "domains.db")
    print("DB_FILE:\n", DB_FILE)
    return DB_FILE


def get_app_config():
    project_path = get_project_path()
    print(f"Project path: {project_path}")
    config_file = f"{project_path}/conf/app.conf"
    config = ConfigFactory.parse_file(config_file)
    return config

