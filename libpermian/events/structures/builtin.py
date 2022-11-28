from .factory import EventStructuresFactory
from .base import BaseStructure

@EventStructuresFactory.register('product')
class ProductStructure(BaseStructure):
    def __init__(self, settings, name, major, minor, other=None, flag=None):
        super().__init__(settings)
        self.name = name
        self.major = major
        self.minor = minor
        self.other = other
        self.flag = flag

@EventStructuresFactory.register('other')
class OtherStructure(BaseStructure):
    def __init__(self, settings, **kwargs):
        super().__init__(settings)
        self.fields = kwargs

    def __iter__(self):
        return self.fields.__iter__()

    def __getitem__(self, key):
        return self.fields.__getitem__(key)
