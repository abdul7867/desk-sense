"""Pluggable thinkers. Add a provider by adding a module and a line in `make`."""


def make(name, **cfg):
    if name == "fake":
        from thinker.fake import ScriptedThinker

        return ScriptedThinker(**cfg)
    if name == "claude":
        from thinker.anthropic_provider import ClaudeThinker  # imported only when used: keeps the SDK out of RAM

        return ClaudeThinker(**cfg)
    raise ValueError("unknown thinker %r (known: claude, fake)" % name)
