"""Capability primitive (task 9). A Capability is a named, domain-tagged handle onto an existing Dimwit
function, resolved lazily from a `module:function` import path so the registry is pure data + late-bound."""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable, Optional

# MARKET is the read-only analysis domain of the market evidence lane (dimwit.market): pure functions over
# caller-supplied bars/images, no network, no credentials, no disk writes. Anything in the market cell that
# writes (chart export, evidence append) is registered under EXECUTE so it stays behind the mutation gate.
DOMAINS = ("DESIGN", "DEVELOP", "EXECUTE", "TEST", "MARKET")


@dataclass
class Capability:
    name: str            # e.g. "TEST/gate.run_all"
    target: str          # "module:function" import path, e.g. "dimwit.engine:run_all_gates"
    domain: str          # one of DOMAINS
    description: str = ""
    _fn: Optional[Callable] = None

    def resolve(self) -> Callable:
        if self._fn is None:
            mod_name, fn_name = self.target.split(":")
            self._fn = getattr(importlib.import_module(mod_name), fn_name)
        if not callable(self._fn):
            raise TypeError(f"capability {self.name} target {self.target} is not callable")
        return self._fn

    def __call__(self, *args, **kwargs):
        return self.resolve()(*args, **kwargs)
