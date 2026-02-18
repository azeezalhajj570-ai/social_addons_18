# -*- coding: utf-8 -*-

from werkzeug.urls import url_join

from odoo import models, tools
from odoo.addons.iap.tools import iap_tools


class SocialAccountPushNotificationsCustomRelay(models.Model):
    _inherit = 'social.account'

    def _firebase_send_message_from_iap(self, data, visitors):
        endpoint = (
            self.env['ir.config_parameter'].sudo().get_param('social.custom_relay_endpoint')
            or self.env['ir.config_parameter'].sudo().get_param('social.social_iap_endpoint')
            or self.env['social.media']._DEFAULT_SOCIAL_IAP_ENDPOINT
        )
        batch_size = 100
        tokens = visitors.mapped('push_subscription_ids.push_token')
        data.update({'db_uuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid')})
        for tokens_batch in tools.split_every(batch_size, tokens, piece_maker=list):
            batch_data = dict(data)
            batch_data['tokens'] = tokens_batch
            iap_tools.iap_jsonrpc(
                url_join(endpoint, '/iap/social_push_notifications/firebase_send_message'),
                params=batch_data,
            )
        return []
