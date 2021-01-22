from unittest import TestCase
from cloudshell.cm.ansible.domain.http_request_service import HttpRequestService
from models import HttpAuth
from mock import Mock

# ADD CREDENTIALS HERE FOR TEST THEN REMOVE

GITHUB_USER_NAME = ""
GITHUB_PASSWORD = ""
GITHUB_PUBLIC_RAW_URL = ""
GITHUB_PRIVATE_REPO_RAW_URL = ""


GITLAB_PERSONAL_ACCESS_TOKEN = "UAAEwzj7qSZn3oHRjzbZ"
GITLAB_PUBLIC_REPO_API_URL = "http://192.168.85.62/api/v4/projects/3/repository/files/my_playbook.yml/raw?ref=master"
GITLAB_PRIVATE_REPO_API_URL = "http://192.168.85.62/api/v4/projects/2/repository/files/my_playbook.yml/raw?ref=master"
GITLAB_PUBLIC_REPO_RAW_URL = "http://192.168.85.62/root/public_test/-/raw/master/my_playbook.yml"


class TestHttpService(TestCase):
    def setUp(self):
        self.http_service = HttpRequestService()
        self.logger = Mock()

    def test_gitlab_public_repo_raw_url(self):
        response = self.http_service.get_response(GITLAB_PUBLIC_REPO_RAW_URL, None, self.logger)
        self.assertTrue(response.ok)
        print(response.status_code)

    def test_gitlab_private_repo_url_with_token(self):
        auth = HttpAuth(None, GITLAB_PERSONAL_ACCESS_TOKEN)
        response = self.http_service.get_response(GITLAB_PRIVATE_REPO_API_URL, auth, self.logger)
        self.assertTrue(response.ok)
        print(response.status_code)

    def test_gitlab_private_repo_url_multi_digit_project_id(self):
        auth = HttpAuth(None, GITLAB_PERSONAL_ACCESS_TOKEN)
        response = self.http_service.get_response(GITLAB_PRIVATE_REPO_API_URL, auth, self.logger)
        self.assertTrue(response.ok)
        print(response.status_code)

    def test_gitlab_private_repo_url_with_token_fails(self):
        auth = HttpAuth(None, None)
        with self.assertRaises(Exception):
            self.http_service.get_response(GITLAB_PRIVATE_REPO_API_URL, auth, self.logger)

    def test_gitlab_public_repo_api_url_with_token(self):
        auth = HttpAuth(None, GITLAB_PERSONAL_ACCESS_TOKEN)
        response = self.http_service.get_response(GITLAB_PRIVATE_REPO_API_URL, auth, self.logger)
        self.assertTrue(response.ok)
        print(response.status_code)

    def test_gitlab_public_repo_raw_url_with_token(self):
        auth = HttpAuth(None, GITLAB_PERSONAL_ACCESS_TOKEN)
        response = self.http_service.get_response(GITLAB_PUBLIC_REPO_RAW_URL, auth, self.logger)
        self.assertTrue(response.ok)
        print(response.status_code)



