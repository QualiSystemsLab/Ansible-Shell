def is_path_supported_protocol(path, supported_protocols):
    """
    :param str path:
    :param list [str] protocols:
    :return:
    """
    path = path.lower()
    return any(path.startswith(protocol) for protocol in supported_protocols)


if __name__ == "__main__":
    protocols = ["http", "https"]
    path = "httpS://www.lol.com"
    print(is_path_supported_protocol(path, protocols))
