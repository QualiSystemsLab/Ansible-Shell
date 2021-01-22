import requests

TEST_URL = "http://192.168.85.62/api/v4/projects/2/repository/files/my_playbook.yml/raw?ref=master"
TEST_GITLAB_TOKEN = "UAAEwzj7qSZn3oHRjzbZ"


headers = {"PRIVATE-TOKEN": TEST_GITLAB_TOKEN}
response = requests.get(TEST_URL, stream=True, verify=False, headers=headers)

if not response.ok:
    raise Exception("Failed request. Error code: {}. Reason: {}".format(response.status_code, response.reason))

print("=== Response Success ===")
print(response.text)
