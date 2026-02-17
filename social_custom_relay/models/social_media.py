# -*- coding: utf-8 -*-

import logging

import requests
from werkzeug.urls import url_join

from odoo import _, models
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class SocialMediaCustomRelay(models.Model):
    _inherit = 'social.media'

    @staticmethod
    def _sanitize_endpoint(endpoint):
        endpoint = (endpoint or '').strip()
        if endpoint.startswith('http://') or endpoint.startswith('https://'):
            return endpoint
        return ''

    def _get_custom_relay_endpoint(self):
        icp = self.env['ir.config_parameter'].sudo()
        endpoint = (
            icp.get_param('social.custom_relay_endpoint')
            or icp.get_param('social.social_iap_endpoint')
            or self.env['social.media']._DEFAULT_SOCIAL_IAP_ENDPOINT
        )
        return self._sanitize_endpoint(endpoint)

    def _relay_get(self, route, params=None, timeout=5):
        endpoint = self._get_custom_relay_endpoint()
        if not endpoint:
            raise UserError(_(
                "Invalid relay endpoint. Please configure 'social.custom_relay_endpoint' or "
                "'social.social_iap_endpoint' with a full URL (including http:// or https://)."
            ))
        try:
            return requests.get(url_join(endpoint, route), params=params or {}, timeout=timeout)
        except requests.RequestException as err:
            raise UserError(_("Failed to contact relay endpoint: %s", err))

    def _relay_add_accounts(self, media, route, callback_path, error_tokens):
        db_uuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        endpoint = self._get_custom_relay_endpoint()
        callback_url = url_join(self.get_base_url(), callback_path)
        _logger.info(
            'social_custom_relay: add account requested media=%s endpoint=%s db_uuid=%s callback=%s',
            media,
            endpoint,
            db_uuid,
            callback_url,
        )
        response = self._relay_get(
            route,
            params={
                'returning_url': callback_url,
                'db_uuid': db_uuid,
            },
        ).text
        _logger.info(
            'social_custom_relay: add account response media=%s value=%s',
            media,
            response,
        )
        if response == 'unauthorized':
            raise UserError(_("You don't have an active subscription. Please buy one here: %s", 'https://www.odoo.com/buy'))
        if response in error_tokens:
            raise UserError(_("The url that this service requested returned an error. Please contact the author of the app."))
        return {'type': 'ir.actions.act_url', 'url': response, 'target': 'self'}

    def _add_facebook_accounts_from_iap(self):
        return self._relay_add_accounts(
            media='facebook',
            route='api/social/facebook/1/add_accounts',
            callback_path='social_facebook/callback',
            error_tokens=('facebook_missing_configuration', 'missing_parameters'),
        )

    def _add_instagram_accounts_from_iap(self):
        return self._relay_add_accounts(
            media='instagram',
            route='api/social/instagram/1/add_accounts',
            callback_path='social_instagram/callback',
            error_tokens=('instagram_missing_configuration', 'missing_parameters'),
        )

    def _add_youtube_accounts_from_iap(self):
        return self._relay_add_accounts(
            media='youtube',
            route='api/social/youtube/1/add_accounts',
            callback_path='social_youtube/callback',
            error_tokens=('youtube_missing_configuration',),
        )

    def _add_twitter_accounts_from_iap(self):
        return self._relay_add_accounts(
            media='twitter',
            route='api/social/twitter/1/add_accounts',
            callback_path='social_twitter/callback',
            error_tokens=('wrong_configuration',),
        )

    def _add_linkedin_accounts_from_iap(self):
        return self._relay_add_accounts(
            media='linkedin',
            route='api/social/linkedin/1/add_accounts',
            callback_path='social_linkedin/callback',
            error_tokens=('linkedin_missing_configuration', 'missing_parameters'),
        )

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
