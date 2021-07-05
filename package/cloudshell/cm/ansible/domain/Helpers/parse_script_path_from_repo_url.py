from urlparse import urlsplit


def parse_script_path_from_url(repo_url):
    parsed = urlsplit(repo_url)
    script_path = parsed.path
    split = script_path.split("/")
    last_dir_and_file = split[-2:]
    script_path = "--".join(last_dir_and_file)
    return script_path


def get_net_loc_from_url(repo_url):
    parsed = urlsplit(repo_url)
    netloc = parsed.netloc
    return netloc


if __name__ == "__main__":
    sample_url = "https://raw.githubusercontent.com/QualiSystemsLab/App-Configuration-Demo-Scripts/master/ansible-scripts/run_dummy_tasks.yml"
    parsed_script_path = parse_script_path_from_url(sample_url)
    print(parsed_script_path)