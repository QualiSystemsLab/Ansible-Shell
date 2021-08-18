from cloudshell.api.cloudshell_api import ResourceAttribute


def get_resource_attribute_gen_agostic(attribute_key, resource_attributes):
    """
    :param str attribute_key:
    :param list[ResourceAttribute] resource_attributes:
    :return:
    :rtype ResourceAttribute:
    """
    for attr in resource_attributes:
        match_conditions = [attr.Name.lower() == attribute_key.lower(),
                            attr.Name.lower().endswith("." + attribute_key.lower())]
        if any(match_conditions):
            return attr
    return None


def get_normalized_attrs_dict(attrs_dict_list):
    """
    strip namespace from attr and build dictionary
    :param list[ResourceAttribute] attrs_dict_list:
    :return:
    """
    result = {}
    for curr_attr in attrs_dict_list:
        key_split = curr_attr.Name.split(".")
        if len(key_split) > 1:
            key = key_split[1]
        else:
            key = curr_attr.Name
        result[key] = curr_attr.Value
    return result