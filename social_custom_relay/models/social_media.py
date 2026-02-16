# -*- coding: utf-8 -*-

import requests
from werkzeug.urls import url_join

from odoo import _, models
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import AccessError, UserError


class SocialMediaCustomRelay(models.Model):
    _inherit = 'social.media'

    def _get_custom_relay_endpoint(self):
        icp = self.env['ir.config_parameter'].sudo()
        return (
            icp.get_param('social.custom_relay_endpoint')
            or icp.get_param('social.social_iap_endpoint')
            or self.env['social.media']._DEFAULT_SOCIAL_IAP_ENDPOINT
        )

    def _relay_get(self, route, params=None, timeout=5):
        endpoint = self._get_custom_relay_endpoint()
        return requests.get(url_join(endpoint, route), params=params or {}, timeout=timeout)

    def _add_facebook_accounts_from_iap(self):
        response = self._relay_get(
            'api/social/facebook/1/add_accounts',
            params={
                'returning_url': url_join(self.get_base_url(), 'social_facebook/callback'),
                'db_uuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
            },
        ).text
        if response == 'unauthorized':
            raise UserError(_("You don't have an active subscription. Please buy one here: %s", 'https://www.odoo.com/buy'))
        if response in ('facebook_missing_configuration', 'missing_parameters'):
            raise UserError(_("The url that this service requested returned an error. Please contact the author of the app."))
        return {'type': 'ir.actions.act_url', 'url': response, 'target': 'self'}

    def _add_instagram_accounts_from_iap(self):
        response = self._relay_get(
            'api/social/instagram/1/add_accounts',
            params={
                'returning_url': url_join(self.get_base_url(), 'social_instagram/callback'),
                'db_uuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
            },
        ).text
        if response == 'unauthorized':
            raise UserError(_("You don't have an active subscription. Please buy one here: %s", 'https://www.odoo.com/buy'))
        if response in ('instagram_missing_configuration', 'missing_parameters'):
            raise UserError(_("The url that this service requested returned an error. Please contact the author of the app."))
        return {'type': 'ir.actions.act_url', 'url': response, 'target': 'self'}

    def _add_youtube_accounts_from_iap(self):
        response = self._relay_get(
            'api/social/youtube/1/add_accounts',
            params={
                'returning_url': url_join(self.get_base_url(), 'social_youtube/callback'),
                'db_uuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
            },
        ).text
        if response == 'unauthorized':
            raise UserError(_("You don't have an active subscription. Please buy one here: %s", 'https://www.odoo.com/buy'))
        if response == 'youtube_missing_configuration':
            raise UserError(_("The url that this service requested returned an error. Please contact the author of the app."))
        return {'type': 'ir.actions.act_url', 'url': response, 'target': 'self'}

    def _add_twitter_accounts_from_iap(self):
        response = self._relay_get(
            'api/social/twitter/1/add_accounts',
            params={
                'returning_url': url_join(self.get_base_url(), 'social_twitter/callback'),
                'db_uuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
            },
        ).text
        if response == 'unauthorized':
            raise UserError(_("You don't have an active subscription. Please buy one here: %s", 'https://www.odoo.com/buy'))
        if response == 'wrong_configuration':
            raise UserError(_("The url that this service requested returned an error. Please contact the author of the app."))
        return {'type': 'ir.actions.act_url', 'url': response, 'target': 'self'}

    def _add_linkedin_accounts_from_iap(self):
        response = self._relay_get(
            'api/social/linkedin/1/add_accounts',
            params={
                'returning_url': url_join(self.get_base_url(), 'social_linkedin/callback'),
                'db_uuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
            },
        ).text
        if response == 'unauthorized':
            raise UserError(_("You don't have an active subscription. Please buy one here: %s", 'https://www.odoo.com/buy'))
        if response in ('linkedin_missing_configuration', 'missing_parameters'):
            raise UserError(_("The url that this service requested returned an error. Please contact the author of the app."))
        return {'type': 'ir.actions.act_url', 'url': response, 'target': 'self'}

    def _get_twitter_oauth_signature_from_iap(self, method, url, params, oauth_token_secret=''):
        params['oauth_nonce'] = str(params['oauth_nonce'])
        payload = {
            'method': method,
            'url': url,
            'params': params,
            'oauth_token_secret': oauth_token_secret,
            'db_uuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
        }
        endpoint = self._get_custom_relay_endpoint()
        try:
            return iap_tools.iap_jsonrpc(url_join(endpoint, 'api/social/twitter/1/get_signature'), params=payload)
        except AccessError:
            return None
