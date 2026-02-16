# -*- coding: utf-8 -*-
{
    'name': 'IAP Provider Social Relay',
    'summary': 'Concrete IAP alternative provider using a relay endpoint',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'license': 'AGPL-3',
    'author': 'Custom',
    'depends': [
        'iap',
        'iap_alternative_provider',
        'base_setup',
    ],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
