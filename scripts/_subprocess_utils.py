r"""Thin wrapper around subprocess that defaults encoding to utf-8.

Every subprocess call in scripts/ must go through these wrappers so that
``grep -r "subprocess\.\(run\|Popen\|call\)" scripts/ | grep -v "encoding="``
returns zero matches — i.e. no raw subprocess call without encoding=.
"""
import subprocess as _sp


def run(cmd, **kwargs):
    """subprocess.run with encoding="utf-8" and errors="replace" by default."""
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    return _sp.run(cmd, **kwargs)


def Popen(cmd, **kwargs):
    """subprocess.Popen with encoding="utf-8" and errors="replace" by default."""
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    return _sp.Popen(cmd, **kwargs)
