# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class WebsiteTheazeeztechVerification(http.Controller):

    @http.route(['/about-us'], type='http', auth='public', website=True, sitemap=True)
    def about_us(self, **kwargs):
        return request.render('website_theazeeztech_verification.page_about_us')

    @http.route(['/privacy-policy'], type='http', auth='public', website=True, sitemap=True)
    def privacy_policy(self, **kwargs):
        return request.render('website_theazeeztech_verification.page_privacy_policy')

    @http.route(['/terms-of-service'], type='http', auth='public', website=True, sitemap=True)
    def terms_of_service(self, **kwargs):
        return request.render('website_theazeeztech_verification.page_terms_of_service')

    @http.route(['/contact-us'], type='http', auth='public', website=True, sitemap=True)
    def contact_us(self, **kwargs):
        return request.render('website_theazeeztech_verification.page_contact_us')
