#!/usr/bin/env python


from godadder.godadder_helper import *
from godadder.util import get_app_config
    
if __name__ == "__main__":

    app_conf = get_app_config()
    
    check_domains = []
    investigate_domains(app_conf, check_domains)

    print("\n--- All domains (as table) ---")
    df_all = select_domains()
    print(df_all)

