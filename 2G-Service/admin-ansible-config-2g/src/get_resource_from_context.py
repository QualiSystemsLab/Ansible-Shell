# this helper is just to abstract the resource class so I can copy paste the driver over to admin version

from data_model import AdminAnsibleConfig2G


def get_resource_from_context(context):
    """
    :param ResourceCommandContext context:
    :return:
    """
    return AdminAnsibleConfig2G.create_from_context(context)
