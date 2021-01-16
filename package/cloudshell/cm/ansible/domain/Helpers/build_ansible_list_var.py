import pyaml
import json


def build_simple_list_from_comma_separated(key, value):
    items = value.split(",")
    output_dict = {key: items}
    return pyaml.dumps(output_dict)


def build_json_to_yaml(key, value):
    try:
        value_obj = json.loads(value)
    except Exception as e:
        raise Exception("Could not load JSON string while preparing VARS file. Input string '{}'. Exception: {}".format(value, str(e)))
    output_dict = {key: value_obj}
    return pyaml.dumps(output_dict)


def params_list_to_yaml(key, value):
    output_dict = {key: value}
    return pyaml.dumps(output_dict)


if __name__ == "__main__":
    vars = {
        "param1": "val1",
        "my_list1": "item1,item2,item3",
        "my_list2": "item1,item2,item3",
        "my_list3": '[{"name": "natti", "age":33},{"name": "DAve", "age":36}]',
        "dhcp_list": '[{"DHCPMAC": "00:50:56:80:86:d2", "DHCPHOST": "Ubuntu-18-Server_6705-ecaa", "DHCPIP": "125" },{"DHCPMAC": "00:50:56:80:62:e5", "DHCPHOST": "Windows-10-Pro_6b72-ecaa", "DHCPIP": "130"}]'
    }

    yaml_from_list = params_list_to_yaml("my_key", ["param1", "param2"])

    print("---")
    for key, value in sorted(vars.iteritems()):
        if value.startswith(("[", "{")):
            print(build_json_to_yaml(key, value))
        elif "," in value:
            print(build_simple_list_from_comma_separated(key, value))
        else:
            print('{}: {}'.format(key, value))