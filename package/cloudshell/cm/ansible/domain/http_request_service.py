import requests
from requests import Response
from Helpers.gitlab_api_url_validator import is_gitlab_rest_url
from models import HttpAuth


class HttpRequestService(object):
    def get_response(self, url, auth, logger):
        """
        :param str url:
        :param HttpAuth auth:
        :param logging.Logger logger:
        :return:
        """
        is_gitlab_url = is_gitlab_rest_url(url)
        if is_gitlab_url:
            logger.info("=== GITLAB Rest API request ===".format(url))
            response = self._get_gitlab_response(url, auth, logger)
            self._validate_response_status_code(response)
            self._invalidate_gitlab_login_page(response)
        else:
            # if auth:
            #     if not auth.username:
            #         raise Exception("Auth download missing 'User' attribute value.")

            auth = (auth.username, auth.password) if auth else None
            if auth:
                logger.info("Auth download flow.")
                response = requests.get(url, auth=auth, stream=True, verify=False)
            else:
                logger.info("No-auth download flow.")
                response = requests.get(url, stream=True, verify=False)
            self._validate_response_status_code(response)
            self._invalidate_html(response.content)

            logger.info("Playbook download response: {}".format(response.status_code))
        return response

    @staticmethod
    def _get_gitlab_response(url, auth, logger):
        """
        :param url:
        :param auth:
        :param logging.Logger logger:
        :return:
        """
        if auth:
            logger.info("Gitlab download from private repo with token...")
            headers = {"PRIVATE-TOKEN": auth.password}
            return requests.get(url, stream=True, verify=False, headers=headers)
        else:
            logger.info("Gitlab no auth download...")
            return requests.get(url, stream=True, verify=False)

    @staticmethod
    def _validate_response_status_code(response):
        if not response.ok:
            raise Exception('Failed to download script file: ' + str(response.status_code) + ' - ' + response.reason +
                            '. Please make sure the URL is valid, and any required credentials are correct.')

    @staticmethod
    def _is_content_html(content):
        return content.lstrip('\n\r').lower().startswith('<!doctype html>')

    def _invalidate_html(self, content):
        if self._is_content_html(content):
            raise Exception('Failed to download script file: url points to an html file')

    def _invalidate_gitlab_login_page(self, response):
        """
        :param Response response: requests response object
        :return:
        """
        if self._is_content_html(response.content) and "users/sign_in" in response.url:
            raise Exception('Authentication failed. Reached Gitlab Login. Gitlab Access Token required.')
