from urlparse import urlsplit


def parse_script_path_from_url(repo_url):
    parsed = urlsplit(repo_url)
    script_path = parsed.path
    reformatted_path = script_path.replace("/", "-").replace("\\", "-")
    if reformatted_path.startswith("-"):
        reformatted_path = reformatted_path[1:]
    return reformatted_path


if __name__ == "__main__":
    sample_url = "https://www.my-gitlab-server.com/dir1/dir2/dir3/my_playbook.yml"
    parsed_script_path = parse_script_path_from_url(sample_url)
    print(parsed_script_path)