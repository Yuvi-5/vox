"""Which microphone Vox records from. The choice is stored by name, because device numbers change between
sessions. An empty name means the Windows default microphone."""


def choose(devices, name):
    """Index of the input device called `name`, or None to use the default.

    `devices` is a list of (index, name, max_input_channels); the first input device with that exact name wins.
    """
    if not name:
        return None
    for index, dev_name, inputs in devices:
        if inputs > 0 and dev_name == name:
            return index
    return None


def _devices(sd):
    return [(i, d["name"], d["max_input_channels"]) for i, d in enumerate(sd.query_devices())]


def input_names(sd=None):
    """Names of the microphones offered in Settings: the inputs of the default audio system, each listed once."""
    if sd is None:
        import sounddevice as sd
    try:
        host = sd.query_devices(kind="input")["hostapi"]
    except Exception:
        return []
    names = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and d["hostapi"] == host and d["name"] not in names:
            names.append(d["name"])
    return names


def input_index(name, sd=None):
    """Device index to pass to sounddevice for the stored name; None means the system default."""
    if not name:
        return None
    if sd is None:
        import sounddevice as sd
    return choose(_devices(sd), name)
