

def rchop(thestring, ending):
    """Remove substring at the end of a string."""
    if thestring.endswith(ending):
        return thestring[:-len(ending)]
    return thestring


def axis_name(axis_num):
    """Return readable name corresponding to axis number."""
    return "xyz"[axis_num]
