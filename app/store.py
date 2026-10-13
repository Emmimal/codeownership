"""Storage layer. How data is held is up to the implementation."""


def reset():
    """Clear all notes, folders and memberships, and restart id allocation.

    The tests call this before every case, so it must leave the store
    exactly as it was when the process started.
    """
    raise NotImplementedError
