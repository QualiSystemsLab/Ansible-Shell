import json


def _parse_domain_specific_input(input_str):
    """
    "input1, val1; input2, val2;" --> [{"name": "input1", "value": "val1"}, ...]
    Semicolon is delimiter between param items
    List 'values' be passed as extra comma separated values. first item will be key, and the rest will be the list
    :param input_str: "input1, val1; input2, val2; input 3, val3"
    :return:
    """
    def _get_comma_separated_params(key_value_pair_str):
        """
        parse, clean, and add to request object
        :param str key_value_pair_str: expected 'input1, val1'
        :return:
        """
        param_items = key_value_pair_str.split(",", 1)
        param_items = [s.strip() for s in param_items]
        return {"name": param_items[0], "value": ",".join(param_items[1:])}

    params_list = input_str.split(";")

    # the conditional is to account for trailing semicolon which results in empty item from split
    params_list = [_get_comma_separated_params(item) for item in params_list if item]
    return params_list


def handle_json_list_params(input_str):
    try:
        ansible_vars = json.loads(input_str)
    except Exception as e:
        raise Exception("Could not load JSON string input: Received {}. Exception: {}".format(input_str, str(e)))

    # convert to expected form of python package [{"name": "ansible_var", value: "value"}]
    results = []
    if type(ansible_vars) == list:
        for param_dict in ansible_vars:
            for key, value in param_dict.items():
                param_item = {"name": key, "value": value}
                results.append(param_item)

    if type(ansible_vars) == dict:
        for key, value in ansible_vars.items():
            param_item = {"name": key, "value": value}
            results.append(param_item)

    return results


def _build_params_list(input_str):
    if not input_str:
        return []

    # if input_str.startswith("{"):
    #     raise ValueError('Invalid input. JSON must be a List of form [{"ansible_variable": "value"}, {"ansible_variable2": "value2"}]. Received: ' + input_str)

    if input_str.startswith(("[", "{")):
        return handle_json_list_params(input_str)

    # parse the custom input option
    return _parse_domain_specific_input(input_str)


if __name__ == "__main__":
    from pprint import pprint
    inputs = ['ansible_var1, val1;my_list,1,2,3;my_dict_list,[{"yo":yup},{"hey": "hi"},{"bye": "bye-bye"}]',
              '{"ansible_var1": "val1"}',
              '{"ansible_var1": ["val1", "val2"], "ansible_var2": ["val1", "val2"]}',
              '[{"ansible_var1": ["val1", "val2"]}, {"ansible_var2": ["val1", "val2"]}]',
              '{"people_list": [{"name": "natti", "age": 33},{"name": "James", "age": 35}]}']
    for index, input in enumerate(inputs):
        print("=== test {} ===".format(index + 1))
        my_params_list = _build_params_list(input)
        pprint(my_params_list)
        pass
