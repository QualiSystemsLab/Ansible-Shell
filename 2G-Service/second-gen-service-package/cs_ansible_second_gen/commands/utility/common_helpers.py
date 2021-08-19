"""
shared helper functions
"""
import json


def get_pretty_json_from_complex_obj(my_obj):
    return json.dumps(my_obj, default=lambda o: getattr(o, '__dict__', str(o)), indent=4)


def get_list_from_comma_separated_string(comma_separated_list):
    """
    get a python list of resource names from comma separated list
    :param str comma_separated_list:
    :return:
    """
    import re
    # remove all extra whitespace after commas and before/after string but NOT in between resource names
    removed_whitespace_str = re.sub(r"(,\s+)", ",", comma_separated_list).strip()
    resource_names = removed_whitespace_str.split(",")
    return resource_names


def str_range_to_list(str_range):
    result = []
    for part in str_range.split(','):
        if '-' in part:
            a, b = part.split('-')
            a, b = int(a), int(b)
            result.extend(range(a, b + 1))
        else:
            a = int(part)
            result.append(a)
    return result


def dict_to_ordered_dict(input_dict, key_order_list):
    """
    convert dict to list of tuples then feed into ordered dict
    :param dict input_dict:
    :param key_order_list:
    :return:
    """
    from collections import OrderedDict
    list_of_tuples = [(key, input_dict[key]) for key in order_of_keys]
    return OrderedDict(list_of_tuples)


def dict_to_ordered_json(input_dict, key_order_list):
    """
    convert dict to list of tuples then feed into ordered dict
    :param dict input_dict:
    :param key_order_list:
    :return:
    """
    import json
    ordered = dict_to_ordered_dict(input_dict, key_order_list)
    json_dict = json.dumps(ordered, indent=4, sort_keys=False)
    return json_dict


def get_list_of_param_dicts(input_dict):
    """
    {"param1": "val1", "param2": "val2"} --> [{"name": "param1", "value": "val1"}, {"name": "param1", "value": "val1"}]
    take cached dict of params and create list of dicts to match how quali server sends request
    :param dict input_dict:
    :return:
    """
    return [{"name": key, "value": value} for key, value in input_dict.items()]


if __name__ == "__main__":
    order_of_keys = ["key1", "key2", "key3"]
    my_dict = {
        "key3": "val3",
        "key2": "val2",
        "key1": "val1"
    }
    ordered_json = dict_to_ordered_json(my_dict, order_of_keys)
    print(ordered_json)
    pass
