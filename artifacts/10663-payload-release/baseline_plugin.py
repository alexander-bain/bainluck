from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
from pathlib import Path

def pytest_collection_modifyitems(items):
    loader=SourceFileLoader('baseline_polymarket_10663',str(Path(__file__).parent/'baseline-service.py.txt'))
    spec=spec_from_loader(loader.name,loader)
    mod=module_from_spec(spec)
    loader.exec_module(mod)
    for item in items:
        item.module.svc=mod
