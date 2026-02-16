# -*- coding: utf-8 -*-

import base64
import hashlib
import hmac
import json
import logging
from urllib.parse import quote

import requests
from werkzeug.urls import url_join
from werkzeug.wrappers import Response

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

_MEDIA_ERROR_TOKEN = {
    'facebook': 'facebook_missing_configuration',
    'instagram': 'missing_parameters',
    'youtube': 'youtube_missing_configuration',
    'twitter': 'wrong_configuration',
    'linkedin': 'missing_parameters',
}

_MEDIA_TEMPLATE_KEY = {
    'facebook': 'social_relay_service.facebook_add_accounts_url',
    'instagram': 'social_relay_service.instagram_add_accounts_url',
    'youtube': 'social_relay_service.youtube_add_accounts_url',
    'twitter': 'social_relay_service.twitter_add_accounts_url',
    'linkedin': 'social_relay_service.linkedin_add_accounts_url',
}


class SocialRelayServiceController(http.Controller):

    def _icp(self):
        return request.env['ir.config_parameter'].sudo()

    def _render_add_accounts_url(self, media, returning_url, db_uuid):
        if not returning_url or not db_uuid:
            return _MEDIA_ERROR_TOKEN[media]

        template = self._icp().get_param(_MEDIA_TEMPLATE_KEY[media])
        if not template:
            return _MEDIA_ERROR_TOKEN[media]

        try:
            return template.format(returning_url=returning_url, db_uuid=db_uuid)
        except Exception:
            _logger.exception('Invalid URL template for media %s', media)
            return _MEDIA_ERROR_TOKEN[media]

    @http.route('/api/social/facebook/1/add_accounts', type='http', auth='public', methods=['GET'], csrf=False)
    def add_facebook_accounts(self, returning_url=None, db_uuid=None, **kwargs):
        return Response(self._render_add_accounts_url('facebook', returning_url, db_uuid), mimetype='text/plain')

    @http.route('/api/social/instagram/1/add_accounts', type='http', auth='public', methods=['GET'], csrf=False)
    def add_instagram_accounts(self, returning_url=None, db_uuid=None, **kwargs):
        return Response(self._render_add_accounts_url('instagram', returning_url, db_uuid), mimetype='text/plain')

    @http.route('/api/social/youtube/1/add_accounts', type='http', auth='public', methods=['GET'], csrf=False)
    def add_youtube_accounts(self, returning_url=None, db_uuid=None, **kwargs):
        return Response(self._render_add_accounts_url('youtube', returning_url, db_uuid), mimetype='text/plain')

    @http.route('/api/social/twitter/1/add_accounts', type='http', auth='public', methods=['GET'], csrf=False)
    def add_twitter_accounts(self, returning_url=None, db_uuid=None, **kwargs):
        return Response(self._render_add_accounts_url('twitter', returning_url, db_uuid), mimetype='text/plain')

    @http.route('/api/social/linkedin/1/add_accounts', type='http', auth='public', methods=['GET'], csrf=False)
    def add_linkedin_accounts(self, returning_url=None, db_uuid=None, **kwargs):
        return Response(self._render_add_accounts_url('linkedin', returning_url, db_uuid), mimetype='text/plain')

    @http.route('/api/social/youtube/1/refresh_token', type='http', auth='public', methods=['GET'], csrf=False)
    def refresh_youtube_token(self, db_uuid=None, refresh_token=None, **kwargs):
        client_id = self._icp().get_param('social_relay_service.youtube_client_id')
        client_secret = self._icp().get_param('social_relay_service.youtube_client_secret')

        if not refresh_token:
            return Response(json.dumps({'error': 'missing_refresh_token'}), mimetype='application/json')
        if not client_id or not client_secret:
            return Response(json.dumps({'error': 'youtube_missing_configuration'}), mimetype='application/json')

        try:
            response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                },
                timeout=10,
            )
            return Response(response.text, mimetype='application/json', status=response.status_code)
        except requests.RequestException:
            _logger.exception('YouTube refresh token call failed')
            return Response(json.dumps({'error': 'upstream_error'}), mimetype='application/json', status=502)

    def _jsonrpc_response(self, rpc_id, result=None, error=None, status=200):
        payload = {'jsonrpc': '2.0', 'id': rpc_id}
        if error is not None:
            payload['error'] = error
        else:
            payload['result'] = result
        return Response(json.dumps(payload), mimetype='application/json', status=status)

    def _jsonrpc_error(self, rpc_id, code, message, name='social_relay_service.Error', status=200):
        return self._jsonrpc_response(
            rpc_id,
            error={
                'code': code,
                'message': message,
                'data': {'name': name, 'message': message},
            },
            status=status,
        )

    @http.route('/api/social/twitter/1/get_signature', type='http', auth='public', methods=['POST'], csrf=False)
    def twitter_get_signature(self, **kwargs):
        try:
            payload = json.loads(request.httprequest.data or '{}')
        except json.JSONDecodeError:
            payload = {}

        rpc_id = payload.get('id')
        params = payload.get('params') or {}
        consumer_secret = self._icp().get_param('social_relay_service.twitter_consumer_secret')
        if not consumer_secret:
            return self._jsonrpc_error(rpc_id, 1, 'twitter_consumer_secret_not_configured')

        method = params.get('method')
        url = params.get('url')
        oauth_token_secret = params.get('oauth_token_secret', '')
        sign_params = params.get('params') or {}

        if not method or not url or not isinstance(sign_params, dict):
            return self._jsonrpc_error(rpc_id, 2, 'invalid_signature_payload')

        signing_key = '&'.join([consumer_secret, oauth_token_secret])
        query = '&'.join([
            '%s=%s' % (quote(str(key), safe='+:/'), quote(str(sign_params[key]), safe='+:/,'))
            for key in sorted(sign_params.keys())
        ])
        base_string = '&'.join([
            method,
            quote(url, safe='+:/'),
            quote(query, safe='+:/'),
        ])
        digest = hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
        signature = base64.b64encode(digest).decode()
        return self._jsonrpc_response(rpc_id, result=signature)

    @http.route('/iap/social_push_notifications/get_firebase_info', type='http', auth='public', methods=['GET'], csrf=False)
    def get_firebase_info(self, db_uuid=None, **kwargs):
        data = {
            'firebase_project_id': self._icp().get_param('social_relay_service.firebase_project_id') or '',
            'firebase_web_api_key': self._icp().get_param('social_relay_service.firebase_web_api_key') or '',
            'firebase_push_certificate_key': self._icp().get_param('social_relay_service.firebase_push_certificate_key') or '',
            'firebase_sender_id': self._icp().get_param('social_relay_service.firebase_sender_id') or '',
            'firebase_web_app_id': self._icp().get_param('social_relay_service.firebase_web_app_id') or '',
        }
        return Response(json.dumps(data), mimetype='application/json')

    @http.route('/iap/social_push_notifications/firebase_send_message', type='http', auth='public', methods=['POST'], csrf=False)
    def firebase_send_message(self, **kwargs):
        try:
            payload = json.loads(request.httprequest.data or '{}')
        except json.JSONDecodeError:
            payload = {}

        rpc_id = payload.get('id')
        params = payload.get('params') or {}
        tokens = params.get('tokens') or []

        # This endpoint is intentionally minimal: it acknowledges the batch.
        # Replace this with your provider call if you need to really dispatch notifications.
        _logger.info('social_relay_service received push batch: %s token(s)', len(tokens))
        return self._jsonrpc_response(rpc_id, result={'accepted': len(tokens)})
