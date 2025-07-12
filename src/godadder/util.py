
import os
import sys
from pyhocon import ConfigFactory


def get_project_path():
    """
    Get the absolute path to the project root directory.
    
    :return: Absolute path to the project root.
    """
    current_path = __file__

    while not current_path.endswith('src'):
        current_path = '/'.join(current_path.split('/')[:-1])

    current_path = '/'.join(current_path.split('/')[:-1])

    return current_path



def get_db_full_path(__file__):
    if getattr(sys, 'frozen', False):
    # Support for PyInstaller or similar
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

    # Example usage
    project_path = get_project_path()
    print(f"Project path: {project_path}")

    config_file = f"{project_path}/conf/app.conf"

    config = ConfigFactory.parse_file(config_file)

    return config

def get_godaddy_headers(conf):
    headers = {
        "Authorization": f"sso-key {conf.GODADDY_API_KEY}:{conf.GODADDY_API_SECRET}",
        "Accept": "application/json"
    }
    return headers


if __name__ == "__main__":
    config = get_app_config()
    print("App configuration loaded successfully.")
    print(config)