# -*- coding: utf-8 -*-
{
    'name': 'Social Custom Relay',
    'version': '18.0.1.0.0',
    'summary': 'Route Social/IAP relay calls to a custom service',
    'category': 'Marketing/Social Marketing',
    'license': 'LGPL-3',
    'depends': [
        'social',
        'iap',
        'social_facebook',
        'social_instagram',
        'social_youtube',
        'social_twitter',
        'social_linkedin',
        'social_push_notifications',
    ],
    'data': [
        'data/ir_config_parameter_data.xml',
    ],
    'installable': True,
    'application': False,
}
