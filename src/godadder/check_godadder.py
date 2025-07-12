#!/usr/bin/env python


from godadder.godadder_helper import *
from godadder.util import get_app_config
    
if __name__ == "__main__":

    app_conf = get_app_config()
    
    check_domains = ["magniv.ai", "uncomplexify.ai", "fantabulous.ai", "navhopper.ai", "falafel.com", "humanize.ai", "humanizer.ai"]
    investigate_domains(app_conf, check_domains)

    print("\n--- All domains (as table) ---")
    df_all = select_domains()
    print(df_all)

    print("\n--- Last 5 conceived domains ---")
    df_last5 = select_domains(columns=["name","available","conceived"], limit=5, order_by="conceived", desc=True)
    print(df_last5)