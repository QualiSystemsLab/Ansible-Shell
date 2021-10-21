import re


def get_router_app_names(input_str):
    pattern = r"\<(.*?)\>"
    return re.findall(pattern, input_str)


def replace_router_app_name_with_address(input_str, router_address):
    pattern = r"(\<.*?\>)"
    return re.sub(pattern, router_address, input_str)


if __name__ == "__main__":
    test_str = '-o ProxyCommand="ssh -W %h:%p -q pradmin@<router1> asdfasfsdf <router3>"'
    # matches = get_delimited_text(test_str)
    # for match in matches:
    #     print(match)

    result = replace_router_app_name_with_address(test_str, "192.168.1.5")
    print(result)
