#--*- coding: utf-8 -*-

"""metadata.py

Metadata normalization utilities.
"""


def _set_path(out: dict, path: list[str], value: any) -> None:
    """Set a value in a nested dict given a path.

    :param out: the dict to modify
    :type out: dict
    :param path: a list of keys representing the path to set
    :type path: list[str]
    :param value: the value to set at the given path
    :type value: any
    :returns: None (modifies out in place)
    :rtype: None
    """
    cur = out
    for k in path[:-1]:
        cur = cur.setdefault(k, {})
    cur[path[-1]] = value

def _get_path(src: dict, path: list[str]) -> any:
    """Get a value from a nested dict given a path.

    :param src: the dict to read from
    :type src: dict
    :param path: a list of keys representing the path to get
    :type path: list[str]
    :returns: the value at the given path, or None if any key is missing
    :rtype: any
    """

    cur = src
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur

def keep_paths(src: dict, paths: list[str]) -> dict:
    """Keep only the specified paths in a nested dict.

    :param src: the original dict to filter
    :type src: dict
    :param paths: a list of dot-separated paths to keep (e.g. "d
ublincore.creator")
    :type paths: list[str]
    :returns: a new dict containing only the specified paths and their values
    :rtype: dict
    """
    if not paths:
        return src  # or {} if none should be kept
    out: dict = {}
    for p in paths:
        parts = p.split(".")
        v = _get_path(src, parts)
        if v is not None:
            _set_path(out, parts, v)
    return out
