"""No external network is allowed in this deterministic producer suite."""
import socket
import pytest
@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
 def fail(*args,**kwargs):
  raise AssertionError('A deterministic producer test attempted a network connection')
 monkeypatch.setattr(socket.socket,'connect',fail)
 monkeypatch.setattr(socket.socket,'connect_ex',fail)
