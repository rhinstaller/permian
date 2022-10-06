import unittest
from unittest.mock import create_autospec, MagicMock
from libpermian.settings import Settings
from libpermian.plugins.compose import ComposeStructure
from libpermian.plugins.anaconda_webui import InstallationSourceStructure


def MockComposeStructure(product, variants):
    settings = Settings(cmdline_overrides={}, environment={}, settings_locations=[])
    instance = create_autospec(ComposeStructure)(settings, 'OS-1.0.2-20220221.1')
    
    instance.product = product
    instance.settings = settings

    def kernel_path(repo, arch):
        return f'http://example.com/{repo}/{arch}/linux'
    def initrd_path(repo, arch):
        return f'http://example.com/{repo}/{arch}/initrd'

    m_get_variants = []
    for var in variants:
        m_variant = MagicMock()
        m_variant.id = var
        m_variant.paths.os_tree.items.return_value = (('x86_64', f'http://example.com/{var}/x86_64/os'), ('aarch64', f'http://example.com/{var}/aarch64/os'))
        m_get_variants.append(m_variant)

    instance.composeinfo.metadata.info.get_variants.return_value = m_get_variants
    instance.composeinfo.kernel_path = kernel_path
    instance.composeinfo.initrd_path = initrd_path

    return instance


class TestFromCompose(unittest.TestCase):
    def test_conversion_rhel(self):
        mock_compose = MockComposeStructure('RHEL', ('AppStream', 'BaseOS', 'CRB'))
        installation_source = InstallationSourceStructure.from_compose(mock_compose)

        self.assertEquals(installation_source.kernel_path('x86_64'), 'http://example.com/BaseOS/x86_64/linux')
        self.assertEquals(installation_source.initrd_path('x86_64'), 'http://example.com/BaseOS/x86_64/initrd')
        self.assertEquals(installation_source.kernel_path('aarch64'), 'http://example.com/BaseOS/aarch64/linux')
        self.assertEquals(installation_source.initrd_path('aarch64'), 'http://example.com/BaseOS/aarch64/initrd')

        self.assertEquals(installation_source.base_repo['x86_64']['os'], 'http://example.com/BaseOS/x86_64/os')

        self.assertEquals(installation_source.repos['AppStream']['x86_64'], {"os": "http://example.com/AppStream/x86_64/os"})

    def test_conversion_fedora(self):
        mock_compose = MockComposeStructure('Fedora', ('Everything',))
        installation_source = InstallationSourceStructure.from_compose(mock_compose)

        self.assertEquals(installation_source.kernel_path('x86_64'), 'http://example.com/Everything/x86_64/linux')
        self.assertEquals(installation_source.initrd_path('x86_64'), 'http://example.com/Everything/x86_64/initrd')
        self.assertEquals(installation_source.kernel_path('aarch64'), 'http://example.com/Everything/aarch64/linux')
        self.assertEquals(installation_source.initrd_path('aarch64'), 'http://example.com/Everything/aarch64/initrd')

        self.assertEquals(installation_source.base_repo['x86_64']['os'], 'http://example.com/Everything/x86_64/os')
