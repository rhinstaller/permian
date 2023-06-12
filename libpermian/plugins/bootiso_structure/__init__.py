from libpermian.plugins import api
from libpermian.events.structures.builtin import OtherStructure


@api.events.register_structure('bootIso')
class BootIsoStructure(OtherStructure):
    """ Structure for boot ISOs for different architectures.

    Structure definition: "bootIso": {"x86_64": "path to iso or http/s url", ... }}
    Structure usage: self.event.bootIso['x86_64']
    """
    pass