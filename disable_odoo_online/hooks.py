from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    """
    Archive the OdooBot partner.
    """
    if isinstance(env, api.Environment):
         env = env
    else:
        # Compatibility if env is passed as cr, registry (older versions or specific contexts)
        # unwrap cr and create env
        cr = env
        env = api.Environment(cr, SUPERUSER_ID, {})
        
    odoobot = env.ref('base.partner_root', raise_if_not_found=False)
    if odoobot:
        odoobot.active = False
